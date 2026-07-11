"""
Celery tasks for radar playlist crawling.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

import redis as redis_lib
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# crawl_radar's beat fires every 24h sharp, but last_crawled_at is stamped at the
# END of a crawl (+queue latency +run time). Without slack, a playlist crawled
# last night reads ~23h55 < 1.0d at the next beat and would wait a whole extra
# day (daily tier → every other day). The margin cannot cause over-crawling:
# the decision is only evaluated at beat passes, which are 24h apart.
CADENCE_SLACK_DAYS = 0.25  # 6h: queue latency + crawl duration + clock skew


def _load_crawlable_playlists(session) -> list[dict]:
    """
    Every watched playlist (C6.e: crawl the whole watchlist — a follower is now
    a crawl-priority signal, not a filter). has_followers / last_changed_at /
    created_at feed the adaptive cadence applied in crawl_radar.
    """
    from sqlalchemy import select

    sys.path.insert(0, "/app")
    from models import UserFollow, WatchedEntity

    has_followers_col = (
        select(UserFollow.entity_id)
        .where(UserFollow.entity_id == WatchedEntity.id)
        .correlate(WatchedEntity)
        .exists()
        .label("has_followers")
    )
    rows = session.execute(select(WatchedEntity, has_followers_col)).all()
    return [
        {
            "id": e.id,
            "source": e.source,
            "external_id": e.external_id,
            # has_changed() implementations parse ISO strings — keep the
            # format the HTTP JSON payload used to carry (string or None)
            "last_crawled_at": (
                e.last_crawled_at.isoformat() if e.last_crawled_at else None
            ),
            "has_followers": bool(followed),
            # datetimes (not ISO): only _crawl_decision consumes these
            "last_changed_at": e.last_changed_at,
            "created_at": e.created_at,
        }
        for e, followed in rows
    ]


def _as_utc(dt):
    """Normalize a naive datetime (SQLite test runs) to UTC; PG returns aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _crawl_decision(
    now, has_followers, last_changed_at, created_at, last_crawled_at
) -> str:
    """Adaptive crawl cadence: returns 'crawl' or 'wait'.

    No 'final' state — unlike a TrackID set, a playlist can always come back to
    life, so it is never permanently abandoned. Followed playlists keep the
    daily floor (the former unconditional behaviour). For the rest, a stability
    age (now - last_changed_at, falling back to created_at) picks the backoff
    tier: <14d → daily, 14-60d → weekly, >60d → monthly. A playlist never
    crawled — or with no stability reference at all — is always due.
    """
    if has_followers:
        min_days = 1.0
    else:
        reference = last_changed_at or created_at
        if reference is None:
            return "crawl"
        stable_days = (now - _as_utc(reference)).total_seconds() / 86400
        if stable_days > 60:
            min_days = 30.0
        elif stable_days > 14:
            min_days = 7.0
        else:
            min_days = 1.0
    if last_crawled_at is None:
        return "crawl"
    crawled_days = (now - _as_utc(last_crawled_at)).total_seconds() / 86400
    return "crawl" if crawled_days > min_days - CADENCE_SLACK_DAYS else "wait"


def _select_crawl_batch(playlists, now, max_dispatch):
    """Pick the playlists due for a crawl this run (C6.e).

    Drops those still inside their cadence window (skipped_cadence), then orders
    the rest — followed playlists first, most-recently-changed next — and caps
    the fan-out at max_dispatch so the cap sheds the lowest-priority playlists
    (dropped_by_cap counts the overflow). Same sort+cap idiom as
    recrawl_incomplete_sets. Returns (batch, skipped_cadence, dropped_by_cap).
    """
    eligible = []
    skipped_cadence = 0
    for pl in playlists:
        lc_iso = pl.get("last_crawled_at")
        last_crawled = datetime.fromisoformat(lc_iso) if lc_iso else None
        decision = _crawl_decision(
            now,
            pl["has_followers"],
            pl.get("last_changed_at"),
            pl.get("created_at"),
            last_crawled,
        )
        if decision == "crawl":
            eligible.append(pl)
        else:
            skipped_cadence += 1

    # Newest change first (recrawl cap idiom); then followed playlists ahead of
    # the rest — the stable sort keeps the recency order within each group.
    eligible.sort(
        key=lambda pl: _as_utc(pl.get("last_changed_at") or pl.get("created_at"))
        if (pl.get("last_changed_at") or pl.get("created_at"))
        else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    eligible.sort(key=lambda pl: not pl["has_followers"])

    dropped_by_cap = 0
    if len(eligible) > max_dispatch:
        dropped_by_cap = len(eligible) - max_dispatch
        logger.warning(
            "crawl_radar: cap %d reached, dropping %d lower-priority playlists",
            max_dispatch,
            dropped_by_cap,
        )
        eligible = eligible[:max_dispatch]
    return eligible, skipped_cadence, dropped_by_cap


def _is_initial_crawl(last_crawled_at, now) -> bool:
    """Whether a crawl's diff must be kept out of trend velocity (is_initial).

    True when the playlist was never crawled or has been dormant for over 30
    days — a reawakened playlist dumps its whole accumulated diff at once, which
    must not count as a burst of activity.
    """
    from datetime import timedelta

    if last_crawled_at is None:
        return True
    return _as_utc(last_crawled_at) < now - timedelta(days=30)


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
    Cadence adaptative (C6.e) puis fan-out: lance crawl_single_playlist en
    parallèle via Celery.
    """
    from sqlalchemy.orm import Session
    from workers.db import get_engine
    from workers.source_clients import get_fetchers

    now = datetime.now(timezone.utc)
    max_dispatch = int(os.environ.get("CRAWL_RADAR_MAX_DISPATCH", "200"))

    engine = get_engine()
    with Session(engine) as session:
        playlists = _load_crawlable_playlists(session)

    batch, skipped_cadence, dropped_by_cap = _select_crawl_batch(
        playlists, now, max_dispatch
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

            for pl in batch:
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
                {
                    "dispatched": dispatched,
                    "skipped": skipped,
                    "skipped_cadence": skipped_cadence,
                    "dropped_by_cap": dropped_by_cap,
                    "errors": errors,
                }
            )

    return {
        "dispatched": dispatched,
        "skipped_playlists": skipped,
        "skipped_cadence": skipped_cadence,
        "dropped_by_cap": dropped_by_cap,
        "errors": errors,
    }


@celery_app.task(
    name="workers.tasks.crawl_single_playlist",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=3600,
    time_limit=4500,
)
def crawl_single_playlist(self, playlist_id: int):
    """
    Crawl une seule playlist (Deezer, TIDAL, ou Spotify) par son watched_entity ID.
    Uses direct DB access (bulk ops) + concurrent async enrichment.
    """
    r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    # Lock timeout must exceed the task's time_limit (4500s) so it cannot expire mid-run
    lock = r.lock(f"crawl:playlist:{playlist_id}", timeout=4600)
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
    from services.image_service import BUCKET_PLAYLIST, ImageService
    from workers.db import (
        bulk_get_or_create_catalog,
        bulk_insert_radar_tracks,
        get_engine,
    )
    from workers.source_clients import PlaylistGoneError, get_fetchers

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
    except PlaylistGoneError:
        # Source confirmed the playlist no longer exists; any other
        # exception propagates and lets Celery autoretry the task.
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
                        ImageService.ensure_bucket(BUCKET_PLAYLIST)
                        if ImageService.upload_from_url(
                            meta.cover_url, BUCKET_PLAYLIST, f"{playlist_id}.jpg"
                        ):
                            entity.has_artwork = True
                    session.commit()

            # 1. Fetch all tracks from source
            source_tracks = fetch_tracks(external_id)

            # 2. Bulk insert radar tracks (direct DB, replaces per-track HTTP POST)
            with Session(engine) as session:
                # C6.e: never crawled OR dormant >30d counts as an initial crawl
                # so the accumulated diff stays out of trend velocity
                entity_for_crawl = session.get(WatchedEntity, playlist_id)
                is_initial = entity_for_crawl is not None and _is_initial_crawl(
                    entity_for_crawl.last_crawled_at, datetime.now(timezone.utc)
                )

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
                from datetime import datetime, timezone

                from workers.async_http import HttpPool
                from workers.enrichment import (
                    enrich_beatport_batch,
                    enrich_deezer_batch,
                    not_recently_searched,
                )
                from workers.rate_limiter import RateLimiter

                limiter = RateLimiter()
                now = datetime.now(timezone.utc)
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
                                    not_recently_searched(
                                        CatalogEntry.deezer_searched_at, now
                                    ),
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
                                    not_recently_searched(
                                        CatalogEntry.beatport_searched_at, now
                                    ),
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
                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    now = datetime.now(timezone.utc)
                    entity.last_crawled_at = now
                    # C6.e: only a real diff (insert or removal) advances the
                    # cadence clock; a no-op crawl leaves last_changed_at alone
                    if inserted or removed:
                        entity.last_changed_at = now
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
