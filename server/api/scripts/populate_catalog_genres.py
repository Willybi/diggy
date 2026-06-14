"""
Script one-shot : peuple la table catalog_genres a partir de catalog.genre et lib_tracks.tags.

Logique :
1. Collecte les genres depuis catalog.genre (28 lignes) et lib_tracks.tags (JSON array).
2. Normalise les noms (casse, tirets, espaces) pour fusionner les doublons.
3. Exclut les tags de workflow (pas des genres musicaux).
4. Cree les genres manquants dans la table genres.
5. Insere les liens dans catalog_genres (sans doublons).

Idempotent et rejouable.

Usage (depuis le VPS) :
    docker compose exec api python scripts/populate_catalog_genres.py
"""
import asyncio
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import CatalogEntry, Genre, LibTrack, catalog_genres

DATABASE_URL = os.environ["DATABASE_URL"]

# Tags de workflow a exclure (pas des genres musicaux)
EXCLUDED_TAGS = {
    "misc. tracks",
    "to_cue",
}

# Mapping de normalisation pour fusionner les variantes connues
GENRE_ALIASES = {
    "nu disco": "Nu Disco",
    "nu-disco": "Nu Disco",
    "electro brut": "Electro Brut",
}


def normalize_genre_name(raw: str) -> str:
    """Normalise un nom de genre pour dedup."""
    stripped = raw.strip()
    lower = stripped.lower()

    # Exclure les tags de workflow
    if lower in EXCLUDED_TAGS:
        return ""

    # Appliquer les alias connus
    if lower in GENRE_ALIASES:
        return GENRE_ALIASES[lower]

    # Sinon garder le nom original avec casse nettoyee (title case du premier mot)
    return stripped


async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # --- Etape 1 : Collecter tous les genres bruts ---
        # catalog_id -> set de noms de genres normalises
        catalog_genre_map: dict[int, set[str]] = {}

        # Source A : catalog.genre
        result = await session.execute(
            select(CatalogEntry.id, CatalogEntry.genre)
            .where(CatalogEntry.genre.isnot(None))
            .where(CatalogEntry.genre != "")
        )
        for catalog_id, genre_str in result.all():
            name = normalize_genre_name(genre_str)
            if name:
                catalog_genre_map.setdefault(catalog_id, set()).add(name)

        # Source B : lib_tracks.tags (JSON array) pour les tracks avec catalog_id
        result = await session.execute(
            select(LibTrack.catalog_id, LibTrack.tags)
            .where(LibTrack.catalog_id.isnot(None))
            .where(LibTrack.tags.isnot(None))
            .where(LibTrack.tags != "")
        )
        for catalog_id, tags_json in result.all():
            try:
                tags = json.loads(tags_json)
            except (json.JSONDecodeError, TypeError):
                continue
            for tag in tags:
                name = normalize_genre_name(tag)
                if name:
                    catalog_genre_map.setdefault(catalog_id, set()).add(name)

        if not catalog_genre_map:
            print("Aucun genre a migrer.")
            return

        # --- Etape 2 : Collecter tous les noms de genres uniques ---
        all_genre_names = set()
        for names in catalog_genre_map.values():
            all_genre_names.update(names)

        print(f"Genres uniques trouves : {len(all_genre_names)}")
        for name in sorted(all_genre_names):
            print(f"  - {name}")

        # --- Etape 3 : Creer les genres manquants ---
        existing = await session.execute(select(Genre.id, Genre.name))
        name_to_id: dict[str, int] = {row.name: row.id for row in existing.all()}

        created = 0
        for name in sorted(all_genre_names):
            if name not in name_to_id:
                genre = Genre(name=name)
                session.add(genre)
                await session.flush()
                name_to_id[name] = genre.id
                created += 1

        print(f"Genres crees : {created}")

        # --- Etape 4 : Inserer les liens catalog_genres ---
        links = []
        for catalog_id, names in catalog_genre_map.items():
            for name in names:
                genre_id = name_to_id.get(name)
                if genre_id:
                    links.append({"catalog_id": catalog_id, "genre_id": genre_id})

        if links:
            stmt = pg_insert(catalog_genres).on_conflict_do_nothing()
            await session.execute(stmt, links)

        await session.commit()

        print(f"Liens catalog_genres inseres : {len(links)} (doublons ignores)")
        print(f"Catalog entries concernees : {len(catalog_genre_map)}")

    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
