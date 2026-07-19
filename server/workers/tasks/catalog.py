"""
Celery tasks for catalog enrichment (Deezer and Beatport).
"""

import asyncio
import logging
import os
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lock TTL must cover the task's time_limit (28800s) so the lock cannot
# expire while a legitimate run is still in progress
BEATPORT_LOCK_TTL = 30000

# Max catalog entries per nightly sweep, PER SOURCE. Deezer (official API,
# 10 req/s) clears the full daily inflow in minutes, so its budget is high.
# Beatport (scraped, 0.66 req/s anti-ban) is throughput-bound: 6000 fills one
# ~7h pass, and a second afternoon beat pass doubles daily capacity to ~12000
# without touching the rate.
DEFAULT_NIGHTLY_BUDGET_DEEZER = 15000
DEFAULT_NIGHTLY_BUDGET_BEATPORT = 6000


def _nightly_budget(source: str) -> int:
    """Per-source nightly enrichment budget.

    A per-source override (ENRICH_NIGHTLY_BUDGET_DEEZER / _BEATPORT) wins; the
    legacy shared ENRICH_NIGHTLY_BUDGET is the fallback default for both.
    """
    shared = os.environ.get("ENRICH_NIGHTLY_BUDGET")
    if source == "deezer":
        return int(
            os.environ.get(
                "ENRICH_NIGHTLY_BUDGET_DEEZER",
                shared or str(DEFAULT_NIGHTLY_BUDGET_DEEZER),
            )
        )
    return int(
        os.environ.get(
            "ENRICH_NIGHTLY_BUDGET_BEATPORT",
            shared or str(DEFAULT_NIGHTLY_BUDGET_BEATPORT),
        )
    )


@celery_app.task(
    name="workers.tasks.enrich_catalog",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=7200,
    time_limit=9000,
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

            budget = _nightly_budget("deezer")

            async def _async_enrich():
                from datetime import datetime, timezone

                from workers.async_http import HttpPool
                from workers.enrichment import (
                    enrich_deezer_batch,
                    select_enrich_candidates,
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

                        entries = select_enrich_candidates(
                            session,
                            source="deezer",
                            budget=budget,
                            now=datetime.now(timezone.utc),
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
    Single-instance: a Redis lock skips the run if another one is in flight
    (beat run vs admin-triggered run, or broker re-delivery).
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:enrich_beatport"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=BEATPORT_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "enrich_catalog_beatport already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_enrich_catalog_beatport(self, batch_size)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_enrich_catalog_beatport(task, batch_size: int):
    from services.image_service import BUCKET_CATALOG, ImageService
    from sqlalchemy.orm import Session
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="enrich_beatport",
            source="beatport",
            celery_task_id=task.request.id,
        ) as clog:

            # batch_size stays as a manual bound on top of the nightly budget
            budget = _nightly_budget("beatport")
            effective_budget = min(batch_size, budget) if batch_size > 0 else budget

            async def _async_enrich():
                from datetime import datetime, timezone

                from workers.async_http import HttpPool
                from workers.enrichment import (
                    enrich_beatport_batch,
                    select_enrich_candidates,
                )
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                total_enriched = 0
                total_not_found = 0
                total_errors = 0

                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        entries = select_enrich_candidates(
                            session,
                            source="beatport",
                            budget=effective_budget,
                            now=datetime.now(timezone.utc),
                        )
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
