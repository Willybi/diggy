#!/usr/bin/env python
"""C14.a Phase 2 — discography backfill orchestrator. Runs on the HOST (PC), stdlib only.

Backfills the full Deezer discography of the DECIDED cohort (C14.a Phase 2, gated by the
benchmark: the "library" ``a_lib`` + "active DJ" ``b_sets12m`` tiers ≈ 1.5k artists) into
the catalog — the tracks we don't already have, so a followed/loved artist's back-catalogue
surfaces alongside the fil-de-l'eau new-release watch (Phase 1). Walking + classifying +
fetching each artist's discography from Deezer is a mass-Deezer workload FORBIDDEN on the
VPS (fair-use, the AV10 lesson), so the compute runs LOCALLY (residential IP) and the WRITE
happens on the VPS through the OPS script ``server/api/scripts/import_discography.py``.
Twin of ``worker/set_artist_backfill/`` (same SSH/psql channel, same dry-run/apply +
checkpoint + salvo shape) and of the read-only benchmark ``benchmark_discography.py`` (same
walk + net-new classification) — this is the WRITE tool the benchmark gated.

The four steps:

  1. COHORT — read-only ``COPY`` of the cohort artists (``tier,artist_id,name,deezer_id``:
     the same mutually-exclusive strata as the benchmark, filtered to ``--tiers``, only a
     real ``deezer_id``). ``--after-id`` / ``--limit`` window a salvo (artist_id keyset);
     ``--shard M/N`` splits by ``artist_id % N`` for disjoint parallel salvos.
  2. INDEX  — read-only ``COPY`` of the catalog identity index (``normalized_key,isrc``) so
     the container classifies net-new OFFLINE. Cached to ``data/catalog_index.csv``
     (``--reuse-index`` skips the re-pull).
  3. BUNDLE — ``docker run`` the driver (``bundle_driver.py`` + its sibling
     ``fetch_driver.py``) in the prod server image: walk ``/artist/{id}/albums`` →
     ``/album/{id}``, classify net-new vs the index, fetch ``/track/{id}`` for the net-new,
     emit ``data/bundle.ndjson`` (one record per artist). Deezer paced by ``--deezer-rate``.
  4. IMPORT — pipe ``bundle.ndjson`` over ssh stdin to the OPS import, propagating
     ``--apply``. Dry-run invokes it WITHOUT ``--apply`` (funnel runs, prints counters +
     a precision sample, rolls back — no write of any kind).

>>> ``--apply`` MUTATES prod (creates catalog/artist/album rows). DUMP PROD FIRST
    (docs/restore.md). <<<  This tool never writes to the DB; the OPS script does, and it
    is idempotent (a re-run counts already-linked rows as ``already_deezer``), but a bad
    dump is not recoverable.

Checkpoint (``<workdir>/processed_artist_ids.txt``): after a SUCCESSFUL ``--apply`` every
artist id emitted is recorded, so a periodic re-run only pulls NEW artists. Unlike the
set tool there is no natural "already done" SQL filter (a backfilled artist stays in the
cohort), so this local checkpoint is the one-shot marker; the OPS import is idempotent
regardless, so a lost checkpoint only costs a re-fetch. Delete it to force a full re-pass.
Dry-run checkpoints NOTHING.

Usage (from the repo root, or anywhere):
    python worker/discography_backfill/backfill_discography.py --limit 20          # dry-run sample
    python worker/discography_backfill/backfill_discography.py                     # dry-run, full cohort
    python worker/discography_backfill/backfill_discography.py --apply             # fetch + write
    python worker/discography_backfill/backfill_discography.py --shard 0/4 --apply # one quarter, parallel-safe
    python worker/discography_backfill/backfill_discography.py --reuse-bundle --apply  # write last bundle
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

print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)

SERVER_IMAGE = "diggy-discography-server"
IMAGE = "diggy-discography-backfill"

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
SERVER_DOCKERFILE = os.path.join(SERVER_DIR, "Dockerfile")
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
CHECKPOINT_FILE = "processed_artist_ids.txt"

COHORT_FIELDS = ["tier", "artist_id", "name", "deezer_id"]
DEFAULT_TIERS = "a_lib,b_sets12m"

DEFAULT_DEEZER_RATE = 1.0
DEFAULT_DEEZER_CONCURRENCY = 5


def _configure_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def safe_print(text=""):
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(text).encode(enc, errors="replace").decode(enc, errors="replace"))


def parse_shard(spec):
    """Parse ``"M/N"`` -> ``(m, n)``, or None for a falsy spec (ValueError on malformed)."""
    if not spec:
        return None
    parts = str(spec).split("/")
    if len(parts) != 2:
        raise ValueError(f"--shard must be 'M/N', got {spec!r}")
    m, n = int(parts[0]), int(parts[1])
    if n < 1 or not (0 <= m < n):
        raise ValueError(f"--shard M/N needs 0 <= M < N and N >= 1, got {spec!r}")
    return m, n


def _tiers_sql(tiers):
    """SQL IN-list literal from a comma tier spec, e.g. ``'a_lib','b_sets12m'``.

    Whitelisted against the known tier labels so nothing arbitrary reaches the query.
    """
    known = {"a_lib", "b_sets12m", "c_catalog", "d_traine"}
    wanted = [t.strip() for t in tiers.split(",") if t.strip()]
    bad = [t for t in wanted if t not in known]
    if bad:
        raise ValueError(f"unknown tier(s) {bad}; known: {sorted(known)}")
    if not wanted:
        raise ValueError("no tiers given")
    return ", ".join(f"'{t}'" for t in wanted)


def build_cohort_query(tiers=DEFAULT_TIERS, after_id=0, shard=None):
    """COPY query for the cohort artists (``tier,artist_id,name,deezer_id``).

    Same mutually-exclusive strata CTE as the benchmark's sample (cohort Signal-3
    predicate for the set count), filtered to ``tiers`` and to a real ``deezer_id``.
    Ordered by ``artist_id`` (clean forward keyset) so ``after_id`` resumes a salvo and
    ``shard`` partitions parallel ones. NB: there is deliberately NO SQL ``LIMIT`` — the
    ``--limit`` knob is applied host-side AFTER the checkpoint filter, so a ``--limit``
    loop advances instead of re-pulling the same head rows forever.
    """
    tier_in = _tiers_sql(tiers)
    clauses = ""
    if after_id:
        clauses += f"    AND artist_id > {int(after_id)}\n"
    if shard is not None:
        m, n = shard
        clauses += f"    AND artist_id % {int(n)} = {int(m)}\n"
    return (
        "COPY (\n"
        "WITH sets12 AS (\n"
        "  SELECT sa.artist_id, COUNT(DISTINCT s.id) AS set_count\n"
        "  FROM set_artists sa JOIN sets s ON s.id = sa.set_id\n"
        "  WHERE sa.role = 'dj' AND s.parent_set_id IS NULL AND s.is_virtual = false\n"
        "    AND s.unreliable IS NOT TRUE\n"
        "    AND COALESCE(s.event_date, s.played_date) >= (CURRENT_DATE - INTERVAL '365 days')\n"
        "  GROUP BY sa.artist_id\n"
        "),\n"
        "cat AS (\n"
        "  SELECT artist_id, COUNT(DISTINCT catalog_id) AS catalog_track_count\n"
        "  FROM catalog_artists GROUP BY artist_id\n"
        "),\n"
        "lib AS (\n"
        "  SELECT ca.artist_id, COUNT(DISTINCT ut.catalog_id) AS lib_count\n"
        "  FROM catalog_artists ca JOIN user_tracks ut ON ut.catalog_id = ca.catalog_id\n"
        "  GROUP BY ca.artist_id\n"
        "),\n"
        "base AS (\n"
        "  SELECT a.id AS artist_id, a.name, a.deezer_id,\n"
        "         COALESCE(s.set_count, 0) AS set_count,\n"
        "         COALESCE(c.catalog_track_count, 0) AS catalog_track_count,\n"
        "         (COALESCE(l.lib_count, 0) > 0) AS in_lib\n"
        "  FROM artists a\n"
        "  LEFT JOIN sets12 s ON s.artist_id = a.id\n"
        "  LEFT JOIN cat c ON c.artist_id = a.id\n"
        "  LEFT JOIN lib l ON l.artist_id = a.id\n"
        "  WHERE a.deezer_id IS NOT NULL AND a.deezer_id <> 'NOT_FOUND'\n"
        "),\n"
        "tagged AS (\n"
        "  SELECT *, CASE\n"
        "      WHEN in_lib THEN 'a_lib'\n"
        "      WHEN set_count >= 5 THEN 'b_sets12m'\n"
        "      WHEN catalog_track_count >= 10 THEN 'c_catalog'\n"
        "      ELSE 'd_traine' END AS tier\n"
        "  FROM base\n"
        ")\n"
        "SELECT tier, artist_id, name, deezer_id\n"
        f"FROM tagged WHERE tier IN ({tier_in})\n"
        f"{clauses}"
        "ORDER BY artist_id\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def build_catalog_index_query():
    """COPY of the catalog identity index (``normalized_key,isrc``) for offline dedup."""
    return (
        "COPY (\n"
        "  SELECT normalized_key, coalesce(isrc, '') AS isrc FROM catalog\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def parse_rows(csv_text):
    return list(csv.DictReader(io.StringIO(csv_text)))


def load_checkpoint(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_checkpoint(path, ids):
    if not ids:
        return
    with open(path, "a", encoding="utf-8") as f:
        for aid in ids:
            f.write(f"{aid}\n")


def filter_new(rows, done):
    return [r for r in rows if str(r["artist_id"]).strip() not in done]


def summarize_bundle(ndjson_text):
    """Parse the bundle NDJSON -> ``(processed_artist_ids, counts)``.

    ``processed_artist_ids`` = string artist ids of every CLEAN (non-errored) well-formed
    record (checkpointed after a successful --apply; errored artists retry next salvo).
    ``counts`` tallies artists / with_new / net_new_tracks /
    errored / malformed / total. Authoritative DB accounting is the OPS script's; this is
    the host's progress + checkpoint bookkeeping.
    """
    processed_ids = []
    counts = {"total": 0, "artists": 0, "with_new": 0, "net_new_tracks": 0,
              "errored": 0, "malformed": 0}
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
        aid = rec.get("artist_id") if isinstance(rec, dict) else None
        tracks = rec.get("tracks") if isinstance(rec, dict) else None
        if not isinstance(aid, int) or isinstance(aid, bool) or not isinstance(tracks, list):
            counts["malformed"] += 1
            continue
        counts["artists"] += 1
        counts["net_new_tracks"] += len(tracks)
        if tracks:
            counts["with_new"] += 1
        if rec.get("error"):
            counts["errored"] += 1
        else:
            # Only a CLEAN attempt is checkpointed. An errored/outage artist (e.g. its
            # /artist/{id}/albums 503'd → error set, 0 tracks) is NOT checkpointed so the
            # next salvo RETRIES it — honouring the driver's "outage ≠ empty" invariant
            # (a checkpointed outage would skip that back-catalogue forever).
            processed_ids.append(str(aid))
    return processed_ids, counts


def build_import_command(apply):
    flag = " --apply" if apply else ""
    return (
        "cd /root/diggy && docker compose exec -T api "
        f"python scripts/import_discography.py{flag}"
    )


def run_remote_sql(remote_cmd, sql):
    proc = subprocess.run(
        ["ssh", SSH_HOST, remote_cmd],
        input=sql, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote psql failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def run_remote_import(ndjson_text, apply):
    cmd = build_import_command(apply)
    proc = subprocess.run(
        ["ssh", SSH_HOST, cmd],
        input=ndjson_text, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote import failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def apply_or_plan(ndjson_text, apply, checkpoint_path, runner=run_remote_import):
    """Summarise the bundle, then hand it to the OPS import (dry-run or apply)."""
    processed_ids, counts = summarize_bundle(ndjson_text)
    print(
        f"\nBundle: {counts['total']} artist record(s) - "
        f"{counts['with_new']} with net-new, "
        f"{counts['net_new_tracks']} net-new track(s), "
        f"{counts['errored']} with errors, {counts['malformed']} malformed"
    )
    if not ndjson_text.strip():
        print("Empty bundle — nothing to import.")
        return counts

    if not apply:
        print("\n=== DRY-RUN — invoking the OPS import WITHOUT --apply ===")
        safe_print(runner(ndjson_text, False))
        print(
            "=== DRY-RUN — nothing written (the OPS script ran the funnel, printed its "
            "counters + a sample, and rolled back). No artist checkpointed — re-run with "
            "--apply, or --reuse-bundle --apply. REVIEW THE SAMPLE, then DUMP PROD before "
            "--apply (docs/restore.md). ==="
        )
        return counts

    print("\n=== APPLY — piping the bundle to the OPS import (--apply) ===")
    safe_print(runner(ndjson_text, True))
    append_checkpoint(checkpoint_path, processed_ids)
    print(
        f"\nCheckpointed {len(processed_ids)} artist id(s). Idempotent: the OPS import "
        "counts already-linked rows as already_deezer. Delete the checkpoint to force a "
        "full re-pass."
    )
    return counts


def _docker_build():
    print(f"[bundle] docker build -t {SERVER_IMAGE} (server/Dockerfile) ...")
    subprocess.run(
        ["docker", "build", "-t", SERVER_IMAGE, "-f", SERVER_DOCKERFILE, SERVER_DIR],
        check=True,
    )
    print(f"[bundle] docker build -t {IMAGE} (FROM {SERVER_IMAGE}) ...")
    subprocess.run(
        ["docker", "build", "-t", IMAGE,
         "--build-arg", f"SERVER_IMAGE={SERVER_IMAGE}", PKG_DIR],
        check=True,
    )


def _docker_bundle(workdir, deezer_rate, deezer_concurrency):
    """Run bundle_driver.py in the container over the pulled CSVs.

    Both driver files are copied into the workdir so the bind-mounted ``bundle_driver.py``
    can import its sibling ``fetch_driver.py`` (the shared walk helpers). No Redis in the
    container → the shared Deezer window fails open, only the local bucket + the
    residential floor govern.
    """
    for name in ("fetch_driver.py", "bundle_driver.py"):
        shutil.copy2(os.path.join(PKG_DIR, name), os.path.join(workdir, name))
    env_flags = [
        "-e", "REDIS_URL=redis://127.0.0.1:1/0",
        "-e", f"DEEZER_RATE={deezer_rate}",
        "-e", f"DEEZER_CONCURRENCY={deezer_concurrency}",
    ]
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{workdir}:/work", *env_flags, IMAGE,
         "python", "/work/bundle_driver.py",
         "--worklist", "/work/sample.csv", "--index", "/work/catalog_index.csv",
         "--out", "/work/bundle.ndjson"],
        check=True,
    )


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(args):
    _configure_stdout()
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    checkpoint_path = os.path.join(workdir, CHECKPOINT_FILE)
    bundle_path = os.path.join(workdir, "bundle.ndjson")
    index_path = os.path.join(workdir, "catalog_index.csv")

    if args.reuse_bundle:
        if not os.path.exists(bundle_path):
            sys.exit(f"--reuse-bundle: no {bundle_path} from a previous run")
        print(f"[reuse] importing previous {bundle_path} (no pull, no fetch)")
        with open(bundle_path, encoding="utf-8") as f:
            apply_or_plan(f.read(), args.apply, checkpoint_path)
        return

    shard = parse_shard(args.shard)

    # 1. COHORT
    print(
        f"[cohort] fetching (tiers={args.tiers}, limit={args.limit or 'none'}, "
        f"after_id={args.after_id or 'none'}, shard={args.shard or 'none'})..."
    )
    cohort_csv = run_remote_sql(
        REMOTE_PSQL_PULL, build_cohort_query(args.tiers, args.after_id, shard)
    )
    cohort = parse_rows(cohort_csv)
    done = load_checkpoint(checkpoint_path)
    fresh = filter_new(cohort, done)
    # --limit is applied AFTER the checkpoint filter (not in SQL), so a `--limit N`
    # loop keeps ADVANCING: each run drops the already-done head and takes the next N.
    # (A SQL LIMIT would re-pull the same head N every run and stall at "done".)
    if args.limit:
        fresh = fresh[: args.limit]
    print(
        f"[cohort] {len(cohort)} artist(s), "
        f"{len(cohort) - len(filter_new(cohort, done))} already done (checkpoint), "
        f"{len(fresh)} to fetch"
    )
    if not fresh:
        print("Nothing new to fetch — done.")
        return
    _write_csv(os.path.join(workdir, "sample.csv"), fresh, COHORT_FIELDS)

    # 2. INDEX (cached; --reuse-index skips the big pull)
    if os.path.exists(index_path) and args.reuse_index:
        print(f"[index] reusing cached {index_path}")
    else:
        print("[index] pulling catalog identity index (normalized_key,isrc) — big one-off...")
        index_csv = run_remote_sql(REMOTE_PSQL_PULL, build_catalog_index_query())
        with open(index_path, "w", encoding="utf-8", newline="") as f:
            f.write(index_csv)

    # 3. BUNDLE — walk + classify + fetch net-new /track in the prod server image
    _docker_build()
    _docker_bundle(workdir, args.deezer_rate, args.deezer_concurrency)
    if not os.path.exists(bundle_path):
        sys.exit(f"[bundle] the container produced no {bundle_path}")
    with open(bundle_path, encoding="utf-8") as f:
        bundle_text = f.read()

    # 4. IMPORT or dry-run plan (the OPS import writes; this tool never does)
    apply_or_plan(bundle_text, args.apply, checkpoint_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill the Deezer discography of the C14.a Phase 2 cohort from a "
        "residential IP: walk + classify net-new + fetch the net-new /track hits in the "
        "prod server image, then import them on the VPS via "
        "server/api/scripts/import_discography.py. Dry-run by default; --apply to write "
        "(DUMP PROD FIRST)."
    )
    parser.add_argument("--apply", action="store_true",
                        help="actually import on prod (default: dry-run, rolled back)")
    parser.add_argument("--tiers", default=DEFAULT_TIERS,
                        help=f"comma cohort tiers (default {DEFAULT_TIERS}; known: "
                        "a_lib,b_sets12m,c_catalog,d_traine)")
    parser.add_argument("--limit", type=int, default=0,
                        help="LIMIT on the cohort pull (0 = full); use with --after-id/--shard")
    parser.add_argument("--after-id", type=int, default=0,
                        help="artist_id keyset: only pull artist_id > this (resume a salvo)")
    parser.add_argument("--shard", default=None,
                        help="split by 'M/N' (AND artist_id %% N = M) for parallel salvos")
    parser.add_argument("--deezer-rate", dest="deezer_rate", type=float,
                        default=DEFAULT_DEEZER_RATE,
                        help=f"residential Deezer pace req/s (DEEZER_RATE, default "
                        f"{DEFAULT_DEEZER_RATE}, the C9 lesson). NEVER raise the PROD rate.")
    parser.add_argument("--deezer-concurrency", dest="deezer_concurrency", type=int,
                        default=DEFAULT_DEEZER_CONCURRENCY,
                        help=f"DEEZER_CONCURRENCY for the container (default {DEFAULT_DEEZER_CONCURRENCY})")
    parser.add_argument("--reuse-index", dest="reuse_index", action="store_true",
                        help="reuse a cached catalog_index.csv (skip only the big index pull)")
    parser.add_argument("--reuse-bundle", dest="reuse_bundle", action="store_true",
                        help="skip pull+fetch and import the existing <workdir>/bundle.ndjson")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR,
                        help="working dir for CSVs + bundle + checkpoint (default: <package>/data)")
    main(parser.parse_args())
