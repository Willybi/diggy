"""
One-shot catch-up script: promotes to 'shared' the private tracks
already confirmed by an official source (Deezer or Beatport).

Replays in the database the private → shared promotion that was lost in the
async enrichment pipeline (A3-01, then Lot A for Beatport). Any track whose
scope is still 'private' while carrying a valid deezer_id OR a beatport_id
should have been promoted — a match on either platform confirms the track
exists on an official source.

    UPDATE catalog
       SET scope = 'shared', owner_id = NULL
     WHERE scope = 'private'
       AND (
             (deezer_id IS NOT NULL AND deezer_id != 'NOT_FOUND')
          OR beatport_id IS NOT NULL
       )

Note: catalog.beatport_id has no 'NOT_FOUND' sentinel (that sentinel lives on
artists.deezer_id), so a non-NULL beatport_id always means a confirmed match.

Run ONCE on prod, after the enrichment fix has been deployed.
Not idempotency-critical: the WHERE only targets rows still 'private',
so a re-run has no effect — but that is no reason to run it again.

Usage:
    docker compose exec api python scripts/promote_private_shared.py
    docker compose exec api python scripts/promote_private_shared.py --dry-run
"""

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_WHERE = (
    "scope = 'private' "
    "AND ("
    "(deezer_id IS NOT NULL AND deezer_id != 'NOT_FOUND') "
    "OR beatport_id IS NOT NULL"
    ")"
)


async def main(dry_run: bool):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            count = (
                await db.execute(text(f"SELECT COUNT(*) FROM catalog WHERE {_WHERE}"))
            ).scalar_one()
            print(f"{count} private tracks confirmed by Deezer/Beatport to promote.")

            if dry_run:
                print("--dry-run: no changes applied.")
                return

            if count:
                await db.execute(
                    text(
                        f"UPDATE catalog SET scope = 'shared', owner_id = NULL "
                        f"WHERE {_WHERE}"
                    )
                )
                await db.commit()

            print(f"Done: {count} tracks promoted to 'shared'.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="count without modifying the database"
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
