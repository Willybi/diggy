"""C6.1 backfill — re-normalize set titles with the new regex branches.

Fills part_number and part_total for all physical sets that match the
roman-numeral or fraction patterns introduced in C6.1.

Run AFTER alembic upgrade head (migration 0030):
    cd server/api && python scripts/backfill_set_parts.py [--dry-run]
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import SessionLocal
from models import DJSet
from services.set_dedup_service import normalize_set_title
from sqlalchemy import select


async def run(dry_run: bool) -> None:
    async with SessionLocal() as db:
        sets = (
            await db.execute(
                select(DJSet).where(DJSet.is_virtual.is_(False))
            )
        ).scalars().all()

        print(f"[backfill] {len(sets)} sets physiques à traiter")

        updated = 0
        for s in sets:
            result = normalize_set_title(s.title)
            changed = False

            if result.part_number is not None and s.part_number != result.part_number:
                if not dry_run:
                    s.part_number = result.part_number
                    s.normalized_title = result.text
                print(
                    f"  set {s.id:>4}: part_number={result.part_number}"
                    f" | {s.title[:60]!r}"
                )
                changed = True

            if result.part_total is not None and s.part_total != result.part_total:
                if not dry_run:
                    s.part_total = result.part_total
                if not changed:
                    print(f"  set {s.id:>4}: part_total={result.part_total} | {s.title[:60]!r}")
                changed = True

            if changed:
                updated += 1

        if dry_run:
            print(f"\n[dry-run] {updated} set(s) seraient mis à jour. Aucune modification.")
        else:
            await db.commit()
            print(f"\n[backfill] {updated} set(s) mis à jour.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill set parts (C6.1)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without modifying DB"
    )
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
