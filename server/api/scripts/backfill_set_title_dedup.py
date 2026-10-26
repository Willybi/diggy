"""Backfill set dedup for same-title duplicates the track-overlap path missed.

TrackID hosts duplicate audiostreams of the same show (distinct external_ids).
A duplicate identifying < 3 tracks never became a match_set candidate (the
candidate bar is 3 shared identified tracks), so it stayed a separate root —
inflating trend scores and listings. The title-based candidate path
(set_dedup_service.get_title_candidate_ids, 2026-10) now routes those sets into
the SAME, unchanged decide_verdict at the funnel; this one-shot catches the
EXISTING rows.

Surgical by design: it only touches roots whose normalized_title is shared by
>= 2 non-virtual roots (the affected universe), NOT every set — so it does not
flood the admin flag queue with unrelated track-overlap flags. It reuses
match_set + apply_match_results verbatim, so the attach/flag decision is
identical to the import funnel (no divergent logic) and stays conservative
(invariant #4: a recurring show under the same title on a different reliable
date is left apart).

Usage:
    python scripts/backfill_set_title_dedup.py            # dry-run (default)
    python scripts/backfill_set_title_dedup.py --apply     # commit (DUMP FIRST)

Dry-run resolves the decisions and prints a per-group summary, then rolls back.
Idempotent: an already-attached set is skipped (match_set re-run is a no-op once
the root has a parent).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import SessionLocal
from models import DJSet
from services.set_dedup_service import apply_match_results, match_set
from sqlalchemy import func, select


async def _affected_set_ids(db) -> list[int]:
    """Root ids whose normalized_title is shared by >= 2 non-virtual roots."""
    shared_titles = (
        select(DJSet.normalized_title)
        .where(
            DJSet.is_virtual.is_(False),
            DJSet.parent_set_id.is_(None),
            DJSet.normalized_title.isnot(None),
            DJSet.normalized_title != "",
        )
        .group_by(DJSet.normalized_title)
        .having(func.count() > 1)
    ).subquery()

    rows = (
        await db.execute(
            select(DJSet.id)
            .where(
                DJSet.is_virtual.is_(False),
                DJSet.parent_set_id.is_(None),
                DJSet.normalized_title.in_(select(shared_titles.c.normalized_title)),
            )
            .order_by(DJSet.id)
        )
    ).scalars().all()
    return list(rows)


async def run(apply: bool) -> None:
    async with SessionLocal() as db:
        set_ids = await _affected_set_ids(db)
        print(f"[scope] {len(set_ids)} roots partageant un normalized_title\n")

        total = {"attached": 0, "flagged": 0, "nothing": 0}
        for set_id in set_ids:
            # Re-read: a set attached earlier in this run is now a child → skip.
            fresh = await db.get(DJSet, set_id)
            if fresh is None or fresh.parent_set_id is not None:
                continue
            pair_results, group_results = await match_set(db, set_id)
            if not (pair_results or group_results):
                continue
            counts = await apply_match_results(db, set_id, pair_results, group_results)
            for k in total:
                total[k] += counts.get(k, 0)
            if counts["attached"] or counts["flagged"]:
                print(
                    f"  set {set_id} ({fresh.title[:48]!r}): {counts}"
                )

        print(
            f"\n[résumé] attached={total['attached']} "
            f"flagged={total['flagged']} nothing={total['nothing']}"
        )

        if apply:
            await db.commit()
            print("[apply] Commit effectué.")
        else:
            await db.rollback()
            print("[dry-run] Aucune modification. Relancer avec --apply pour appliquer.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill same-title set dedup (title-candidate path)"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Commit decisions (DUMP PROD FIRST)"
    )
    args = parser.parse_args()
    asyncio.run(run(args.apply))


if __name__ == "__main__":
    main()
