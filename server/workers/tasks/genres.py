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
    Strategy per track: clear genre → try Beatport → fallback Deezer (album) → commit.
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
        except Exception:
            pass

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
                        entry.genres = []
                        found = False

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

                        if not found:
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
    soft_time_limit=25200,
    time_limit=28800,
)
def reclassify_all_genres(self, num_chunks: int = 3):
    """
    Orchestrator: splits catalog into N chunks and dispatches parallel workers.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from workers.crawl_logger import CrawlLogger
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
    chunk_size = (total + num_chunks - 1) // num_chunks
    chunks = [all_ids[i : i + chunk_size] for i in range(0, total, chunk_size)]

    logger.info(
        "Reclassify: dispatching %d chunks (%d tracks total, ~%d per chunk)",
        len(chunks),
        total,
        chunk_size,
    )

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="reclassify_genres",
            source="beatport+deezer",
            celery_task_id=self.request.id,
        ) as clog:
            from celery import group

            job = group(
                reclassify_genres_chunk.s(chunk, i) for i, chunk in enumerate(chunks)
            )
            result = job.apply_async()
            result.get(disable_sync_subtasks=False, timeout=25200)

            # Aggregate stats from all chunks
            agg = {
                "total": total,
                "deezer": 0,
                "beatport": 0,
                "cleared": 0,
                "errors": 0,
            }
            for chunk_result in result.results:
                if chunk_result.successful():
                    r = chunk_result.result
                    for k in ("deezer", "beatport", "cleared", "errors"):
                        agg[k] += r.get(k, 0)

            logger.info("Reclassify complete: %s", agg)
            clog.set_stats(agg)

    return agg
