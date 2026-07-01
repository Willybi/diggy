"""
Discover DJ sets containing a known track via TrackID.net.

Usage (from VPS):
    docker compose exec api python scripts/discover_trackid_sets.py --artist "Adam Beyer" --title "Teach Me"
    docker compose exec api python scripts/discover_trackid_sets.py --catalog-id 42
    docker compose exec api python scripts/discover_trackid_sets.py --catalog-id 42 --max-sets 20
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import CatalogEntry
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from trackid.client import TrackIDClient
from trackid.importer import import_audiostream

DATABASE_URL = os.environ["DATABASE_URL"]


async def main(
    artist: str | None, title: str | None, catalog_id: int | None, max_sets: int
):
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Resolve artist/title from catalog if needed
    if catalog_id:
        async with async_session() as db:
            entry = await db.get(CatalogEntry, catalog_id)
            if not entry:
                print(f"Catalog entry {catalog_id} not found.")
                return
            artist = entry.artist
            title = entry.title
            print(f"Catalog #{catalog_id}: {artist} - {title}")

    if not title:
        print("Error: --title is required (or --catalog-id)")
        return

    total_sets = 0
    total_tracks = 0
    skipped = 0

    async with TrackIDClient() as client:
        # Search for the track on TrackID
        keywords = f"{artist} {title}" if artist else title
        tracks, count = await client.search_tracks(keywords=keywords)

        if not tracks:
            print(f"No track found on TrackID for: {keywords}")
            await engine.dispose()
            return

        # Pick first match
        music_track = tracks[0]
        mtid = music_track["id"]
        print(
            f"Found: {music_track.get('artist', '?')} - {music_track.get('title', '?')} (musicTrackId={mtid})"
        )

        # Find all sets containing this track
        page = 0
        page_size = 20

        while True:
            async with async_session() as db:
                sets, row_count = await client.search_sets(
                    music_track_id=mtid,
                    page_size=page_size,
                    current_page=page,
                )

                if not sets:
                    break

                for audiostream in sets:
                    if total_sets >= max_sets:
                        break

                    dj_set, track_count = await import_audiostream(
                        db, client, audiostream
                    )

                    if dj_set is None:
                        skipped += 1
                        continue

                    total_sets += 1
                    total_tracks += track_count
                    print(f"  [{total_sets}] {dj_set.title} — {track_count} tracks")

                await db.commit()

            if total_sets >= max_sets:
                break

            page += 1
            if page * page_size >= row_count:
                break

    print(
        f"\nDone. Sets imported: {total_sets}, tracks: {total_tracks}, skipped: {skipped}"
    )
    print(f"Total sets on TrackID containing this track: {row_count}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Discover TrackID sets containing a known track"
    )
    parser.add_argument("--artist", default=None, help="Artist name")
    parser.add_argument("--title", default=None, help="Track title")
    parser.add_argument(
        "--catalog-id",
        type=int,
        default=None,
        help="Catalog entry ID (overrides artist/title)",
    )
    parser.add_argument(
        "--max-sets", type=int, default=50, help="Max sets to import (default 50)"
    )
    args = parser.parse_args()
    asyncio.run(main(args.artist, args.title, args.catalog_id, args.max_sets))
