"""
Celery tasks for DJ set track resolution and enrichment.
"""

import asyncio
import logging
import os
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.resolve_set_tracks",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def resolve_set_tracks(self):
    """
    Résout les set_tracks sans catalog_id.
    Uses bulk catalog operations + concurrent async enrichment.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry, SetTrack
    from services.image_service import BUCKET_CATALOG, ImageService
    from workers.crawl_logger import CrawlLogger
    from workers.db import bulk_get_or_create_catalog, get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session, task_type="resolve_set_tracks", celery_task_id=self.request.id
        ) as clog:
            resolved = 0

            with Session(engine) as session:
                tracks = (
                    session.execute(
                        select(SetTrack).where(
                            SetTrack.catalog_id.is_(None),
                            SetTrack.is_id == False,  # noqa: E712
                            SetTrack.raw_title.isnot(None),
                        )
                    )
                    .scalars()
                    .all()
                )

                if not tracks:
                    clog.set_stats({"resolved": 0, "enriched": 0, "bp_enriched": 0})
                    return {"resolved": 0, "enriched": 0, "bp_enriched": 0}

                # Bulk catalog lookup/create
                track_dicts = [
                    {"title": st.raw_title, "artist": st.raw_artist} for st in tracks
                ]
                catalog_map = bulk_get_or_create_catalog(session, track_dicts)

                from utils import make_normalized_key

                for st in tracks:
                    nk = make_normalized_key(st.raw_title, st.raw_artist)
                    entry = catalog_map.get(nk)
                    if entry:
                        st.catalog_id = entry.id
                        resolved += 1

                # Save IDs before commit expires ORM attributes
                resolved_ids = {st.catalog_id for st in tracks if st.catalog_id}
                session.commit()

            # Async enrichment for entries missing deezer_id or beatport_id
            async def _async_enrich():
                from workers.async_http import HttpPool
                from workers.enrichment import (
                    enrich_beatport_batch,
                    enrich_deezer_batch,
                )
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        existing_isrcs = {
                            r[0]
                            for r in session.execute(
                                select(CatalogEntry.isrc).where(
                                    CatalogEntry.isrc.isnot(None)
                                )
                            ).all()
                        }
                        dz_entries = (
                            session.execute(
                                select(CatalogEntry).where(
                                    CatalogEntry.id.in_(resolved_ids),
                                    CatalogEntry.deezer_id.is_(None),
                                )
                            )
                            .scalars()
                            .all()
                        )

                        dz_stats = {"enriched": 0}
                        if dz_entries:
                            dz_stats = await enrich_deezer_batch(
                                session, dz_entries, pool, None, existing_isrcs
                            )
                        session.commit()

                        bp_entries = (
                            session.execute(
                                select(CatalogEntry).where(
                                    CatalogEntry.id.in_(resolved_ids),
                                    CatalogEntry.beatport_id.is_(None),
                                )
                            )
                            .scalars()
                            .all()
                        )

                        bp_stats = {"enriched": 0}
                        if bp_entries:
                            bp_stats = await enrich_beatport_batch(
                                session, bp_entries, pool, None
                            )
                        session.commit()

                return dz_stats, bp_stats

            try:
                dz_stats, bp_stats = asyncio.run(_async_enrich())
            except Exception:
                logger.exception("Async enrichment failed in resolve_set_tracks")
                raise

            result = {
                "resolved": resolved,
                "enriched": dz_stats.get("enriched", 0),
                "bp_enriched": bp_stats.get("enriched", 0),
            }
            clog.set_stats(result)

    return result


@celery_app.task(
    name="workers.tasks.enrich_set_tracks",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def enrich_set_tracks(self):
    """
    Enrichit les entrées catalog liées aux sets qui n'ont pas encore de deezer_id.
    Ne touche pas aux tracks déjà enrichies.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry, SetTrack
    from services.image_service import BUCKET_CATALOG, ImageService
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session, task_type="enrich_set_tracks", celery_task_id=self.request.id
        ) as clog:
            # Collect all catalog_ids from set_tracks
            with Session(engine) as session:
                catalog_ids = {
                    r[0]
                    for r in session.execute(
                        select(SetTrack.catalog_id)
                        .where(
                            SetTrack.catalog_id.isnot(None),
                        )
                        .distinct()
                    ).all()
                }

            if not catalog_ids:
                clog.set_stats({"enriched": 0, "bp_enriched": 0, "total": 0})
                return {"enriched": 0, "bp_enriched": 0, "total": 0}

            async def _async_enrich():
                from workers.async_http import HttpPool
                from workers.enrichment import enrich_deezer_batch
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        existing_isrcs = {
                            r[0]
                            for r in session.execute(
                                select(CatalogEntry.isrc).where(
                                    CatalogEntry.isrc.isnot(None)
                                )
                            ).all()
                        }

                        dz_entries = (
                            session.execute(
                                select(CatalogEntry).where(
                                    CatalogEntry.id.in_(catalog_ids),
                                    CatalogEntry.deezer_id.is_(None),
                                )
                            )
                            .scalars()
                            .all()
                        )

                        dz_total = 0
                        dz_errors = 0
                        if dz_entries:
                            for i in range(0, len(dz_entries), 100):
                                batch = dz_entries[i : i + 100]
                                stats = await enrich_deezer_batch(
                                    session, batch, pool, None, existing_isrcs
                                )
                                dz_total += stats.get("enriched", 0)
                                dz_errors += stats.get("errors", 0)
                                session.commit()
                                logger.info(
                                    "Set tracks Deezer enrich: %d/%d",
                                    min(i + 100, len(dz_entries)),
                                    len(dz_entries),
                                )

                        return {"enriched": dz_total, "errors": dz_errors}

            try:
                stats = asyncio.run(_async_enrich())
            except Exception:
                logger.exception("enrich_set_tracks failed")
                raise

            result = {
                "enriched": stats.get("enriched", 0),
                "total": len(catalog_ids),
            }
            clog.set_stats(result)

    return result


@celery_app.task(
    name="workers.tasks.crawl_followed_sets",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def crawl_followed_sets(self):
    """
    Re-crawl followed sets whose tracklist is not 100% identified.
    Skips sets crawled < 12h ago.
    After re-import, resolves unlinked tracks via catalog matching + Deezer enrichment.
    """
    import asyncio
    from datetime import datetime, timezone

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import DJSet, SetTrack, UserSetFollow
    from workers.db import get_engine

    engine = get_engine()

    sets_to_crawl = []
    skipped_complete = 0
    skipped_recent = 0

    with Session(engine) as session:
        followed_ids = {
            r[0] for r in session.execute(select(UserSetFollow.set_id).distinct()).all()
        }

        if not followed_ids:
            return {"crawled": 0, "skipped_complete": 0, "skipped_recent": 0}

        for sid in followed_ids:
            dj_set = session.get(DJSet, sid)
            if not dj_set or dj_set.source != "trackid" or dj_set.is_virtual:
                continue

            total = (
                session.execute(
                    select(func.count(SetTrack.id)).where(SetTrack.set_id == sid)
                ).scalar()
                or 0
            )
            identified = (
                session.execute(
                    select(func.count(SetTrack.id)).where(
                        SetTrack.set_id == sid,
                        SetTrack.is_id.is_(False),
                        SetTrack.catalog_id.isnot(None),
                    )
                ).scalar()
                or 0
            )

            if total > 0 and identified >= total:
                skipped_complete += 1
                continue

            if dj_set.last_crawled_at:
                age_h = (
                    datetime.now(timezone.utc) - dj_set.last_crawled_at
                ).total_seconds() / 3600
                if age_h < 12:
                    skipped_recent += 1
                    continue

            sets_to_crawl.append(
                {"ext_id": dj_set.external_id, "slug": dj_set.external_slug}
            )

    if not sets_to_crawl:
        return {
            "crawled": 0,
            "skipped_complete": skipped_complete,
            "skipped_recent": skipped_recent,
        }

    async def _crawl_all():
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as async_sessionmaker
        from trackid.client import TrackIDClient
        from trackid.importer import import_audiostream
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        async_engine = create_async_engine(os.environ["DATABASE_URL"])
        AsyncS = async_sessionmaker(async_engine, class_=AsyncSession)
        crawled = 0

        async with TrackIDClient() as client:
            for info in sets_to_crawl:
                if not info["slug"]:
                    continue
                try:
                    async with limiter.acquire("trackid"):
                        async with AsyncS() as db:
                            audiostream = {"id": info["ext_id"], "slug": info["slug"]}
                            result, track_count = await import_audiostream(
                                db, client, audiostream, min_age_hours=0
                            )
                            if result and track_count > 0:
                                crawled += 1
                            parent_set_id = result.parent_set_id if result else None
                            await db.commit()
                            if parent_set_id is not None:
                                from services.set_dedup_service import (
                                    materialize_parent,
                                )
                                try:
                                    await materialize_parent(db, parent_set_id)
                                    await db.commit()
                                except Exception:
                                    pass  # ne pas bloquer le crawl
                except Exception:
                    logger.exception(
                        "crawl_followed_sets: failed for set %s", info.get("slug")
                    )

        await async_engine.dispose()
        return crawled

    crawled = asyncio.run(_crawl_all())

    # Trigger track resolution for updated sets
    resolve_set_tracks.delay()

    return {
        "crawled": crawled,
        "skipped_complete": skipped_complete,
        "skipped_recent": skipped_recent,
    }
