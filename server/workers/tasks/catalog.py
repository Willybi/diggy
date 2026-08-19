"""
Celery tasks for catalog enrichment (Deezer and Beatport).
"""

import asyncio
import logging
import os
import sys
import time

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lock TTL must cover the task's time_limit (3300s) so the lock cannot
# expire while a legitimate run is still in progress (invariant: TTL ≥ time_limit).
# 3900s = 65 min, just above the hourly-drain 3300s time_limit.
BEATPORT_LOCK_TTL = 3900

# Same invariant for the Deezer sweep (TTL ≥ time_limit): the Deezer task runs a
# single nightly pass with a much longer time_limit (9000s), so its lock TTL must
# stay above it. 9300s = just above the 9000s time_limit.
DEEZER_LOCK_TTL = 9300

# Soft time limits, extracted as module constants so the task decorator AND the
# internal deadline guard share ONE source of truth (AV9). Never read
# task.soft_time_limit at runtime — fragile under the tests' MagicMock harness.
DEEZER_SOFT_TIME_LIMIT = 7200
BEATPORT_SOFT_TIME_LIMIT = 3000

# AV9 — margin (seconds) subtracted from the soft limit to build an internal
# monotonic deadline checked between batches. billiard's SoftTimeLimitExceeded
# can fire WHILE the asyncio internals are mid-write and be swallowed by the
# transport's error handler ("Fatal write error on socket transport", Sentry
# DIGGY-APP-J): it then never reaches the task's except clause and the run dies
# at the hard limit (SIGKILL — uncommitted work lost + orphaned lock ≤1h). The
# deadline exits the loop cleanly WITHOUT depending on signal delivery; the
# SoftTimeLimitExceeded catch stays in place as defense in depth.
DEADLINE_MARGIN = int(os.environ.get("ENRICH_DEADLINE_MARGIN", "120"))

# Max catalog entries per sweep, PER SOURCE. Deezer (official API, 10 req/s)
# clears the full daily inflow in minutes, so its budget is high. Beatport
# (scraped, 0.66 req/s anti-ban) is throughput-bound and now drained by an
# HOURLY beat (6h-23h) capped at batch_size=550/run — ~18 créneaux → up to
# ~9900/day, itself bounded by the rate (~940/h). The per-source budget stays
# 6000: each run is already bounded by min(batch_size, budget), so batch_size
# (550) is the effective per-run cap and the budget is the daily safety ceiling.
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
    soft_time_limit=DEEZER_SOFT_TIME_LIMIT,
    time_limit=9000,
)
def enrich_catalog(self):
    """
    Enrichit les entrées catalog sans deezer_id via Deezer.
    Concurrent async enrichment (5 parallel requests).
    Single-instance: a Redis lock skips the run if another one is in flight
    (beat run vs admin trigger, or broker re-delivery) — twin of the Beatport
    drain. No autoretry_for=(Exception,): SoftTimeLimitExceeded IS an Exception,
    so that decorator would loop the whole Deezer sweep; the soft-limit catch +
    the lock guard the run instead.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:enrich_deezer"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=DEEZER_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning("enrich_catalog already running (task %s), skipping", holder)
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_enrich_catalog(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_enrich_catalog(task):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from services.image_service import BUCKET_ALBUM, BUCKET_CATALOG, ImageService
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)
    ImageService.ensure_bucket(BUCKET_ALBUM)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="enrich_catalog",
            source="deezer",
            celery_task_id=task.request.id,
        ) as clog:

            budget = _nightly_budget("deezer")

            # AV9 — internal deadline (see DEADLINE_MARGIN): checked BEFORE
            # each batch, never mid-batch, so a shortened run stamps nothing
            # on the entries it never reached (not an E1 attempt).
            deadline = time.monotonic() + DEEZER_SOFT_TIME_LIMIT - DEADLINE_MARGIN
            deadline_hit = False

            # Hoisted so a SoftTimeLimitExceeded mid-run still yields the work
            # committed so far (each 100-batch is committed before the next).
            progress = {
                "enriched": 0,
                "errors": 0,
                "merged": 0,
            }

            async def _async_enrich():
                nonlocal deadline_hit

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
                            return

                        for i in range(0, len(entries), 100):
                            if time.monotonic() >= deadline:
                                deadline_hit = True
                                logger.warning(
                                    "enrich_catalog hit internal deadline "
                                    "(soft limit %ds - margin %ds); stopping "
                                    "before next batch, partial stats: %s",
                                    DEEZER_SOFT_TIME_LIMIT,
                                    DEADLINE_MARGIN,
                                    progress,
                                )
                                break
                            batch = entries[i : i + 100]
                            stats = await enrich_deezer_batch(
                                session, batch, pool, None, existing_isrcs
                            )
                            progress["enriched"] += stats.get("enriched", 0)
                            progress["errors"] += stats.get("errors", 0)
                            progress["merged"] += stats.get("merged", 0)
                            session.commit()
                            logger.info(
                                "Deezer enrich progress: %d/%d",
                                min(i + 100, len(entries)),
                                len(entries),
                            )

            # Catch the soft limit so the run ends cleanly (status success) with
            # the partial stats flushed, and the Redis lock is released by the
            # outer `finally` — instead of propagating to a hard-limit SIGKILL
            # that skips the lock release and orphans it (twin of enrich_beatport).
            from celery.exceptions import SoftTimeLimitExceeded

            try:
                asyncio.run(_async_enrich())
            except SoftTimeLimitExceeded:
                logger.warning(
                    "enrich_catalog hit soft time limit; flushing partial stats: %s",
                    progress,
                )
            except Exception:
                logger.exception("enrich_catalog failed")
                raise

            # Observability (AV9): a deadline exit is a SUCCESS with partial
            # work, distinguishable from a full run in crawl_logs.
            progress["deadline_hit"] = deadline_hit
            clog.set_stats(progress)

    return progress


@celery_app.task(
    name="workers.tasks.enrich_catalog_beatport",
    bind=True,
    soft_time_limit=BEATPORT_SOFT_TIME_LIMIT,
    time_limit=3300,
)
def enrich_catalog_beatport(self, batch_size: int = 0, *, genre_only: bool = False):
    """
    Enrichit les entrées catalog via Beatport (concurrent async scraping).
    Uses 2 concurrent scrapers with Redis caching.
    Single-instance: a Redis lock skips the run if another one is in flight
    (beat run vs admin-triggered run, or broker re-delivery).

    ``genre_only`` (keyword-only, default False, back-compat with the by-name
    ``send_task`` dispatch from both the beat and admin): when True the run
    targets catalog rows with NO genre instead of rows missing a beatport_id —
    backs the admin "auto-classifier" button (A3-01).
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
        return _run_enrich_catalog_beatport(self, batch_size, genre_only=genre_only)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_enrich_catalog_beatport(task, batch_size: int, *, genre_only: bool = False):
    from services.image_service import BUCKET_ALBUM, BUCKET_CATALOG, ImageService
    from sqlalchemy.orm import Session
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_CATALOG)
    ImageService.ensure_bucket(BUCKET_ALBUM)

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

            # AV9 — internal deadline (see DEADLINE_MARGIN): checked BEFORE
            # each batch, never mid-batch, so a shortened run stamps nothing
            # on the entries it never reached (not an E1 attempt).
            deadline = time.monotonic() + BEATPORT_SOFT_TIME_LIMIT - DEADLINE_MARGIN
            deadline_hit = False

            # Hoisted so a SoftTimeLimitExceeded mid-run still yields the work
            # committed so far (each 50-batch is committed before the next).
            progress = {
                "enriched": 0,
                "not_found": 0,
                "errors": 0,
                "merged": 0,
                "total": 0,
            }

            async def _async_enrich():
                nonlocal deadline_hit

                from datetime import datetime, timezone

                from workers.async_http import HttpPool
                from workers.enrichment import (
                    enrich_beatport_batch,
                    select_enrich_candidates,
                )
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()

                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        entries = select_enrich_candidates(
                            session,
                            source="beatport",
                            budget=effective_budget,
                            now=datetime.now(timezone.utc),
                            genre_only=genre_only,
                        )
                        progress["total"] = len(entries)

                        for i in range(0, len(entries), 50):
                            if time.monotonic() >= deadline:
                                deadline_hit = True
                                logger.warning(
                                    "enrich_catalog_beatport hit internal "
                                    "deadline (soft limit %ds - margin %ds); "
                                    "stopping before next batch, "
                                    "partial stats: %s",
                                    BEATPORT_SOFT_TIME_LIMIT,
                                    DEADLINE_MARGIN,
                                    progress,
                                )
                                break
                            batch = entries[i : i + 50]
                            stats = await enrich_beatport_batch(
                                session, batch, pool, None
                            )
                            progress["enriched"] += stats.get("enriched", 0)
                            progress["not_found"] += stats.get("not_found", 0)
                            progress["errors"] += stats.get("errors", 0)
                            progress["merged"] += stats.get("merged", 0)
                            session.commit()
                            logger.info(
                                "Beatport enrich progress: %d/%d",
                                min(i + 50, progress["total"]),
                                progress["total"],
                            )

            # Catch the soft limit so the run ends cleanly (status success) with
            # the partial stats flushed, and the Redis lock is released by the
            # outer `finally` — instead of propagating to a hard-limit SIGKILL
            # that skips the lock release and orphans it (constaté 2026-07-23).
            from celery.exceptions import SoftTimeLimitExceeded

            soft_limit_hit = False
            try:
                asyncio.run(_async_enrich())
            except SoftTimeLimitExceeded:
                soft_limit_hit = True
                logger.warning(
                    "enrich_catalog_beatport hit soft time limit; "
                    "flushing partial stats: %s",
                    progress,
                )
            except Exception:
                logger.exception("enrich_catalog_beatport failed")
                raise

            result = dict(progress)
            result["soft_limit_hit"] = soft_limit_hit
            # Observability (AV9): a deadline exit is a SUCCESS with partial
            # work, distinguishable from a full run in crawl_logs.
            result["deadline_hit"] = deadline_hit
            # Recorded in crawl_logs so a genre-classify run is distinguishable
            # from a normal drain in monitoring (A3-01 observability).
            result["genre_only"] = genre_only
            clog.set_stats(result)

    return result
