"""E2.c — nightly Celery task: estimate BPM from Deezer previews.

Strict clone of the Beatport hourly drain (``tasks/catalog.py``):
  - single-instance Redis lock (``SET NX EX``, TTL ≥ time_limit, conditional
    release so an orphaned lock from a deploy-kill self-heals within one slot);
  - bounded soft/hard time limits, NO ``autoretry_for`` (the budget cap is the
    loop guard — a retry decorator turned a soft timeout into an infinite loop
    on the artist backlog, cf. CLAUDE.md);
  - budget via ``min(batch_size, nightly_budget)``;
  - hoisted batch-commit ``progress`` so a ``SoftTimeLimitExceeded`` still
    flushes the partial;
  - ``CrawlLogger`` run row.

Runs on the ``enrich`` queue (Deezer API, rate-limited), hourly 00h→03h — kept
clear of the 05h Deezer enrich window and the 06h→23h Beatport drain. A run with
no eligible candidate is a no-op in seconds (empty selection → empty loop).
"""

import asyncio
import logging
import os
import sys
import time

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lock TTL must cover the task's time_limit (3300s) so the lock cannot expire
# while a legitimate run is still in progress (invariant: TTL ≥ time_limit).
# 3900s = 65 min, just above the 3300s time_limit; a short TTL means an orphaned
# lock (worker killed by a deploy mid-run) self-heals in ≤1 slot.
ANALYSIS_BPM_LOCK_TTL = int(os.environ.get("ANALYSIS_BPM_LOCK_TTL", "3900"))

# Nightly budget = safety ceiling on candidates per RUN (min()-bound below the
# per-run batch_size, which the beat passes as batch_size=2000). 4 slots
# (00h-03h) × 2000 ≈ 8000/night.
DEFAULT_ANALYSIS_BPM_NIGHTLY_BUDGET = 8000

# Executor width: 2 threads so the CPU analysis of one preview overlaps the
# download of the next (Essentia is blocking + not thread-shareable → a fresh
# instance per call, capped concurrency).
ANALYSIS_EXECUTOR_WORKERS = int(os.environ.get("ANALYSIS_BPM_EXECUTOR_WORKERS", "2"))

# Soft time limit, extracted as a module constant so the task decorator AND the
# internal deadline guard share ONE source of truth (AV9). Never read
# task.soft_time_limit at runtime — fragile under the tests' MagicMock harness.
ANALYSIS_BPM_SOFT_TIME_LIMIT = 3000

# AV9 — margin (seconds) subtracted from the soft limit to build an internal
# monotonic deadline checked between batches. billiard's SoftTimeLimitExceeded
# can fire WHILE the asyncio internals are mid-write and be swallowed by the
# transport's error handler ("Fatal write error on socket transport", Sentry
# DIGGY-APP-J): it then never reaches the task's except clause and the run dies
# at the hard limit (SIGKILL — uncommitted work lost + orphaned lock ≤1h). The
# deadline exits the loop cleanly WITHOUT depending on signal delivery; the
# SoftTimeLimitExceeded catch stays in place as defense in depth.
DEADLINE_MARGIN = int(os.environ.get("ANALYSIS_BPM_DEADLINE_MARGIN", "120"))


def _nightly_budget() -> int:
    return int(
        os.environ.get(
            "ANALYSIS_BPM_NIGHTLY_BUDGET", str(DEFAULT_ANALYSIS_BPM_NIGHTLY_BUDGET)
        )
    )


def _min_conf() -> float:
    return float(os.environ.get("ANALYSIS_BPM_MIN_CONF", "2.0"))


@celery_app.task(
    name="workers.tasks.analyze_bpm_previews",
    bind=True,
    soft_time_limit=ANALYSIS_BPM_SOFT_TIME_LIMIT,
    time_limit=3300,
)
def analyze_bpm_previews(self, batch_size: int = 0):
    """Estimate BPM from Deezer previews for catalog rows missing a bpm.

    Single-instance: a Redis lock skips the run if another one is in flight
    (beat run vs admin-triggered run, or broker re-delivery).
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:analyze_bpm"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=ANALYSIS_BPM_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "analyze_bpm_previews already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_analyze_bpm_previews(self, batch_size)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_analyze_bpm_previews(task, batch_size: int):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.orm import Session
    from workers.db import get_engine

    engine = get_engine()

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="analyze_bpm",
            source="deezer",
            celery_task_id=task.request.id,
        ) as clog:

            # batch_size stays a manual per-run bound on top of the nightly budget.
            budget = _nightly_budget()
            effective_budget = min(batch_size, budget) if batch_size > 0 else budget
            min_conf = _min_conf()

            # AV9 — internal deadline (see DEADLINE_MARGIN): checked BEFORE
            # each batch, never mid-batch, so a shortened run stamps nothing
            # on the entries it never reached (not an attempt).
            deadline = (
                time.monotonic() + ANALYSIS_BPM_SOFT_TIME_LIMIT - DEADLINE_MARGIN
            )
            deadline_hit = False

            # Hoisted so a SoftTimeLimitExceeded mid-run still yields the work
            # committed so far (each 50-batch is committed before the next).
            progress = {
                "estimated": 0,
                "low_conf": 0,
                "no_preview": 0,
                "skipped": 0,
                "errors": 0,
                "total": 0,
            }

            async def _async_analyze():
                nonlocal deadline_hit

                from workers.async_http import HttpPool
                from workers.bpm_analysis import (
                    analyze_bpm_batch,
                    select_bpm_candidates,
                )
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                executor = ThreadPoolExecutor(max_workers=ANALYSIS_EXECUTOR_WORKERS)
                try:
                    async with HttpPool(limiter) as pool:
                        with Session(engine) as session:
                            entries = select_bpm_candidates(session, effective_budget)
                            progress["total"] = len(entries)

                            for i in range(0, len(entries), 50):
                                if time.monotonic() >= deadline:
                                    deadline_hit = True
                                    logger.warning(
                                        "analyze_bpm_previews hit internal "
                                        "deadline (soft limit %ds - "
                                        "margin %ds); stopping before next "
                                        "batch, partial stats: %s",
                                        ANALYSIS_BPM_SOFT_TIME_LIMIT,
                                        DEADLINE_MARGIN,
                                        progress,
                                    )
                                    break
                                batch = entries[i : i + 50]
                                stats = await analyze_bpm_batch(
                                    session,
                                    batch,
                                    pool,
                                    executor,
                                    min_conf=min_conf,
                                )
                                for k in (
                                    "estimated",
                                    "low_conf",
                                    "no_preview",
                                    "skipped",
                                    "errors",
                                ):
                                    progress[k] += stats.get(k, 0)
                                session.commit()
                                logger.info(
                                    "BPM analysis progress: %d/%d",
                                    min(i + 50, progress["total"]),
                                    progress["total"],
                                )
                finally:
                    executor.shutdown(wait=False)

            # Catch the soft limit so the run ends cleanly (status success) with
            # the partial stats flushed and the Redis lock released by the outer
            # `finally` — instead of a hard-limit SIGKILL that would orphan the
            # lock (same rationale as enrich_catalog_beatport).
            from celery.exceptions import SoftTimeLimitExceeded

            soft_limit_hit = False
            try:
                asyncio.run(_async_analyze())
            except SoftTimeLimitExceeded:
                soft_limit_hit = True
                logger.warning(
                    "analyze_bpm_previews hit soft time limit; "
                    "flushing partial stats: %s",
                    progress,
                )
            except Exception:
                logger.exception("analyze_bpm_previews failed")
                raise

            result = dict(progress)
            result["soft_limit_hit"] = soft_limit_hit
            # Observability (AV9): a deadline exit is a SUCCESS with partial
            # work, distinguishable from a full run in crawl_logs.
            result["deadline_hit"] = deadline_hit
            clog.set_stats(result)

    return result
