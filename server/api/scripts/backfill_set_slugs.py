"""One-shot: backfill external_slug for existing TrackID sets."""
import asyncio
import sys
sys.path.insert(0, "/app")

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

from models import DJSet

TRACKID_API = "https://trackid.net/api/public/audiostreams"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://trackid.net",
    "Referer": "https://trackid.net/",
}


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = sessionmaker(engine, class_=AsyncSession)

    async with Session() as db:
        result = await db.execute(
            select(DJSet).where(
                DJSet.source == "trackid",
                DJSet.external_slug.is_(None),
            )
        )
        sets = result.scalars().all()
        print(f"{len(sets)} sets without slug")

        updated = 0
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            for s in sets:
                try:
                    # Search by title keywords to find the slug
                    keywords = s.title[:40] if s.title else ""
                    r = await client.get(TRACKID_API, params={
                        "keywords": keywords,
                        "pageSize": 10,
                    })
                    data = r.json().get("result", {}).get("audiostreams", [])

                    slug = None
                    for item in data:
                        if str(item.get("id")) == s.external_id:
                            slug = item.get("slug")
                            break

                    if slug:
                        s.external_slug = slug
                        updated += 1
                        print(f"  OK: {s.title[:50]} -> {slug[:40]}")
                    else:
                        print(f"  SKIP: {s.title[:50]} (not found in search)")

                    await asyncio.sleep(1.1)
                except Exception as e:
                    print(f"  ERR: {s.title[:50]} — {e}")

        await db.commit()
        print(f"\nDone: {updated}/{len(sets)} slugs found")

    await engine.dispose()

asyncio.run(main())
