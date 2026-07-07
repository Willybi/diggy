"""
Celery tasks for DJ set track resolution and enrichment.
"""

import asyncio
import logging
import os
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _should_skip_backfill(cursor_date: str, min_date: str) -> bool:
    """Return True if the backfill cursor has passed the minimum date."""
    return cursor_date < min_date


def _collect_backfill_batch(
    audiostreams: list[dict],
    cursor_date: str,
    max_sets: int,
) -> tuple[list[dict], str | None]:
    """Filter audiostreams to those with addedOn < cursor_date, capped at max_sets.

    Returns (batch, oldest_added_on) where oldest_added_on is the YYYY-MM-DD date
    of the last (oldest) item in the batch, or None if the batch is empty.
    Audiostreams missing addedOn are skipped.
    """
    batch = []
    for a in audiostreams:
        added_on = a.get("addedOn")
        if not added_on:
            continue
        added_date = added_on[:10]  # YYYY-MM-DD
        if added_date >= cursor_date:
            continue
        batch.append(a)
        if len(batch) >= max_sets:
            break
    oldest = batch[-1].get("addedOn", "")[:10] if batch else None
    return batch, oldest


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


@celery_app.task(
    name="workers.tasks.crawl_trackid_latest",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def crawl_trackid_latest(self):
    """
    Crawl TrackID.net for sets published since last run.
    Uses Redis cursor trackid_crawl_last_run (ISO 8601 UTC).
    First run (no cursor): crawls last 24h.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    import redis as redis_lib
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    cursor_val = r.get("trackid_crawl_last_run")
    if cursor_val:
        last_run_ts = datetime.fromisoformat(cursor_val)
        if last_run_ts.tzinfo is None:
            last_run_ts = last_run_ts.replace(tzinfo=timezone.utc)
    else:
        last_run_ts = datetime.now(timezone.utc) - timedelta(hours=24)

    run_start = datetime.now(timezone.utc)
    engine = get_engine()

    async def _crawl_all():
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as async_sessionmaker
        from trackid.client import TrackIDClient
        from trackid.importer import import_audiostream
        from trackid.parsing import parse_trackid_date
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        async_engine = create_async_engine(os.environ["DATABASE_URL"])
        AsyncS = async_sessionmaker(async_engine, class_=AsyncSession)
        imported = 0
        skipped = 0
        pages = 0
        stop = False

        async with TrackIDClient() as client:
            current_page = 0
            page_size = 20

            while not stop:
                audiostreams, total_count = await client.search_sets(
                    sort_field="addedOn",
                    sort_direction="desc",
                    page_size=page_size,
                    current_page=current_page,
                )
                pages += 1

                if not audiostreams:
                    break

                for audiostream in audiostreams:
                    added_on_str = audiostream.get("addedOn")
                    if not added_on_str:
                        continue
                    added_on = parse_trackid_date(added_on_str)
                    if added_on is None:
                        continue
                    if added_on <= last_run_ts:
                        stop = True
                        break

                    try:
                        async with limiter.acquire("trackid"):
                            async with AsyncS() as db:
                                result, _track_count = await import_audiostream(
                                    db, client, audiostream
                                )
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
                        if result:
                            imported += 1
                        else:
                            skipped += 1
                    except Exception:
                        logger.exception(
                            "crawl_trackid_latest: failed for audiostream %s",
                            audiostream.get("id"),
                        )
                        skipped += 1

                if not stop:
                    current_page += 1
                    if current_page * page_size >= total_count:
                        break

        await async_engine.dispose()
        return imported, skipped, pages

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="crawl_trackid_latest",
            celery_task_id=self.request.id,
        ) as clog:
            imported, skipped, pages = asyncio.run(_crawl_all())

            r.set("trackid_crawl_last_run", run_start.isoformat())

            if imported > 0:
                resolve_set_tracks.delay()

            result = {"imported": imported, "skipped": skipped, "pages": pages}
            clog.set_stats(result)

    return result


@celery_app.task(
    name="workers.tasks.backfill_trackid_sets",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def backfill_trackid_sets(self):
    """
    Rattrapage historique progressif de sets TrackID.net.
    Remonte dans le temps depuis le curseur Redis trackid_backfill_cursor (YYYY-MM-DD).
    S'arrête quand le curseur dépasse TRACKID_BACKFILL_MIN_DATE ou que le batch est vide.
    """
    import asyncio
    from datetime import date, timedelta

    import redis as redis_lib
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    # Early exit if backfill already complete
    if r.get("trackid_backfill_done"):
        return {"status": "done"}

    # Config
    sets_per_day = int(os.environ.get("TRACKID_BACKFILL_SETS_PER_DAY", "500"))
    default_min = (date.today() - timedelta(days=730)).isoformat()
    min_date = os.environ.get("TRACKID_BACKFILL_MIN_DATE") or default_min

    # Init or read cursor
    cursor_date = r.get("trackid_backfill_cursor")
    if not cursor_date:
        cursor_date = date.today().isoformat()
        r.set("trackid_backfill_cursor", cursor_date)

    logger.info(
        "backfill_trackid_sets: cursor=%s min_date=%s quota=%d",
        cursor_date,
        min_date,
        sets_per_day,
    )

    # Termination check
    if _should_skip_backfill(cursor_date, min_date):
        r.set("trackid_backfill_done", "1")
        logger.info("backfill_trackid_sets: min_date reached, marking done")
        return {"status": "done", "reason": "min_date_reached"}

    engine = get_engine()

    async def _backfill_all():
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as async_sessionmaker
        from trackid.client import TrackIDClient
        from trackid.importer import import_audiostream
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        async_engine = create_async_engine(os.environ["DATABASE_URL"])
        AsyncS = async_sessionmaker(async_engine, class_=AsyncSession)

        batch: list[dict] = []
        page = 0

        async with TrackIDClient() as client:
            # Collect up to sets_per_day audiostreams with addedOn < cursor_date
            while len(batch) < sets_per_day:
                async with limiter.acquire("trackid"):
                    audiostreams, _ = await client.search_sets(
                        sort_field="addedOn",
                        sort_direction="desc",
                        page_size=20,
                        current_page=page,
                    )
                if not audiostreams:
                    break
                new_items, _ = _collect_backfill_batch(
                    audiostreams, cursor_date, sets_per_day - len(batch)
                )
                batch.extend(new_items)
                if len(audiostreams) < 20:
                    break
                page += 1

            if not batch:
                await async_engine.dispose()
                return 0, 0, None

            imported = 0
            skipped = 0

            for audiostream in batch:
                try:
                    async with limiter.acquire("trackid"):
                        async with AsyncS() as db:
                            result, _track_count = await import_audiostream(
                                db, client, audiostream
                            )
                            parent_set_id = result.parent_set_id if result else None
                            await db.commit()
                            if result:
                                imported += 1
                            if parent_set_id is not None:
                                from services.set_dedup_service import (
                                    materialize_parent,
                                )

                                try:
                                    await materialize_parent(db, parent_set_id)
                                    await db.commit()
                                except Exception:
                                    pass  # ne pas bloquer le backfill
                except Exception:
                    logger.exception(
                        "backfill_trackid_sets: failed for set %s",
                        audiostream.get("id"),
                    )
                    skipped += 1

        new_cursor = batch[-1].get("addedOn", "")[:10]
        await async_engine.dispose()
        return imported, skipped, new_cursor

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="backfill_trackid_sets",
            celery_task_id=self.request.id,
        ) as clog:
            imported, skipped, new_cursor = asyncio.run(_backfill_all())

            if new_cursor is None:
                r.set("trackid_backfill_done", "1")
                logger.info("backfill_trackid_sets: empty batch, marking done")
                result = {"status": "done", "reason": "no_more_sets"}
            else:
                r.set("trackid_backfill_cursor", new_cursor)
                logger.info("backfill_trackid_sets: new cursor=%s", new_cursor)
                if imported > 0:
                    resolve_set_tracks.delay()
                result = {
                    "status": "running",
                    "imported": imported,
                    "skipped": skipped,
                    "new_cursor": new_cursor,
                }

            clog.set_stats(result)

    return result
