"""
Celery tasks for catalog enrichment (Deezer and Beatport).
"""

import asyncio
import logging
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.enrich_catalog",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def enrich_catalog(self):
    """
    Enrichit les entrées catalog sans deezer_id via Deezer.
    Concurrent async enrichment (5 parallel requests).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from services.image_service import BUCKET_CATALOG, ImageService
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="enrich_catalog",
            source="deezer",
            celery_task_id=self.request.id,
        ) as clog:

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

                        entries = (
                            session.execute(
                                select(CatalogEntry)
                                .where(
                                    CatalogEntry.deezer_id.is_(None),
                                    CatalogEntry.deezer_searched_at.is_(None),
                                )
                                .order_by(CatalogEntry.id)
                            )
                            .scalars()
                            .all()
                        )

                        if not entries:
                            return {"enriched": 0, "errors": 0}

                        total_enriched = 0
                        total_errors = 0
                        for i in range(0, len(entries), 100):
                            batch = entries[i : i + 100]
                            stats = await enrich_deezer_batch(
                                session, batch, pool, None, existing_isrcs
                            )
                            total_enriched += stats.get("enriched", 0)
                            total_errors += stats.get("errors", 0)
                            session.commit()
                            logger.info(
                                "Deezer enrich progress: %d/%d",
                                min(i + 100, len(entries)),
                                len(entries),
                            )

                        return {"enriched": total_enriched, "errors": total_errors}

            try:
                stats = asyncio.run(_async_enrich())
            except Exception:
                logger.exception("enrich_catalog failed")
                raise

            clog.set_stats(stats)

    return stats


@celery_app.task(
    name="workers.tasks.enrich_catalog_beatport",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=25200,
    time_limit=28800,
)
def enrich_catalog_beatport(self, batch_size: int = 0):
    """
    Enrichit les entrées catalog via Beatport (concurrent async scraping).
    Uses 2 concurrent scrapers with Redis caching.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from services.image_service import BUCKET_CATALOG, ImageService
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="enrich_beatport",
            source="beatport",
            celery_task_id=self.request.id,
        ) as clog:

            async def _async_enrich():
                from workers.async_http import HttpPool
                from workers.enrichment import enrich_beatport_batch
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                total_enriched = 0
                total_not_found = 0
                total_errors = 0

                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        query = (
                            select(CatalogEntry)
                            .where(
                                CatalogEntry.beatport_id.is_(None),
                                CatalogEntry.beatport_searched_at.is_(None),
                            )
                            .order_by(CatalogEntry.id)
                        )
                        if batch_size > 0:
                            query = query.limit(batch_size)
                        entries = session.execute(query).scalars().all()
                        total = len(entries)

                        if not entries:
                            return {
                                "enriched": 0,
                                "not_found": 0,
                                "errors": 0,
                                "total": 0,
                            }

                        for i in range(0, len(entries), 50):
                            batch = entries[i : i + 50]
                            stats = await enrich_beatport_batch(
                                session, batch, pool, None
                            )
                            total_enriched += stats.get("enriched", 0)
                            total_not_found += stats.get("not_found", 0)
                            total_errors += stats.get("errors", 0)
                            session.commit()
                            logger.info(
                                "Beatport enrich progress: %d/%d",
                                min(i + 50, total),
                                total,
                            )

                        return {
                            "enriched": total_enriched,
                            "not_found": total_not_found,
                            "errors": total_errors,
                            "total": total,
                        }

            try:
                result = asyncio.run(_async_enrich())
            except Exception:
                logger.exception("enrich_catalog_beatport failed")
                raise

            clog.set_stats(result)

    return result
