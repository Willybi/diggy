"""Celery task: nightly auto-link of artists' OFFICIAL YouTube channels (C14.b).

Resolves the official YouTube channel of each watch-cohort artist (``artist_cohort``)
and creates the matching watched ``channels`` row — with NO human intervention and
WITHOUT spending YouTube quota (the official tier is Wikidata SPARQL + a bounded
title-check). The anchor is the artist's ``deezer_id`` (held for ~99.6% of the
cohort), far more reliable than a name search: Wikidata property ``P2722`` (Deezer
artist id) → ``P2397`` (YouTube channel id), via
:func:`workers.artist_channel_resolve.resolve_channel_by_deezer_id`.

Skeleton mirrors ``tasks/youtube.py``: a Redis single-instance lock in the wrapper
(SET NX EX + conditional release), a ``CrawlLogger`` on a sync ``Session``, inline
per-batch commits (so the work survives an interruption), an AV9 internal monotonic
deadline (module ``time`` so it is fakeable in tests without touching the event
loop's clock), and deliberately NO ``autoretry_for=(Exception,)``
(``SoftTimeLimitExceeded`` IS an ``Exception`` → that decorator would turn a soft
timeout into a retry loop).

Two bounds keep it gentle so the nightly crawl absorbs the load progressively:

  * a CAP on the number of channels CREATED per run
    (``CHANNEL_AUTOLINK_MAX_PER_RUN``, default 200; set to 0 to make the task a
    no-op kill switch);
  * a Redis DEDUP of the per-id resolution outcome (hit or definitive miss, TTL
    ~60 days, key ``yt:autolink:deezer:{deezer_id}``) so a cohort artist that
    resolves to nothing is not re-queried against Wikidata every single night.
    Fail-open: a Redis outage never blocks the run.

An outage (SPARQL non-200) is NOT an attempt: the failing batch's ids are left
un-marked (retried next run) and the other batches still run. A missing
``YOUTUBE_API_KEY`` only degrades the "- Topic" check (accepted best-effort), never
a crash.
"""

import asyncio
import json
import logging
import os
import sys
import time

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Soft/hard limits + lock TTL. Extracted as module constants so the decorator AND
# the internal deadline guard share ONE source of truth (AV9 — never read
# task.soft_time_limit at runtime). The TTL is STRICTLY above the hard time_limit so
# a live run's lock can never expire under it; a worker killed mid-run leaves an
# orphan lock that self-heals within the TTL.
CHANNEL_AUTOLINK_SOFT_TIME_LIMIT = 1800
CHANNEL_AUTOLINK_TIME_LIMIT = 2100
CHANNEL_AUTOLINK_LOCK_TTL = 2400

# AV9 — margin (seconds) subtracted from the soft limit to build an internal
# monotonic deadline checked before each batch (billiard's SoftTimeLimitExceeded can
# fire mid-write and be swallowed by the asyncio transport, never reaching the
# except clause → the run would die at the hard limit; the deadline exits cleanly
# without depending on signal delivery).
CHANNEL_AUTOLINK_DEADLINE_MARGIN = int(
    os.environ.get("CHANNEL_AUTOLINK_DEADLINE_MARGIN", "120")
)

# Cap on channels CREATED per run (the crawl absorbs the load progressively). A
# modest default; 0 = a safe no-op kill switch. Env-overridable (no code deploy).
CHANNEL_AUTOLINK_DEFAULT_MAX_PER_RUN = 200

# Per-id resolution-outcome dedup TTL (~60 days): a cohort artist that resolves to
# nothing is not re-queried every night. Env-tunable.
CHANNEL_AUTOLINK_DEDUP_TTL = int(
    os.environ.get("CHANNEL_AUTOLINK_DEDUP_TTL", str(60 * 24 * 3600))
)

# How many cohort ids per SPARQL batch. Also bounds the YouTube title-check
# overshoot past the cap to at most one batch's hits (see _autolink_channels).
CHANNEL_AUTOLINK_BATCH = int(os.environ.get("CHANNEL_AUTOLINK_BATCH", "100"))

# Spacing (seconds) between the historical backfills dispatched for the channels
# created by a run, so they do not all land on the worker's slots at once.
CHANNEL_AUTOLINK_BACKFILL_STAGGER = int(
    os.environ.get("CHANNEL_AUTOLINK_BACKFILL_STAGGER", "30")
)

# Chunk size for the batched Redis MGET dedup read (cheap pre-filter).
_DEDUP_MGET_CHUNK = 500


@celery_app.task(
    name="workers.tasks.autolink_official_channels",
    bind=True,
    # Deliberately NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS an
    # Exception, so that decorator would turn a soft timeout into a retry loop (same
    # footgun as the youtube/sets/artist tasks). The Redis lock + per-batch inline
    # commits + the internal deadline guard are what bound the run.
    soft_time_limit=CHANNEL_AUTOLINK_SOFT_TIME_LIMIT,
    time_limit=CHANNEL_AUTOLINK_TIME_LIMIT,
)
def autolink_official_channels(self):
    """Nightly: resolve + create official YouTube channels for cohort artists (C14.b).

    Single-instance: a Redis lock skips the run if another one is still in flight.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:autolink_official_channels"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=CHANNEL_AUTOLINK_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "autolink_official_channels already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_autolink_official_channels(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run).
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_autolink_official_channels(task):
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    # AV9 internal deadline (see CHANNEL_AUTOLINK_DEADLINE_MARGIN): checked at the
    # top of each batch so a shortened run exits cleanly without depending on the
    # SoftTimeLimitExceeded signal being delivered.
    deadline = (
        time.monotonic()
        + CHANNEL_AUTOLINK_SOFT_TIME_LIMIT
        - CHANNEL_AUTOLINK_DEADLINE_MARGIN
    )
    # Read the Data-API key + cap at RUNTIME (a `docker compose up -d` applies a
    # change without a code redeploy). The key only gates the "- Topic" check; the
    # cap bounds the channels created this run (0 = no-op).
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    max_per_run = int(
        os.environ.get(
            "CHANNEL_AUTOLINK_MAX_PER_RUN", str(CHANNEL_AUTOLINK_DEFAULT_MAX_PER_RUN)
        )
    )

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="autolink_official_channels",
            celery_task_id=task.request.id,
        ) as clog:
            try:
                stats = asyncio.run(
                    _autolink_driver(
                        api_key=api_key, deadline=deadline, max_per_run=max_per_run
                    )
                )
            except SoftTimeLimitExceeded:
                # Every batch is committed inline, so progress is persisted. Flush a
                # partial log and return normally rather than routing to the DLQ (no
                # autoretry is present); the next run resumes from the still-pending
                # cohort ids.
                logger.warning(
                    "autolink_official_channels: cut by soft time limit "
                    "(per-batch progress persisted, next run resumes)"
                )
                stats = {"status": "interrupted"}
            clog.set_stats(stats)

    return stats


async def _autolink_driver(*, api_key, deadline, max_per_run):
    """Build the async engine + Redis client + HTTP client, then run the core.

    Kept thin so the real work (:func:`_autolink_channels`) stays fully injectable
    for unit tests (an in-memory engine + a fake redis + a resolver stub). Disposes
    the engine and closes the client in ``finally``. The SAME httpx client serves
    both Wikidata SPARQL and the YouTube title-check (different absolute URLs).
    """
    import redis as redis_lib
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as async_sessionmaker
    from workers import youtube
    from workers.celery_app import REDIS_URL

    redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
    async_engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession)
    client = youtube.default_client()
    try:
        async with client:
            return await _autolink_channels(
                session_factory,
                redis_client,
                client,
                client,
                api_key=api_key,
                deadline=deadline,
                max_per_run=max_per_run,
            )
    finally:
        await async_engine.dispose()


async def _autolink_channels(
    session_factory,
    redis_client,
    wiki_client,
    yt_client,
    *,
    api_key,
    deadline,
    max_per_run,
):
    """Resolve cohort artists' official channels and upsert the watched rows.

    ``session_factory`` is an async ``sessionmaker``; ``redis_client`` a sync Redis
    (or stand-in) used for the dedup pre-filter/store; ``wiki_client``/``yt_client``
    injected ``httpx.AsyncClient``s passed to the resolver. Returns the stats dict
    ``{candidates, pending, resolved, created, backfills_dispatched, deadline_hit}``.
    """
    from workers.artist_channel_resolve import (
        ChannelResolveHTTPError,
        resolve_channel_by_deezer_id,
    )

    stats = {
        "candidates": 0,
        "pending": 0,
        "resolved": 0,
        "created": 0,
        "backfills_dispatched": 0,
        "deadline_hit": False,
    }

    # cap <= 0 → a safe no-op kill switch (resolve nothing, create nothing).
    if max_per_run <= 0:
        logger.info(
            "autolink_official_channels: CHANNEL_AUTOLINK_MAX_PER_RUN=%d → no-op",
            max_per_run,
        )
        return stats

    # Worklist: non-excluded cohort members with a real deezer_id and no channel yet
    # linked to them, ordered T1-first. Read into plain dicts (detached) so a later
    # per-batch commit never expires ORM state.
    candidates = await _load_autolink_candidates(session_factory)
    stats["candidates"] = len(candidates)
    if not candidates:
        return stats

    # Drop the ids already tried (a Redis dedup key present) — avoids re-querying
    # Wikidata for a known miss every night. Fail-open (Redis down → all pending).
    pending = _filter_pending(redis_client, candidates)
    stats["pending"] = len(pending)

    for batch in _chunks(pending, CHANNEL_AUTOLINK_BATCH):
        # AV9 deadline: exit cleanly BEFORE the next batch (never mid-write).
        if time.monotonic() >= deadline:
            stats["deadline_hit"] = True
            logger.warning(
                "autolink_official_channels hit internal deadline (soft %ds - "
                "margin %ds); stopping (created %d, next run resumes)",
                CHANNEL_AUTOLINK_SOFT_TIME_LIMIT,
                CHANNEL_AUTOLINK_DEADLINE_MARGIN,
                stats["created"],
            )
            break
        if stats["created"] >= max_per_run:
            break

        ids = [c["deezer_id"] for c in batch]
        try:
            hits = await resolve_channel_by_deezer_id(
                ids,
                wiki_client=wiki_client,
                yt_client=yt_client,
                api_key=api_key,
            )
        except ChannelResolveHTTPError:
            # A SPARQL outage for this batch: mark nothing (the ids stay un-tried →
            # a later run retries them), do not fail the other batches.
            logger.warning(
                "autolink_official_channels: SPARQL query failed for a batch — "
                "skipping (ids left un-marked for a later run)",
                exc_info=True,
            )
            continue
        except Exception:
            logger.exception(
                "autolink_official_channels: unexpected resolve error — skipping "
                "batch"
            )
            continue

        # One transaction per batch so a kill keeps the channels already created.
        created_ids = []
        async with session_factory() as db:
            reached_cap = False
            for c in batch:
                res = hits.get(c["deezer_id"])
                if not res:
                    # Definitive miss → cache so we don't re-query Wikidata nightly.
                    _dedup_store(redis_client, c["deezer_id"], None)
                    continue
                if stats["created"] >= max_per_run:
                    # Cap reached: leave this HIT un-marked so a later run creates
                    # its channel (never cache a hit we did not finalize).
                    reached_cap = True
                    break
                new_id = await _upsert_autolink_channel(db, c, res)
                _dedup_store(redis_client, c["deezer_id"], res)
                stats["resolved"] += 1
                if new_id is not None:
                    stats["created"] += 1
                    created_ids.append(new_id)
            await db.commit()
        # AFTER the commit, so the worker can load each row in its own session.
        stats["backfills_dispatched"] += _dispatch_backfills(
            created_ids, start_index=stats["backfills_dispatched"]
        )
        if reached_cap:
            break

    logger.info("autolink_official_channels: %s", stats)
    return stats


async def _load_autolink_candidates(session_factory):
    """Cohort artists eligible for an auto-link, ordered T1-first.

    Non-excluded ``artist_cohort`` members whose ``Artist.deezer_id`` is present and
    not the ``NOT_FOUND`` sentinel, and for whom NO ``channels`` row is already
    linked (``NOT EXISTS`` on ``Channel.artist_id`` — NULL-safe, idempotent: a
    created channel drops its artist from the worklist next run). Ordered by tier
    asc (T1 first), id asc tie-break. Returns a list of detached dicts.
    """
    from models import Artist, ArtistCohort, Channel
    from sqlalchemy import select

    async with session_factory() as db:
        linked_exists = (
            select(Channel.id).where(Channel.artist_id == Artist.id).exists()
        )
        stmt = (
            select(Artist.id, Artist.deezer_id, Artist.name)
            .join(ArtistCohort, ArtistCohort.artist_id == Artist.id)
            .where(
                ArtistCohort.excluded.isnot(True),
                Artist.deezer_id.isnot(None),
                Artist.deezer_id != "NOT_FOUND",
                ~linked_exists,
            )
            .order_by(ArtistCohort.tier.asc(), Artist.id.asc())
        )
        rows = (await db.execute(stmt)).all()
    return [
        {"artist_id": r[0], "deezer_id": r[1], "name": r[2]} for r in rows
    ]


def _dispatch_backfills(channel_ids, *, start_index=0):
    """Fire the one-shot historical backfill of each newly created channel.

    Without it an auto-linked channel only ever sees the ~15 uploads of its RSS feed.
    Staggered by :data:`CHANNEL_AUTOLINK_BACKFILL_STAGGER`, continuing from
    ``start_index`` across batches. Best-effort, like the admin add path: a dispatch
    failure is logged and never fails the run (the nightly crawl still covers the
    channel). Returns the number of backfills actually dispatched.
    """
    dispatched = 0
    for channel_id in channel_ids:
        try:
            celery_app.send_task(
                "workers.tasks.backfill_youtube_channel",
                args=[channel_id],
                countdown=(start_index + dispatched)
                * CHANNEL_AUTOLINK_BACKFILL_STAGGER,
            )
            dispatched += 1
        except Exception:
            logger.warning(
                "autolink_official_channels: backfill dispatch failed for channel "
                "%s (best-effort)",
                channel_id,
                exc_info=True,
            )
    return dispatched


async def _upsert_autolink_channel(db, candidate, res) -> int | None:
    """Upsert a watched ``artist`` channel for a resolved hit.

    Idempotent on ``(platform='youtube', external_id)``: a brand-new row is created
    watched + linked to the artist and its id is returned; an EXISTING row only gets
    the artist backlink (if free) and is re-watched, returning None — and an existing
    EXCLUDED row (an operator's curated "no") is left entirely untouched. Commit is
    the caller's (per batch).
    """
    from models import Channel
    from sqlalchemy import select

    channel_id = res["channel_id"]
    title = res.get("channel_title") or channel_id

    row = (
        await db.execute(
            select(Channel).where(
                Channel.platform == "youtube",
                Channel.external_id == channel_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        new_row = Channel(
            platform="youtube",
            external_id=channel_id,
            name=title,
            channel_type="artist",
            artist_id=candidate["artist_id"],
            watched=True,
            excluded=False,
            signals={
                "method": res.get("method", "wikidata_deezer"),
                "confidence": res.get("confidence", "high"),
            },
        )
        db.add(new_row)
        await db.flush()  # assigns the id the backfill dispatch needs
        return new_row.id

    # Existing row: never override a curated exclusion; else link the artist if the
    # slot is free and re-flag it watched.
    if row.excluded:
        return None
    if row.artist_id is None:
        row.artist_id = candidate["artist_id"]
    if not row.watched:
        row.watched = True
    return None


# ── Redis dedup helpers (fail-open) ───────────────────────────────────────────


def _dedup_key(deezer_id: str) -> str:
    return f"yt:autolink:deezer:{deezer_id}"


def _filter_pending(redis_client, candidates):
    """Drop candidates already tried (a dedup key present). Fail-open: a Redis read
    error treats the chunk as all-pending (the run is never blocked by Redis)."""
    if redis_client is None:
        return list(candidates)
    pending = []
    for chunk in _chunks(candidates, _DEDUP_MGET_CHUNK):
        keys = [_dedup_key(c["deezer_id"]) for c in chunk]
        try:
            values = redis_client.mget(keys)
        except Exception as exc:  # fail-open: Redis down must not stop the run
            logger.warning(
                "autolink dedup mget skipped (Redis unavailable): %s", exc
            )
            pending.extend(chunk)
            continue
        for c, value in zip(chunk, values):
            if value is None:
                pending.append(c)
    return pending


def _dedup_store(redis_client, deezer_id, res):
    """Record a definitive resolution outcome (hit payload or a miss sentinel) with
    a long TTL so the id is not re-queried every night. Fail-open."""
    if redis_client is None:
        return
    try:
        payload = json.dumps(res) if res else "none"
        redis_client.set(_dedup_key(deezer_id), payload, ex=CHANNEL_AUTOLINK_DEDUP_TTL)
    except Exception as exc:  # fail-open: a cache write must never fail the run
        logger.warning("autolink dedup store skipped (Redis unavailable): %s", exc)


def _chunks(seq, size):
    """Yield successive ``size``-length slices of ``seq`` (local helper)."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
