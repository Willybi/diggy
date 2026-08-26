#!/usr/bin/env python
"""One-shot OPS import: load the TrackID index NDJSON export into prod (C11 / lot L3).

The local spider (lot L2) crawls the ~381k TrackID.net audiostreams into a SQLite
staging DB and exports them as NDJSON on the column CONTRACT shared with L1 (the
``trackid_index`` prod table, lot L1). This script imports that export into prod,
seeds each row's hydration state, and computes an ultra-conservative dedup
pre-grouping. It NEVER hydrates a set (no TrackID detail call, no DJSet/SetTrack
creation) — that is C12's job.

Three steps, all idempotent (a re-run converges):

  1. IMPORT — reads the NDJSON (one JSON object per line, keyed by the L2 column
     contract), decodes it (``styles``/``raw_json`` are JSON STRINGS -> list/dict;
     ``is_deleted`` 0/1 -> bool; ``added_on``/``created_on`` ISO -> tz-aware datetime
     via the project's ``parse_trackid_date``, which maps the .NET default date to
     NULL; ``duration`` kept VERBATIM as the raw timespan string) and upserts every
     row into ``trackid_index`` via ``INSERT ... ON CONFLICT (trackid_id) DO UPDATE``.
     The upsert refreshes the raw-payload MIRROR columns + ``window_id`` +
     ``indexed_at`` but NEVER the Diggy-side state (``hydration_state``, ``set_id``,
     ``dedup_group_id``, ``score``/``score_components``/``matched_artist_ids`` stay
     as they were / their defaults) — those belong to steps 2/3 and to C12.

  2. SEED hydration — a single ``UPDATE ... FROM sets`` marks every index row whose
     ``trackid_id`` already backs an imported set (``sets.source='trackid'`` AND
     ``sets.external_id = trackid_id::text``) as ``hydration_state='hydrated'`` +
     links ``set_id``. The ~38k already-present sets (and the daily inflow) are thus
     NOT re-hydrated by C12; everything else stays ``not_hydrated``.

  3. DEDUP pre-grouping — an ULTRA-CONSERVATIVE clustering fills ``dedup_group_id``
     for members of clusters of size >= 2 (singletons stay NULL). It blocks by
     channel (two different channels NEVER group), groups on identical normalized
     ``base_title`` OR ``token_set_ratio >= 0.95`` (reusing the PURE
     ``set_dedup_service`` helpers — no threshold from C6's 0.80/0.50 is transposed),
     and applies a duration guard (a pair whose two KNOWN durations differ by > 2%
     never groups; an unknown duration is permissive). The C6 ``match_set`` filet at
     hydration time stays the AUTHORITY — this is only a pre-grouping.

Convention (mirrors the other OPS scripts): DRY-RUN by default (reads the NDJSON +
read-only DB queries, prints what WOULD be imported/seeded/grouped, writes NOTHING);
``--apply`` to write; ``--input <path.ndjson>`` (required); ``--limit N`` to cap the
rows read; ``--batch-size`` for the write batch size. Idempotent, committed per
batch, safe to crash mid-run (a re-run re-converges).

>>> ``--apply`` mutates ~381k rows. DUMP PROD FIRST (encrypted, see docs/restore.md). <<<

Prod sequence: deploy this script (push -> CI -> image) -> dry-run and read the
counters -> ENCRYPTED DUMP -> ``--apply`` -> re-dry-run to confirm convergence.

Usage (from the VPS, the NDJSON copied into the api container first):
    docker compose exec api python scripts/import_trackid_index.py --input /tmp/trackid_index.ndjson
    docker compose exec api python scripts/import_trackid_index.py --input /tmp/trackid_index.ndjson --apply
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models.trackid_index import TrackIdIndex
from services.set_dedup_service import normalize_set_title, token_set_ratio
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from trackid.parsing import parse_timespan_to_ms, parse_trackid_date

# ── config ────────────────────────────────────────────────────────────────────

# Rows per upsert / update statement (committed after each batch).
_BATCH = 1000

# Dedup thresholds (deliberately NOT the C6 0.80/0.50 — this is a pre-grouping).
FUZZY_RATIO = 0.95  # token_set_ratio bar to fuzzy-group two base_titles
DURATION_REL_TOL = 0.02  # a pair of KNOWN durations may differ by at most 2%
# A single-token difference only reaches Jaccard >= FUZZY_RATIO when both token
# sets are large (min / (min + 1) >= 0.95 => min >= 19). Below that, only an
# IDENTICAL token set clears the bar — already caught by the exact token-set
# bucket — so the bounded deletion-neighbourhood fuzzy pass is built ONLY for
# long titles (keeps the whole clustering well under a global O(n^2)).
FUZZY_MIN_TOKENS = 19
MAX_FUZZY_BUCKET = 200  # safety cap: skip fuzzy pairwise on a pathological bucket
# Same-title (identical token set) buckets are usually tiny (genuine re-uploads);
# do exact pairwise up to this size, fall back to the O(k log k) sweep beyond it.
MAX_SAME_TITLE_PAIRWISE = 500

# Raw-payload MIRROR columns refreshed on every (re-)import. Diggy-side state
# (hydration_state / set_id / dedup_group_id / score* / matched_artist_ids) is
# NEVER touched here — steps 2/3 and C12 own it.
MIRROR_COLS = (
    "trackid_id", "slug", "title", "channel", "styles", "status", "is_deleted",
    "track_count", "duration", "time_hit_rate", "track_hit_rate",
    "processing_priority", "artwork_url", "added_on", "created_on", "added_by",
    "added_by_id", "audio_stream_type", "external_id", "url", "favourite_count",
    "like_count", "average_rating", "raw_json", "window_id", "indexed_at",
)
_ON_CONFLICT_COLS = [c for c in MIRROR_COLS if c != "trackid_id"]

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors the other OPS scripts: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


# ── NDJSON decoding ───────────────────────────────────────────────────────────


def _as_int(v):
    if v is None or v == "":
        return None
    return int(v)


def _as_float(v):
    if v is None or v == "":
        return None
    return float(v)


def _as_bool(v):
    """is_deleted is 0/1 in the export (be defensive about a native bool too)."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    return bool(int(v))


def _as_json(v):
    """styles / raw_json are compact JSON STRINGS in the export -> list/dict."""
    if v is None or v == "":
        return None
    if isinstance(v, (list, dict)):
        return v  # defensive: already decoded
    return json.loads(v)


def parse_ndjson_row(obj, indexed_at):
    """One decoded NDJSON object -> a column dict for the upsert (mirror cols only)."""
    return {
        "trackid_id": _as_int(obj.get("trackid_id")),
        "slug": obj.get("slug"),
        "title": obj.get("title"),
        "channel": obj.get("channel"),
        "styles": _as_json(obj.get("styles")),
        "status": _as_int(obj.get("status")),
        "is_deleted": _as_bool(obj.get("is_deleted")),
        "track_count": _as_int(obj.get("track_count")),
        "duration": obj.get("duration") or None,  # raw timespan string, verbatim
        "time_hit_rate": _as_float(obj.get("time_hit_rate")),
        "track_hit_rate": _as_float(obj.get("track_hit_rate")),
        "processing_priority": _as_int(obj.get("processing_priority")),
        "artwork_url": obj.get("artwork_url"),
        "added_on": parse_trackid_date(obj.get("added_on")),
        "created_on": parse_trackid_date(obj.get("created_on")),
        "added_by": obj.get("added_by"),
        "added_by_id": _as_int(obj.get("added_by_id")),
        "audio_stream_type": _as_int(obj.get("audio_stream_type")),
        "external_id": obj.get("external_id"),
        "url": obj.get("url"),
        "favourite_count": _as_int(obj.get("favourite_count")),
        "like_count": _as_int(obj.get("like_count")),
        "average_rating": _as_float(obj.get("average_rating")),
        "raw_json": _as_json(obj.get("raw_json")),
        "window_id": obj.get("window_id"),
        "indexed_at": indexed_at,
    }


def iter_ndjson(path, limit=None):
    """Yield each decoded NDJSON object (blank lines skipped, capped by ``limit``)."""
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if limit is not None and n >= limit:
                break
            yield json.loads(line)
            n += 1


# ── dedup pre-grouping (PURE, DB-free — unit-tested without a database) ─────────


def _duration_compatible(a_ms, b_ms):
    """Duration guard: block a grouping only when BOTH durations are known and
    differ by more than ``DURATION_REL_TOL`` (relative). An unknown duration never
    blocks — permissive on the unknown, conservative overall."""
    if a_ms is None or b_ms is None:
        return True
    hi = max(a_ms, b_ms)
    if hi <= 0:
        return True
    return abs(a_ms - b_ms) / hi <= DURATION_REL_TOL


def _cluster_same_title(members, idxs, union):
    """Union an identical-token-set bucket. base_title matches for every pair here,
    so only the duration guard decides. Exact pairwise up to ``MAX_SAME_TITLE_PAIRWISE``;
    beyond it a bounded fallback (an unknown duration bridges the whole bucket —
    the permissive rule — otherwise union duration-adjacent members in sorted order,
    which reproduces the pairwise components for the 'within 2%' relation)."""
    if len(idxs) <= MAX_SAME_TITLE_PAIRWISE:
        for i in range(len(idxs)):
            a = members[idxs[i]]
            for j in range(i + 1, len(idxs)):
                b = members[idxs[j]]
                if _duration_compatible(a[3], b[3]):
                    union(a[0], b[0])
        return
    if any(members[i][3] is None for i in idxs):
        anchor = members[idxs[0]][0]
        for i in idxs:
            union(anchor, members[i][0])
        return
    known = sorted(idxs, key=lambda i: members[i][3])
    for a, b in zip(known, known[1:]):
        if _duration_compatible(members[a][3], members[b][3]):
            union(members[a][0], members[b][0])


def cluster_index(rows):
    """Ultra-conservative TrackID index dedup pre-grouping (C11 / L3), PURE & DB-free.

    ``rows``: iterable of ``(trackid_id, title, channel, duration)`` where ``duration``
    is the raw TrackID timespan string (or None). Returns ``{trackid_id: group_id}``
    holding ONLY the members of clusters of size >= 2 (a singleton is omitted -> its
    ``dedup_group_id`` stays NULL). Group ids are opaque 1..K in deterministic order.

    Rules: block by channel (two different channels NEVER group); within a channel
    group when the normalized ``base_title`` strings are identical OR
    ``token_set_ratio(base_a, base_b) >= FUZZY_RATIO``; the duration guard blocks a
    pair whose two KNOWN durations differ by more than ``DURATION_REL_TOL``. The C6
    0.80/0.50 thresholds are deliberately NOT transposed (they are calibrated on
    mtid overlap + order, absent here) — the C6 ``match_set`` filet at hydration is
    the authority; this is a pre-grouping only.

    Scales without a global O(n^2): channel blocking, then an exact token-set bucket
    (O(n), the guaranteed path — catches identical base_titles AND token reorderings,
    ``token_set_ratio == 1.0``), plus a bounded deletion-neighbourhood fuzzy pass
    restricted to long titles (a >= 0.95 non-identical ratio is only reachable there).
    Union-find gives the transitive closure inside a channel.
    """
    by_channel = defaultdict(list)  # channel -> [(tid, base, tokens, dur_ms)]
    for tid, title, channel, duration in rows:
        base = normalize_set_title(title or "", channel).base_title
        tokens = tuple(sorted(set(base.split())))
        by_channel[channel].append((tid, base, tokens, parse_timespan_to_ms(duration)))

    parent = {}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for members in by_channel.values():
        for m in members:
            parent.setdefault(m[0], m[0])

        # Exact token-set bucket (identical base_title or a token reorder) — O(n).
        tbuckets = defaultdict(list)
        for idx, m in enumerate(members):
            tbuckets[m[2]].append(idx)
        for idxs in tbuckets.values():
            if len(idxs) >= 2:
                _cluster_same_title(members, idxs, union)

        # Bounded fuzzy pass: a one-token deletion neighbourhood, long titles only.
        dbuckets = defaultdict(list)
        for idx, m in enumerate(members):
            tokens = m[2]
            if len(tokens) >= FUZZY_MIN_TOKENS:
                for i in range(len(tokens)):
                    dbuckets[tokens[:i] + tokens[i + 1:]].append(idx)
        for idxs in dbuckets.values():
            if len(idxs) < 2 or len(idxs) > MAX_FUZZY_BUCKET:
                continue
            for i in range(len(idxs)):
                a = members[idxs[i]]
                for j in range(i + 1, len(idxs)):
                    b = members[idxs[j]]
                    if not _duration_compatible(a[3], b[3]):
                        continue
                    if a[1] == b[1] or token_set_ratio(a[1], b[1]) >= FUZZY_RATIO:
                        union(a[0], b[0])

    comps = defaultdict(list)
    for tid in parent:
        comps[find(tid)].append(tid)
    result = {}
    gid = 0
    for root in sorted(comps):
        bucket = comps[root]
        if len(bucket) >= 2:
            gid += 1
            for tid in bucket:
                result[tid] = gid
    return result


# ── writers (apply) ────────────────────────────────────────────────────────────


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _upsert_batch(session, rows):
    stmt = pg_insert(TrackIdIndex).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["trackid_id"],
        set_={c: stmt.excluded[c] for c in _ON_CONFLICT_COLS},
    )
    session.execute(stmt)


def import_and_collect(session, path, indexed_at, *, apply, limit, batch_size):
    """Stream the NDJSON: (apply) upsert every row, and ALWAYS collect the dedup
    tuples + the trackid_ids (a single file read backs import + dedup + preview).
    Returns ``(imported, skipped, cluster_tuples, all_tids)``."""
    imported = skipped = 0
    cluster_tuples = []
    all_tids = []
    batch = []
    for obj in iter_ndjson(path, limit):
        row = parse_ndjson_row(obj, indexed_at)
        tid = row["trackid_id"]
        if tid is None:
            skipped += 1
            continue
        all_tids.append(tid)
        cluster_tuples.append((tid, row["title"], row["channel"], row["duration"]))
        if apply:
            batch.append(row)
            if len(batch) >= batch_size:
                _upsert_batch(session, batch)
                session.commit()
                imported += len(batch)
                batch = []
    if apply and batch:
        _upsert_batch(session, batch)
        session.commit()
        imported += len(batch)
    return imported, skipped, cluster_tuples, all_tids


def seed_hydration(session):
    """Single UPDATE ... FROM: hydrated + set_id for index rows already backed by a
    trackid set. Guarded so a re-run rewrites nothing (idempotent). Returns rowcount."""
    res = session.execute(
        text(
            "UPDATE trackid_index AS ti "
            "SET hydration_state = 'hydrated', set_id = s.id "
            "FROM sets AS s "
            "WHERE s.source = 'trackid' "
            "  AND s.external_id = CAST(ti.trackid_id AS text) "
            "  AND (ti.hydration_state <> 'hydrated' OR ti.set_id IS DISTINCT FROM s.id)"
        )
    )
    session.commit()
    return res.rowcount


def apply_dedup(session, mapping, all_tids, *, batch_size):
    """Reset ``dedup_group_id`` among the imported ids (only rows currently grouped),
    then stamp each cluster member's group id. Scoped to ``all_tids`` so a ``--limit``
    run never disturbs rows outside this import. Returns ``(reset, set_count)``."""
    clustered = set(mapping)
    to_null = [t for t in all_tids if t not in clustered]
    reset = set_count = 0
    for chunk in _chunks(to_null, batch_size):
        r = session.execute(
            text(
                "UPDATE trackid_index SET dedup_group_id = NULL "
                "WHERE trackid_id = ANY(:ids) AND dedup_group_id IS NOT NULL"
            ),
            {"ids": chunk},
        )
        reset += r.rowcount or 0
        session.commit()
    items = list(mapping.items())
    for chunk in _chunks(items, batch_size):
        session.execute(
            text("UPDATE trackid_index SET dedup_group_id = :g WHERE trackid_id = :t"),
            [{"g": g, "t": t} for t, g in chunk],
        )
        session.commit()
        set_count += len(chunk)
    return reset, set_count


# ── read-only helpers (dry-run preview + final report) ─────────────────────────


def existing_trackid_set_ids(session):
    """external_id of every trackid-sourced set (for the dry-run seed preview)."""
    rows = session.execute(
        text(
            "SELECT external_id FROM sets "
            "WHERE source = 'trackid' AND external_id IS NOT NULL"
        )
    ).scalars().all()
    return set(rows)


def db_report(session):
    return session.execute(
        text(
            "SELECT count(*) AS n, min(trackid_id) AS lo, max(trackid_id) AS hi, "
            "count(*) FILTER (WHERE hydration_state = 'hydrated') AS hydrated, "
            "count(*) FILTER (WHERE dedup_group_id IS NOT NULL) AS clustered, "
            "count(DISTINCT dedup_group_id) AS clusters "
            "FROM trackid_index"
        )
    ).one()


# ── reporting ──────────────────────────────────────────────────────────────────


def _dedup_summary(mapping):
    n_members = len(mapping)
    n_clusters = len(set(mapping.values()))
    sizes = defaultdict(int)
    for gid in mapping.values():
        sizes[gid] += 1
    examples = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return n_members, n_clusters, examples


def main(apply, input_path, limit, batch_size):
    if not os.path.exists(input_path):
        sys.exit(f"import: no NDJSON file at {input_path}")

    indexed_at = datetime.now(timezone.utc)
    engine = _get_engine()
    head = "APPLY" if apply else "DRY-RUN — nothing will be written (use --apply)"
    print(f"=== TrackID index import — {head} ===")
    print(f"    input: {input_path}" + (f"  (limit {limit})" if limit else ""))

    try:
        with Session(engine) as session:
            imported, skipped, cluster_tuples, all_tids = import_and_collect(
                session, input_path, indexed_at,
                apply=apply, limit=limit, batch_size=batch_size,
            )
            read = len(all_tids)
            verb = "imported" if apply else "would import"
            print(
                f"\n[import] read {read + skipped} line(s): {verb} {read} row(s)"
                + (f" ({skipped} skipped: no trackid_id)" if skipped else "")
            )

            # Dedup pre-grouping (computed from the input in BOTH modes).
            mapping = cluster_index(cluster_tuples)
            n_members, n_clusters, examples = _dedup_summary(mapping)
            dverb = "grouped" if apply else "would group"
            print(
                f"[dedup]  {dverb} {n_members} row(s) into {n_clusters} cluster(s) "
                f"(size >= 2); {read - n_members} singleton(s) -> NULL."
            )
            for gid, size in examples:
                print(f"    cluster #{gid}: {size} member(s)")

            if apply:
                seeded = seed_hydration(session)
                print(f"[seed]   marked {seeded} index row(s) hydrated (already a set).")
                reset, set_count = apply_dedup(
                    session, mapping, all_tids, batch_size=batch_size
                )
                print(
                    f"[dedup]  stamped {set_count} member(s); cleared {reset} stale "
                    f"group(s) among the imported ids."
                )
                r = db_report(session)
                print(
                    f"\n[report] table now holds {r.n} row(s) "
                    f"(trackid_id {r.lo}..{r.hi}); {r.hydrated} hydrated; "
                    f"{r.clustered} row(s) in {r.clusters} cluster(s)."
                )
            else:
                seen = existing_trackid_set_ids(session)
                would_seed = sum(1 for tid in all_tids if str(tid) in seen)
                existing = session.execute(
                    text("SELECT count(*) FROM trackid_index")
                ).scalar_one()
                print(
                    f"[seed]   {would_seed} imported row(s) match an existing trackid "
                    f"set and WOULD be hydrated."
                )
                print(
                    f"\n[report] table currently holds {existing} row(s) (pre-import). "
                    "Re-run with --apply to write — DUMP PROD FIRST (docs/restore.md)."
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import the TrackID index NDJSON export into prod (mirror upsert "
        "+ hydration seed + ultra-conservative dedup pre-grouping). Dry-run by default."
    )
    parser.add_argument(
        "--input", required=True, help="path to the NDJSON export (from L2 export)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="cap the number of NDJSON rows read"
    )
    parser.add_argument(
        "--batch-size", type=int, default=_BATCH, help="rows per write batch/commit"
    )
    args = parser.parse_args()
    main(
        apply=args.apply,
        input_path=args.input,
        limit=args.limit,
        batch_size=args.batch_size,
    )
