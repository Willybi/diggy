#!/usr/bin/env python
"""C13 C3 — local set-artist backfill orchestrator. Runs on the HOST (PC), stdlib only.

Backfills the ~42k EXISTING TrackID root sets that carry no artist link yet — the
fil-de-l'eau task ``link_set_artists`` only links NEW sets (bounded), so the pre-
existing backlog is this tool's job. Resolving a set means deriving artist
candidates from its ``(title, channel)`` and (on a base miss) hitting Deezer — a
mass-Deezer workload that is FORBIDDEN on the VPS (fair-use CPU + rate limiting,
the AV10 lesson). So the compute runs LOCALLY on the operator's residential IP and
the WRITE happens on the VPS through the OPS script
``server/api/scripts/import_set_artists_matches.py``. Twin of
``worker/beatport_backfill/``: same SSH/psql channel, same dry-run/apply +
checkpoint + salvo-relaunchable shape, same container-driven compute.

The three steps:

  1. PULL   — stream, read-only via the documented SSH/psql channel:
              (a) the WORKLIST of unlinked TrackID root sets (``id,title,channel``:
                  ``source='trackid'``, ``parent_set_id IS NULL``, ``NOT EXISTS`` a
                  ``set_artists`` row — the same selection the fil-de-l'eau task
                  uses), and (b) the ARTIST BASE (every ``artists.name`` + every
                  ``artist_aliases.normalized_alias`` → its artist id) so the
                  container resolves candidate names to VALID PROD artist ids
                  offline. ``--after-id`` / ``--limit`` window a salvo (clean id
                  keyset); ``--shard M/N`` splits the backlog by ``id % N`` for
                  disjoint parallel salvos.
  2. RESOLVE — ``docker run`` the driver in the PROD server image so the extractor,
              the resolver helpers AND the Deezer matcher are byte-identical to the
              fil-de-l'eau task (zero re-implementation of the X4 guards). It builds
              the fold-key lookup, resolves each set BASE-FIRST (free, our curated
              base) and only on a base miss verifies the name against Deezer
              (``_matching_deezer_hits`` + the optional fan floor, both reused
              VERBATIM), and emits ``links.ndjson`` (one record per processed set).
              The driver NEVER creates an artist and NEVER touches the DB — a Deezer
              match is emitted as ``(name, deezer_id)`` and the artist is resolved/
              created LIVE at push (invariant #4). Deezer is paced by the residential
              floor ``--deezer-rate`` (default 1.0 rps, the C9 lesson).
  3. APPLY  — pipe ``links.ndjson`` over ssh stdin to the OPS import script,
              propagating ``--apply``. In dry-run (default) the OPS script is invoked
              WITHOUT ``--apply``: it resolves identity live, prints its counters +
              a SAMPLE of the links it WOULD create (set title → artist[s], the
              human precision-review vector), and rolls back — no write of any kind.

>>> ``--apply`` MUTATES rows on prod (writes ``set_artists`` + may get-or-create an
    artist from a Deezer id). DUMP PROD FIRST (docs/restore.md). <<<  The tool
    itself never writes to the DB; the OPS script does, and it is idempotent, but a
    bad dump is not recoverable.

Checkpoint (``<workdir>/processed_set_ids.txt``): after a SUCCESSFUL ``--apply``,
every set id emitted in the NDJSON (a completed attempt, with or without links) is
recorded, so a periodic re-run only pulls NEW sets — including the no-resolve ones,
which otherwise have no ``set_artists`` row and would be re-pulled + re-searched
forever. Delete the checkpoint to force a full re-pass later. In dry-run nothing is
checkpointed (nothing was written); use ``--reuse-links --apply`` to write a prior
dry-run's links without re-resolving.

Usage (from the repo root, or anywhere):
    python worker/set_artist_backfill/backfill_set_artists.py --limit 50          # dry-run sample
    python worker/set_artist_backfill/backfill_set_artists.py                     # dry-run, full backlog
    python worker/set_artist_backfill/backfill_set_artists.py --apply             # resolve + write
    python worker/set_artist_backfill/backfill_set_artists.py --shard 0/4 --apply # one quarter, parallel-safe
    python worker/set_artist_backfill/backfill_set_artists.py --reuse-links --apply  # write last links
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

# the resolve step interleaves container output with ours — keep progress ordered
# even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path (PULL): -q keeps the COPY stream clean (CSV only on stdout).
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)

# Prod server image (context ./server via server/Dockerfile): carries workers/ +
# curl_cffi at /app. The package image (below) is a thin FROM of it so the local
# tool has a stable tag; the driver is bind-mounted at /work at run time.
SERVER_IMAGE = "diggy-set-artist-server"
IMAGE = "diggy-set-artist-backfill"

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
SERVER_DOCKERFILE = os.path.join(SERVER_DIR, "Dockerfile")
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
CHECKPOINT_FILE = "processed_set_ids.txt"

# CSV column contracts written for the container driver.
WORKLIST_FIELDS = ["id", "title", "channel"]
ARTIST_FIELDS = ["name", "artist_id"]

# Default residential-IP Deezer pace (req/s), passed to the container as DEEZER_RATE
# — the C9 lesson: a sustained residential Deezer rate gets rate-limited; ~1 rps +
# cooldown lifts it. NEVER raise the PROD rate (the server deezer config is fixed).
DEFAULT_DEEZER_RATE = 1.0

# Row-level concurrency for the driver's gather (== the server deezer source's
# semaphore); the token bucket + the residential floor still cap the request rate.
DEFAULT_DEEZER_CONCURRENCY = 5


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


def build_worklist_query(limit=0, after_id=0, shard=None):
    """COPY query for the unlinked TrackID root sets.

    Mirrors the fil-de-l'eau selection (``_select_unlinked_sets``): ``source=
    'trackid'``, roots only (``parent_set_id IS NULL``), and no existing
    ``set_artists`` row (``NOT EXISTS``) — that guard is the cross-run idempotence
    (a written set drops out of the next pull, exactly like beatport's
    ``searched_at IS NULL``). Ordered by ``id`` (a clean forward keyset), so
    ``after_id`` (``id > after_id``) resumes a salvo and ``shard`` (``id % N``)
    partitions parallel ones.
    """
    clauses = ""
    if after_id:
        clauses += f"    AND s.id > {int(after_id)}\n"
    if shard is not None:
        m, n = shard
        clauses += f"    AND s.id % {int(n)} = {int(m)}\n"
    limit_clause = f"  LIMIT {int(limit)}\n" if limit else ""
    return (
        "COPY (\n"
        "  SELECT s.id, s.title, s.channel\n"
        "  FROM sets s\n"
        "  WHERE s.source = 'trackid'\n"
        "    AND s.parent_set_id IS NULL\n"
        "    AND NOT EXISTS (\n"
        "      SELECT 1 FROM set_artists sa WHERE sa.set_id = s.id\n"
        "    )\n"
        f"{clauses}"
        "  ORDER BY s.id\n"
        f"{limit_clause}"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def build_artist_query():
    """COPY query for the artist main names (``name,artist_id``).

    Pulled FIRST so ``build_artist_lookup`` (first-spelling-wins on a fold collision)
    prefers a main name over an alias — parity with the task's ``_load_artist_lookup``.
    """
    return (
        "COPY (\n"
        "  SELECT a.name, a.id AS artist_id FROM artists a\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def build_alias_query():
    """COPY query for the artist aliases (``normalized_alias`` as ``name``,artist_id)."""
    return (
        "COPY (\n"
        "  SELECT al.normalized_alias AS name, al.artist_id\n"
        "  FROM artist_aliases al\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def parse_rows(csv_text):
    """Rows (dicts) from a COPY CSV output."""
    return list(csv.DictReader(io.StringIO(csv_text)))


def load_checkpoint(path):
    """Set of already-attempted set ids (as strings); missing file = empty set."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_checkpoint(path, ids):
    if not ids:
        return
    with open(path, "a", encoding="utf-8") as f:
        for sid in ids:
            f.write(f"{sid}\n")


def filter_new(rows, done):
    """Worklist rows whose set id is not yet in the checkpoint set."""
    return [r for r in rows if str(r["id"]).strip() not in done]


def summarize_links(ndjson_text):
    """Parse a links NDJSON blob -> ``(processed_set_ids, counts)``.

    ``processed_set_ids`` = string set ids of every well-formed record (a completed
    attempt, checkpointed after a successful --apply). ``counts`` tallies
    sets_with_links / sets_no_links / base_links / deezer_links / malformed / total.
    A malformed line (bad JSON, missing/invalid set_id or a non-list ``links``) is
    counted and skipped — never fatal. The OPS script does the authoritative DB
    accounting; this is only the host's progress + checkpoint bookkeeping.
    """
    processed_ids = []
    counts = {
        "total": 0,
        "sets_with_links": 0,
        "sets_no_links": 0,
        "base_links": 0,
        "deezer_links": 0,
        "malformed": 0,
    }
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
        sid = rec.get("set_id") if isinstance(rec, dict) else None
        links = rec.get("links") if isinstance(rec, dict) else None
        if (
            not isinstance(sid, int)
            or isinstance(sid, bool)
            or not isinstance(links, list)
        ):
            counts["malformed"] += 1
            continue
        processed_ids.append(str(sid))
        if links:
            counts["sets_with_links"] += 1
        else:
            counts["sets_no_links"] += 1
        for link in links:
            if isinstance(link, dict) and link.get("source") == "deezer":
                counts["deezer_links"] += 1
            elif isinstance(link, dict) and link.get("source") == "base":
                counts["base_links"] += 1
    return processed_ids, counts


def build_import_command(apply):
    """Remote command that pipes the NDJSON into the OPS import script.

    Dry-run invokes it WITHOUT ``--apply`` (it resolves identity live, prints its
    counters + a sample of proposed links and rolls back — no write); ``--apply``
    propagates the flag so it commits.
    """
    flag = " --apply" if apply else ""
    return (
        "cd /root/diggy && docker compose exec -T api "
        f"python scripts/import_set_artists_matches.py{flag}"
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
    """Pipe the links NDJSON to the OPS import script over ssh; return its stdout.

    The OPS script prints a human-readable report (linked / already_linked /
    artist_missing / placeholder_skipped / no_links / missing / malformed) plus, in
    dry-run, a SAMPLE of the links it would create. A non-zero exit raises.
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


def apply_or_plan(ndjson_text, apply, checkpoint_path, runner=run_remote_import):
    """Summarise the links, then hand them to the OPS import (dry-run or apply).

    Returns the counters dict. Checkpointing: after a SUCCESSFUL --apply, every
    processed set id is recorded; dry-run checkpoints NOTHING (nothing was written).
    An empty NDJSON short-circuits without touching the OPS script.
    """
    processed_ids, counts = summarize_links(ndjson_text)
    print(
        f"\nLinks: {counts['total']} set record(s) - "
        f"{counts['sets_with_links']} with links, "
        f"{counts['sets_no_links']} no-resolve, "
        f"{counts['base_links']} base + {counts['deezer_links']} deezer link(s), "
        f"{counts['malformed']} malformed"
    )

    if not ndjson_text.strip():
        print("No links to import (empty NDJSON) — nothing to do.")
        return counts

    if not apply:
        print("\n=== DRY-RUN — invoking the OPS import WITHOUT --apply ===")
        out = runner(ndjson_text, False)
        print(out)
        print(
            "=== DRY-RUN — nothing was written (the OPS script resolved identity, "
            "printed its counters + a sample of proposed links, and rolled back). No "
            "set id checkpointed — re-run with --apply, or --reuse-links --apply to "
            "skip re-resolving. REVIEW THE SAMPLE, then DUMP PROD before --apply "
            "(docs/restore.md). ==="
        )
        return counts

    print("\n=== APPLY — piping links to the OPS import (--apply) ===")
    out = runner(ndjson_text, True)
    print(out)
    append_checkpoint(checkpoint_path, processed_ids)
    print(
        f"\nCheckpointed {len(processed_ids)} attempted set id(s). Idempotent: the "
        "OPS import skips existing set_artists rows (already_linked), and the next "
        "pull drops written sets via NOT EXISTS. Delete the checkpoint to force a "
        "full re-pass."
    )
    return counts


def _docker_build():
    """Build the prod server image, then the thin package image FROM it."""
    print(f"[resolve] docker build -t {SERVER_IMAGE} (server/Dockerfile) ...")
    subprocess.run(
        ["docker", "build", "-t", SERVER_IMAGE, "-f", SERVER_DOCKERFILE, SERVER_DIR],
        check=True,
    )
    print(f"[resolve] docker build -t {IMAGE} (FROM {SERVER_IMAGE}) ...")
    subprocess.run(
        [
            "docker", "build",
            "-t", IMAGE,
            "--build-arg", f"SERVER_IMAGE={SERVER_IMAGE}",
            PKG_DIR,
        ],
        check=True,
    )


def _docker_resolve(workdir, deezer_rate, deezer_concurrency, fan_floor):
    """Run resolve_driver.py in the container over the pulled CSVs.

    Le conteneur local n'a pas de Redis. Une adresse qui refuse vite (port fermé)
    déclenche le fail-open immédiat du shared window Deezer → seul le bucket local +
    le plancher résidentiel (DEEZER_RATE) gouvernent (même astuce que beatport).
    """
    shutil.copy2(
        os.path.join(PKG_DIR, "resolve_driver.py"),
        os.path.join(workdir, "resolve_driver.py"),
    )
    env_flags = [
        "-e", "REDIS_URL=redis://127.0.0.1:1/0",
        "-e", f"DEEZER_RATE={deezer_rate}",
        "-e", f"DEEZER_CONCURRENCY={deezer_concurrency}",
    ]
    if fan_floor:
        env_flags += ["-e", f"LINK_SET_ARTIST_FAN_FLOOR={fan_floor}"]
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            *env_flags,
            IMAGE,
            "python", "/work/resolve_driver.py",
            "--worklist", "/work/worklist.csv",
            "--artists", "/work/artists.csv",
            "--aliases", "/work/aliases.csv",
            "--out", "/work/links.ndjson",
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
    links_path = os.path.join(workdir, "links.ndjson")

    if args.reuse_links:
        if not os.path.exists(links_path):
            sys.exit(f"--reuse-links: no {links_path} from a previous run")
        print(f"[reuse] importing previous {links_path} (no pull, no resolve)")
        with open(links_path, encoding="utf-8") as f:
            apply_or_plan(f.read(), args.apply, checkpoint_path)
        return

    shard = parse_shard(args.shard)

    # 1. PULL — read-only COPY from prod through the documented SSH channel
    print(
        f"[pull] fetching worklist (limit={args.limit or 'none'}, "
        f"after_id={args.after_id or 'none'}, shard={args.shard or 'none'})..."
    )
    worklist_csv = run_remote_sql(
        REMOTE_PSQL_PULL, build_worklist_query(args.limit, args.after_id, shard)
    )
    worklist = parse_rows(worklist_csv)
    _write_csv(os.path.join(workdir, "worklist.csv"), worklist, WORKLIST_FIELDS)

    done = load_checkpoint(checkpoint_path)
    fresh = filter_new(worklist, done)
    print(
        f"[pull] {len(worklist)} set(s), "
        f"{len(worklist) - len(fresh)} already attempted (checkpoint), "
        f"{len(fresh)} to resolve"
    )
    if not fresh:
        print("Nothing new to resolve - done.")
        return
    _write_csv(os.path.join(workdir, "worklist.csv"), fresh, WORKLIST_FIELDS)

    print("[pull] fetching artist base (names + aliases)...")
    artists_csv = run_remote_sql(REMOTE_PSQL_PULL, build_artist_query())
    aliases_csv = run_remote_sql(REMOTE_PSQL_PULL, build_alias_query())
    artists = parse_rows(artists_csv)
    aliases = parse_rows(aliases_csv)
    _write_csv(os.path.join(workdir, "artists.csv"), artists, ARTIST_FIELDS)
    _write_csv(os.path.join(workdir, "aliases.csv"), aliases, ARTIST_FIELDS)
    print(f"[pull] {len(artists)} artist name(s) + {len(aliases)} alias(es)")

    # 2. RESOLVE — in the prod server image (real extractor + matchers)
    _docker_build()
    _docker_resolve(
        workdir, args.deezer_rate, args.deezer_concurrency, args.fan_floor
    )
    if not os.path.exists(links_path):
        sys.exit(f"[resolve] the container produced no {links_path}")
    with open(links_path, encoding="utf-8") as f:
        links_text = f.read()

    # 3. APPLY or dry-run plan (the OPS import writes; this tool never does)
    apply_or_plan(links_text, args.apply, checkpoint_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill artist links for the existing unlinked TrackID sets "
        "from a residential IP: resolve (extractor + base + Deezer) in the prod "
        "server image, then import the links on the VPS via "
        "server/api/scripts/import_set_artists_matches.py (C13 C3 local tooling). "
        "Dry-run by default; --apply to write (DUMP PROD FIRST)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually import the links on prod (default: dry-run — the OPS script "
        "runs without --apply, prints its plan + a sample and rolls back)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="LIMIT on the worklist pull (0 = full backlog); use with --after-id or "
        "--shard to window a salvo",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="id keyset: only pull sets with id > this value (resume a salvo)",
    )
    parser.add_argument(
        "--shard",
        default=None,
        help="split the backlog by 'M/N' (adds AND s.id %% N = M) to run several "
        "residential-IP salvos in parallel without overlap",
    )
    parser.add_argument(
        "--deezer-rate",
        dest="deezer_rate",
        type=float,
        default=DEFAULT_DEEZER_RATE,
        help=f"residential-IP Deezer pace in req/s, passed to the container as "
        f"DEEZER_RATE (default {DEFAULT_DEEZER_RATE}; the C9 lesson — a sustained "
        "residential Deezer rate gets rate-limited, ~1 rps lifts it). NEVER raise "
        "the PROD rate.",
    )
    parser.add_argument(
        "--deezer-concurrency",
        dest="deezer_concurrency",
        type=int,
        default=DEFAULT_DEEZER_CONCURRENCY,
        help=f"DEEZER_CONCURRENCY for the container (default "
        f"{DEFAULT_DEEZER_CONCURRENCY} = the server deezer semaphore); the token "
        "bucket + the residential floor still cap the request rate",
    )
    parser.add_argument(
        "--fan-floor",
        dest="fan_floor",
        type=int,
        default=0,
        help="optional LINK_SET_ARTIST_FAN_FLOOR for the container: refuse a Deezer "
        "hit below this nb_fan (0 = off, an exact-name match of a small DJ links)",
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help="working directory for CSVs + NDJSON + checkpoint "
        "(default: <package>/data)",
    )
    parser.add_argument(
        "--reuse-links",
        action="store_true",
        help="skip pull+resolve and import the existing <workdir>/links.ndjson "
        "(e.g. dry-run first, inspect, then --reuse-links --apply)",
    )
    main(parser.parse_args())
