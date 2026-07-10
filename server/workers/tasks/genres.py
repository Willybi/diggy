"""
Celery tasks for genre reclassification.
"""

import asyncio
import logging
import os
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.reclassify_genres_chunk",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=14400,
    time_limit=16200,
)
def reclassify_genres_chunk(self, catalog_ids: list[int], chunk_index: int = 0):
    """
    Re-classify genres for a chunk of catalog entries.
    Strategy per track: try Beatport → fallback Deezer (album) → commit.
    Existing genres are only cleared when both sources answered without
    error and found nothing; on source failure they are kept, so re-running
    the task after a network incident never destroys valid classifications.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from workers.db import get_engine

    engine = get_engine()

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

        stats = {
            "total": len(catalog_ids),
            "deezer": 0,
            "beatport": 0,
            "cleared": 0,
            "errors": 0,
        }

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
                    for i, entry in enumerate(entries):
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

        return stats

    try:
        result = asyncio.run(_async_reclassify())
    except Exception:
        logger.exception("reclassify_genres_chunk %d failed", chunk_index)
        raise

    logger.info("Chunk %d done: %s", chunk_index, result)
    return result


@celery_app.task(
    name="workers.tasks.reclassify_all_genres",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def reclassify_all_genres(self, num_chunks: int = 3):
    """
    Orchestrator: splits catalog into N chunks and dispatches them as a chord.
    Returns immediately (no result.get() inside a task); finalize_reclassify
    aggregates the stats and writes the crawl_logs line once all chunks are done.
    """
    from celery import chord, group
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from workers.db import get_engine

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
        logger.info("Reclassify: catalog is empty, nothing to dispatch")
        return {"dispatched": 0, "total": 0}

    chunk_size = (total + num_chunks - 1) // num_chunks
    chunks = [all_ids[i : i + chunk_size] for i in range(0, total, chunk_size)]

    logger.info(
        "Reclassify: dispatching %d chunks (%d tracks total, ~%d per chunk)",
        len(chunks),
        total,
        chunk_size,
    )

    callback = finalize_reclassify.s(total=total).on_error(
        reclassify_genres_error.s()
    )
    chord(
        group(reclassify_genres_chunk.s(chunk, i) for i, chunk in enumerate(chunks))
    )(callback)

    return {"dispatched": len(chunks), "total": total}


@celery_app.task(
    name="workers.tasks.finalize_reclassify",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def finalize_reclassify(self, results, total: int = 0):
    """
    Chord callback: aggregates per-chunk stats and records the single
    crawl_logs line for the whole reclassify run.
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

    logger.info("Reclassify complete: %s", agg)
    return agg


@celery_app.task(name="workers.tasks.reclassify_genres_error", bind=True)
def reclassify_genres_error(self, request, exc, traceback):
    """
    Chord errback: a chunk (or the finalize callback) failed after its retries,
    so finalize_reclassify never ran normally. Record the failure in crawl_logs
    so the run does not fail invisibly.
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
