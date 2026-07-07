"""Audit set deduplication on existing sets (dry-run by default).

Usage:
    python audit_set_dedup.py [--apply]

Without --apply: prints a report of proposed groupings without modifying DB.
With --apply: executes AUTO_ATTACH and FLAG insertions.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import SessionLocal
from models import DJSet
from services.set_dedup_service import (
    MatchVerdict,
    apply_match_results,
    backfill_normalized_titles,
    match_set,
)
from sqlalchemy import select


async def run(apply: bool) -> None:
    async with SessionLocal() as db:
        # 1. Backfill normalized_title on all existing sets
        n = await backfill_normalized_titles(db)
        print(f"[backfill] {n} normalized_title(s) remplis")

        # 2. Load all physical sets without a parent
        sets = (
            await db.execute(
                select(DJSet)
                .where(DJSet.is_virtual.is_(False), DJSet.parent_set_id.is_(None))
                .order_by(DJSet.id)
            )
        ).scalars().all()

        print(f"\n[audit] {len(sets)} sets physiques à analyser\n")

        total_auto = 0
        total_flag = 0
        total_nothing = 0
        seen_pairs: set[tuple[int, int]] = set()

        seen_groups: set[str] = set()

        for dj_set in sets:
            pair_results, group_results = await match_set(db, dj_set.id)

            for r in pair_results:
                pair = (min(dj_set.id, r.candidate_id), max(dj_set.id, r.candidate_id))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                verdict_label = {
                    MatchVerdict.AUTO_ATTACH: "AUTO_ATTACH",
                    MatchVerdict.FLAG: "FLAG        ",
                    MatchVerdict.NOTHING: "NOTHING     ",
                }[r.verdict]

                print(
                    f"  {verdict_label} | sets ({dj_set.id:>3}, {r.candidate_id:>3}) "
                    f"| overlap={r.signals.overlap:.2f} "
                    f"title={r.signals.title_sim:.2f} "
                    f"date={'Y' if r.signals.date_match else 'N'} "
                    f"| {dj_set.title[:40]!r} <-> {r.candidate_id}"
                )

                if r.verdict == MatchVerdict.AUTO_ATTACH:
                    total_auto += 1
                elif r.verdict == MatchVerdict.FLAG:
                    total_flag += 1
                else:
                    total_nothing += 1

            for gr in group_results:
                if gr.group_key in seen_groups:
                    continue
                seen_groups.add(gr.group_key)
                print(
                    f"  PART_FLAG   | group={gr.group_key!r} "
                    f"members={gr.member_set_ids} "
                    f"conf={gr.confidence:.2f} type={gr.flag_type}"
                )
                total_flag += 1

        print(
            f"\n[résumé] AUTO_ATTACH={total_auto} FLAG={total_flag} NOTHING={total_nothing}"
        )

        if apply:
            print("\n[apply] Application des décisions...")
            seen_pairs.clear()
            for dj_set in sets:
                fresh = await db.get(DJSet, dj_set.id)
                if fresh is None or fresh.parent_set_id is not None:
                    continue
                pair_results, group_results = await match_set(db, dj_set.id)
                if pair_results or group_results:
                    counts = await apply_match_results(
                        db, dj_set.id, pair_results, group_results
                    )
                    if counts["attached"] or counts["flagged"]:
                        print(f"  set {dj_set.id}: {counts}")
            await db.commit()
            print("[apply] Terminé.")
        else:
            print(
                "\n[dry-run] Aucune modification. Relancer avec --apply pour appliquer."
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit set deduplication")
    parser.add_argument("--apply", action="store_true", help="Apply decisions to DB")
    args = parser.parse_args()
    asyncio.run(run(args.apply))


if __name__ == "__main__":
    main()
