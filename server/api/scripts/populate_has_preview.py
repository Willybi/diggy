"""
Peuple has_preview dans la table catalog en checkant l'API Deezer.
Met has_preview=True si Deezer retourne une preview non vide, False sinon.

Usage :
    docker compose exec api python scripts/populate_has_preview.py
    docker compose exec api python scripts/populate_has_preview.py --limit 10
"""

import argparse
import asyncio
import os
import sys

import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from models import CatalogEntry, RadarTrack

DEEZER_API = "https://api.deezer.com"


def check_preview(deezer_track_id: str) -> bool:
    try:
        r = requests.get(f"{DEEZER_API}/track/{deezer_track_id}", timeout=10)
        r.raise_for_status()
        return bool(r.json().get("preview", "").strip())
    except Exception:
        return False


async def run(limit: int | None):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        q = select(CatalogEntry)
        if limit:
            q = q.limit(limit)
        result = await db.execute(q)
        entries = result.scalars().all()

    print(f"{len(entries)} entrées à traiter.")
    ok = skipped = 0

    async with async_session() as db:
        for entry in entries:
            r = await db.execute(
                select(RadarTrack.external_track_id)
                .where(RadarTrack.catalog_id == entry.id)
                .where(RadarTrack.source == "deezer")
                .limit(1)
            )
            row = r.first()
            if not row:
                skipped += 1
                continue

            entry.has_preview = check_preview(row[0])
            db.add(entry)
            ok += 1

            if ok % 100 == 0:
                await db.commit()
                print(f"  {ok} traités…")

            await asyncio.sleep(0.15)

        await db.commit()

    print(f"\nTerminé — traités: {ok}, sans source Deezer: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit))
