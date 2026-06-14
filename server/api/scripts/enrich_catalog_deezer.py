"""
Enrich catalog entries with Deezer data (deezer_id, isrc, duration, preview, cover).

Targets entries missing deezer_id, or optionally all entries with --force.
Rate-limited to stay under Deezer's free API limits.

Usage (from VPS):
    docker compose exec api python scripts/enrich_catalog_deezer.py
    docker compose exec api python scripts/enrich_catalog_deezer.py --dry-run
    docker compose exec api python scripts/enrich_catalog_deezer.py --limit 50
    docker compose exec api python scripts/enrich_catalog_deezer.py --force
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from models import CatalogEntry
from deezer_enrich import search_deezer, enrich_entry, _get_s3, _ensure_bucket

DATABASE_URL = os.environ["DATABASE_URL"]


async def main(dry_run: bool, limit: int | None, force: bool):
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    s3 = None
    if not dry_run:
        s3 = _get_s3()
        _ensure_bucket(s3)

    async with async_session() as db:
        q = select(CatalogEntry)
        if not force:
            q = q.where(CatalogEntry.deezer_id.is_(None))
        q = q.order_by(CatalogEntry.id)
        if limit:
            q = q.limit(limit)

        result = await db.execute(q)
        entries = result.scalars().all()

    print(f"{len(entries)} entries to process.")

    enriched = 0
    not_found = 0
    errors = 0

    async with async_session() as db:
        for i, entry in enumerate(entries):
            # Re-attach to session
            entry = await db.get(CatalogEntry, entry.id)

            try:
                hit = search_deezer(entry.artist, entry.title)
            except Exception as e:
                print(f"  ERROR [{entry.id}] {entry.artist} — {entry.title}: {e}")
                errors += 1
                time.sleep(0.5)
                continue

            if not hit:
                not_found += 1
                if dry_run:
                    print(f"  [{entry.id}] {entry.artist} — {entry.title} -> NOT FOUND")
            else:
                if dry_run:
                    print(f"  [{entry.id}] {entry.artist} — {entry.title} -> deezer:{hit['id']}, "
                          f"isrc:{hit.get('isrc', '?')}, dur:{hit.get('duration', '?')}s, "
                          f"preview:{'yes' if hit.get('preview') else 'no'}")
                    enriched += 1
                else:
                    if enrich_entry(entry, hit, s3=s3):
                        enriched += 1

            time.sleep(0.12)

            if not dry_run and (i + 1) % 100 == 0:
                await db.commit()
                print(f"  [{i + 1}/{len(entries)}] {enriched} enriched so far...")

        if not dry_run:
            await db.commit()

    action = "Would enrich" if dry_run else "Enriched"
    print(f"\nDone. {action}: {enriched}, not found: {not_found}, errors: {errors}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich catalog entries with Deezer data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    parser.add_argument("--limit", type=int, default=None, help="Max entries to process")
    parser.add_argument("--force", action="store_true", help="Re-check all entries, not just missing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run, args.limit, args.force))
