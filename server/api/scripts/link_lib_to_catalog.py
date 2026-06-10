"""
Script one-shot : lie les lib_tracks sans catalog_id à une entrée catalog.

Stratégie :
1. Cherche une entrée catalog existante par normalized_key (titre+artiste normalisés)
2. Si absent, interroge l'API Deezer search pour trouver le track et crée l'entrée catalog
3. Met à jour lib_track.catalog_id

Usage (depuis le VPS) :
    docker compose exec api python scripts/link_lib_to_catalog.py
"""
import asyncio
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from models import CatalogEntry, LibTrack
from utils import make_normalized_key

DATABASE_URL = os.environ["DATABASE_URL"]

DEEZER_SEARCH = "https://api.deezer.com/search"


def _parse_date(s):
    if not s or s == "0000-00-00":
        return None
    try:
        from datetime import date
        return date.fromisoformat(s)
    except Exception:
        return None


async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(
            select(LibTrack).where(LibTrack.catalog_id.is_(None))
        )
        tracks = result.scalars().all()
        # Exclure les faux tracks rekordbox (playlists vides)
        tracks = [t for t in tracks if t.artist and t.artist.lower() != "rekordbox" and t.title]
        print(f"{len(tracks)} lib_tracks à lier")

        matched_existing = 0
        created = 0
        not_found = 0

        async with httpx.AsyncClient(timeout=10) as client:
            for i, lt in enumerate(tracks):
                norm_key = make_normalized_key(lt.title, lt.artist)

                # 1. Cherche dans catalog par normalized_key
                r = await db.execute(
                    select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
                )
                entry = r.scalar_one_or_none()

                if entry:
                    lt.catalog_id = entry.id
                    matched_existing += 1
                    continue

                # 2. Cherche sur Deezer
                try:
                    resp = await client.get(
                        DEEZER_SEARCH,
                        params={"q": f'artist:"{lt.artist}" track:"{lt.title}"', "limit": 1},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    print(f"  ERREUR Deezer pour '{lt.title}' — {lt.artist}: {e}")
                    not_found += 1
                    continue

                hits = data.get("data", [])
                if not hits:
                    # Retry sans guillemets
                    try:
                        resp = await client.get(
                            DEEZER_SEARCH,
                            params={"q": f"{lt.artist} {lt.title}", "limit": 1},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        hits = data.get("data", [])
                    except Exception:
                        pass

                if not hits:
                    not_found += 1
                    if i % 50 == 0:
                        print(f"  [{i}/{len(tracks)}] NOT FOUND: {lt.artist} — {lt.title}")
                    continue

                hit = hits[0]
                dz_title = hit.get("title", "")
                dz_artist = hit.get("artist", {}).get("name", "")
                dz_isrc = hit.get("isrc", "")
                dz_bpm = hit.get("bpm") or None
                dz_duration = hit.get("duration")
                dz_preview = hit.get("preview", "").strip() or None

                # Vérifie si l'ISRC existe déjà
                if dz_isrc:
                    r = await db.execute(
                        select(CatalogEntry).where(CatalogEntry.isrc == dz_isrc)
                    )
                    entry = r.scalar_one_or_none()
                    if entry:
                        lt.catalog_id = entry.id
                        matched_existing += 1
                        continue

                # Vérifie normalized_key du résultat Deezer
                dz_norm = make_normalized_key(dz_title, dz_artist)
                r = await db.execute(
                    select(CatalogEntry).where(CatalogEntry.normalized_key == dz_norm)
                )
                entry = r.scalar_one_or_none()
                if entry:
                    lt.catalog_id = entry.id
                    matched_existing += 1
                    continue

                # Crée l'entrée catalog
                album = hit.get("album", {})
                release_date = _parse_date(album.get("release_date", ""))

                entry = CatalogEntry(
                    title=dz_title,
                    artist=dz_artist,
                    normalized_key=dz_norm,
                    isrc=dz_isrc or None,
                    bpm=float(dz_bpm) if dz_bpm else None,
                    duration_ms=dz_duration * 1000 if dz_duration else None,
                    release_date=release_date,
                    has_preview=bool(dz_preview),
                )
                db.add(entry)
                await db.flush()
                lt.catalog_id = entry.id
                created += 1

                # Rate limit doux
                time.sleep(0.05)

                if i % 50 == 0:
                    print(f"  [{i}/{len(tracks)}] en cours…")
                    await db.commit()

        await db.commit()
        print(f"\nTerminé : {matched_existing} matchés existants, {created} créés, {not_found} non trouvés")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
