"""
Backfill artist_aliases from catalog.artist strings.

For each catalog.artist that matches an artist (via normalized name)
but whose exact string differs, create an ArtistAlias.

Idempotent: skips aliases that already exist (unique constraint on normalized_alias).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from models import Artist, ArtistAlias, CatalogEntry
from utils import normalize

DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
engine = create_engine(DATABASE_URL)


def main():
    with Session(engine) as session:
        # Get all distinct catalog.artist strings
        result = session.execute(
            select(CatalogEntry.artist, func.count(CatalogEntry.id).label("cnt"))
            .group_by(CatalogEntry.artist)
        )
        catalog_names = {row[0]: row[1] for row in result.all() if row[0]}

        # Get all artists with their normalized names
        artists = session.execute(select(Artist)).scalars().all()
        norm_to_artist = {}
        for a in artists:
            norm_to_artist[normalize(a.name)] = a

        # Get existing aliases
        existing_aliases = session.execute(select(ArtistAlias)).scalars().all()
        for alias in existing_aliases:
            norm_to_artist[alias.normalized_alias] = session.get(Artist, alias.artist_id)

        # Existing normalized_alias values (to skip duplicates)
        existing_norms = {a.normalized_alias for a in existing_aliases}

        created = 0
        skipped = 0

        for catalog_name, cnt in sorted(catalog_names.items(), key=lambda x: -x[1]):
            norm = normalize(catalog_name)
            artist = norm_to_artist.get(norm)
            if not artist:
                continue
            # If catalog name differs from artist name, create alias
            if catalog_name.strip() != artist.name.strip():
                if norm in existing_norms:
                    skipped += 1
                    continue
                session.add(ArtistAlias(
                    artist_id=artist.id,
                    alias=catalog_name.strip(),
                    normalized_alias=norm,
                ))
                existing_norms.add(norm)
                created += 1

        session.commit()
        print(f"Done: {created} aliases created, {skipped} skipped (already exist)")


if __name__ == "__main__":
    main()
