#!/usr/bin/env python
"""One-shot cleanup: merge EXISTING catalog duplicates that are the same recording.

Ingestion dedups on ``normalized_key``/``isrc`` but never on the platform ids,
so the same track can land in ``catalog`` twice (X1). This script looks at every
group of rows sharing a non-NULL ``deezer_id`` (then ``beatport_id``) but does
NOT collapse the whole group: sharing a platform id does not mean same recording
(Deezer returns hits[0] unchecked so a remix inherits the original's deezer_id;
the Beatport release fallback stamps one beatport_id on every EP track). Instead
each id-group is CLUSTERED by ``workers.catalog_merge.same_track`` (ISRC identity,
else a conservative remix-aware title match), and only clusters of 2+ rows — the
true duplicates — are folded to a single canonical row via the L1 primitive
``merge_catalog_entries`` (which repoints every FK — incl. the ON DELETE RESTRICT
``user_tracks`` — before deleting the loser). Singleton clusters (remixes, EP
tracks) are left intact; the row to keep per cluster is chosen by ``pick_canonical``.

Deezer is processed FIRST and committed, THEN beatport is re-queried on the
up-to-date state: a deezer merge may already have united rows that also shared a
beatport_id, so re-querying avoids ever touching an already-deleted row.

>>> DESTRUCTIVE (deletes rows). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
whole operation is idempotent — a re-run finds the remaining groups), but a bad
dump is not recoverable.

The run is DRY-RUN by default: it prints how many id-groups hold a real duplicate
cluster, how many are distinct recordings left intact, how many rows would be
removed, and a few examples, WITHOUT modifying anything. Pass --apply to actually
merge. A second --apply run is idempotent (finds 0 mergeable cluster).

Trend scores and the similarity cache are NOT recomputed here: they refresh on
the next nightly run (compute_trends + similarity cache). No manual recompute.

Usage (from the VPS):
    docker compose exec api python scripts/dedup_catalog.py            # dry-run
    docker compose exec api python scripts/dedup_catalog.py --apply    # merge
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import CatalogEntry
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from workers.catalog_merge import merge_catalog_entries, pick_canonical, same_track

# Platform-id columns to fold, in order. Deezer FIRST so a deezer merge that also
# unites a beatport group is applied before the beatport pass re-queries.
_DEDUP_COLUMNS = ("deezer_id", "beatport_id")
# Groups per committed transaction in --apply mode: small enough to never hold a
# giant transaction, large enough to avoid a commit per group.
_COMMIT_EVERY = 50

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _duplicate_values(session, column):
    """Return the ``column`` values shared by 2+ catalog rows (merge candidates)."""
    col = getattr(CatalogEntry, column)
    return [
        row[0]
        for row in session.execute(
            select(col).where(col.isnot(None)).group_by(col).having(func.count() > 1)
        ).all()
    ]


def _cluster_by_same_track(rows):
    """Partition rows sharing a platform id into same-recording clusters.

    Sharing a platform id is NOT proof of identity, so the group is split by
    ``same_track``: for each still-unassigned row a new cluster is opened, then
    every other unassigned row that ``same_track`` confirms is pulled in. A
    cluster of 1 (a remix, an EP track) is a distinct recording and must NOT be
    merged; only clusters of 2+ are true duplicates.

    A row joins only if it is ``same_track`` with EVERY current member (a clique),
    not merely with the seed. ``same_track`` is not transitive across the
    ISRC/title boundary — a no-ISRC row can match two rows that carry conflicting
    ISRCs (two distinct recordings under one title). The seed-only rule would
    merge those two; the clique rule cannot, so a bad merge is impossible
    (invariant #4). The cost is at worst a missed duplicate — cheap storage debt.
    Platform-id groups are tiny (a handful of rows), so the O(n²) scan is cheap.
    """
    clusters = []
    assigned = set()
    for seed in rows:
        if seed.id in assigned:
            continue
        cluster = [seed]
        assigned.add(seed.id)
        for other in rows:
            if other.id in assigned:
                continue
            if all(same_track(member, other) for member in cluster):
                cluster.append(other)
                assigned.add(other.id)
        clusters.append(cluster)
    return clusters


def dedup_by_column(
    session, column, *, apply=False, commit_every=_COMMIT_EVERY, max_examples=5
):
    """Merge the same-recording clusters within each shared-``column`` group.

    Each group of rows sharing a non-NULL ``column`` is split by
    ``_cluster_by_same_track``; only clusters of 2+ rows are true duplicates.
    For each such cluster ``pick_canonical`` picks the row to keep and the others
    are folded in with ``merge_catalog_entries``. Singleton clusters (remixes, EP
    tracks that merely share the platform id) are left untouched — the bulk of
    beatport groups fall here, by design.

    The value list is snapshotted once for THIS column, but the rows of each
    group are re-loaded fresh and groups an earlier pass already collapsed
    (``len(rows) < 2``) are skipped — so running this for ``beatport_id`` AFTER
    the ``deezer_id`` pass never touches a deleted row.

    apply=False (default) is read-only: nothing is committed and the returned
    counts describe what WOULD happen (post-clustering, i.e. only the rows that
    are actually mergeable). In --apply mode the work is committed every
    ``commit_every`` groups (plus a trailing commit).

    Returns ``{"groups", "distinct", "losers", "deleted", "examples"}`` where
    ``groups`` counts id-groups holding at least one mergeable cluster,
    ``distinct`` counts id-groups left fully intact (only singleton clusters),
    and ``examples`` is a list of ``(value, canonical_id, [loser_id, ...])`` per
    merged cluster.
    """
    col = getattr(CatalogEntry, column)
    dup_values = _duplicate_values(session, column)

    groups = distinct = losers = deleted = 0
    examples = []
    pending = 0

    for value in dup_values:
        rows = session.execute(select(CatalogEntry).where(col == value)).scalars().all()
        if len(rows) < 2:
            continue  # already collapsed by a previous pass

        mergeable = [c for c in _cluster_by_same_track(rows) if len(c) > 1]
        if not mergeable:
            distinct += 1  # only distinct recordings share this id — leave intact
            continue
        groups += 1

        for cluster in mergeable:
            canonical = pick_canonical(cluster)
            loser_ids = [r.id for r in cluster if r.id != canonical.id]
            losers += len(loser_ids)
            if len(examples) < max_examples:
                examples.append((value, canonical.id, loser_ids))
            if apply:
                for loser_id in loser_ids:
                    merge_catalog_entries(session, canonical.id, loser_id)
                    deleted += 1

        if apply:
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "groups": groups,
        "distinct": distinct,
        "losers": losers,
        "deleted": deleted,
        "examples": examples,
    }


def _total_rows(session):
    return session.execute(select(func.count()).select_from(CatalogEntry)).scalar_one()


def _print_report(column, stats, apply):
    verb = "merged" if apply else "would merge"
    print(
        f"\n[{column}] {stats['groups']} group(s) with a real duplicate "
        f"({stats['distinct']} distinct-recording group(s) left intact), "
        f"{verb} {stats['losers']} loser row(s)."
    )
    for value, canonical_id, loser_ids in stats["examples"]:
        print(f"    {column}={value!r}: keep {canonical_id}, merge {loser_ids}")


def main(apply):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total_before = _total_rows(session)
            print(f"Catalog rows before: {total_before}")

            if not apply:
                print("\n=== DRY-RUN — nothing will be modified (use --apply) ===")
                for column in _DEDUP_COLUMNS:
                    _print_report(
                        column,
                        dedup_by_column(session, column, apply=False),
                        apply=False,
                    )
                session.rollback()
                print(
                    "\nDry-run only. Most beatport id-groups are EP tracks / "
                    "remixes and will NOT merge (only same-recording clusters "
                    "do) — that is expected, not a miss. The beatport figures "
                    "are computed on the pre-merge state and may over-count "
                    "clusters the deezer pass would already collapse — the real "
                    "--apply run re-queries beatport afterwards."
                )
                print(
                    "Re-run with --apply to merge — DUMP PROD FIRST (see "
                    "docs/restore.md)."
                )
                return

            print("\n=== APPLY — merging duplicates (deezer, then beatport) ===")
            for column in _DEDUP_COLUMNS:
                _print_report(
                    column, dedup_by_column(session, column, apply=True), apply=True
                )
            session.commit()

            total_after = _total_rows(session)
            shared = {c: len(_duplicate_values(session, c)) for c in _DEDUP_COLUMNS}
            remaining_mergeable = {
                c: dedup_by_column(session, c, apply=False)["groups"]
                for c in _DEDUP_COLUMNS
            }
            print(
                f"\nCatalog rows after: {total_after} "
                f"(removed {total_before - total_after})"
            )
            print(
                "Remaining mergeable groups: "
                + ", ".join(f"{c}={remaining_mergeable[c]}" for c in _DEDUP_COLUMNS)
                + "  (expected 0)"
            )
            print(
                "Shared-id groups still present (distinct recordings kept apart "
                "by design — remixes, EP tracks): "
                + ", ".join(f"{c}={shared[c]}" for c in _DEDUP_COLUMNS)
            )
            print(
                "\nTrend scores and the similarity cache refresh on the next "
                "nightly run (compute_trends + similarity cache) — no manual "
                "recompute needed."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge same-recording catalog duplicates within shared "
        "platform-id groups (remixes / EP tracks are kept apart)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually merge duplicates (default: dry-run, no changes)",
    )
    args = parser.parse_args()
    main(apply=args.apply)
