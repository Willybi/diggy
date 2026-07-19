"""
Celery tasks for DJ set track resolution and enrichment.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lock TTL must cover the task's time_limit (2400s) so the lock cannot
# expire while a legitimate run is still in progress
RESOLVE_SET_TRACKS_LOCK_TTL = 2700

# Same rule for recrawl_incomplete_sets (time_limit 3900s)
RECRAWL_INCOMPLETE_SETS_LOCK_TTL = 4200

# Same rule for backfill_trackid_sets (time_limit 3900s)
BACKFILL_TRACKID_SETS_LOCK_TTL = 4200

# recrawl_incomplete_sets' beat fires every 24h sharp, but the reference is
# stamped during the previous run. Without slack, a set re-crawled last night
# reads ~23h55 < 1.0d at the next beat and would wait a whole extra day (daily
# tier → every other day). The margin cannot cause over-crawling: the decision
# is only evaluated at beat passes, which are 24h apart. (>90d → 'final' is
# untouched: it is not a cadence gate.)
CADENCE_SLACK_DAYS = 0.25  # 6h: queue latency + crawl duration + clock skew


def _should_skip_backfill(cursor_date: str, min_date: str) -> bool:
    """Return True if the backfill cursor has passed the minimum date."""
    return cursor_date < min_date


def _collect_backfill_batch(
    audiostreams: list[dict],
    cursor_date: str,
    max_sets: int,
) -> tuple[list[dict], str | None]:
    """Filter audiostreams to those with addedOn < cursor_date, capped at max_sets.

    Returns (batch, oldest_added_on) where oldest_added_on is the FULL addedOn
    timestamp of the last (oldest) item in the batch, or None if the batch is
    empty. Audiostreams missing addedOn are skipped.

    The filter compares the FULL ISO8601 addedOn (lexicographically), not just
    its date: two sets added the same day either side of the cursor are split
    correctly, where the old date-only truncation dropped the whole tail of the
    cursor's day. Legacy compatibility needs no shim — a date-only cursor left
    by an older build ("2026-06-10") is a lexicographic prefix of every
    timestamp that day, so any "2026-06-10T..." item still satisfies
    >= "2026-06-10" and is skipped, exactly the previous semantics; the cursor
    turns into a full timestamp on its first rewrite.
    """
    batch = []
    for a in audiostreams:
        added_on = a.get("addedOn")
        if not added_on:
            continue
        if added_on >= cursor_date:
            continue
        batch.append(a)
        if len(batch) >= max_sets:
            break
    oldest = batch[-1].get("addedOn", "") if batch else None
    return batch, oldest


def _resume_page_decision(
    start_page: int,
    first_added_on: str | None,
    cursor_date: str,
) -> int:
    """Decide which listing page to start collecting from when resuming.

    Inputs: the persisted offset (start_page), the addedOn of the FIRST
    audiostream fetched at that offset (None when the page came back empty),
    and the current cursor. Returns:
      - start_page for a normal resume — the offset still sits at or above the
        cursor (its first item is newer-or-equal, older content lies below);
      - 0 to force a full re-page when the offset is stale (Guard 1: empty page,
        sets were deleted upstream and the offset points past the end) or has
        overshot (Guard 2: first item already older than the cursor, so content
        moved up and untreated sets may sit between the cursor and this offset).
    start_page <= 0 always returns 0: there is nothing to validate.
    """
    if start_page <= 0:
        return 0
    if not first_added_on:
        return 0  # Guard 1: empty page at the saved offset → re-page from top
    if first_added_on < cursor_date:
        return 0  # Guard 2: overshoot → re-page from top
    return start_page


@celery_app.task(
    name="workers.tasks.resolve_set_tracks",
    bind=True,
    # Resolution-only (bulk catalog linking, no external API calls) → fast, stays
    # well under a short limit even for a full night's inflow. Enrichment of the
    # freshly-linked entries is owned by the nightly enrich_catalog /
    # enrich_catalog_beatport tasks on the dedicated enrich worker (their E1
    # budgets + re-scan backoff are the single point of throughput control).
    # Deliberately NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS an
    # Exception, so that decorator would turn a timeout into a retry loop (same
    # footgun as the artist backlog tasks). The Redis lock + idempotent bulk
    # resolve + nightly re-dispatch are the guards.
    soft_time_limit=1800,
    time_limit=2400,
)
def resolve_set_tracks(self):
    """
    Résout les set_tracks sans catalog_id (liage catalog en masse uniquement).
    L'enrichissement Deezer/Beatport des entrées liées est laissé aux tâches
    nightly enrich_catalog / enrich_catalog_beatport (worker enrich dédié).
    Single-instance: a Redis lock skips the run if another one is in flight
    (three beat tasks and the API all dispatch this task fire-and-forget).
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:resolve_set_tracks"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=RESOLVE_SET_TRACKS_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "resolve_set_tracks already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_resolve_set_tracks(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_resolve_set_tracks(task):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import SetTrack
    from workers.crawl_logger import CrawlLogger
    from workers.db import bulk_get_or_create_catalog, get_engine

    engine = get_engine()

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session, task_type="resolve_set_tracks", celery_task_id=task.request.id
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
                    clog.set_stats({"resolved": 0})
                    return {"resolved": 0}

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

                session.commit()

            result = {"resolved": resolved}
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


def _as_utc(dt):
    """Normalize a naive datetime (SQLite test runs) to UTC; PG returns aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _completion_pct(total: int, unidentified: int) -> float:
    """Share of identified tracks, based on is_id ONLY.

    catalog_id is deliberately ignored: import_audiostream deletes and
    re-inserts set_tracks, resetting catalog_id to NULL until the next
    asynchronous resolve_set_tracks run — a catalog_id-based ratio would be
    wrong between the two.
    """
    if total <= 0:
        return 0.0
    return (total - unidentified) / total


def _recrawl_decision(now, created_at, reference) -> str:
    """Age-tiered re-crawl backoff: returns 'crawl', 'wait' or 'final'.

    Age counts from created_at (Diggy import date); reference is the last
    (re-)crawl, COALESCE(last_recrawl_at, last_crawled_at). Tiers:
    0-7d → re-crawl after 24h, 7-30d → after 7d, 30-90d → after 30d,
    >90d → final (no more crawls).
    """
    age_days = 0.0
    if created_at is not None:
        age_days = (now - _as_utc(created_at)).total_seconds() / 86400
    if age_days > 90:
        return "final"
    if age_days > 30:
        min_days = 30.0
    elif age_days > 7:
        min_days = 7.0
    else:
        min_days = 1.0
    if reference is None:
        return "crawl"
    ref_days = (now - _as_utc(reference)).total_seconds() / 86400
    return "crawl" if ref_days > min_days - CADENCE_SLACK_DAYS else "wait"


def _apply_recrawl_outcome(dj_set, old_pct, new_pct, now) -> str | None:
    """Update a set's re-crawl state after a fresh import.

    recrawl_count counts CONSECUTIVE re-crawls without progression and is
    reset to 0 whenever completion_pct improves (old NULL counts as
    progression). Returns 'complete' or 'stale' when the set is finalized,
    None otherwise.
    """
    if old_pct is None or new_pct > old_pct:
        dj_set.recrawl_count = 0
    else:
        dj_set.recrawl_count = (dj_set.recrawl_count or 0) + 1

    finalized = None
    if new_pct >= 1.0:
        finalized = "complete"
    elif dj_set.recrawl_count >= 3:
        finalized = "stale"
    if finalized:
        dj_set.recrawl_status = "final"

    dj_set.completion_pct = new_pct
    dj_set.last_recrawl_at = now
    return finalized


@celery_app.task(
    name="workers.tasks.recrawl_incomplete_sets",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=3600,
    time_limit=3900,
)
def recrawl_incomplete_sets(self):
    """
    Re-crawl incomplete TrackID sets with an age-tiered backoff (TrackID
    keeps identifying tracks for days after a set is first imported).
    Single-instance: Redis lock, same pattern as resolve_set_tracks.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:recrawl_incomplete_sets"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=RECRAWL_INCOMPLETE_SETS_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "recrawl_incomplete_sets already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_recrawl_incomplete_sets(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_recrawl_incomplete_sets(task):
    from sqlalchemy import case, func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import DJSet, SetTrack
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()
    max_sets = int(os.environ.get("RECRAWL_MAX_SETS_PER_RUN", "500"))

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="recrawl_incomplete_sets",
            celery_task_id=task.request.id,
        ) as clog:
            now = datetime.now(timezone.utc)
            finalized_complete = 0
            finalized_age = 0
            to_crawl = []

            with Session(engine) as session:
                counts = (
                    select(
                        SetTrack.set_id.label("set_id"),
                        func.count(SetTrack.id).label("total"),
                        func.sum(
                            case((SetTrack.is_id.is_(True), 1), else_=0)
                        ).label("unidentified"),
                    )
                    .group_by(SetTrack.set_id)
                    .subquery()
                )
                rows = session.execute(
                    select(DJSet, counts.c.total, counts.c.unidentified)
                    .outerjoin(counts, counts.c.set_id == DJSet.id)
                    .where(
                        DJSet.source == "trackid",
                        DJSet.is_virtual.is_(False),
                        DJSet.recrawl_status == "active",
                    )
                ).all()

                for dj_set, total, unidentified in rows:
                    total = total or 0
                    unidentified = unidentified or 0

                    # Bulk pre-pass: already fully identified → close it
                    # without crawling
                    if total > 0 and unidentified == 0:
                        dj_set.completion_pct = 1.0
                        dj_set.recrawl_status = "final"
                        finalized_complete += 1
                        continue

                    decision = _recrawl_decision(
                        now,
                        dj_set.created_at,
                        dj_set.last_recrawl_at or dj_set.last_crawled_at,
                    )
                    if decision == "final":
                        dj_set.recrawl_status = "final"
                        finalized_age += 1
                    elif decision == "crawl":
                        to_crawl.append(
                            {
                                "id": dj_set.id,
                                "ext_id": dj_set.external_id,
                                "slug": dj_set.external_slug,
                                "old_pct": dj_set.completion_pct,
                                "created_at": dj_set.created_at,
                            }
                        )
                session.commit()

            # Newest first, so the cap drops the oldest sets
            to_crawl.sort(
                key=lambda s: _as_utc(s["created_at"])
                if s["created_at"]
                else datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            eligible = len(to_crawl)
            dropped_by_cap = 0
            if eligible > max_sets:
                dropped_by_cap = eligible - max_sets
                to_crawl = to_crawl[:max_sets]
                logger.warning(
                    "recrawl_incomplete_sets: cap %d reached, dropping %d older sets",
                    max_sets,
                    dropped_by_cap,
                )

            if not to_crawl:
                result = {
                    "eligible": eligible,
                    "crawled": 0,
                    "finalized_complete": finalized_complete,
                    "finalized_age": finalized_age,
                    "finalized_stale": 0,
                    "errors": 0,
                    "dropped_by_cap": dropped_by_cap,
                }
                clog.set_stats(result)
                return result

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
                completed = 0
                stale = 0
                errors = 0

                async with TrackIDClient() as client:
                    for info in to_crawl:
                        if not info["slug"]:
                            continue
                        try:
                            async with limiter.acquire("trackid"):
                                async with AsyncS() as db:
                                    audiostream = {
                                        "id": info["ext_id"],
                                        "slug": info["slug"],
                                    }
                                    result, _track_count = await import_audiostream(
                                        db, client, audiostream, min_age_hours=0
                                    )
                                    if result is None:
                                        # Detail fetch failed: an outage is
                                        # not an attempt, leave the re-crawl
                                        # state untouched
                                        errors += 1
                                        continue

                                    total = (
                                        await db.execute(
                                            select(func.count(SetTrack.id)).where(
                                                SetTrack.set_id == result.id
                                            )
                                        )
                                    ).scalar() or 0
                                    unidentified = (
                                        await db.execute(
                                            select(func.count(SetTrack.id)).where(
                                                SetTrack.set_id == result.id,
                                                SetTrack.is_id.is_(True),
                                            )
                                        )
                                    ).scalar() or 0
                                    finalized = _apply_recrawl_outcome(
                                        result,
                                        info["old_pct"],
                                        _completion_pct(total, unidentified),
                                        datetime.now(timezone.utc),
                                    )
                                    if finalized == "complete":
                                        completed += 1
                                    elif finalized == "stale":
                                        stale += 1
                                    crawled += 1
                                    parent_set_id = result.parent_set_id
                                    await db.commit()
                                    if parent_set_id is not None:
                                        from services.set_dedup_service import (
                                            materialize_parent,
                                        )
                                        try:
                                            await materialize_parent(db, parent_set_id)
                                            await db.commit()
                                        except Exception:
                                            # ne pas bloquer le crawl
                                            logger.warning(
                                                "materialize_parent failed for set %s",
                                                parent_set_id,
                                                exc_info=True,
                                            )
                        except Exception:
                            errors += 1
                            logger.exception(
                                "recrawl_incomplete_sets: failed for set %s",
                                info.get("slug"),
                            )

                await async_engine.dispose()
                return crawled, completed, stale, errors

            crawled, completed, finalized_stale, errors = asyncio.run(_crawl_all())
            finalized_complete += completed

            # Trigger track resolution for updated sets
            if crawled > 0:
                resolve_set_tracks.delay()

            result = {
                "eligible": eligible,
                "crawled": crawled,
                "finalized_complete": finalized_complete,
                "finalized_age": finalized_age,
                "finalized_stale": finalized_stale,
                "errors": errors,
                "dropped_by_cap": dropped_by_cap,
            }
            clog.set_stats(result)

    return result


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
                                        # ne pas bloquer le crawl
                                        logger.warning(
                                            "materialize_parent failed for set %s",
                                            parent_set_id,
                                            exc_info=True,
                                        )
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
    # A batch of up to 1000 inline set imports (rate-limited detail fetch per
    # set) never fits in the global 1800s limit, so give this task its own
    # budget, kept under the broker visibility_timeout (30000s) to avoid
    # duplicate deliveries. Deliberately NO autoretry_for=(Exception,):
    # SoftTimeLimitExceeded IS an Exception, so autoretry would spawn four
    # 30-min timeouts then DLQ every night. Progress is instead made resumable
    # by advancing the Redis cursor inline and catching SoftTimeLimitExceeded
    # gracefully (see below), so a re-raise/retry is neither needed nor wanted.
    soft_time_limit=3600,
    time_limit=3900,
)
def backfill_trackid_sets(self):
    """
    Rattrapage historique progressif de sets TrackID.net.
    Remonte dans le temps depuis le curseur Redis trackid_backfill_cursor
    (timestamp ISO8601 complet ; les anciennes valeurs date-only restent
    compatibles par comparaison lexicographique) et reprend la pagination à
    l'offset persisté trackid_backfill_page.
    S'arrête quand le curseur dépasse TRACKID_BACKFILL_MIN_DATE ou que le batch est vide.
    Single-instance: a Redis lock skips the run if another one is still in
    flight (a slow run can overlap the next daily beat), same pattern as
    resolve_set_tracks / recrawl_incomplete_sets.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:backfill_trackid_sets"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=BACKFILL_TRACKID_SETS_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "backfill_trackid_sets already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_backfill_trackid_sets(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_backfill_trackid_sets(task):
    import asyncio
    from datetime import date, timedelta

    import redis as redis_lib
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    # Early exit if backfill already complete
    if r.get("trackid_backfill_done"):
        return {"status": "done"}

    # Config. 1000 sets/night matches the downstream capacity: Beatport
    # enrichment handles ~6000 tracks/night and a set yields ~5 new tracks, so
    # ~750-1400 new tracks/day here stays within that budget while draining the
    # ~100k-set historical backlog meaningfully faster than the old 500.
    sets_per_day = int(os.environ.get("TRACKID_BACKFILL_SETS_PER_DAY", "1000"))
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
        # Resume paging from the persisted offset instead of re-scanning from
        # page 0 every night: the listing keeps growing at the top, so a fixed
        # start would push the skip-scan (items newer than the cursor) ever
        # deeper. start_page is validated on the first fetch before it is
        # trusted (see _resume_page_decision).
        start_page = int(r.get("trackid_backfill_page") or 0)
        page = start_page
        # Page index of the last page that actually contributed sets to the
        # batch — where the oldest (cursor) set lives. Persisted only on a
        # complete batch, so the saved offset always sits at or above (newer
        # than) the cursor position.
        last_collected_page = start_page
        resume_checked = False

        async with TrackIDClient() as client:
            # Collect up to sets_per_day audiostreams with addedOn < cursor_date.
            # No except swallows a soft-timeout here, so it propagates cleanly to
            # the task-level handler; nothing is imported yet, so no progress is
            # lost and the next run resumes from the unchanged cursor.
            while len(batch) < sets_per_day:
                async with limiter.acquire("trackid"):
                    audiostreams, _ = await client.search_sets(
                        sort_field="addedOn",
                        sort_direction="desc",
                        page_size=20,
                        current_page=page,
                    )

                # First fetch of a resumed run: validate the saved offset. A
                # stale/overshot offset falls back to a full re-page — it must
                # NOT be read as "empty → no more sets → done".
                if not resume_checked:
                    resume_checked = True
                    if start_page > 0:
                        first_added = (
                            audiostreams[0].get("addedOn", "")
                            if audiostreams
                            else None
                        )
                        if (
                            _resume_page_decision(start_page, first_added, cursor_date)
                            != start_page
                        ):
                            logger.warning(
                                "backfill_trackid_sets: saved page %d unusable "
                                "(first=%s cursor=%s), restarting from page 0",
                                start_page,
                                first_added,
                                cursor_date,
                            )
                            page = 0
                            last_collected_page = 0
                            continue

                if not audiostreams:
                    break
                new_items, _ = _collect_backfill_batch(
                    audiostreams, cursor_date, sets_per_day - len(batch)
                )
                if new_items:
                    batch.extend(new_items)
                    last_collected_page = page
                if len(audiostreams) < 20:
                    break
                page += 1

            if not batch:
                await async_engine.dispose()
                return 0, 0, None, None

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
                                except SoftTimeLimitExceeded:
                                    # Never let the soft limit be mistaken for a
                                    # materialize failure — it must reach the
                                    # per-set handler below and stop the loop.
                                    raise
                                except Exception:
                                    # ne pas bloquer le backfill
                                    logger.warning(
                                        "materialize_parent failed for set %s",
                                        parent_set_id,
                                        exc_info=True,
                                    )
                    # Advance the cursor after each processed set. The batch is
                    # newest→oldest (addedOn desc), so the cursor decreases
                    # monotonically: a soft-timeout mid-batch leaves it on the
                    # last set handled and the next run resumes from there. The
                    # cursor stores the FULL addedOn timestamp so sets sharing
                    # the oldest processed day are not dropped next run (the
                    # date-only truncation was the historical data-loss bug).
                    added_on = audiostream.get("addedOn", "")
                    if added_on:
                        r.set("trackid_backfill_cursor", added_on)
                except SoftTimeLimitExceeded:
                    # Re-raise BEFORE the generic handler: SoftTimeLimitExceeded
                    # IS an Exception, so without this clause it would be
                    # swallowed and the loop would run to the hard time_limit
                    # SIGKILL. The cursor is already persisted up to the last
                    # fully-processed set.
                    raise
                except Exception:
                    logger.exception(
                        "backfill_trackid_sets: failed for set %s",
                        audiostream.get("id"),
                    )
                    skipped += 1

        new_cursor = batch[-1].get("addedOn", "")
        await async_engine.dispose()
        return imported, skipped, new_cursor, last_collected_page

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="backfill_trackid_sets",
            celery_task_id=task.request.id,
        ) as clog:
            try:
                imported, skipped, new_cursor, end_page = asyncio.run(_backfill_all())
            except SoftTimeLimitExceeded:
                # The cursor was advanced inline in the import loop, so progress
                # is already persisted; kick off resolution of what was imported
                # and return normally. Re-raising would route the task to the
                # DLQ (no autoretry is present to absorb it) and lose nothing.
                # The page offset is deliberately NOT persisted on this path:
                # collection ran further (older) than the import reached, so the
                # end-of-collection page sits below the cursor — saving it would
                # skip the un-imported tail. The next run resumes from the
                # previous offset (re-scanning a batch's worth of pages is the
                # accepted cost).
                logger.warning(
                    "backfill_trackid_sets: cut by soft time limit, cursor=%s "
                    "(progress persisted, next run resumes)",
                    r.get("trackid_backfill_cursor"),
                )
                resolve_set_tracks.delay()
                result = {"status": "interrupted"}
                clog.set_stats(result)
                return result

            if new_cursor is None:
                r.set("trackid_backfill_done", "1")
                r.delete("trackid_backfill_page")
                logger.info("backfill_trackid_sets: empty batch, marking done")
                result = {"status": "done", "reason": "no_more_sets"}
            else:
                r.set("trackid_backfill_cursor", new_cursor)
                # Persist the paging offset ONLY here, next to the cursor, on a
                # complete batch: end_page is the page of the oldest imported set
                # and is guaranteed at or above (newer than) the cursor.
                if end_page is not None:
                    r.set("trackid_backfill_page", end_page)
                logger.info(
                    "backfill_trackid_sets: new cursor=%s page=%s",
                    new_cursor,
                    end_page,
                )
                if imported > 0:
                    resolve_set_tracks.delay()
                result = {
                    "status": "running",
                    "imported": imported,
                    "skipped": skipped,
                    "new_cursor": new_cursor,
                    "page": end_page,
                }

            clog.set_stats(result)

    return result
