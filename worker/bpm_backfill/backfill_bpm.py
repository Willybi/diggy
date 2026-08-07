#!/usr/bin/env python
"""E2.b — local BPM backfill orchestrator. Runs on the HOST (Windows PC), stdlib only.

Derives an ESTIMATED BPM from Deezer 30s previews for the ~48k ``catalog`` rows
that have a preview but no ``bpm`` (never linked to Beatport — though rows with a
``beatport_id`` and still no bpm are deliberately INCLUDED, a product decision).
Engine + gate come from the E2.a benchmark (docs/e2a-benchmark/): Essentia
``RhythmExtractor2013(multifeature)``, BPM written ONLY at confidence >= 2.0
(~84% precision), provenance ``bpm_source='analysis'``.

Local tooling (A7-07 pattern): Essentia does not install on Windows, so the
analysis pass runs in a Docker Linux container (image built from this package's
Dockerfile) while THIS script drives the pipeline from the host — it needs only
the Python stdlib, ``ssh`` (the ``diggy-vps`` alias) and ``docker``.

The three steps:

  1. PULL    — stream the candidates (``id,deezer_id``) from prod, read-only,
               via ``ssh diggy-vps '... psql -q -f -'`` fed a
               ``COPY (...) TO STDOUT WITH (FORMAT csv, HEADER true)`` query.
  2. ANALYZE — ``docker run --rm -v <workdir>:/work`` on ``analyze_bpm.py``
               (throttled Deezer fetch, transient MP3, RhythmExtractor2013,
               conf gate). NO audio is ever persisted.
  3. APPLY   — only with ``--apply``: batched ``UPDATE catalog ... FROM (VALUES
               ...)`` through the same SSH/psql channel. The ``AND c.bpm IS
               NULL`` clause is the idempotence + race guard: an existing bpm
               (beatport / rekordbox / legacy, or a concurrent enrichment run)
               is NEVER overwritten — 'analysis' is the lowest authority.

DRY-RUN by default: without ``--apply`` the UPDATE is NOT executed; the plan is
printed instead (written/low_conf/failed counters + an excerpt of the SQL).

Checkpoint (``<workdir>/processed_ids.txt``): every attempted id whose outcome
is FINAL is recorded — rejected rows (low_conf / no_preview / error) always,
written rows after a successful --apply batch. A periodic re-run ("fil de
l'eau") therefore only downloads NEW candidates, never the known rejects. Rows
analyzed OK during a dry-run are NOT checkpointed (they still need writing); use
``--reuse-results`` to apply a previous run's results.csv without re-analyzing.
To force a retry of ``error:*`` rows, delete their ids from the checkpoint file.

Usage (from the repo root, or anywhere):
    python worker/bpm_backfill/backfill_bpm.py --limit 20            # dry-run sample
    python worker/bpm_backfill/backfill_bpm.py                       # dry-run, full backlog
    python worker/bpm_backfill/backfill_bpm.py --apply               # analyze + write
    python worker/bpm_backfill/backfill_bpm.py --reuse-results --apply  # write last results
"""

import argparse
import csv
import functools
import io
import os
import re
import shutil
import subprocess
import sys

# the analyze step interleaves container output with ours — keep progress ordered
# even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path (PULL): -q keeps the COPY stream clean (CSV only on stdout).
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)
# Write path (APPLY): no -q so psql prints the "UPDATE n" command tags (parsed
# for the real written count); ON_ERROR_STOP makes a failed statement abort with
# a non-zero exit instead of silently continuing.
REMOTE_PSQL_APPLY = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -v ON_ERROR_STOP=1 -f -'"
)

IMAGE = "diggy-bpm-backfill"
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
CHECKPOINT_FILE = "processed_ids.txt"

MIN_CONF = 2.0
BATCH_SIZE = 500
# statuses whose outcome is final — checkpointed even on dry-run (a re-run
# would just re-download the same reject). "ok" is final only once WRITTEN.
_REJECT_STATUSES = ("low_conf", "no_preview")


def build_pull_query(limit=0):
    """COPY query for the candidates: preview but no bpm, resolvable deezer_id.

    ``beatport_id`` is deliberately NOT filtered (product decision: rows already
    linked to Beatport but still bpm-less are included — a later Beatport run
    overwrites 'analysis' anyway, authority invariant #3).
    """
    limit_clause = f"    LIMIT {int(limit)}\n" if limit else ""
    return (
        "COPY (\n"
        "  SELECT id, deezer_id\n"
        "  FROM catalog\n"
        "  WHERE has_preview = true\n"
        "    AND bpm IS NULL\n"
        "    AND deezer_id IS NOT NULL\n"
        "    AND deezer_id <> 'NOT_FOUND'\n"
        "  ORDER BY id\n"
        f"{limit_clause}"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def parse_candidates(csv_text):
    """Rows (dicts with id/deezer_id) from the COPY CSV output."""
    return list(csv.DictReader(io.StringIO(csv_text)))


def load_checkpoint(path):
    """Set of already-attempted ids (as strings); missing file = empty set."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_checkpoint(path, ids):
    if not ids:
        return
    with open(path, "a", encoding="utf-8") as f:
        for cid in ids:
            f.write(f"{cid}\n")


def filter_new(candidates, done):
    """Candidates not yet in the checkpoint set."""
    return [c for c in candidates if str(c["id"]).strip() not in done]


def read_results(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def eligible_updates(results, min_conf=MIN_CONF):
    """(id, bpm) pairs safe to write: status ok AND conf >= gate.

    The gate already ran in the container (analyze_bpm withholds the bpm below
    min_conf) — this re-check is defense in depth on the results file.
    """
    pairs = []
    for row in results:
        if row.get("status") != "ok":
            continue
        bpm, conf = row.get("bpm"), row.get("conf")
        if not bpm or not conf:
            continue
        if float(conf) < min_conf:
            continue
        pairs.append((int(row["id"]), float(bpm)))
    return pairs


def reject_ids(results):
    """Ids with a FINAL negative outcome (checkpointed even on dry-run)."""
    return [
        str(r["id"]).strip()
        for r in results
        if r.get("status") in _REJECT_STATUSES
        or str(r.get("status", "")).startswith("error:")
    ]


def build_update_batches(pairs, batch_size=BATCH_SIZE):
    """[(sql, [ids...]), ...] — one guarded UPDATE ... FROM (VALUES ...) per batch.

    ``int()``/``float()`` coercion makes the interpolated literals injection-safe;
    ``AND c.bpm IS NULL`` is the idempotence + race guard (never overwrite an
    existing bpm, whatever its source).
    """
    batches = []
    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i : i + batch_size]
        values = ",\n    ".join(
            f"({int(cid)}, {float(bpm):.1f})" for cid, bpm in chunk
        )
        sql = (
            "UPDATE catalog AS c\n"
            "SET bpm = v.bpm, bpm_source = 'analysis'\n"
            "FROM (VALUES\n"
            f"    {values}\n"
            ") AS v(id, bpm)\n"
            "WHERE c.id = v.id AND c.bpm IS NULL;\n"
        )
        batches.append((sql, [str(int(cid)) for cid, _ in chunk]))
    return batches


def parse_update_count(psql_output):
    """Sum of the ``UPDATE n`` command tags psql printed for a batch."""
    return sum(int(n) for n in re.findall(r"^UPDATE (\d+)", psql_output, re.M))


def run_remote_sql(remote_cmd, sql):
    """Feed ``sql`` to psql on the VPS via ssh stdin; return psql's stdout."""
    proc = subprocess.run(
        ["ssh", SSH_HOST, remote_cmd],
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote psql failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def apply_or_plan(
    results,
    apply,
    checkpoint_path,
    min_conf=MIN_CONF,
    batch_size=BATCH_SIZE,
    runner=run_remote_sql,
):
    """Gate the results, then either print the plan (dry-run) or run the UPDATEs.

    Returns the counters dict. Checkpointing: rejects always; written ids per
    SUCCESSFUL batch only (a failed batch leaves its ids un-checkpointed, and the
    ``bpm IS NULL`` guard makes the eventual re-write idempotent).
    """
    pairs = eligible_updates(results, min_conf)
    rejects = reject_ids(results)
    batches = build_update_batches(pairs, batch_size)
    counters = {
        "analyzed": len(results),
        "eligible": len(pairs),
        "low_conf": sum(1 for r in results if r.get("status") == "low_conf"),
        "no_preview": sum(1 for r in results if r.get("status") == "no_preview"),
        "errors": sum(
            1 for r in results if str(r.get("status", "")).startswith("error:")
        ),
        "written": 0,
    }
    print(
        f"\nResults: {counters['analyzed']} analyzed - "
        f"{counters['eligible']} eligible (conf >= {min_conf}), "
        f"{counters['low_conf']} low_conf, {counters['no_preview']} no_preview, "
        f"{counters['errors']} errors"
    )

    if not apply:
        if batches:
            excerpt = batches[0][0]
            if len(excerpt) > 600:
                excerpt = excerpt[:600] + "    ...\n"
            print(
                f"\nPlanned SQL ({len(batches)} batch(es) of <= {batch_size} rows), "
                f"first batch excerpt:\n{excerpt}"
            )
        append_checkpoint(checkpoint_path, rejects)
        print(
            "=== DRY-RUN - nothing was written (use --apply) ===\n"
            f"{counters['eligible']} row(s) WOULD be updated with "
            "bpm_source='analysis', guarded by AND c.bpm IS NULL (an existing "
            "beatport/rekordbox/legacy bpm is never overwritten). Rejected ids "
            "were checkpointed; the eligible ids were NOT (they still need "
            "writing - re-run with --apply, or --reuse-results --apply to skip "
            "re-analysis)."
        )
        return counters

    print(f"\n=== APPLY - {len(batches)} batch(es) of <= {batch_size} rows ===")
    for i, (sql, ids) in enumerate(batches, 1):
        out = runner(REMOTE_PSQL_APPLY, sql)
        written = parse_update_count(out)
        counters["written"] += written
        append_checkpoint(checkpoint_path, ids)
        print(
            f"  batch {i}/{len(batches)}: {written}/{len(ids)} written "
            "(others already had a bpm - guard)"
        )
    append_checkpoint(checkpoint_path, rejects)
    print(
        f"\nWritten {counters['written']}/{counters['eligible']} row(s) with "
        f"bpm_source='analysis'; {counters['eligible'] - counters['written']} "
        "skipped by the bpm IS NULL guard. Attempted ids checkpointed."
    )
    return counters


def _docker_build():
    print(f"[analyze] docker build -t {IMAGE} ...")
    subprocess.run(["docker", "build", "-t", IMAGE, PKG_DIR], check=True)


def _docker_analyze(workdir, workers, min_conf):
    """Run analyze_bpm.py in the container over <workdir>/to_analyze.csv."""
    shutil.copy2(
        os.path.join(PKG_DIR, "analyze_bpm.py"),
        os.path.join(workdir, "analyze_bpm.py"),
    )
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            IMAGE,
            "python", "/work/analyze_bpm.py",
            "--csv", "/work/to_analyze.csv",
            "--out", "/work/results.csv",
            "--workers", str(workers),
            "--min-conf", str(min_conf),
        ],
        check=True,
    )


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(args):
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    checkpoint_path = os.path.join(workdir, CHECKPOINT_FILE)
    results_path = os.path.join(workdir, "results.csv")

    if args.reuse_results:
        if not os.path.exists(results_path):
            sys.exit(f"--reuse-results: no {results_path} from a previous run")
        print(f"[reuse] gating previous {results_path} (no pull, no analysis)")
        results = read_results(results_path)
        apply_or_plan(
            results, args.apply, checkpoint_path,
            min_conf=args.min_conf, batch_size=args.batch_size,
        )
        return

    # 1. PULL — read-only COPY from prod through the documented SSH channel
    print(f"[pull] fetching candidates from prod (limit={args.limit or 'none'})...")
    csv_text = run_remote_sql(REMOTE_PSQL_PULL, build_pull_query(args.limit))
    candidates = parse_candidates(csv_text)
    _write_csv(
        os.path.join(workdir, "candidates.csv"), candidates, ["id", "deezer_id"]
    )
    done = load_checkpoint(checkpoint_path)
    fresh = filter_new(candidates, done)
    print(
        f"[pull] {len(candidates)} candidate(s), "
        f"{len(candidates) - len(fresh)} already attempted (checkpoint), "
        f"{len(fresh)} to analyze"
    )
    if not fresh:
        print("Nothing new to analyze - done.")
        return
    _write_csv(os.path.join(workdir, "to_analyze.csv"), fresh, ["id", "deezer_id"])

    # 2. ANALYZE — in the container (essentia is Linux-only)
    _docker_build()
    _docker_analyze(workdir, args.workers, args.min_conf)
    results = read_results(results_path)

    # 3. APPLY or dry-run plan
    apply_or_plan(
        results, args.apply, checkpoint_path,
        min_conf=args.min_conf, batch_size=args.batch_size,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill estimated BPM (bpm_source='analysis') from Deezer "
        "previews for catalog rows with a preview and no bpm (E2.b local tooling)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually run the batched UPDATEs on prod (default: dry-run, "
        "prints the plan and writes nothing)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="LIMIT on the candidates pull (0 = full backlog)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="analysis threads in the container (Deezer API stays ~5 rps)",
    )
    parser.add_argument(
        "--min-conf",
        type=float,
        default=MIN_CONF,
        help="RhythmExtractor2013 confidence gate (E2.a: 2.0 = ~84%% precision)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="rows per UPDATE statement in --apply",
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help="working directory for CSVs + checkpoint (default: <package>/data)",
    )
    parser.add_argument(
        "--reuse-results",
        action="store_true",
        help="skip pull+analysis and gate/apply the existing <workdir>/results.csv "
        "(e.g. dry-run first, inspect, then --reuse-results --apply)",
    )
    main(parser.parse_args())
