#!/usr/bin/env python
"""One-shot cleanup: merge EXISTING catalog duplicates sharing a platform id.

Ingestion dedups on ``normalized_key``/``isrc`` but never on the platform ids,
so the same track can land in ``catalog`` twice (~1934 rows, X1). This script
folds every group of rows sharing a non-NULL ``deezer_id`` (then ``beatport_id``)
down to a single canonical row, using the L1 primitive
``workers.catalog_merge.merge_catalog_entries`` (which repoints every FK — incl.
the ON DELETE RESTRICT ``user_tracks`` — before deleting the loser). The row to
keep per group is chosen deterministically by ``pick_canonical``.

Deezer is processed FIRST and committed, THEN beatport is re-queried on the
up-to-date state: a deezer merge may already have united rows that also shared a
beatport_id, so re-querying avoids ever touching an already-deleted row.

>>> DESTRUCTIVE (deletes rows). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
whole operation is idempotent — a re-run finds the remaining groups), but a bad
dump is not recoverable.

The run is DRY-RUN by default: it prints the number of groups, how many rows
would be removed, and a few examples, WITHOUT modifying anything. Pass --apply to
actually merge. A second --apply run is idempotent (finds 0 group).

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
from workers.catalog_merge import merge_catalog_entries, pick_canonical

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


def dedup_by_column(
    session, column, *, apply=False, commit_every=_COMMIT_EVERY, max_examples=5
):
    """Merge every group of catalog rows sharing the same non-NULL ``column``.

    For each duplicate group ``pick_canonical`` picks the row to keep and the
    others are folded in with ``merge_catalog_entries``. The value list is
    snapshotted once for THIS column, but the rows of each group are re-loaded
    fresh and groups an earlier pass already collapsed (``len(rows) < 2``) are
    skipped — so running this for ``beatport_id`` AFTER the ``deezer_id`` pass
    never touches a deleted row.

    apply=False (default) is read-only: nothing is committed and the returned
    counts describe what WOULD happen. In --apply mode the work is committed
    every ``commit_every`` groups (plus a trailing commit).

    Returns ``{"groups", "losers", "deleted", "examples"}`` where ``examples`` is
    a list of ``(value, canonical_id, [loser_id, ...])``.
    """
    col = getattr(CatalogEntry, column)
    dup_values = _duplicate_values(session, column)

    groups = losers = deleted = 0
    examples = []
    pending = 0

    for value in dup_values:
        rows = session.execute(select(CatalogEntry).where(col == value)).scalars().all()
        if len(rows) < 2:
            continue  # already collapsed by a previous pass
        groups += 1
        canonical = pick_canonical(rows)
        loser_ids = [r.id for r in rows if r.id != canonical.id]
        losers += len(loser_ids)
        if len(examples) < max_examples:
            examples.append((value, canonical.id, loser_ids))

        if apply:
            for loser_id in loser_ids:
                merge_catalog_entries(session, canonical.id, loser_id)
                deleted += 1
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "groups": groups,
        "losers": losers,
        "deleted": deleted,
        "examples": examples,
    }


def _total_rows(session):
    return session.execute(select(func.count()).select_from(CatalogEntry)).scalar_one()


def _print_report(column, stats, apply):
    verb = "merged" if apply else "would merge"
    print(
        f"\n[{column}] {stats['groups']} duplicate group(s), "
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
                    "\nDry-run only. The beatport figures are computed on the "
                    "pre-merge state and may over-count groups the deezer pass "
                    "would already collapse — the real --apply run re-queries "
                    "beatport afterwards."
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
            left = {c: len(_duplicate_values(session, c)) for c in _DEDUP_COLUMNS}
            print(
                f"\nCatalog rows after: {total_after} "
                f"(removed {total_before - total_after})"
            )
            print(
                "Remaining duplicate groups: "
                + ", ".join(f"{c}={left[c]}" for c in _DEDUP_COLUMNS)
                + "  (expected 0)"
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
        description="Merge existing catalog duplicates sharing a platform id"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually merge duplicates (default: dry-run, no changes)",
    )
    args = parser.parse_args()
    main(apply=args.apply)
