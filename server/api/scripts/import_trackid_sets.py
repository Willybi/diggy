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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # server/

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from trackid.client import TrackIDClient
from trackid.importer import get_or_create_artist, import_audiostream

DATABASE_URL = os.environ["DATABASE_URL"]


def _humanize_slug(slug: str) -> str:
    """Convert 'adambeyer' → 'Adambeyer' as fallback display name."""
    return slug.strip().title() if slug else slug


def _extract_artist_name(detail: dict, channel: str) -> str | None:
    """Try to extract a proper artist name from set title.

    TrackID set titles often contain the artist name, e.g.:
    'DCR827 – Drumcode Radio Live - Adam Beyer live from ...'
    We look for a substring that normalizes to the channel slug.
    """
    title = detail.get("title", "")
    # Split on common separators
    for sep in [" - ", " – ", " — ", " | "]:
        parts = title.split(sep)
        for part in parts:
            candidate = part.strip()
            # Check if removing spaces/lowering matches the channel
            if re.sub(r"\s+", "", candidate.lower()) == channel.lower():
                return candidate
    return None


async def main(
    channel: str | None, keywords: str | None, limit: int | None, resolve: bool
):
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_sets = 0
    total_tracks = 0
    skipped = 0
    artist_id = None

    async with TrackIDClient() as client:
        # Create artist only when using --channel
        if channel:
            # Fetch one set to extract a proper display name from tracklist artist credits
            display_name = _humanize_slug(channel)
            probe_sets, _ = await client.search_sets(
                channel=channel, page_size=1, current_page=0
            )
            if probe_sets:
                detail = await client.get_set_detail(probe_sets[0].get("slug", ""))
                if detail:
                    extracted = _extract_artist_name(detail, channel)
                    if extracted:
                        display_name = extracted

            async with async_session() as db:
                artist = await get_or_create_artist(
                    db, display_name, trackid_id=channel
                )
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

    print(
        f"\nDone. Sets imported: {total_sets}, tracks: {total_tracks}, skipped: {skipped}"
    )

    if resolve:
        print("\nResolving set_tracks -> catalog...")
        resolved, created = await _resolve_set_tracks(engine)
        print(f"Resolved: {resolved}, new catalog entries: {created}")

    await engine.dispose()


async def _resolve_set_tracks(engine):
    """Inline async version of resolve_set_tracks Celery task with Deezer enrichment."""
    from datetime import datetime, timezone

    from models import CatalogEntry, SetTrack
    from services.image_service import ImageService
    from sqlalchemy import select
    from utils import make_normalized_key
    from workers.deezer_enrich import enrich_entry, search_deezer

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ImageService.ensure_bucket("catalog-artworks")

    resolved = 0
    created = 0
    enriched = 0

    async with async_session() as db:
        # Preload ISRCs to avoid unique constraint violations
        isrc_result = await db.execute(
            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
        )
        known_isrcs = {r[0] for r in isrc_result.all()}

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

            entry = (
                await db.execute(
                    select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
                )
            ).scalar_one_or_none()

            is_new = False
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
                is_new = True

            st.catalog_id = entry.id
            resolved += 1

            # Enrich new entries or entries missing deezer_id
            if is_new or not entry.deezer_id:
                hit = search_deezer(st.raw_artist, st.raw_title)
                if hit and enrich_entry(entry, hit, s3=None, _known_isrcs=known_isrcs):
                    enriched += 1
                    print(f"    enriched: {st.raw_artist} — {st.raw_title}")
                await asyncio.sleep(0.12)

        await db.commit()

    return resolved, created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import TrackID.net sets by channel or keywords"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", help="TrackID channel name (e.g. adambeyer)")
    group.add_argument("--keywords", help="Search by keywords (e.g. 'fred again')")
    parser.add_argument(
        "--limit", type=int, default=None, help="Max number of sets to import"
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Resolve set_tracks to catalog after import",
    )
    args = parser.parse_args()
    asyncio.run(main(args.channel, args.keywords, args.limit, args.resolve))
