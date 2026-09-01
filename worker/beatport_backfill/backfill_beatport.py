#!/usr/bin/env python
"""L1a — local Beatport backfill orchestrator. Runs on the HOST (Windows PC), stdlib only.

Drains the Beatport enrichment backlog from the operator's RESIDENTIAL IP, in
parallel with the VPS's hourly Beatport drain, to burn it down faster. Twin of the
C9.a embedding tool (``worker/embedding_backfill/``): same SSH/psql channel, same
dry-run/apply + checkpoint + salvo-relaunchable shape, same container-driven compute.
The difference: this tool ONLY scrapes + validates (in the container) and produces
an NDJSON of matches; the WRITE is done on the VPS by the OPS script
``server/api/scripts/import_beatport_matches.py`` (reusing the drain's enrichment
code — artwork upload AND the merge-on-collision are handled there, invariant #4).

The three steps:

  1. PULL   — stream the FRESH Tier-1 candidates (``id,title,isrc,flat_artist,
              m2m_artists``) from prod, read-only, via the documented SSH/psql
              channel fed a ``COPY (...) TO STDOUT``. Fresh only:
              ``beatport_id IS NULL AND beatport_searched_at IS NULL`` — the E1
              retries (30/90d) are left entirely to the VPS. Ordered by the C12
              priority scalar (``coalesce(enrich_priority, 75) DESC, id DESC``).
              ``--after-id`` / ``--limit`` window a salvo; ``--shard M/N`` splits
              the backlog by ``id % N``.
  2. SCRAPE — ``docker run`` the driver in the PROD server image (beatport/ +
              workers/ + curl_cffi), passing the L1b rate knob ``BEATPORT_RATE``
              (``--rate``, default a prudent 4 rps under the probed 6 rps ceiling)
              via ``-e``. Produces ``matches.ndjson`` on the L1b contract.
  3. APPLY  — pipe ``matches.ndjson`` over ssh stdin to the OPS import script,
              propagating ``--apply``. In dry-run (default) the OPS script is
              invoked WITHOUT ``--apply`` (it runs the enrichment code, prints its
              counters and rolls back — no external write of any kind).

>>> ``--apply`` MUTATES rows on prod (through the reused enrichment code). DUMP
    PROD FIRST (docs/restore.md). <<<  The tool itself never writes to the DB; the
    OPS script does, and it is idempotent, but a bad dump is not recoverable.

Checkpoint (``<workdir>/processed_ids.txt``): after a SUCCESSFUL ``--apply``, every
id emitted in the NDJSON (found/not_found = a completed attempt) is recorded, so a
periodic re-run only pulls NEW candidates. Ids that hit an outage are absent from
the NDJSON and never checkpointed -> re-tried. In dry-run nothing is checkpointed
(nothing was written); use ``--reuse-matches --apply`` to write a prior dry-run's
matches without re-scraping. The pull's ``beatport_searched_at IS NULL`` predicate
is the PRIMARY guard anyway — a written row drops out of the next pull.

Usage (from the repo root, or anywhere):
    python worker/beatport_backfill/backfill_beatport.py --limit 20            # dry-run sample
    python worker/beatport_backfill/backfill_beatport.py                       # dry-run, full backlog
    python worker/beatport_backfill/backfill_beatport.py --apply               # scrape + write
    python worker/beatport_backfill/backfill_beatport.py --shard 0/4 --apply   # one quarter of the backlog
    python worker/beatport_backfill/backfill_beatport.py --reuse-matches --apply  # write last matches
"""

import argparse
import csv
import functools
import io
import json
import os
import shutil
import subprocess
import sys

# the scrape step interleaves container output with ours — keep progress ordered
# even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path (PULL): -q keeps the COPY stream clean (CSV only on stdout).
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)

# Prod server image (context ./server via server/Dockerfile): carries beatport/ +
# workers/ + curl_cffi at /app. The package image (below) is a thin FROM of it so
# the local tool has a stable tag; the driver is bind-mounted at /work at run time.
SERVER_IMAGE = "diggy-beatport-server"
IMAGE = "diggy-beatport-backfill"

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
SERVER_DOCKERFILE = os.path.join(SERVER_DIR, "Dockerfile")
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
CHECKPOINT_FILE = "processed_ids.txt"

# C12 priority baseline: a NULL enrich_priority folds to the median so unscored
# rows sort between the flux (100) and the lowest phase — mirror the drain gate.
PRIORITY_BASELINE = 75

# CSV column contract passed to the container driver (to_analyze.csv).
CANDIDATE_FIELDS = ["id", "title", "isrc", "flat_artist", "m2m_artists"]

# Default residential-IP scrape rate: the probe proved 6 rps sustained (0×403),
# but we keep a margin below it. Tunable per run via --rate; passed to the
# container as BEATPORT_RATE (the L1b knob).
DEFAULT_RATE = 4.0


def parse_shard(spec):
    """Parse a ``"M/N"`` shard spec -> ``(m, n)`` ints, or ``None`` for a falsy spec.

    Validates ``0 <= m < n`` (n >= 1). Raises ``ValueError`` on a malformed spec so
    the CLI surfaces it instead of silently pulling the whole backlog.
    """
    if not spec:
        return None
    parts = str(spec).split("/")
    if len(parts) != 2:
        raise ValueError(f"--shard must be 'M/N', got {spec!r}")
    m, n = int(parts[0]), int(parts[1])
    if n < 1 or not (0 <= m < n):
        raise ValueError(f"--shard M/N needs 0 <= M < N and N >= 1, got {spec!r}")
    return m, n


def build_pull_query(limit=0, after_id=0, shard=None):
    """COPY query for the FRESH Tier-1 Beatport candidates.

    Fresh only (``beatport_id IS NULL AND beatport_searched_at IS NULL``): E1
    retries are the VPS's job, never this tool's. M2M artist names are aggregated
    (``string_agg`` ordered by ``catalog_artists.position``) with the flat
    ``catalog.artist`` carried alongside as a fallback — the driver picks
    ``m2m or flat`` exactly like the drain. Ordered by the C12 priority scalar so
    the residential IP drains the highest-value rows first. ``after_id`` (an id
    window, not a strict keyset over the priority sort) and ``shard`` (``id % N``)
    partition a salvo; the ``beatport_searched_at IS NULL`` guard makes the whole
    thing self-idempotent across runs.
    """
    clauses = ""
    if after_id:
        clauses += f"    AND c.id > {int(after_id)}\n"
    if shard is not None:
        m, n = shard
        clauses += f"    AND c.id % {int(n)} = {int(m)}\n"
    limit_clause = f"  LIMIT {int(limit)}\n" if limit else ""
    return (
        "COPY (\n"
        "  SELECT c.id,\n"
        "         c.title,\n"
        "         c.isrc,\n"
        "         c.artist AS flat_artist,\n"
        "         coalesce(string_agg(a.name, ', ' ORDER BY ca.position), '') "
        "AS m2m_artists\n"
        "  FROM catalog c\n"
        "  LEFT JOIN catalog_artists ca ON ca.catalog_id = c.id\n"
        "  LEFT JOIN artists a ON a.id = ca.artist_id\n"
        "  WHERE c.beatport_id IS NULL\n"
        "    AND c.beatport_searched_at IS NULL\n"
        f"{clauses}"
        "  GROUP BY c.id\n"
        f"  ORDER BY coalesce(c.enrich_priority, {PRIORITY_BASELINE}) DESC, c.id DESC\n"
        f"{limit_clause}"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def parse_candidates(csv_text):
    """Rows (dicts on CANDIDATE_FIELDS) from the COPY CSV output."""
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


def summarize_matches(ndjson_text):
    """Parse a matches NDJSON blob -> ``(processed_ids, counts)``.

    ``processed_ids`` = string catalog ids of every well-formed found/not_found
    line (a completed attempt, checkpointed after a successful --apply). ``counts``
    tallies found / not_found / malformed / total. A malformed line (bad JSON,
    missing/invalid catalog_id or status) is counted and skipped — never fatal.
    """
    processed_ids = []
    counts = {"total": 0, "found": 0, "not_found": 0, "malformed": 0}
    for line in ndjson_text.splitlines():
        line = line.strip()
        if not line:
            continue
        counts["total"] += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            counts["malformed"] += 1
            continue
        cid = rec.get("catalog_id") if isinstance(rec, dict) else None
        status = rec.get("status") if isinstance(rec, dict) else None
        if (
            not isinstance(cid, int)
            or isinstance(cid, bool)
            or status not in ("found", "not_found")
        ):
            counts["malformed"] += 1
            continue
        counts[status] += 1
        processed_ids.append(str(cid))
    return processed_ids, counts


def build_import_command(apply):
    """Remote command that pipes the NDJSON into the OPS import script.

    Dry-run invokes it WITHOUT ``--apply`` (the OPS script runs the enrichment
    code, prints its counters and rolls back — no write); ``--apply`` propagates
    the flag so it commits.
    """
    flag = " --apply" if apply else ""
    return (
        "cd /root/diggy && docker compose exec -T api "
        f"python scripts/import_beatport_matches.py{flag}"
    )


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


def run_remote_import(ndjson_text, apply):
    """Pipe the matches NDJSON to the OPS import script over ssh; return its stdout.

    The OPS script prints a human-readable report (enriched / not_matched / merged /
    not_found_marked / already_linked / missing / malformed) which we surface
    verbatim. A non-zero exit (e.g. ON_ERROR_STOP) raises.
    """
    cmd = build_import_command(apply)
    proc = subprocess.run(
        ["ssh", SSH_HOST, cmd],
        input=ndjson_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote import failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def apply_or_plan(
    ndjson_text, apply, checkpoint_path, runner=run_remote_import
):
    """Summarise the matches, then hand them to the OPS import (dry-run or apply).

    Returns the counters dict. Checkpointing: after a SUCCESSFUL --apply, every
    processed id is recorded; dry-run checkpoints NOTHING (nothing was written).
    An empty NDJSON short-circuits without touching the OPS script.
    """
    processed_ids, counts = summarize_matches(ndjson_text)
    print(
        f"\nMatches: {counts['total']} line(s) - {counts['found']} found, "
        f"{counts['not_found']} not_found, {counts['malformed']} malformed"
    )

    if not ndjson_text.strip():
        print("No matches to import (empty NDJSON) — nothing to do.")
        return counts

    if not apply:
        print("\n=== DRY-RUN — invoking the OPS import WITHOUT --apply ===")
        out = runner(ndjson_text, False)
        print(out)
        print(
            "=== DRY-RUN — nothing was written (the OPS script ran the enrichment "
            "code, printed its counters and rolled back). No id checkpointed (they "
            "still need writing — re-run with --apply, or --reuse-matches --apply "
            "to skip re-scraping). DUMP PROD before --apply (docs/restore.md). ==="
        )
        return counts

    print("\n=== APPLY — piping matches to the OPS import (--apply) ===")
    out = runner(ndjson_text, True)
    print(out)
    append_checkpoint(checkpoint_path, processed_ids)
    print(
        f"\nCheckpointed {len(processed_ids)} attempted id(s). Idempotent: the OPS "
        "import counts already-linked rows as already_linked (nothing re-stamped), "
        "and the next pull drops written rows via beatport_searched_at IS NULL."
    )
    return counts


def _docker_build():
    """Build the prod server image, then the thin package image FROM it."""
    print(f"[scrape] docker build -t {SERVER_IMAGE} (server/Dockerfile) ...")
    subprocess.run(
        ["docker", "build", "-t", SERVER_IMAGE, "-f", SERVER_DOCKERFILE, SERVER_DIR],
        check=True,
    )
    print(f"[scrape] docker build -t {IMAGE} (FROM {SERVER_IMAGE}) ...")
    subprocess.run(
        [
            "docker", "build",
            "-t", IMAGE,
            "--build-arg", f"SERVER_IMAGE={SERVER_IMAGE}",
            PKG_DIR,
        ],
        check=True,
    )


def _docker_scrape(workdir, rate, concurrency=None, max_403=None):
    """Run scrape_driver.py in the container over <workdir>/to_analyze.csv."""
    shutil.copy2(
        os.path.join(PKG_DIR, "scrape_driver.py"),
        os.path.join(workdir, "scrape_driver.py"),
    )
    env_flags = ["-e", f"BEATPORT_RATE={rate}"]
    if concurrency:
        env_flags += ["-e", f"BEATPORT_CONCURRENCY={concurrency}"]
    if max_403:
        env_flags += ["-e", f"BEATPORT_MAX_CONSECUTIVE_403={max_403}"]
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            *env_flags,
            IMAGE,
            "python", "/work/scrape_driver.py",
            "--csv", "/work/to_analyze.csv",
            "--out", "/work/matches.ndjson",
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
    matches_path = os.path.join(workdir, "matches.ndjson")

    if args.reuse_matches:
        if not os.path.exists(matches_path):
            sys.exit(f"--reuse-matches: no {matches_path} from a previous run")
        print(f"[reuse] importing previous {matches_path} (no pull, no scrape)")
        with open(matches_path, encoding="utf-8") as f:
            apply_or_plan(f.read(), args.apply, checkpoint_path)
        return

    shard = parse_shard(args.shard)

    # 1. PULL — read-only COPY from prod through the documented SSH channel
    print(
        f"[pull] fetching FRESH candidates (limit={args.limit or 'none'}, "
        f"after_id={args.after_id or 'none'}, shard={args.shard or 'none'})..."
    )
    csv_text = run_remote_sql(
        REMOTE_PSQL_PULL, build_pull_query(args.limit, args.after_id, shard)
    )
    candidates = parse_candidates(csv_text)
    _write_csv(
        os.path.join(workdir, "candidates.csv"), candidates, CANDIDATE_FIELDS
    )
    done = load_checkpoint(checkpoint_path)
    fresh = filter_new(candidates, done)
    print(
        f"[pull] {len(candidates)} candidate(s), "
        f"{len(candidates) - len(fresh)} already attempted (checkpoint), "
        f"{len(fresh)} to scrape"
    )
    if not fresh:
        print("Nothing new to scrape - done.")
        return
    _write_csv(
        os.path.join(workdir, "to_analyze.csv"), fresh, CANDIDATE_FIELDS
    )

    # 2. SCRAPE — in the prod server image (real matchers + curl_cffi)
    _docker_build()
    _docker_scrape(workdir, args.rate, args.concurrency, args.max_403)
    if not os.path.exists(matches_path):
        sys.exit(f"[scrape] the container produced no {matches_path}")
    with open(matches_path, encoding="utf-8") as f:
        matches_text = f.read()

    # 3. APPLY or dry-run plan (the OPS import writes; this tool never does)
    apply_or_plan(matches_text, args.apply, checkpoint_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Drain the Beatport enrichment backlog from a residential IP: "
        "scrape + validate in the prod server image, then import the matches on the "
        "VPS via server/api/scripts/import_beatport_matches.py (L1a local tooling). "
        "Dry-run by default; --apply to write (DUMP PROD FIRST)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually import the matches on prod (default: dry-run — the OPS "
        "script runs without --apply, prints its plan and rolls back)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="LIMIT on the candidates pull (0 = full backlog); use with --after-id "
        "or --shard to window a salvo",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="id window: only pull candidates with catalog id > this value "
        "(coarse salvo bound; the searched_at guard is the real cross-run guard)",
    )
    parser.add_argument(
        "--shard",
        default=None,
        help="split the backlog by 'M/N' (adds AND c.id %% N = M) to run several "
        "residential-IP salvos in parallel without overlap",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE,
        help=f"residential-IP scrape rate in req/s, passed to the container as the "
        f"L1b BEATPORT_RATE knob (default {DEFAULT_RATE}; the probe proved 6 rps "
        "sustained with 0x403, keep a margin). NEVER raise the PROD rate.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="optional BEATPORT_CONCURRENCY override for the container "
        "(rows are scraped sequentially; this only bounds the per-row requests)",
    )
    parser.add_argument(
        "--max-403",
        dest="max_403",
        type=int,
        default=None,
        help="consecutive 403s that trip a clean batch abort in the container "
        "(BEATPORT_MAX_CONSECUTIVE_403, default 5)",
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help="working directory for CSVs + NDJSON + checkpoint "
        "(default: <package>/data)",
    )
    parser.add_argument(
        "--reuse-matches",
        action="store_true",
        help="skip pull+scrape and import the existing <workdir>/matches.ndjson "
        "(e.g. dry-run first, inspect, then --reuse-matches --apply)",
    )
    main(parser.parse_args())
