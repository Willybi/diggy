"""Celery task: nightly YouTube DJ-set watch (C14.b, YouTube-first slice).

Iterates the watched ``channels`` (``platform='youtube'``), pulls each channel's
RSS/Atom feed, keeps the "long" videos (= DJ sets, via the duration gate) and
creates metadata-only sets through the L2 client (``workers.youtube``). No model,
service or front change — pure orchestration of the L2 building blocks.

Skeleton mirrors ``tasks/sets.py``: a Redis single-instance lock in the wrapper
(SET NX EX + conditional release), a ``CrawlLogger`` on a sync ``Session``,
per-channel inline commits (so the work survives an interruption), an AV9
internal monotonic deadline (checked BEFORE each channel, module ``time`` so it is
fakeable in tests without touching the event loop's clock), and deliberately NO
``autoretry_for=(Exception,)`` (``SoftTimeLimitExceeded`` IS an ``Exception`` →
that decorator turns a soft timeout into a retry loop).

Invariants honoured: an HTTP outage (``YouTubeHTTPError``) is NOT a check — it
never fails the other channels and never stamps ``last_checked_at`` on the failed
channel (the next run retries it). A missing ``YOUTUBE_API_KEY`` (needed for the
duration gate) is a graceful no-op, never a crash.
"""

import asyncio
import logging
import os
import sys
import time

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Soft/hard limits + lock TTL. Extracted as module constants so the decorator AND
# the internal deadline guard share ONE source of truth (AV9 — never read
# task.soft_time_limit at runtime). The TTL is STRICTLY above the hard time_limit
# so a live run's lock can never expire under it; a worker killed mid-run leaves an
# orphan lock that self-heals within the TTL.
YOUTUBE_CRAWL_SOFT_TIME_LIMIT = 1800
YOUTUBE_CRAWL_TIME_LIMIT = 2100
YOUTUBE_CRAWL_LOCK_TTL = 2400

# AV9 — margin (seconds) subtracted from the soft limit to build an internal
# monotonic deadline checked before each channel. billiard's SoftTimeLimitExceeded
# can fire mid-write and be swallowed by the asyncio transport's error handler
# (DIGGY-APP-J), never reaching the task's except clause → the run dies at the hard
# limit (SIGKILL). The deadline exits the loop cleanly WITHOUT depending on signal
# delivery; the SoftTimeLimitExceeded catch stays in place as defense in depth.
YOUTUBE_CRAWL_DEADLINE_MARGIN = int(
    os.environ.get("YOUTUBE_CRAWL_DEADLINE_MARGIN", "120")
)

# ── Backfill (L7): one-shot historical catch-up dispatched on channel add ─────
# Same shape and rules as the crawl limits — own lock TTL STRICTLY above the hard
# time_limit, soft/time_limit + deadline margin as module constants shared by the
# decorator AND the internal deadline guard (AV9, one source of truth).
YOUTUBE_BACKFILL_SOFT_TIME_LIMIT = 1800
YOUTUBE_BACKFILL_TIME_LIMIT = 2100
YOUTUBE_BACKFILL_LOCK_TTL = 2400
YOUTUBE_BACKFILL_DEADLINE_MARGIN = int(
    os.environ.get("YOUTUBE_BACKFILL_DEADLINE_MARGIN", "120")
)
# Videos per DB transaction (also the durations-API batch size); the internal
# deadline is checked between batches so a long history exits cleanly mid-run.
YOUTUBE_BACKFILL_BATCH = 50


@celery_app.task(
    name="workers.tasks.crawl_youtube_channels",
    bind=True,
    # Deliberately NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS an
    # Exception, so that decorator would turn a soft timeout into a retry loop
    # (same footgun as the sets/artist backlog tasks). The Redis lock + per-channel
    # inline commits + the internal deadline guard are what bound the run.
    soft_time_limit=YOUTUBE_CRAWL_SOFT_TIME_LIMIT,
    time_limit=YOUTUBE_CRAWL_TIME_LIMIT,
)
def crawl_youtube_channels(self):
    """Nightly: poll every watched YouTube channel for new DJ sets (C14.b).

    Single-instance: a Redis lock skips the run if another one is still in flight.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:crawl_youtube_channels"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=YOUTUBE_CRAWL_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "crawl_youtube_channels already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_crawl_youtube_channels(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run).
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_crawl_youtube_channels(task):
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    # AV9 internal deadline (see YOUTUBE_CRAWL_DEADLINE_MARGIN): checked at the top
    # of each channel iteration so a shortened run exits cleanly without depending
    # on the SoftTimeLimitExceeded signal being delivered.
    deadline = (
        time.monotonic()
        + YOUTUBE_CRAWL_SOFT_TIME_LIMIT
        - YOUTUBE_CRAWL_DEADLINE_MARGIN
    )
    # Read the Data-API key at RUNTIME (a `docker compose up -d` applies a change
    # without a code redeploy). It gates the duration lookup; absent → no-op.
    api_key = os.environ.get("YOUTUBE_API_KEY", "")

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="crawl_youtube_channels",
            celery_task_id=task.request.id,
        ) as clog:
            try:
                stats = asyncio.run(
                    _crawl_driver(api_key=api_key, deadline=deadline)
                )
            except SoftTimeLimitExceeded:
                # The signal reached the task despite the deadline guard: every
                # channel is committed inline, so progress is persisted. Flush a
                # partial log and return normally instead of routing to the DLQ (no
                # autoretry is present to absorb it); the next run resumes from the
                # least-recently-checked channels (last_checked_at ordering).
                logger.warning(
                    "crawl_youtube_channels: cut by soft time limit "
                    "(per-channel progress persisted, next run resumes)"
                )
                stats = {"status": "interrupted"}
            clog.set_stats(stats)

    return stats


async def _crawl_driver(*, api_key, deadline):
    """Build the async engine + HTTP client + rate limiter, then run the core.

    Kept thin so the real work (:func:`_crawl_channels`) stays fully injectable
    for unit tests (an in-memory engine + a fake limiter/client). Disposes the
    engine and closes the client in ``finally``.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sessionmaker
    from workers import youtube
    from workers.rate_limiter import RateLimiter

    limiter = RateLimiter()
    async_engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession)
    client = youtube.default_client()
    try:
        async with client:
            return await _crawl_channels(
                session_factory,
                client,
                limiter,
                api_key=api_key,
                deadline=deadline,
            )
    finally:
        await async_engine.dispose()


async def _crawl_channels(session_factory, client, limiter, *, api_key, deadline):
    """Iterate the watched YouTube channels and create metadata-only sets.

    ``session_factory`` is an async ``sessionmaker``; ``client`` an injected
    ``httpx.AsyncClient`` (passed through to the L2 cores); ``limiter`` a
    ``RateLimiter`` (or stand-in) whose ``acquire('youtube')`` is an async CM.
    Returns the stats dict ``{channels, videos_seen, sets_created, deadline_hit}``.
    """
    from datetime import datetime, timezone

    from models import Channel, DJSet
    from sqlalchemy import select, update
    from workers import youtube

    stats = {
        "channels": 0,
        "videos_seen": 0,
        "sets_created": 0,
        "deadline_hit": False,
    }

    # No Data-API key → we cannot gate durations, so the run can't decide which
    # videos are sets. Warn and no-op WITHOUT stamping last_checked_at, so every
    # channel stays due once a key is configured (graceful, never a crash).
    if not api_key:
        logger.warning(
            "crawl_youtube_channels: no YOUTUBE_API_KEY set — skipping run "
            "(channels left un-checked for a later run)"
        )
        return stats

    # Worklist: watched, non-excluded, resolved youtube channels, least recently
    # checked first (NULLS FIRST → a never-checked channel wins). Read into plain
    # tuples (detached) so no per-channel commit expires ORM state.
    async with session_factory() as db:
        result = await db.execute(
            select(Channel.id, Channel.external_id, Channel.name)
            .where(
                Channel.platform == "youtube",
                Channel.watched.is_(True),
                Channel.excluded.isnot(True),
                Channel.external_id.isnot(None),
            )
            .order_by(Channel.last_checked_at.asc().nulls_first())
        )
        worklist = result.all()

    for chan_id, external_id, chan_name in worklist:
        # AV9 deadline: exit cleanly BEFORE the next channel (never mid-write).
        if time.monotonic() >= deadline:
            stats["deadline_hit"] = True
            logger.warning(
                "crawl_youtube_channels hit internal deadline (soft %ds - margin "
                "%ds); stopping (checked channels committed, next run resumes)",
                YOUTUBE_CRAWL_SOFT_TIME_LIMIT,
                YOUTUBE_CRAWL_DEADLINE_MARGIN,
            )
            break

        # 1. Feed. An outage is NOT a check: skip this channel, do not stamp
        #    last_checked_at, do not fail the others (the next run retries it).
        try:
            async with limiter.acquire("youtube"):
                videos = await youtube.fetch_channel_feed(client, external_id)
        except youtube.YouTubeHTTPError:
            logger.warning(
                "crawl_youtube_channels: feed fetch failed for %s (%s), "
                "skipping channel (not stamped)",
                chan_name,
                external_id,
                exc_info=True,
            )
            continue
        except Exception:
            logger.exception(
                "crawl_youtube_channels: unexpected feed error for %s (%s)",
                chan_name,
                external_id,
            )
            continue

        stats["channels"] += 1
        stats["videos_seen"] += len(videos)

        # 2. Drop videos already stored as a youtube set (idempotence / quota).
        video_ids = [v["video_id"] for v in videos if v.get("video_id")]
        known: set = set()
        if video_ids:
            async with session_factory() as db:
                res = await db.execute(
                    select(DJSet.external_id).where(
                        DJSet.source == "youtube",
                        DJSet.external_id.in_(video_ids),
                    )
                )
                known = {row[0] for row in res}
        fresh = [
            v for v in videos if v.get("video_id") and v["video_id"] not in known
        ]

        # 3. Durations for the fresh videos (the set-duration gate). An outage
        #    skips the channel WITHOUT stamping (retry next run).
        durations: dict = {}
        if fresh:
            try:
                async with limiter.acquire("youtube"):
                    durations = await youtube.fetch_video_durations(
                        client, [v["video_id"] for v in fresh], api_key
                    )
            except youtube.YouTubeHTTPError:
                logger.warning(
                    "crawl_youtube_channels: durations fetch failed for %s, "
                    "skipping channel (not stamped)",
                    chan_name,
                    exc_info=True,
                )
                continue
            except Exception:
                logger.exception(
                    "crawl_youtube_channels: unexpected durations error for %s",
                    chan_name,
                )
                continue

        # 4. Create metadata-only sets for videos clearing the gate, then stamp
        #    last_checked_at — all in ONE transaction committed PER CHANNEL, so
        #    the work survives an interruption.
        async with session_factory() as db:
            created_here = 0
            for v in fresh:
                secs = durations.get(v["video_id"])
                if not youtube.is_set_duration(secs):
                    continue
                # Feed a duration_ms so upsert_youtube_set records it.
                enriched = {**v, "duration_ms": secs * 1000}
                try:
                    _dj, created = await youtube.upsert_youtube_set(
                        db, video=enriched, channel_name=chan_name
                    )
                    if created:
                        created_here += 1
                except Exception:
                    logger.exception(
                        "crawl_youtube_channels: upsert failed for video %s "
                        "(channel %s)",
                        v.get("video_id"),
                        chan_name,
                    )

            now = datetime.now(timezone.utc)
            await db.execute(
                update(Channel)
                .where(Channel.id == chan_id)
                .values(last_checked_at=now)
            )
            await db.commit()
            stats["sets_created"] += created_here

    return stats


# ── Backfill (L7): one-shot historical catch-up on channel add ────────────────


@celery_app.task(
    name="workers.tasks.backfill_youtube_channel",
    bind=True,
    # Deliberately NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS an
    # Exception (same footgun as the crawl task). The per-channel Redis lock +
    # per-batch commits + the internal deadline bound the run; a re-add re-
    # dispatches if a run aborts on an outage.
    soft_time_limit=YOUTUBE_BACKFILL_SOFT_TIME_LIMIT,
    time_limit=YOUTUBE_BACKFILL_TIME_LIMIT,
)
def backfill_youtube_channel(self, channel_id):
    """One-shot: backfill a channel's HISTORICAL DJ sets on add (C14.b, L7).

    The nightly RSS/Atom watch (:func:`crawl_youtube_channels`) only sees the ~15
    latest uploads; this task pages the channel's « uploads » playlist via the
    Data API to catch the back-catalogue once, right after the channel is added.

    Single-instance PER CHANNEL via a Redis lock (``lock:backfill_youtube_channel:
    {channel_id}``) so two backfills of the same channel never overlap.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = f"lock:backfill_youtube_channel:{channel_id}"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=YOUTUBE_BACKFILL_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "backfill_youtube_channel already running for channel %s (task %s), "
            "skipping",
            channel_id,
            holder,
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_backfill_youtube_channel(self, channel_id)
    finally:
        # Release only if we still own it (TTL may have expired mid-run).
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_backfill_youtube_channel(task, channel_id):
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    # AV9 internal deadline (module `time` so it is fakeable in tests without
    # touching the event loop's clock — see the crawl task).
    deadline = (
        time.monotonic()
        + YOUTUBE_BACKFILL_SOFT_TIME_LIMIT
        - YOUTUBE_BACKFILL_DEADLINE_MARGIN
    )
    # Read the Data-API key at RUNTIME; absent → graceful no-op.
    api_key = os.environ.get("YOUTUBE_API_KEY", "")

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="backfill_youtube_channel",
            celery_task_id=task.request.id,
        ) as clog:
            try:
                stats = asyncio.run(
                    _backfill_driver(
                        channel_id=channel_id, api_key=api_key, deadline=deadline
                    )
                )
            except SoftTimeLimitExceeded:
                # Every batch is committed inline, so progress is persisted. Flush a
                # partial log and return normally rather than routing to the DLQ (no
                # autoretry is present); the channel can be re-added to finish.
                logger.warning(
                    "backfill_youtube_channel: cut by soft time limit for channel "
                    "%s (per-batch progress persisted)",
                    channel_id,
                )
                stats = {"status": "interrupted"}
            clog.set_stats(stats)

    return stats


async def _backfill_driver(*, channel_id, api_key, deadline):
    """Build the async engine + HTTP client + rate limiter, then run the core.

    Kept thin so :func:`_backfill_channel` stays fully injectable for unit tests
    (an in-memory engine + a fake limiter/client). Disposes the engine in
    ``finally``.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sessionmaker
    from workers import youtube
    from workers.rate_limiter import RateLimiter

    limiter = RateLimiter()
    async_engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession)
    client = youtube.default_client()
    try:
        async with client:
            return await _backfill_channel(
                session_factory,
                client,
                limiter,
                channel_id=channel_id,
                api_key=api_key,
                deadline=deadline,
            )
    finally:
        await async_engine.dispose()


async def _backfill_channel(
    session_factory, client, limiter, *, channel_id, api_key, deadline
):
    """Page one channel's uploads history and create metadata-only sets.

    Returns ``{videos_seen, sets_created, deadline_hit}``. Returns early (nothing
    created) when the channel is absent / not youtube / unresolved (external_id
    NULL) / excluded, or when no Data-API key is configured. A YouTube outage (or a
    malformed non-UC id) aborts CLEANLY, keeping what was committed; the internal
    deadline is checked between batches (AV9). Deliberately does NOT stamp
    ``last_checked_at`` — cadence is the nightly crawl's job, this is a one-shot.
    """
    from models import Channel, DJSet
    from sqlalchemy import select
    from workers import youtube

    stats = {"videos_seen": 0, "sets_created": 0, "deadline_hit": False}

    # Load the target channel row as a detached tuple.
    async with session_factory() as db:
        row = (
            await db.execute(
                select(
                    Channel.external_id,
                    Channel.name,
                    Channel.platform,
                    Channel.excluded,
                ).where(Channel.id == channel_id)
            )
        ).first()

    if row is None:
        logger.warning(
            "backfill_youtube_channel: channel %s not found — nothing to do",
            channel_id,
        )
        return stats
    external_id, chan_name, platform, excluded = row
    if platform != "youtube" or not external_id or excluded:
        logger.info(
            "backfill_youtube_channel: channel %s not eligible (platform=%s, "
            "external_id=%r, excluded=%s) — nothing to do",
            channel_id,
            platform,
            external_id,
            excluded,
        )
        return stats

    # No Data-API key → cannot page the playlist or gate durations. Graceful no-op.
    if not api_key:
        logger.warning(
            "backfill_youtube_channel: no YOUTUBE_API_KEY — skipping backfill of "
            "channel %s (nothing created)",
            channel_id,
        )
        return stats

    # 1. Page the uploads playlist (most-recent first, capped). An outage or a
    #    malformed (non-UC) id aborts cleanly — the add already succeeded, a re-add
    #    re-dispatches.
    try:
        async with limiter.acquire("youtube"):
            videos = await youtube.fetch_channel_uploads(
                client,
                external_id,
                api_key,
                max_videos=youtube.YOUTUBE_BACKFILL_MAX_VIDEOS,
            )
    except youtube.YouTubeHTTPError:
        logger.warning(
            "backfill_youtube_channel: uploads fetch failed for %s (%s), aborting "
            "backfill (re-add to retry)",
            chan_name,
            external_id,
            exc_info=True,
        )
        return stats
    except ValueError:
        logger.warning(
            "backfill_youtube_channel: channel %s has a non-UC external_id %r, "
            "cannot backfill",
            chan_name,
            external_id,
        )
        return stats

    stats["videos_seen"] = len(videos)

    # 2. Drop videos already stored as a youtube set (idempotence — a re-run, or an
    #    RSS crawl that already caught a recent upload, creates nothing).
    video_ids = [v["video_id"] for v in videos if v.get("video_id")]
    known: set = set()
    if video_ids:
        async with session_factory() as db:
            res = await db.execute(
                select(DJSet.external_id).where(
                    DJSet.source == "youtube",
                    DJSet.external_id.in_(video_ids),
                )
            )
            known = {row[0] for row in res}
    fresh = [
        v for v in videos if v.get("video_id") and v["video_id"] not in known
    ]

    # 3. Batch: deadline gate → durations → set-duration gate → upsert → commit
    #    PER BATCH so a long history survives an interruption.
    for start in range(0, len(fresh), YOUTUBE_BACKFILL_BATCH):
        # AV9 deadline: exit cleanly BEFORE the next batch (never mid-write).
        if time.monotonic() >= deadline:
            stats["deadline_hit"] = True
            logger.warning(
                "backfill_youtube_channel hit internal deadline for channel %s "
                "(soft %ds - margin %ds); stopping (committed batches kept)",
                channel_id,
                YOUTUBE_BACKFILL_SOFT_TIME_LIMIT,
                YOUTUBE_BACKFILL_DEADLINE_MARGIN,
            )
            break
        batch = fresh[start : start + YOUTUBE_BACKFILL_BATCH]

        # Durations for the batch (the set-duration gate). An outage stops the run
        # WITHOUT losing the committed batches (retry via a re-add).
        try:
            async with limiter.acquire("youtube"):
                durations = await youtube.fetch_video_durations(
                    client, [v["video_id"] for v in batch], api_key
                )
        except youtube.YouTubeHTTPError:
            logger.warning(
                "backfill_youtube_channel: durations fetch failed for %s, "
                "stopping (committed batches kept)",
                chan_name,
                exc_info=True,
            )
            break
        except Exception:
            logger.exception(
                "backfill_youtube_channel: unexpected durations error for %s",
                chan_name,
            )
            break

        async with session_factory() as db:
            created_here = 0
            for v in batch:
                secs = durations.get(v["video_id"])
                if not youtube.is_set_duration(secs):
                    continue
                # Feed a duration_ms so upsert_youtube_set records it.
                enriched = {**v, "duration_ms": secs * 1000}
                try:
                    _dj, created = await youtube.upsert_youtube_set(
                        db, video=enriched, channel_name=chan_name
                    )
                    if created:
                        created_here += 1
                except Exception:
                    logger.exception(
                        "backfill_youtube_channel: upsert failed for video %s "
                        "(channel %s)",
                        v.get("video_id"),
                        chan_name,
                    )
            await db.commit()
            stats["sets_created"] += created_here

    return stats
