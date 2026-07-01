"""
Script one-shot : remplit deezer_id sur les entrées catalog qui n'en ont pas
mais ont has_preview=true et pas de radar_track lié.

Usage :
    docker compose exec api python scripts/backfill_deezer_id.py
"""

import asyncio
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import CatalogEntry, RadarTrack
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
DEEZER_SEARCH = "https://api.deezer.com/search"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Entrées sans deezer_id, sans radar_track Deezer
        result = await db.execute(
            select(CatalogEntry).where(CatalogEntry.deezer_id.is_(None))
        )
        entries = result.scalars().all()

        # Filtre : celles sans radar_track deezer
        to_fill = []
        for entry in entries:
            r = await db.execute(
                select(RadarTrack.id)
                .where(RadarTrack.catalog_id == entry.id)
                .where(RadarTrack.source == "deezer")
                .limit(1)
            )
            if not r.first():
                to_fill.append(entry)

        print(f"{len(to_fill)} entrées catalog à backfiller")

        filled = 0
        not_found = 0

        async with httpx.AsyncClient(timeout=10) as client:
            for i, entry in enumerate(to_fill):
                try:
                    resp = await client.get(
                        DEEZER_SEARCH,
                        params={
                            "q": f'artist:"{entry.artist}" track:"{entry.title}"',
                            "limit": 1,
                        },
                    )
                    data = resp.json()
                    hits = data.get("data", [])
                    if not hits:
                        resp2 = await client.get(
                            DEEZER_SEARCH,
                            params={"q": f"{entry.artist} {entry.title}", "limit": 1},
                        )
                        hits = resp2.json().get("data", [])
                except Exception as e:
                    print(f"  ERREUR: {entry.artist} — {entry.title}: {e}")
                    not_found += 1
                    continue

                if hits:
                    entry.deezer_id = str(hits[0]["id"])
                    entry.has_preview = bool(hits[0].get("preview", "").strip())
                    filled += 1
                else:
                    entry.has_preview = False  # plus de preview, on corrige
                    not_found += 1

                time.sleep(0.05)

                if i % 100 == 0:
                    print(f"  [{i}/{len(to_fill)}] en cours…")
                    await db.commit()

        await db.commit()
        print(
            f"\nTerminé : {filled} deezer_id remplis, {not_found} non trouvés (has_preview mis à false)"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
