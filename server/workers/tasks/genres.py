"""
Celery tasks for genre reclassification.
"""

import asyncio
import logging
import os
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Single-instance lock for the WHOLE reclassify run (A8-03). The orchestrator
# acquires it and the chord callback/errback release it — the orchestrator must
# NOT release it, because the chord runs asynchronously AFTER the orchestrator
# returns. The TTL is a generous auto-heal ceiling covering a full run (hundreds
# of chunks, each up to soft_time_limit=1800s): if the callback/errback that
# releases the lock never runs (whole chord lost), the lock frees itself after
# this TTL instead of blocking every future run. Same SET NX EX /
# conditional-release pattern as enrich_catalog_beatport (tasks/catalog.py).
RECLASSIFY_LOCK_KEY = "lock:reclassify_genres"
RECLASSIFY_LOCK_TTL = 21600  # 6h

# Per-item wall-clock ceiling for one entry's Beatport+Deezer classification
# (env-overridable). Without it a single external call that hangs (a stalled
# Beatport scrape, a Deezer socket that never returns) freezes the WHOLE chunk
# until the task-level soft_time_limit (1800s) fires — and, since the task did
# not catch SoftTimeLimitExceeded, acks_late redelivered the chunk into a clean
# crash-loop (537 Sentry events, AV8-02). Bound each item instead: a timeout is
# treated as a source error (existing genres kept, the loop moves on). Read the
# module global at call time so a test can monkeypatch it to a small value.
RECLASSIFY_ITEM_TIMEOUT = int(os.environ.get("RECLASSIFY_ITEM_TIMEOUT", "120"))


def _release_reclassify_lock(lock_token):
    """Conditionally release the reclassify single-instance lock.

    Deletes the key only when it is still owned by ``lock_token`` (a conditional
    release, in case the TTL already expired mid-run and another run took
    ownership). ``None`` → no-op. Best-effort: a Redis hiccup must never fail the
    caller (chord callback / orchestrator early return).
    """
    if lock_token is None:
        return
    try:
        import redis as redis_lib
        from workers.celery_app import REDIS_URL

        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        if r.get(RECLASSIFY_LOCK_KEY) == lock_token:
            r.delete(RECLASSIFY_LOCK_KEY)
    except Exception as e:
        logger.warning("Failed to release reclassify lock: %s", e)


@celery_app.task(
    name="workers.tasks.reclassify_genres_chunk",
    bind=True,
    # NO autoretry_for=(Exception,): the global config is task_acks_late=True +
    # task_reject_on_worker_lost=True, so a chunk that dies (OOM/SIGKILL or
    # soft-timeout) is ALREADY requeued once by the broker. Adding autoretry on
    # top turns any resource failure into an infinite OOM crash-loop — this bit
    # prod on 2026-08-10 (a fixed-COUNT split loaded ~58k ORM rows per chunk →
    # OOM every 2-3s forever). Per-entry source errors are caught inside the
    # loop; a genuine chunk-level failure surfaces via the chord errback/DLQ.
    soft_time_limit=1800,
    time_limit=2100,
)
def reclassify_genres_chunk(self, catalog_ids: list[int], chunk_index: int = 0):
    """
    Re-classify genres for a chunk of catalog entries.
    Strategy per track: try Beatport → fallback Deezer (album) → commit.
    Existing genres are only cleared when both sources answered without
    error and found nothing; on source failure they are kept, so re-running
    the task after a network incident never destroys valid classifications.

    Chunks are sized by the orchestrator (fixed number of ids, ~200) so the
    up-front `SELECT ... WHERE id IN (...)` never loads more than a bounded set
    of ORM rows into memory — keep it that way (a whole-catalog chunk OOMs).

    Robustness (AV8-02): each item is bounded by RECLASSIFY_ITEM_TIMEOUT so a
    hung external call can never freeze the whole chunk (a timeout counts as a
    source error → genres kept, loop continues), and SoftTimeLimitExceeded is
    caught so the task ends cleanly with the partial stats flushed (the per-50
    commits make the work durable) instead of dying under the hard limit and
    being redelivered by acks_late into a crash-loop. Twin of the soft-limit
    handling in enrich_catalog_beatport (tasks/catalog.py).
    """
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from workers.db import get_engine

    engine = get_engine()

    # Hoisted out of the coroutine so a SoftTimeLimitExceeded mid-run still yields
    # the work committed so far (each 50-batch is committed before the next).
    stats = {
        "total": len(catalog_ids),
        "deezer": 0,
        "beatport": 0,
        "cleared": 0,
        "errors": 0,
    }

    async def _async_reclassify():
        import httpx
        from workers.async_http import HttpPool
        from workers.enrichment import _search_beatport_async
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        rcache = None
        try:
            import redis as redis_lib

            rcache = redis_lib.from_url(
                os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                decode_responses=True,
            )
        except Exception as e:
            logger.warning("Beatport cache unavailable: %s", e)
            rcache = None

        async with HttpPool(limiter) as pool:
            with Session(engine) as session:
                entries = (
                    session.execute(
                        select(CatalogEntry)
                        .where(CatalogEntry.id.in_(catalog_ids))
                        .order_by(CatalogEntry.id)
                    )
                    .scalars()
                    .all()
                )

                async with httpx.AsyncClient(timeout=10) as dz_client:

                    async def _process_one(entry):
                        """Classify one entry (Beatport → Deezer fallback).

                        Mutates ``entry.genres`` + ``stats`` in place and returns
                        ``(found, source_error)``. Runs under a per-item
                        ``asyncio.wait_for`` so a stalled external call can't
                        freeze the whole chunk; the cancellation raised on timeout
                        is a BaseException, so the per-source ``except Exception``
                        below never swallows it.
                        """
                        found = False
                        source_error = False

                        # 1) Try Beatport first (better genre taxonomy)
                        try:
                            bp_track = await _search_beatport_async(
                                pool,
                                entry.title,
                                entry.artist,
                                entry.isrc,
                                rcache=rcache,
                            )
                            if bp_track:
                                genre_obj = bp_track.get("genre")
                                if genre_obj:
                                    genre_name = (
                                        genre_obj.get("name")
                                        if isinstance(genre_obj, dict)
                                        else str(genre_obj)
                                    )
                                    if genre_name:
                                        entry.genres = [genre_name[:100]]
                                        stats["beatport"] += 1
                                        found = True
                        except Exception as e:
                            logger.warning(
                                "Beatport genre failed for catalog %s: %s", entry.id, e
                            )
                            stats["errors"] += 1
                            source_error = True

                        # 2) Fallback: Deezer (album → genres, up to 3)
                        if not found and entry.deezer_id:
                            try:
                                async with limiter.acquire("deezer"):
                                    r = await dz_client.get(
                                        f"https://api.deezer.com/track/{entry.deezer_id}"
                                    )
                                track_data = r.json()
                                album_id = (track_data.get("album") or {}).get("id")
                                if album_id:
                                    async with limiter.acquire("deezer"):
                                        r2 = await dz_client.get(
                                            f"https://api.deezer.com/album/{album_id}"
                                        )
                                    genres_data = (r2.json().get("genres") or {}).get(
                                        "data"
                                    ) or []
                                    if genres_data:
                                        entry.genres = [
                                            g["name"][:100] for g in genres_data[:3]
                                        ]
                                        stats["deezer"] += 1
                                        found = True
                            except Exception as e:
                                logger.warning(
                                    "Deezer genre failed for catalog %s: %s",
                                    entry.id,
                                    e,
                                )
                                stats["errors"] += 1
                                source_error = True

                        return found, source_error

                    for i, entry in enumerate(entries):
                        try:
                            found, source_error = await asyncio.wait_for(
                                _process_one(entry),
                                timeout=RECLASSIFY_ITEM_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            # A hung source is not a "no genre" answer: count it
                            # as a source error, KEEP the existing genres (same
                            # semantics as source_error=True), and move on to the
                            # next item instead of freezing the whole chunk.
                            logger.warning(
                                "Reclassify item timed out (>%ss) for catalog %s",
                                RECLASSIFY_ITEM_TIMEOUT,
                                entry.id,
                            )
                            stats["errors"] += 1
                            found, source_error = False, True

                        # Clearing is only legitimate when every source gave a
                        # valid (empty) answer; a failed source means we cannot
                        # tell "no genre" from "source down" → keep existing.
                        if not found and not source_error:
                            entry.genres = []
                            stats["cleared"] += 1

                        if (i + 1) % 50 == 0:
                            session.commit()
                            logger.info(
                                "Chunk %d reclassify: %d/%d (dz=%d bp=%d cleared=%d)",
                                chunk_index,
                                i + 1,
                                stats["total"],
                                stats["deezer"],
                                stats["beatport"],
                                stats["cleared"],
                            )

                    session.commit()

    # Catch the soft limit so the run ends cleanly (status success) with the
    # partial stats flushed instead of propagating to a hard-limit SIGKILL that
    # acks_late would redeliver into a crash-loop (AV8-02). A genuine chunk-level
    # error still surfaces (re-raised) so the chord errback/DLQ can record it.
    soft_limit_hit = False
    try:
        asyncio.run(_async_reclassify())
    except SoftTimeLimitExceeded:
        soft_limit_hit = True
        logger.warning(
            "reclassify_genres_chunk %d hit soft time limit; "
            "flushing partial stats: %s",
            chunk_index,
            stats,
        )
    except Exception:
        logger.exception("reclassify_genres_chunk %d failed", chunk_index)
        raise

    result = dict(stats)
    result["soft_limit_hit"] = soft_limit_hit
    logger.info("Chunk %d done: %s", chunk_index, result)
    return result


@celery_app.task(
    name="workers.tasks.reclassify_all_genres",
    bind=True,
    # NO autoretry: a retry would dispatch a SECOND chord of hundreds of chunks
    # on top of the first. If the dispatch itself fails, re-run manually.
)
def reclassify_all_genres(self, chunk_size: int = 200):
    """
    Orchestrator: splits the catalog into fixed-SIZE chunks and dispatches them
    as a chord. Chunk by size (~200 ids), never by a fixed COUNT: a fixed count
    over a growing catalog makes each chunk unbounded (~58k ids at 175k tracks),
    and `reclassify_genres_chunk` loads every chunk's rows into memory at once →
    OOM. A fixed size keeps per-chunk memory constant as the catalog grows.
    The default was lowered 500→200 (AV8-02) as a secondary guard: a smaller
    chunk finishes well within the 1800s soft limit, so a slow run is far less
    likely to hit it (the per-item timeout is the primary defence).

    Single-instance (A8-03): a Redis lock skips the run if another full
    reclassify is already in flight — two overlapping runs would double the
    external API traffic and the work. The lock is released by the chord
    callback (finalize_reclassify) on the nominal path and by the errback
    (reclassify_genres_error) on failure, NOT here: the chord runs
    asynchronously after this orchestrator returns.

    Returns immediately (no result.get() inside a task); finalize_reclassify
    aggregates the stats and writes the crawl_logs line once all chunks are done.
    """
    import redis as redis_lib
    from celery import chord, group
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from workers.celery_app import REDIS_URL
    from workers.db import get_engine

    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        RECLASSIFY_LOCK_KEY, self.request.id, nx=True, ex=RECLASSIFY_LOCK_TTL
    ):
        holder = r.get(RECLASSIFY_LOCK_KEY)
        logger.warning(
            "reclassify_all_genres already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    if chunk_size < 1:
        chunk_size = 200

    engine = get_engine()

    with Session(engine) as session:
        all_ids = [
            row[0]
            for row in session.execute(
                select(CatalogEntry.id).order_by(CatalogEntry.id)
            ).fetchall()
        ]

    total = len(all_ids)
    if not all_ids:
        # No chord is dispatched, so neither the callback nor the errback will
        # run to release the lock — release it here (conditionally, in case the
        # TTL already expired and another run took ownership).
        logger.info("Reclassify: catalog is empty, nothing to dispatch")
        _release_reclassify_lock(self.request.id)
        return {"dispatched": 0, "total": 0}

    chunks = [all_ids[i : i + chunk_size] for i in range(0, total, chunk_size)]

    logger.info(
        "Reclassify: dispatching %d chunks (%d tracks total, %d per chunk)",
        len(chunks),
        total,
        chunk_size,
    )

    # Pass the owner token to the callback for a conditional lock release; the
    # errback releases it best-effort (it does not carry the token).
    callback = finalize_reclassify.s(
        total=total, lock_token=self.request.id
    ).on_error(reclassify_genres_error.s())
    chord(
        group(reclassify_genres_chunk.s(chunk, i) for i, chunk in enumerate(chunks))
    )(callback)

    return {"dispatched": len(chunks), "total": total}


@celery_app.task(
    name="workers.tasks.finalize_reclassify",
    bind=True,
    # NO autoretry_for=(Exception,): this is the chord callback. acks_late +
    # reject_on_worker_lost re-deliver it once on a crash; a retry decorator
    # would re-run the aggregation (a duplicate crawl_logs line) and re-release
    # the orchestrator lock.
)
def finalize_reclassify(self, results, total: int = 0, lock_token: str | None = None):
    """
    Chord callback: aggregates per-chunk stats and records the single
    crawl_logs line for the whole reclassify run, then releases the
    reclassify_all_genres single-instance lock.

    ``lock_token`` (default None, keeps the callback back-compatible) is the
    owner token set by the orchestrator: the lock is released only when it still
    matches (conditional release, in case the 6h TTL already expired mid-run and
    another run took ownership). None → no release.
    """
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    agg = {"total": total, "deezer": 0, "beatport": 0, "cleared": 0, "errors": 0}
    for chunk_stats in results or []:
        if not isinstance(chunk_stats, dict):
            continue
        for k in ("deezer", "beatport", "cleared", "errors"):
            agg[k] += chunk_stats.get(k, 0)

    engine = get_engine()
    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="reclassify_genres",
            source="beatport+deezer",
            celery_task_id=self.request.id,
        ) as clog:
            clog.set_stats(agg)

    _release_reclassify_lock(lock_token)

    logger.info("Reclassify complete: %s", agg)
    return agg


@celery_app.task(name="workers.tasks.reclassify_genres_error", bind=True)
def reclassify_genres_error(self, request, exc, traceback):
    """
    Chord errback: a chunk (or the finalize callback) failed, so
    finalize_reclassify never ran normally. Record the failure in crawl_logs so
    the run does not fail invisibly, and release the reclassify single-instance
    lock (best-effort, unconditional: the errback does not carry the owner token,
    and the 6h TTL is the ultimate backstop).
    """
    from datetime import datetime, timezone

    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CrawlLog
    from workers.db import get_engine

    logger.error(
        "Reclassify chord failed (task %s): %s", getattr(request, "id", None), exc
    )

    now = datetime.now(timezone.utc)
    engine = get_engine()
    with Session(engine) as session:
        session.add(
            CrawlLog(
                task_type="reclassify_genres",
                source="beatport+deezer",
                status="error",
                error_message=str(exc)[:2000],
                started_at=now,
                finished_at=now,
                duration_ms=0,
                celery_task_id=getattr(request, "id", None),
            )
        )
        session.commit()

    # Best-effort release so a failed run does not hold the single-instance lock
    # for the full TTL. Unconditional (no token check): the errback does not
    # receive the owner token; the 6h TTL is the backstop if this delete misses.
    try:
        import redis as redis_lib
        from workers.celery_app import REDIS_URL

        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        r.delete(RECLASSIFY_LOCK_KEY)
    except Exception as e:
        logger.warning("Failed to release reclassify lock in errback: %s", e)
