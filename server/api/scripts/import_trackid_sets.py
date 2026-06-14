"""
Import DJ sets from TrackID.net by channel or keyword search.

Usage (from VPS):
    docker compose exec api python scripts/import_trackid_sets.py --channel adambeyer
    docker compose exec api python scripts/import_trackid_sets.py --keywords "fred again" --resolve
    docker compose exec api python scripts/import_trackid_sets.py --channel adambeyer --limit 5 --resolve
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from trackid.client import TrackIDClient
from trackid.importer import get_or_create_artist, import_audiostream

DATABASE_URL = os.environ["DATABASE_URL"]


async def main(channel: str | None, keywords: str | None, limit: int | None, resolve: bool):
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_sets = 0
    total_tracks = 0
    skipped = 0
    artist_id = None

    async with TrackIDClient() as client:
        # Create artist only when using --channel
        if channel:
            async with async_session() as db:
                artist = await get_or_create_artist(db, channel, trackid_id=channel)
                await db.commit()
                artist_id = artist.id

        # Paginate through sets
        page = 0
        page_size = 20

        while True:
            async with async_session() as db:
                sets, row_count = await client.search_sets(
                    channel=channel,
                    keywords=keywords,
                    page_size=page_size,
                    current_page=page,
                    sort_field="addedOn",
                    sort_direction="desc",
                )

                if not sets:
                    break

                if page == 0:
                    print(f"Found {row_count} sets on TrackID.")

                for audiostream in sets:
                    if limit is not None and total_sets >= limit:
                        break

                    dj_set, track_count = await import_audiostream(
                        db, client, audiostream, artist_id=artist_id
                    )

                    if dj_set is None:
                        skipped += 1
                        continue

                    total_sets += 1
                    total_tracks += track_count
                    print(f"  [{total_sets}] {dj_set.title} — {track_count} tracks")

                await db.commit()

            if limit is not None and total_sets >= limit:
                break

            page += 1
            if page * page_size >= row_count:
                break

    print(f"\nDone. Sets imported: {total_sets}, tracks: {total_tracks}, skipped: {skipped}")

    if resolve:
        print("\nResolving set_tracks -> catalog...")
        resolved, created = await _resolve_set_tracks(engine)
        print(f"Resolved: {resolved}, new catalog entries: {created}")

    await engine.dispose()


async def _resolve_set_tracks(engine):
    """Inline async version of resolve_set_tracks Celery task."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from models import SetTrack, CatalogEntry
    from utils import make_normalized_key

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    resolved = 0
    created = 0

    async with async_session() as db:
        result = await db.execute(
            select(SetTrack).where(
                SetTrack.catalog_id.is_(None),
                SetTrack.is_id == False,  # noqa: E712
                SetTrack.raw_title.isnot(None),
            )
        )
        tracks = result.scalars().all()

        for st in tracks:
            norm_key = make_normalized_key(st.raw_title, st.raw_artist)

            entry = (await db.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
            )).scalar_one_or_none()

            if not entry:
                entry = CatalogEntry(
                    title=st.raw_title,
                    artist=st.raw_artist,
                    normalized_key=norm_key,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(entry)
                await db.flush()
                created += 1

            st.catalog_id = entry.id
            resolved += 1

        await db.commit()

    return resolved, created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import TrackID.net sets by channel or keywords")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", help="TrackID channel name (e.g. adambeyer)")
    group.add_argument("--keywords", help="Search by keywords (e.g. 'fred again')")
    parser.add_argument("--limit", type=int, default=None, help="Max number of sets to import")
    parser.add_argument("--resolve", action="store_true", help="Resolve set_tracks to catalog after import")
    args = parser.parse_args()
    asyncio.run(main(args.channel, args.keywords, args.limit, args.resolve))
