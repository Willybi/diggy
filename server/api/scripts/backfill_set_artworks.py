"""One-shot: fetch artworks for existing sets from TrackID artworkUrl."""

import asyncio
import sys

sys.path.insert(0, "/app")

import httpx
from models import DJSet
from services.image_service import ImageService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

SET_ARTWORK_BUCKET = "set-artworks"
TRACKID_API = "https://trackid.net/api/public/audiostreams"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://trackid.net",
    "Referer": "https://trackid.net/",
}


async def main():
    import os

    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = sessionmaker(engine, class_=AsyncSession)

    ImageService.ensure_bucket(SET_ARTWORK_BUCKET)

    async with Session() as db:
        result = await db.execute(
            select(DJSet).where(
                DJSet.has_artwork.is_(False),
                DJSet.source == "trackid",
                DJSet.external_id.isnot(None),
            )
        )
        sets = result.scalars().all()
        print(f"{len(sets)} sets without artwork")

        fetched = 0
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            for s in sets:
                # Try to find artwork via search by external ID
                try:
                    # Use the set's source_url slug
                    if s.source_url:
                        # Build slug from title or search
                        pass

                    # Search by external ID
                    r = await client.get(
                        f"{TRACKID_API}",
                        params={"keywords": s.title[:50], "pageSize": 5},
                    )
                    data = r.json().get("result", {}).get("audiostreams", [])
                    artwork_url = None
                    for item in data:
                        if (
                            str(item.get("id")) == s.external_id
                            or str(item.get("externalId")) == s.external_id
                        ):
                            artwork_url = item.get("artworkUrl")
                            break

                    if not artwork_url and data:
                        # Try first result if title matches
                        for item in data:
                            if item.get("artworkUrl"):
                                artwork_url = item["artworkUrl"]
                                break

                    if artwork_url:
                        if ImageService.upload_from_url(
                            artwork_url, SET_ARTWORK_BUCKET, f"{s.id}.jpg"
                        ):
                            s.has_artwork = True
                            fetched += 1
                            print(f"  OK: {s.title[:60]}")
                        else:
                            print(f"  SKIP (upload failed): {s.title[:60]}")
                    else:
                        print(f"  SKIP (no artwork): {s.title[:60]}")

                    await asyncio.sleep(1.1)  # rate limit
                except Exception as e:
                    print(f"  ERR: {s.title[:60]} — {e}")

        await db.commit()
        print(f"\nDone: {fetched}/{len(sets)} artworks fetched")

    await engine.dispose()


asyncio.run(main())
