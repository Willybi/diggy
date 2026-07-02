"""
Celery tasks for radar playlist crawling.
"""

import asyncio
import logging
import os
import sys

import redis as redis_lib
import requests
from workers.celery_app import celery_app

API_BASE = os.environ.get("DIGGY_API_URL", "http://api:8000")

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.crawl_radar",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def crawl_radar(self):
    """
    Crawl toutes les playlists surveillées (Deezer, TIDAL, Spotify).
    Fan-out: lance crawl_single_playlist en parallèle via Celery.
    """
    from sqlalchemy.orm import Session
    from workers.db import get_engine
    from workers.source_clients import get_fetchers

    engine = get_engine()
    resp = requests.get(f"{API_BASE}/api/watchlist/active", timeout=10)
    resp.raise_for_status()
    playlists = resp.json()
    if not isinstance(playlists, list):
        raise TypeError(
            f"Expected list from /api/watchlist/active, got {type(playlists).__name__}: {str(playlists)[:200]}"
        )

    with Session(engine) as log_session:
        from workers.crawl_logger import CrawlLogger

        with CrawlLogger(
            log_session,
            task_type="crawl_radar",
            target_label=f"{len(playlists)} playlists",
            celery_task_id=self.request.id,
        ) as clog:
            dispatched = 0
            skipped = 0
            errors = 0

            for pl in playlists:
                source = pl.get("source")
                try:
                    _, _, has_changed = get_fetchers(source)
                except ValueError:
                    logger.warning(
                        "Unknown source %s for playlist %s, skipping", source, pl["id"]
                    )
                    continue

                try:
                    if not has_changed(pl["external_id"], pl.get("last_crawled_at")):
                        skipped += 1
                        continue
                except Exception as e:
                    logger.warning(
                        "has_changed check failed for %s/%s: %s", source, pl["id"], e
                    )

                try:
                    crawl_single_playlist.delay(pl["id"])
                    dispatched += 1
                except Exception as e:
                    logger.error(
                        "Failed to dispatch crawl for %s/%s: %s", source, pl["id"], e
                    )
                    errors += 1

            clog.set_stats(
                {"dispatched": dispatched, "skipped": skipped, "errors": errors}
            )

    return {"dispatched": dispatched, "skipped_playlists": skipped, "errors": errors}


@celery_app.task(
    name="workers.tasks.crawl_single_playlist",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def crawl_single_playlist(self, playlist_id: int):
    """
    Crawl une seule playlist (Deezer, TIDAL, ou Spotify) par son watched_entity ID.
    Uses direct DB access (bulk ops) + concurrent async enrichment.
    """
    r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    lock = r.lock(f"crawl:playlist:{playlist_id}", timeout=900)
    if not lock.acquire(blocking=False):
        logger.info("Crawl already running for playlist %s, skipping", playlist_id)
        return {"skipped": True, "playlist_id": playlist_id, "reason": "lock"}

    try:
        return _crawl_single_playlist_inner(self, playlist_id)
    finally:
        try:
            lock.release()
        except redis_lib.exceptions.LockNotOwnedError:
            pass  # lock expired before we finished


def _crawl_single_playlist_inner(self, playlist_id: int):
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry, RadarTrack, UserFollow, WatchedEntity
    from services.image_service import ImageService
    from workers.db import (
        bulk_get_or_create_catalog,
        bulk_insert_radar_tracks,
        get_engine,
    )
    from workers.source_clients import get_fetchers

    engine = get_engine()

    # Load playlist info from DB directly
    with Session(engine) as session:
        entity = session.get(WatchedEntity, playlist_id)
        if not entity:
            return {"error": "playlist not found"}
        source = entity.source
        external_id = entity.external_id
        entity_title = entity.title

    try:
        fetch_meta, fetch_tracks, _ = get_fetchers(source)
    except ValueError:
        return {"error": f"unknown source: {source}"}

    ImageService.ensure_bucket("catalog-artworks")

    # 0. Fetch playlist metadata + update entity
    try:
        meta = fetch_meta(external_id)
    except Exception as e:
        err_str = str(e).lower()
        if "not found" in err_str or "404" in err_str:
            logger.warning(
                "Playlist %s (%s) no longer exists on %s — removing",
                playlist_id,
                entity_title,
                source,
            )
            with Session(engine) as session:
                session.execute(
                    sa_delete(RadarTrack).where(
                        RadarTrack.watched_entity_id == playlist_id
                    )
                )
                session.execute(
                    sa_delete(UserFollow).where(UserFollow.entity_id == playlist_id)
                )
                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    session.delete(entity)
                session.commit()
            return {
                "deleted": True,
                "playlist_id": playlist_id,
                "source": source,
                "reason": "not_found_on_source",
            }
        raise

    # CrawlLogger wraps the main work
    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="crawl_playlist",
            target_id=playlist_id,
            target_label=entity_title,
            source=source,
            celery_task_id=self.request.id,
        ) as clog:
            with Session(engine) as session:
                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    if meta.track_count is not None:
                        entity.track_count = meta.track_count
                    if meta.description:
                        entity.description = meta.description
                    if meta.owner:
                        entity.owner = meta.owner
                    if meta.title and not entity.title:
                        entity.title = meta.title
                    if not entity.has_artwork and meta.cover_url:
                        ImageService.ensure_bucket("playlist-artworks")
                        if ImageService.upload_from_url(
                            meta.cover_url, "playlist-artworks", f"{playlist_id}.jpg"
                        ):
                            entity.has_artwork = True
                    session.commit()

            # 1. Fetch all tracks from source
            source_tracks = fetch_tracks(external_id)

            # 2. Bulk insert radar tracks (direct DB, replaces per-track HTTP POST)
            with Session(engine) as session:
                # Detect initial crawl (last_crawled_at is None)
                entity_for_crawl = session.get(WatchedEntity, playlist_id)
                is_initial = entity_for_crawl is not None and entity_for_crawl.last_crawled_at is None

                track_dicts = [
                    {
                        "title": st.title,
                        "artist": st.artist,
                        "isrc": st.isrc,
                        "duration_ms": st.duration_ms,
                    }
                    for st in source_tracks
                ]
                catalog_map = bulk_get_or_create_catalog(session, track_dicts)
                crawl_result = bulk_insert_radar_tracks(
                    session, playlist_id, source, source_tracks, catalog_map,
                    is_initial_crawl=is_initial,
                )
                inserted = crawl_result["inserted"]
                removed = crawl_result["removed"]
                session.commit()

            # 3 & 4. Async enrichment (Deezer + Beatport) — concurrent
            async def _async_enrich():
                from workers.async_http import HttpPool
                from workers.enrichment import (
                    enrich_beatport_batch,
                    enrich_deezer_batch,
                )
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                dz_stats = {"enriched": 0, "errors": 0}
                bp_stats = {"enriched": 0, "not_found": 0, "errors": 0}

                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        # Preload ISRCs
                        existing_isrcs = {
                            r[0]
                            for r in session.execute(
                                select(CatalogEntry.isrc).where(
                                    CatalogEntry.isrc.isnot(None)
                                )
                            ).all()
                        }

                        # Get catalog IDs from radar tracks for this playlist
                        radar_rows = session.execute(
                            select(
                                RadarTrack.external_track_id, RadarTrack.catalog_id
                            ).where(RadarTrack.watched_entity_id == playlist_id)
                        ).all()
                        catalog_ids = {
                            row.catalog_id for row in radar_rows if row.catalog_id
                        }

                        # Deezer enrichment — entries missing deezer_id
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

                        if dz_entries:
                            ext_id_map = None
                            if source == "deezer":
                                ext_to_catalog = {
                                    row.external_track_id: row.catalog_id
                                    for row in radar_rows
                                }
                                ext_id_map = {}
                                for ext_id, cat_id in ext_to_catalog.items():
                                    if cat_id:
                                        ext_id_map[cat_id] = ext_id

                            dz_stats = await enrich_deezer_batch(
                                session,
                                dz_entries,
                                pool,
                                None,
                                existing_isrcs,
                                source=source if source == "deezer" else "cross-search",
                                ext_id_map=ext_id_map,
                            )

                        session.commit()

                        # Beatport enrichment — entries missing beatport_id
                        bp_entries = (
                            session.execute(
                                select(CatalogEntry).where(
                                    CatalogEntry.id.in_(catalog_ids),
                                    CatalogEntry.beatport_id.is_(None),
                                )
                            )
                            .scalars()
                            .all()
                        )

                        if bp_entries:
                            bp_stats = await enrich_beatport_batch(
                                session, bp_entries, pool, None
                            )

                        session.commit()

                return dz_stats, bp_stats

            try:
                dz_stats, bp_stats = asyncio.run(_async_enrich())
            except Exception:
                logger.exception("Async enrichment failed for playlist %s", playlist_id)
                raise

            # 5. Mark playlist as crawled
            with Session(engine) as session:
                from datetime import datetime, timezone

                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    entity.last_crawled_at = datetime.now(timezone.utc)
                    session.commit()

            clog.set_stats(
                {
                    "inserted": inserted,
                    "removed": removed,
                    "enriched": dz_stats.get("enriched", 0),
                    "bp_enriched": bp_stats.get("enriched", 0),
                    "total_tracks": len(source_tracks),
                }
            )

    return {
        "playlist_id": playlist_id,
        "source": source,
        "title": entity_title or (meta.title if meta else None),
        "inserted": inserted,
        "removed": removed,
        "enriched": dz_stats.get("enriched", 0),
        "bp_enriched": bp_stats.get("enriched", 0),
        "total_tracks": len(source_tracks),
    }
