#!/usr/bin/env python
"""C9.a — local EffNet embedding backfill orchestrator. Runs on the HOST (Windows PC), stdlib only.

Computes the frozen C9 v1 audio embedding (Discogs-EffNet, 1280-d) from Deezer
30s previews for the ~266k ``catalog`` rows that have a preview and no
``track_embeddings`` row yet for ``(MODEL_NAME, MODEL_VERSION)``, and writes them
to the prod pgvector table. Twin of the E2.b BPM tool
(``worker/bpm_backfill/``): same SSH/psql channel, same dry-run/apply + checkpoint
+ salvo-relaunchable shape, but it INSERTs a vector instead of UPDATE-ing a scalar.

The embed model + node are frozen at the C9.0-bis benchmark (EffNet won):
``TensorflowPredictEffnetDiscogs`` node ``PartitionedCall:1``, 16 kHz, mean over
patches, L2-normalised (``docs/c9-benchmark/embed_eval.py``, reused verbatim in
``embed.py``).

Local tooling (A7-07 pattern): Essentia does not install on Windows, so the embed
pass runs in a Docker Linux container (image built from this package's Dockerfile,
essentia-tensorflow + the baked EffNet graph) while THIS script drives the pipeline
from the host — it needs only the Python stdlib, ``ssh`` (the ``diggy-vps`` alias)
and ``docker``.

The three steps:

  1. PULL    — stream the candidates (``id,deezer_id``) from prod, read-only,
               via ``ssh diggy-vps '... psql -q -f -'`` fed a ``COPY (...) TO
               STDOUT`` query. Candidates = previewable rows with a resolvable
               deezer_id and NO embedding yet for (model,version) — a LEFT JOIN
               on ``track_embeddings`` with ``te.id IS NULL``. ``ORDER BY c.id``
               (+ optional ``--after-id``) makes the pull keyset-resumable.
  2. EMBED   — ``docker run --rm -v <workdir>:/work`` on ``embed.py`` (throttled
               Deezer fetch, transient MP3, EffNet, L2-norm). NO audio persisted.
  3. APPLY   — only with ``--apply``: batched ``INSERT INTO track_embeddings ...
               ON CONFLICT (catalog_id, model_name, model_version) DO NOTHING``
               through the same SSH/psql channel. The ON CONFLICT clause is the
               idempotence guard: an embedding already written for that
               (track,model,version) is NEVER duplicated. The vector is rendered
               as a pgvector literal ``'[f1,f2,...]'::vector``.

DRY-RUN by default: without ``--apply`` the INSERT is NOT executed; the plan is
printed instead (eligible/no_preview/errors counters + an excerpt of the SQL).

Checkpoint (``<workdir>/processed_ids.txt``): every attempted id whose outcome is
FINAL is recorded — ``no_preview`` rows always, written rows after a successful
--apply batch. ``error:*`` rows are NEVER recorded: they are mostly Deezer rate
limits, so they must stay retryable. A periodic re-run ("fil de l'eau") therefore
downloads new candidates and past errors, never the known no_preview rows
(already-embedded rows also drop out of the pull via the ``te.id IS NULL`` join).
Rows embedded OK during a dry-run are NOT checkpointed (they still need writing);
use ``--reuse-results`` to apply a previous run's results.csv without re-embedding.

Usage (from the repo root, or anywhere):
    python worker/embedding_backfill/backfill_embeddings.py --limit 20            # dry-run sample
    python worker/embedding_backfill/backfill_embeddings.py                       # dry-run, full backlog
    python worker/embedding_backfill/backfill_embeddings.py --apply               # embed + write
    python worker/embedding_backfill/backfill_embeddings.py --loop --apply         # marathon: drain the whole backlog
    python worker/embedding_backfill/backfill_embeddings.py --reuse-results --apply  # write last results
"""

import argparse
import csv
import functools
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import namedtuple

# the embed step interleaves container output with ours — keep progress ordered
# even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path (PULL): -q keeps the COPY stream clean (CSV only on stdout).
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)
# Write path (APPLY): no -q so psql prints the "INSERT 0 n" command tags (parsed
# for the real inserted count); ON_ERROR_STOP makes a failed statement abort with
# a non-zero exit instead of silently continuing.
REMOTE_PSQL_APPLY = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -v ON_ERROR_STOP=1 -f -'"
)

IMAGE = "diggy-embedding-backfill"
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
CHECKPOINT_FILE = "processed_ids.txt"

# Frozen C9.a identity of the default embedding model. MUST stay in sync with
# server/api/models/embedding.py (MODEL_NAME/MODEL_VERSION/EMBEDDING_DIM) — this
# host script is stdlib-only and cannot import that SQLAlchemy module.
MODEL_NAME = "discogs-effnet"
MODEL_VERSION = "bs64-1"
EMBEDDING_DIM = 1280

BATCH_SIZE = 200
# --loop window size when --limit is not given: each marathon pass pulls+embeds+
# writes this many rows so results land in prod recurrently (not one burst at the
# very end of a multi-day run).
LOOP_WINDOW_DEFAULT = 20000
# --loop re-runs the whole backlog while rows fail, waiting between rounds: the
# Deezer rate limit is throughput-driven and lifts after a 20-30 min cooldown.
LOOP_MAX_ROUNDS_DEFAULT = 3
LOOP_RETRY_COOLDOWN_DEFAULT = 1800
# statuses whose outcome is final — checkpointed even on dry-run (a re-run would
# just re-download the same reject). "ok" is final only once WRITTEN. "error:*" is
# deliberately absent: a rate-limited row must stay retryable.
_REJECT_STATUSES = ("no_preview",)

# One PULL -> EMBED -> APPLY window: rows pulled, highest id pulled, rows ignored
# because they are in the checkpoint, rows that failed with error:*.
PassResult = namedtuple("PassResult", "pulled max_id skipped errors")


def build_pull_query(limit=0, after_id=0):
    """COPY query for the candidates: previewable, resolvable deezer_id, and NO
    embedding yet for (MODEL_NAME, MODEL_VERSION).

    ``ORDER BY c.id`` + optional ``after_id`` (``AND c.id > N``) make the pull
    keyset-resumable across salvos. The ``te.id IS NULL`` LEFT JOIN is what makes
    the whole thing idempotent: an already-embedded row never re-appears.
    """
    after_clause = f"    AND c.id > {int(after_id)}\n" if after_id else ""
    limit_clause = f"  LIMIT {int(limit)}\n" if limit else ""
    return (
        "COPY (\n"
        "  SELECT c.id, c.deezer_id\n"
        "  FROM catalog c\n"
        "  LEFT JOIN track_embeddings te\n"
        "    ON te.catalog_id = c.id\n"
        f"   AND te.model_name = '{MODEL_NAME}'\n"
        f"   AND te.model_version = '{MODEL_VERSION}'\n"
        "  WHERE c.has_preview = true\n"
        "    AND c.deezer_id IS NOT NULL\n"
        "    AND c.deezer_id <> 'NOT_FOUND'\n"
        "    AND te.id IS NULL\n"
        f"{after_clause}"
        "  ORDER BY c.id\n"
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


def _parse_emb(raw):
    """Parse the ``emb`` cell (JSON list of floats) -> list, or None if unusable."""
    if not raw:
        return None
    try:
        vec = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(vec, list):
        return None
    return vec


def eligible_inserts(results, dim=EMBEDDING_DIM):
    """(id, [floats]) pairs safe to write: status ok AND a well-formed dim-vector.

    The dim check is defense in depth on the results file — a malformed or
    wrong-length vector is dropped rather than written into a fixed-width pgvector
    column (which would reject the whole batch under ON_ERROR_STOP).
    """
    pairs = []
    for row in results:
        if row.get("status") != "ok":
            continue
        vec = _parse_emb(row.get("emb"))
        if vec is None or len(vec) != dim:
            continue
        pairs.append((int(row["id"]), vec))
    return pairs


def reject_ids(results):
    """Ids with a FINAL negative outcome (checkpointed even on dry-run)."""
    return [str(r["id"]).strip() for r in results if r.get("status") in _REJECT_STATUSES]


def format_vector_literal(vec):
    """Render a float list as a pgvector literal ``'[f1,f2,...]'::vector``.

    ``float()`` coercion of every component makes the interpolated literal
    injection-safe (the values come from our own container, but the pull could
    in principle carry anything — coerce anyway).
    """
    inner = ",".join(repr(float(x)) for x in vec)
    return f"'[{inner}]'::vector"


def build_insert_batches(
    pairs,
    batch_size=BATCH_SIZE,
    model_name=MODEL_NAME,
    model_version=MODEL_VERSION,
):
    """[(sql, [ids...]), ...] — one ``INSERT ... ON CONFLICT DO NOTHING`` per batch.

    ``int()`` coercion of the id + ``format_vector_literal`` make the interpolated
    literals injection-safe; ON CONFLICT on (catalog_id, model_name, model_version)
    — the ``uq_track_embeddings_catalog_model`` unique — is the idempotence guard
    (an existing embedding for that track/model/version is never duplicated).
    ``created_at`` is stamped server-side with ``now()``.
    """
    batches = []
    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i : i + batch_size]
        values = ",\n    ".join(
            f"({int(cid)}, '{model_name}', '{model_version}', "
            f"{format_vector_literal(vec)}, now())"
            for cid, vec in chunk
        )
        sql = (
            "INSERT INTO track_embeddings\n"
            "    (catalog_id, model_name, model_version, embedding, created_at)\n"
            "VALUES\n"
            f"    {values}\n"
            "ON CONFLICT (catalog_id, model_name, model_version) DO NOTHING;\n"
        )
        batches.append((sql, [str(int(cid)) for cid, _ in chunk]))
    return batches


def parse_insert_count(psql_output):
    """Sum of the inserted-row counts from psql's ``INSERT 0 n`` command tags."""
    return sum(int(n) for n in re.findall(r"^INSERT \d+ (\d+)", psql_output, re.M))


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
    dim=EMBEDDING_DIM,
    batch_size=BATCH_SIZE,
    runner=run_remote_sql,
):
    """Gate the results, then either print the plan (dry-run) or run the INSERTs.

    Returns the counters dict. Checkpointing: no_preview rows always; written ids
    per SUCCESSFUL batch only (a failed batch leaves its ids un-checkpointed, and
    the ON CONFLICT guard makes the eventual re-write idempotent); error rows never.
    """
    pairs = eligible_inserts(results, dim)
    rejects = reject_ids(results)
    batches = build_insert_batches(pairs, batch_size)
    counters = {
        "embedded": len(results),
        "eligible": len(pairs),
        "no_preview": sum(1 for r in results if r.get("status") == "no_preview"),
        "errors": sum(
            1 for r in results if str(r.get("status", "")).startswith("error:")
        ),
        "written": 0,
    }
    print(
        f"\nResults: {counters['embedded']} embedded - "
        f"{counters['eligible']} eligible (dim == {dim}), "
        f"{counters['no_preview']} no_preview, {counters['errors']} errors"
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
            f"{counters['eligible']} embedding(s) WOULD be inserted for "
            f"({MODEL_NAME}, {MODEL_VERSION}), guarded by ON CONFLICT DO NOTHING "
            "(an already-stored embedding is never duplicated). no_preview ids were "
            "checkpointed; the eligible and error ids were NOT (eligible ids still "
            "need writing - re-run with --apply, or --reuse-results --apply to skip "
            "re-embedding)."
        )
        return counters

    print(f"\n=== APPLY - {len(batches)} batch(es) of <= {batch_size} rows ===")
    for i, (sql, ids) in enumerate(batches, 1):
        out = runner(REMOTE_PSQL_APPLY, sql)
        written = parse_insert_count(out)
        counters["written"] += written
        append_checkpoint(checkpoint_path, ids)
        print(
            f"  batch {i}/{len(batches)}: {written}/{len(ids)} inserted "
            "(others already had an embedding - ON CONFLICT)"
        )
    append_checkpoint(checkpoint_path, rejects)
    print(
        f"\nInserted {counters['written']}/{counters['eligible']} embedding(s) for "
        f"({MODEL_NAME}, {MODEL_VERSION}); "
        f"{counters['eligible'] - counters['written']} skipped by ON CONFLICT. "
        f"Written and no_preview ids checkpointed; {counters['errors']} error(s) "
        "left retryable."
    )
    return counters


_IMAGE_BUILT = False


def _docker_build():
    """Build the embed image once per process (idempotent — a --loop marathon must
    not re-shell `docker build` on every window; the layers are cached anyway)."""
    global _IMAGE_BUILT
    if _IMAGE_BUILT:
        return
    print(f"[embed] docker build -t {IMAGE} ...")
    subprocess.run(["docker", "build", "-t", IMAGE, PKG_DIR], check=True)
    _IMAGE_BUILT = True


def _docker_embed(workdir, workers):
    """Run embed.py in the container over <workdir>/to_analyze.csv."""
    shutil.copy2(
        os.path.join(PKG_DIR, "embed.py"),
        os.path.join(workdir, "embed.py"),
    )
    env_flags = []
    # Optional gentler Deezer pacing for a mop-up pass under a cumulative rate-limit.
    min_interval = os.environ.get("EMBED_MIN_INTERVAL")
    if min_interval:
        env_flags += ["-e", f"EMBED_MIN_INTERVAL={min_interval}"]
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            *env_flags,
            IMAGE,
            "python", "/work/embed.py",
            "--csv", "/work/to_analyze.csv",
            "--out", "/work/results.csv",
            "--workers", str(workers),
        ],
        check=True,
    )


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _run_pass(after_id, limit, workdir, checkpoint_path, results_path, args):
    """One PULL -> EMBED -> APPLY window, returned as a ``PassResult``.

    ``pulled == 0`` means no row is left past ``after_id``, NOT that the backlog is
    empty: rows behind the cursor may have failed or been skipped, which is why
    ``skipped`` and ``errors`` are reported. The --loop driver advances its keyset
    cursor to ``max_id`` — a window that pulls rows but has nothing FRESH STILL
    returns it, so the marathon steps over a band of known rows instead of stalling.
    """
    # 1. PULL — read-only COPY from prod through the documented SSH channel
    print(
        f"[pull] fetching candidates from prod (limit={limit or 'none'}, "
        f"after_id={after_id or 'none'})..."
    )
    csv_text = run_remote_sql(REMOTE_PSQL_PULL, build_pull_query(limit, after_id))
    candidates = parse_candidates(csv_text)
    _write_csv(
        os.path.join(workdir, "candidates.csv"), candidates, ["id", "deezer_id"]
    )
    if not candidates:
        print("[pull] 0 candidate(s) - nothing left past this cursor.")
        return PassResult(0, after_id, 0, 0)
    max_id = max(int(c["id"]) for c in candidates)
    done = load_checkpoint(checkpoint_path)
    fresh = filter_new(candidates, done)
    skipped = len(candidates) - len(fresh)
    print(
        f"[pull] {len(candidates)} candidate(s), "
        f"{skipped} skipped (checkpoint), "
        f"{len(fresh)} to embed"
    )
    if not fresh:
        print("Nothing new to embed in this window.")
        return PassResult(len(candidates), max_id, skipped, 0)
    _write_csv(os.path.join(workdir, "to_analyze.csv"), fresh, ["id", "deezer_id"])

    # 2. EMBED — in the container (essentia-tensorflow is Linux-only)
    _docker_build()  # idempotent: the real `docker build` runs once per process
    _docker_embed(workdir, args.workers)
    results = read_results(results_path)

    # 3. APPLY or dry-run plan
    counters = apply_or_plan(
        results, args.apply, checkpoint_path,
        dim=EMBEDDING_DIM, batch_size=args.batch_size,
    )
    return PassResult(len(candidates), max_id, skipped, counters["errors"])


def _run_round(window, workdir, checkpoint_path, results_path, args):
    """Walk the backlog once by keyset. Returns (errors, skipped) over the round."""
    after_id = args.after_id
    errors = skipped = 0
    while True:
        print(f"\n===== [loop] window (after_id={after_id or 'none'}) =====")
        res = _run_pass(after_id, window, workdir, checkpoint_path, results_path, args)
        errors += res.errors
        skipped += res.skipped
        if res.pulled == 0:
            return errors, skipped
        if res.max_id <= after_id:
            print(
                f"[loop] cursor did not advance (max_id={res.max_id} "
                f"<= after_id={after_id}) - ending this round to avoid a tight loop."
            )
            return errors, skipped
        after_id = res.max_id


def _run_loop(workdir, checkpoint_path, results_path, args):
    """Marathon: walk the backlog in keyset windows, then walk it again while rows
    keep failing (--apply only: a dry-run writes nothing, so re-walking would just
    re-embed everything).

    Each window writes (per BATCH_SIZE INSERT) and checkpoints BEFORE the next, so
    results reach prod recurrently and a restart resumes from the checkpoint. Run it
    in a durable terminal. The final line only claims "drained" when no row was
    left behind: skipped rows still lack an embedding, they are just not retried.
    """
    window = args.limit or LOOP_WINDOW_DEFAULT
    print(
        f"[loop] marathon: window={window}, workers={args.workers}, "
        f"apply={args.apply}, start after_id={args.after_id or 'none'}, "
        f"max_rounds={args.max_rounds}"
    )
    errors = skipped = 0
    for round_no in range(1, args.max_rounds + 1):
        if round_no > 1:
            print(f"\n[loop] {errors} error(s): cooling down {args.retry_cooldown}s")
            time.sleep(args.retry_cooldown)
        print(f"\n########## [loop] round {round_no}/{args.max_rounds} ##########")
        errors, skipped = _run_round(window, workdir, checkpoint_path, results_path, args)
        if not errors or not args.apply:
            break
    if not errors and not skipped:
        print("\n[loop] drained - no candidate left.")
        return
    print(
        f"\n[loop] stopped with rows left: {errors} still in error (re-run to retry), "
        f"{skipped} skipped by the checkpoint (no_preview, not retried)."
    )


def main(args):
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    checkpoint_path = os.path.join(workdir, CHECKPOINT_FILE)
    results_path = os.path.join(workdir, "results.csv")

    if args.reuse_results:
        if not os.path.exists(results_path):
            sys.exit(f"--reuse-results: no {results_path} from a previous run")
        print(f"[reuse] gating previous {results_path} (no pull, no embed)")
        results = read_results(results_path)
        apply_or_plan(
            results, args.apply, checkpoint_path,
            dim=EMBEDDING_DIM, batch_size=args.batch_size,
        )
        return

    if args.loop:
        _run_loop(workdir, checkpoint_path, results_path, args)
        return

    res = _run_pass(
        args.after_id, args.limit, workdir, checkpoint_path, results_path, args
    )
    if res.pulled == 0:
        print("Nothing new to embed - done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill EffNet audio embeddings (Discogs-EffNet, 1280-d) "
        "from Deezer previews into the prod track_embeddings pgvector table "
        "for catalog rows with a preview and no embedding yet (C9.a local tooling)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually run the batched INSERTs on prod (default: dry-run, "
        "prints the plan and writes nothing)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="LIMIT on the candidates pull (0 = full backlog); use with "
        "--after-id to window a salvo",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="keyset resume: only pull candidates with catalog id > this value "
        "(0 = from the start)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="embed threads in the container (Deezer API stays ~5 rps; EffNet "
        "inference is CPU-bound, keep this modest on a laptop)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="rows per INSERT statement in --apply (each row carries a 1280-float "
        "vector literal, so keep batches modest)",
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help="working directory for CSVs + checkpoint (default: <package>/data)",
    )
    parser.add_argument(
        "--reuse-results",
        action="store_true",
        help="skip pull+embed and gate/apply the existing <workdir>/results.csv "
        "(e.g. dry-run first, inspect, then --reuse-results --apply)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="marathon mode: repeatedly pull+embed+write a window of --limit rows "
        f"(default {LOOP_WINDOW_DEFAULT}), advancing a keyset cursor, until the "
        "backlog is drained. Results reach prod after EVERY window (not once at "
        "the very end), and a restart resumes from the checkpoint. Pair with "
        "--apply; run it in a durable terminal.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=LOOP_MAX_ROUNDS_DEFAULT,
        help="--loop: walk the whole backlog at most this many times while rows "
        "fail with error:*",
    )
    parser.add_argument(
        "--retry-cooldown",
        type=int,
        default=LOOP_RETRY_COOLDOWN_DEFAULT,
        help="--loop: seconds to wait between two rounds, to let the Deezer rate "
        "limit lift",
    )
    main(parser.parse_args())
