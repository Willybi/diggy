"""
One-shot script: fix artist names that are stored as slugs (e.g. 'adambeyer' -> 'Adam Beyer').

Looks at catalog.artist to find the proper display name for each artist whose
name looks like a slug (no spaces, no uppercase).

Usage (from VPS):
    docker compose exec api python scripts/fix_artist_names.py
    docker compose exec api python scripts/fix_artist_names.py --dry-run
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Artist, CatalogEntry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]


def _is_slug(name: str) -> bool:
    """True if name looks like a slug (all lowercase, no spaces)."""
    return name == name.lower() and " " not in name


async def main(dry_run: bool):
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(select(Artist))
        artists = result.scalars().all()

        fixed = 0
        for artist in artists:
            if not _is_slug(artist.name):
                continue

            # Try to find a proper name in catalog.artist
            catalog_norm = func.replace(func.lower(CatalogEntry.artist), " ", "")
            cat_result = await db.execute(
                select(CatalogEntry.artist)
                .where(catalog_norm == artist.normalized_name)
                .limit(1)
            )
            cat_name = cat_result.scalar_one_or_none()

            if cat_name and cat_name != artist.name:
                print(f"  {artist.name} -> {cat_name}")
                if not dry_run:
                    artist.name = cat_name
                fixed += 1
            else:
                print(f"  {artist.name} -> (no match in catalog)")

        if not dry_run:
            await db.commit()

    print(f"\n{'Would fix' if dry_run else 'Fixed'}: {fixed} artists")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix artist names stored as slugs")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show changes without applying"
    )
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
