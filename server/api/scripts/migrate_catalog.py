"""
Script one-shot : peuple la table catalog depuis les radar_tracks et lib_tracks existants.

Usage (depuis le VPS) :
    docker compose exec api python scripts/migrate_catalog.py
"""
import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from models import Base, CatalogEntry, LibTrack, RadarTrack
from utils import make_normalized_key

DATABASE_URL = os.environ["DATABASE_URL"]


async def migrate():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # --- 1. Peuple catalog depuis radar_tracks ---
        result = await db.execute(select(RadarTrack).where(RadarTrack.catalog_id.is_(None)))
        radar_tracks = result.scalars().all()
        print(f"radar_tracks sans catalog_id : {len(radar_tracks)}")

        for rt in radar_tracks:
            norm_key = make_normalized_key(rt.title, rt.artist)

            # Cherche par ISRC
            entry = None
            if rt.isrc:
                r = await db.execute(select(CatalogEntry).where(CatalogEntry.isrc == rt.isrc))
                entry = r.scalar_one_or_none()

            # Cherche par normalized_key
            if not entry:
                r = await db.execute(
                    select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
                )
                entry = r.scalar_one_or_none()

            # Crée si absent
            if not entry:
                entry = CatalogEntry(
                    title=rt.title,
                    artist=rt.artist,
                    normalized_key=norm_key,
                    isrc=rt.isrc or None,
                )
                db.add(entry)
                await db.flush()

            rt.catalog_id = entry.id

        await db.commit()
        print("radar_tracks migrés.")

        # --- 2. Lie lib_tracks au catalog par normalized_key ---
        result = await db.execute(select(LibTrack).where(LibTrack.catalog_id.is_(None)))
        lib_tracks = result.scalars().all()
        print(f"lib_tracks sans catalog_id : {len(lib_tracks)}")

        matched = 0
        for lt in lib_tracks:
            norm_key = make_normalized_key(lt.title, lt.artist)
            r = await db.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
            )
            entry = r.scalar_one_or_none()
            if entry:
                lt.catalog_id = entry.id
                # Sync genre depuis les tags RB (priorité lib)
                if lt.tags:
                    try:
                        tags = json.loads(lt.tags)
                        style_tags = [t for t in tags if not t.startswith("TO_")]
                        if style_tags:
                            entry.genre = style_tags[0]
                    except Exception:
                        pass
                matched += 1

        await db.commit()
        print(f"lib_tracks liés au catalog : {matched}/{len(lib_tracks)}")

    await engine.dispose()
    print("Migration terminée.")


if __name__ == "__main__":
    asyncio.run(migrate())
