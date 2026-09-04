"""
Celery tasks for DJ set track resolution and enrichment.
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lock TTL must cover the task's time_limit (2400s) so the lock cannot
# expire while a legitimate run is still in progress
RESOLVE_SET_TRACKS_LOCK_TTL = 2700

# C12 — priority stamped on catalog rows whose source set is NOT scored in
# trackid_index (a recent live-flux set). It sits ABOVE every backfill phase
# (phases 60-99): freshly crawled sets are the absolute priority for the
# Beatport drain (L2 gate). trackid_index.score is a Float where higher = more
# prioritary; a scored set's priority is round(score).
FLUX_PRIORITY = int(os.environ.get("C12_FLUX_PRIORITY", "100"))

# Same rule for recrawl_incomplete_sets (time_limit 3900s)
RECRAWL_INCOMPLETE_SETS_LOCK_TTL = 4200

# Same rule for backfill_trackid_sets (time_limit 3900s)
BACKFILL_TRACKID_SETS_LOCK_TTL = 4200

# Soft time limit for backfill_trackid_sets, extracted as a module constant so
# the task decorator AND the internal deadline guard share ONE source of truth
# (AV9). Never read task.soft_time_limit at runtime.
TRACKID_BACKFILL_SOFT_TIME_LIMIT = 3600

# AV9 — margin (seconds) subtracted from the soft limit to build an internal
# monotonic deadline checked before each loop iteration. billiard's
# SoftTimeLimitExceeded can fire WHILE the asyncio internals are mid-write and be
# swallowed by the transport's error handler ("Fatal write error on socket
# transport", Sentry DIGGY-APP-4/DIGGY-APP-J): it then never reaches the task's
# except clause and the run dies at the hard limit (SIGKILL → DLQ). The deadline
# exits the collect/import loops cleanly WITHOUT depending on signal delivery;
# the SoftTimeLimitExceeded catches stay in place as defense in depth.
TRACKID_BACKFILL_DEADLINE_MARGIN = int(
    os.environ.get("TRACKID_BACKFILL_DEADLINE_MARGIN", "120")
)

# crawl_trackid_latest has no explicit time_limit, so it inherits the global
# hard limit (3600s); keep the lock TTL above it so a legitimate run never
# loses its lock mid-flight.
CRAWL_TRACKID_LATEST_LOCK_TTL = 4200

# Local-hydration lease TTL (seconds), read at RUNTIME (a `docker compose up -d`
# applies a change without a code redeploy). The local trackid_hydrate tool
# atomically CLAIMS a batch of trackid_index rows (hydration_state='claimed',
# claimed_at=now()) that this drain then ignores (it selects only 'not_hydrated').
# A claim not finalised (flipped to 'hydrated') within this TTL is REAPED back to
# 'not_hydrated' at the top of each run — auto-healing a hard crash of the local
# tool that skipped its own release. Default 2h (a local batch's detail-fetch +
# container run + push). Env: TRACKID_CLAIM_LEASE_SECONDS.
_DEFAULT_CLAIM_LEASE_SECONDS = 7200

# Reaper UPDATE (PG-only: now()/make_interval). Kept as a module constant so the
# same SQL backs both the async drain path and the PG integration test.
_REAP_STALE_CLAIMS_SQL = (
    "UPDATE trackid_index "
    "SET hydration_state = 'not_hydrated', claimed_at = NULL "
    "WHERE hydration_state = 'claimed' "
    "AND claimed_at < now() - make_interval(secs => :lease)"
)

# recrawl_incomplete_sets' beat fires every 24h sharp, but the reference is
# stamped during the previous run. Without slack, a set re-crawled last night
# reads ~23h55 < 1.0d at the next beat and would wait a whole extra day (daily
# tier → every other day). The margin cannot cause over-crawling: the decision
# is only evaluated at beat passes, which are 24h apart. (age > cap → 'final'
# is untouched: it is not a cadence gate.)
CADENCE_SLACK_DAYS = 0.25  # 6h: queue latency + crawl duration + clock skew

# completion_pct is re-based on trackid_index.time_hit_rate (the authoritative
# TrackID identification ratio from the listing) — NOT on is_id, which is
# structurally biased to ~1.0 because the import only stores identified tracks.
# A set whose time_hit_rate is at/above this threshold is considered complete
# and finalized. Env-tunable for prod calibration.
RECRAWL_FINAL_HITRATE = float(os.environ.get("RECRAWL_FINAL_HITRATE", "0.95"))

# Age (days) past which a set is finalized regardless of hit rate: TrackID stops
# identifying new tracks long after import, so beyond this cap re-crawling is
# wasted. 730 = 24 months (replaces the previous 90-day final tier).
RECRAWL_MAX_AGE_DAYS = float(os.environ.get("RECRAWL_MAX_AGE_DAYS", "730"))


async def _reap_stale_claims(db, lease_seconds: int) -> int:
    """Return local-hydration claims older than the lease to the pool. Returns count.

    A trackid_index row the local ``trackid_hydrate`` tool CLAIMED
    (``hydration_state='claimed'``) but did NOT finalise (flip to ``hydrated``) within
    ``lease_seconds`` is reset to ``not_hydrated`` so this drain re-selects it —
    auto-healing a hard crash of the local tool that skipped its own release. Run at
    the top of a drain run, BEFORE the selection, so a stale claim becomes eligible
    again this run. PG-only (``now()``/``make_interval``); the drain runs on PG.
    """
    from sqlalchemy import text

    res = await db.execute(text(_REAP_STALE_CLAIMS_SQL), {"lease": lease_seconds})
    return res.rowcount or 0


def _select_sets_to_hydrate_stmt(limit: int):
    """Statement selecting the next sets to hydrate, highest score first (C12 L4).

    The backfill no longer crawls the TrackID listing by addedOn: it consumes
    ``trackid_index`` rows ordered by ``score`` desc. Only rows that are scored
    (``score IS NOT NULL``) AND still ``hydration_state='not_hydrated'`` are
    eligible — the un-scored "rest" of the index is NEVER hydrated by the drain, and
    a row the local ``trackid_hydrate`` tool has CLAIMED (``hydration_state='claimed'``)
    is naturally invisible here (it is not ``not_hydrated``) until it is hydrated or
    reaped back (see ``_reap_stale_claims``) — the dynamic reservation replaces the
    old static shard exclusion, with zero overlap and no wasted half of the backlog
    when the local tool is idle. Tie-break on ``trackid_id`` desc for a stable order
    across runs; capped at ``limit`` (``TRACKID_BACKFILL_SETS_PER_DAY``). Returns
    ``(trackid_id, slug)`` rows — all ``import_audiostream`` needs (it re-fetches the
    detail itself).
    """
    from models import TrackIdIndex
    from sqlalchemy import select

    return (
        select(TrackIdIndex.trackid_id, TrackIdIndex.slug)
        .where(
            TrackIdIndex.hydration_state == "not_hydrated",
            TrackIdIndex.score.isnot(None),
        )
        .order_by(TrackIdIndex.score.desc(), TrackIdIndex.trackid_id.desc())
        .limit(limit)
    )


def _mark_hydrated_stmt(trackid_id: int):
    """UPDATE flagging a trackid_index row ``hydrated`` so a later run does not
    re-select it. The ~38k already-imported rows were seeded ``hydrated`` by the
    OPS import (``import_trackid_index.seed_hydration``); this marks the NEW ones
    as they hydrate through the drain.
    """
    from models import TrackIdIndex
    from sqlalchemy import update

    return (
        update(TrackIdIndex)
        .where(TrackIdIndex.trackid_id == trackid_id)
        .values(hydration_state="hydrated")
    )


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


def _merge_priority(existing, new):
    """MAX-merge a new enrich priority onto a possibly-NULL existing one.

    Handles the NULL start (bulk_get_or_create_catalog creates rows with
    enrich_priority NULL) and keeps the highest priority across sets/runs.
    """
    return new if existing is None else max(existing, new)


def _build_set_priority_map(session, set_ids):
    """Map set_id -> enrich priority for a batch of set_ids (C12).

    A set's priority is its C12 phase, precomputed elsewhere and stored in
    trackid_index.score (Float, higher = more prioritary). Only trackid sets
    carry a trackid_index row, so the join is scoped to source='trackid' and
    keyed on external_id == CAST(trackid_id AS text) (same pattern as
    import_trackid_index.seed_hydration). A set with no scored trackid_index
    row (a recent live-flux set) is deliberately ABSENT from the map; callers
    default it to FLUX_PRIORITY via ``.get(set_id, FLUX_PRIORITY)``.
    """
    if not set_ids:
        return {}

    from models import DJSet, TrackIdIndex
    from sqlalchemy import String, cast, select

    rows = session.execute(
        select(DJSet.id, TrackIdIndex.score)
        .join(
            TrackIdIndex,
            cast(TrackIdIndex.trackid_id, String) == DJSet.external_id,
        )
        .where(
            DJSet.id.in_(set_ids),
            DJSet.source == "trackid",
            TrackIdIndex.score.isnot(None),
        )
    ).all()
    return {sid: int(round(score)) for sid, score in rows}


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

                # C12 — stamp enrich_priority so the Beatport drain (L2 gate)
                # processes the rows of prioritary sets first. The catalog rows
                # are created with enrich_priority NULL by
                # bulk_get_or_create_catalog (left untouched on purpose); we
                # stamp them HERE from the source set's priority, MAX-merged when
                # a row is shared across sets/runs.
                prio_map = _build_set_priority_map(
                    session, {st.set_id for st in tracks}
                )

                for st in tracks:
                    nk = make_normalized_key(st.raw_title, st.raw_artist)
                    entry = catalog_map.get(nk)
                    if entry:
                        st.catalog_id = entry.id
                        prio = prio_map.get(st.set_id, FLUX_PRIORITY)
                        entry.enrich_priority = _merge_priority(
                            entry.enrich_priority, prio
                        )
                        resolved += 1

                session.commit()

            result = {"resolved": resolved}
            clog.set_stats(result)

    return result


def _as_utc(dt):
    """Normalize a naive datetime (SQLite test runs) to UTC; PG returns aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _recrawl_decision(now, created_at, reference) -> str:
    """Age-tiered re-crawl backoff: returns 'crawl', 'wait' or 'final'.

    Age counts from created_at (Diggy import date); reference is the last
    (re-)crawl, COALESCE(last_recrawl_at, last_crawled_at). Tiers:
    0-7d → re-crawl after 24h, 7-30d → after 7d, 30d-RECRAWL_MAX_AGE_DAYS →
    after 30d (monthly), > RECRAWL_MAX_AGE_DAYS → final (no more crawls).
    """
    age_days = 0.0
    if created_at is not None:
        age_days = (now - _as_utc(created_at)).total_seconds() / 86400
    if age_days > RECRAWL_MAX_AGE_DAYS:
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

    new_pct is the set's trackid_index.time_hit_rate (authoritative TrackID
    identification ratio), or None when the set has no trackid_index row (no
    measurable completion). recrawl_count counts CONSECUTIVE re-crawls without
    progression and is reset to 0 whenever completion_pct improves (old NULL
    counts as progression). A set at/above RECRAWL_FINAL_HITRATE is finalized
    'complete'; 3 stagnant re-crawls finalize it 'stale'. When new_pct is None
    the hit rate is unknown: treat it as a non-progression (bump the stale
    counter, leave completion_pct untouched) — finalization stays possible by
    stability (stale) or, in the pre-pass, by age. Returns 'complete' or
    'stale' when the set is finalized, None otherwise.
    """
    if new_pct is None:
        dj_set.recrawl_count = (dj_set.recrawl_count or 0) + 1
    elif old_pct is None or new_pct > old_pct:
        dj_set.recrawl_count = 0
    else:
        dj_set.recrawl_count = (dj_set.recrawl_count or 0) + 1

    finalized = None
    if new_pct is not None and new_pct >= RECRAWL_FINAL_HITRATE:
        finalized = "complete"
    elif dj_set.recrawl_count >= 3:
        finalized = "stale"
    if finalized:
        dj_set.recrawl_status = "final"

    if new_pct is not None:
        dj_set.completion_pct = new_pct
    dj_set.last_recrawl_at = now
    return finalized


@celery_app.task(
    name="workers.tasks.recrawl_incomplete_sets",
    bind=True,
    # Deliberately NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS an
    # Exception, so that decorator would turn a soft timeout into a retry loop
    # (same footgun as backfill_trackid_sets / the artist backlog tasks). The
    # Redis lock + the per-item and task-level SoftTimeLimitExceeded guards
    # below are what bound the run.
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
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import DJSet, TrackIdIndex
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
                # completion_pct is re-based on the authoritative TrackID
                # identification ratio (trackid_index.time_hit_rate), joined by
                # the trackid_index.set_id FK. is_id is NO LONGER counted for
                # completeness (the import only stores identified tracks, so an
                # is_id-based ratio is structurally ~1.0). A set with no
                # trackid_index row has time_hit_rate = None (LEFT JOIN).
                rows = session.execute(
                    select(DJSet, TrackIdIndex.time_hit_rate)
                    .outerjoin(TrackIdIndex, TrackIdIndex.set_id == DJSet.id)
                    .where(
                        DJSet.source == "trackid",
                        DJSet.is_virtual.is_(False),
                        DJSet.recrawl_status == "active",
                    )
                ).all()

                for dj_set, hit_rate in rows:
                    # Bulk pre-pass: hit rate already at/above the completion
                    # threshold → close it without crawling. A set WITHOUT a
                    # trackid_index hit rate is not finalized here — it follows
                    # the normal age/cadence decision and keeps completion_pct.
                    if hit_rate is not None and hit_rate >= RECRAWL_FINAL_HITRATE:
                        dj_set.completion_pct = hit_rate
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
                                # time_hit_rate is a static listing snapshot
                                # (import_audiostream does not touch it), so
                                # carry it to the crawl outcome instead of
                                # re-reading trackid_index.
                                "hit_rate": hit_rate,
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

                                    # completion_pct = trackid_index.time_hit_rate
                                    # (static listing snapshot carried from the
                                    # pre-pass). None → hit rate unknown, handled
                                    # as a non-progression by _apply_recrawl_outcome.
                                    finalized = _apply_recrawl_outcome(
                                        result,
                                        info["old_pct"],
                                        info["hit_rate"],
                                        datetime.now(timezone.utc),
                                    )
                                    # C8 reliability (sets.unreliable) is
                                    # refreshed by import_audiostream above: the
                                    # re-import re-observes the ID ratio,
                                    # source_url AND the fresh artworkUrl, so the
                                    # flag is recomputed here for free. It is
                                    # deliberately NOT recomputed a second time
                                    # from this task — we have no artworkUrl at
                                    # this vantage, so a carry-over would only
                                    # overwrite the fresher placeholder
                                    # observation with a stickier approximation.
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
                        except SoftTimeLimitExceeded:
                            # Re-raise BEFORE the generic handler:
                            # SoftTimeLimitExceeded IS an Exception, so without
                            # this clause the soft limit would be counted as a
                            # per-set error and the loop would run to the hard
                            # time_limit SIGKILL. Sets already handled were
                            # committed inline.
                            raise
                        except Exception:
                            errors += 1
                            logger.exception(
                                "recrawl_incomplete_sets: failed for set %s",
                                info.get("slug"),
                            )

                await async_engine.dispose()
                return crawled, completed, stale, errors

            try:
                crawled, completed, finalized_stale, errors = asyncio.run(
                    _crawl_all()
                )
            except SoftTimeLimitExceeded:
                # Soft limit hit mid-crawl: every set was committed inline, so DB
                # progress is persisted; the in-flight per-set counters are lost
                # with the re-raise (see the per-item guard). Kick resolution of
                # what was crawled and flush a partial log instead of routing to
                # the DLQ (no autoretry is present to absorb it). The next run
                # re-evaluates eligibility from the persisted set state.
                logger.warning(
                    "recrawl_incomplete_sets: cut by soft time limit "
                    "(progress persisted per set, next run resumes)"
                )
                resolve_set_tracks.delay()
                result = {
                    "status": "interrupted",
                    "eligible": eligible,
                    "finalized_complete": finalized_complete,
                    "finalized_age": finalized_age,
                    "dropped_by_cap": dropped_by_cap,
                }
                clog.set_stats(result)
                return result
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
    # Deliberately NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS an
    # Exception, so that decorator would turn a soft timeout into a retry loop
    # (same footgun as backfill_trackid_sets / recrawl_incomplete_sets). No
    # explicit time_limit → inherits the global hard limit (3600s). The Redis
    # lock + the per-item and task-level SoftTimeLimitExceeded guards bound the
    # run.
)
def crawl_trackid_latest(self):
    """
    Crawl TrackID.net for sets published since last run.
    Uses Redis cursor trackid_crawl_last_run (ISO 8601 UTC).
    First run (no cursor): crawls last 24h.
    Single-instance: a Redis lock skips the run if another one is still in
    flight, same pattern as recrawl_incomplete_sets.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:crawl_trackid_latest"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=CRAWL_TRACKID_LATEST_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "crawl_trackid_latest already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_crawl_trackid_latest(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_crawl_trackid_latest(task):
    import asyncio
    from datetime import datetime, timedelta, timezone

    import redis as redis_lib
    from celery.exceptions import SoftTimeLimitExceeded
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
                    except SoftTimeLimitExceeded:
                        # Re-raise BEFORE the generic handler:
                        # SoftTimeLimitExceeded IS an Exception, so without this
                        # clause the soft limit would be counted as a per-set
                        # skip and the loop would run to the hard time_limit
                        # SIGKILL. Imported sets were committed inline.
                        raise
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
            celery_task_id=task.request.id,
        ) as clog:
            try:
                imported, skipped, pages = asyncio.run(_crawl_all())
            except SoftTimeLimitExceeded:
                # Soft limit hit mid-crawl: every imported set was committed
                # inline, so DB progress is persisted; the in-flight counters are
                # lost with the re-raise. Do NOT advance the cursor — newer sets
                # past the interruption point were not all imported, so the next
                # run must re-scan from the unchanged cursor (re-import is
                # idempotent via dedup). Resolve what was imported and flush a
                # partial log instead of routing to the DLQ (no autoretry).
                logger.warning(
                    "crawl_trackid_latest: cut by soft time limit "
                    "(cursor unchanged, next run resumes)"
                )
                resolve_set_tracks.delay()
                result = {"status": "interrupted"}
                clog.set_stats(result)
                return result

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
    # by marking each hydrated row inline and catching SoftTimeLimitExceeded
    # gracefully (see below), so a re-raise/retry is neither needed nor wanted.
    soft_time_limit=TRACKID_BACKFILL_SOFT_TIME_LIMIT,
    time_limit=3900,
)
def backfill_trackid_sets(self):
    """
    Hydratation progressive des sets TrackID.net par ordre de priorité (C12).
    Ne crawle plus le listing par addedOn décroissant : consomme la table
    trackid_index triée par score décroissant (les sets les plus prioritaires
    d'abord ; les sets non scorés — score NULL — ne sont JAMAIS hydratés). Chaque
    set retenu passe par import_audiostream (re-fetch du détail) puis est marqué
    hydration_state='hydrated' pour ne pas être re-sélectionné.
    No-op propre quand aucun set scoré non hydraté ne reste.
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

    import redis as redis_lib
    from celery.exceptions import SoftTimeLimitExceeded
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    # Manual kill switch (C11 Étape 0 → kept for C12 L4): an operator sets
    # trackid_backfill_done=1 to pause the drain immediately. It is NEVER set
    # automatically anymore — the drain is naturally a no-op once no scored,
    # un-hydrated trackid_index row remains, so there is no "done" terminal
    # state to auto-reach and no chronological cursor to advance.
    if r.get("trackid_backfill_done"):
        return {"status": "done"}

    # LIMIT on how many sets one run consumes from trackid_index (score order).
    # Kept under the TRACKID_BACKFILL_SETS_PER_DAY name for prod-config
    # continuity. The CODE default is 1000, but this OUTPACES downstream Beatport
    # capacity (~9900/day = 18 hourly runs × 550), so PROD overrides it via .env
    # (e.g. 400-600) to leave a drainage margin.
    sets_per_day = int(os.environ.get("TRACKID_BACKFILL_SETS_PER_DAY", "1000"))

    logger.info("backfill_trackid_sets: consuming trackid_index, cap=%d", sets_per_day)

    engine = get_engine()

    # AV9 — internal deadline (see TRACKID_BACKFILL_DEADLINE_MARGIN): checked
    # BEFORE each import iteration so a shortened run exits cleanly without
    # depending on the SoftTimeLimitExceeded signal being delivered.
    deadline = (
        time.monotonic()
        + TRACKID_BACKFILL_SOFT_TIME_LIMIT
        - TRACKID_BACKFILL_DEADLINE_MARGIN
    )
    deadline_hit = False

    async def _backfill_all():
        nonlocal deadline_hit
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as async_sessionmaker
        from trackid.client import TrackIDClient
        from trackid.importer import import_audiostream
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        async_engine = create_async_engine(os.environ["DATABASE_URL"])
        AsyncS = async_sessionmaker(async_engine, class_=AsyncSession)

        # REAPER: BEFORE selecting, return local-hydration claims older than the
        # lease to the pool (auto-heals a crashed local trackid_hydrate run whose
        # reserved sets would otherwise stay 'claimed' forever). Read the TTL at
        # runtime so a `docker compose up -d` applies a change without a redeploy.
        lease_seconds = int(
            os.environ.get(
                "TRACKID_CLAIM_LEASE_SECONDS", str(_DEFAULT_CLAIM_LEASE_SECONDS)
            )
        )
        async with AsyncS() as db:
            reaped = await _reap_stale_claims(db, lease_seconds)
            await db.commit()
        if reaped:
            logger.info(
                "backfill_trackid_sets: reaped %d stale claim(s) (lease %ds) "
                "back to not_hydrated",
                reaped,
                lease_seconds,
            )

        # SELECTION (C12 L4): the next sets to hydrate are read from
        # trackid_index ordered by score desc — NOT crawled from the TrackID
        # listing. A single fast DB query, so no deadline check is needed here.
        # import_audiostream reads only id + slug and re-fetches the detail.
        async with AsyncS() as db:
            rows = (
                await db.execute(_select_sets_to_hydrate_stmt(sets_per_day))
            ).all()

        selected = len(rows)
        if not selected:
            await async_engine.dispose()
            return 0, 0, 0

        batch: list[dict] = [{"id": tid, "slug": slug} for tid, slug in rows]

        imported = 0
        skipped = 0

        async with TrackIDClient() as client:
            for audiostream in batch:
                if time.monotonic() >= deadline:
                    deadline_hit = True
                    logger.warning(
                        "backfill_trackid_sets hit internal deadline "
                        "(soft limit %ds - margin %ds) during import; stopping "
                        "(hydrated sets marked, next run resumes from index)",
                        TRACKID_BACKFILL_SOFT_TIME_LIMIT,
                        TRACKID_BACKFILL_DEADLINE_MARGIN,
                    )
                    break
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
                                # Mark the index row hydrated so the next run
                                # does not re-select it. Only on a real hydration
                                # (result is not None) — a failed detail fetch
                                # leaves the row not_hydrated for a retry.
                                await db.execute(
                                    _mark_hydrated_stmt(audiostream["id"])
                                )
                                await db.commit()
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
                except SoftTimeLimitExceeded:
                    # Re-raise BEFORE the generic handler: SoftTimeLimitExceeded
                    # IS an Exception, so without this clause it would be
                    # swallowed and the loop would run to the hard time_limit
                    # SIGKILL. Sets already hydrated were marked inline.
                    raise
                except Exception:
                    logger.exception(
                        "backfill_trackid_sets: failed for set %s",
                        audiostream.get("id"),
                    )
                    skipped += 1

        await async_engine.dispose()
        return imported, skipped, selected

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="backfill_trackid_sets",
            celery_task_id=task.request.id,
        ) as clog:
            try:
                imported, skipped, selected = asyncio.run(_backfill_all())
            except SoftTimeLimitExceeded:
                # Hydrated rows were marked inline, so progress is already
                # persisted; kick off resolution of what was imported and return
                # normally. Re-raising would route the task to the DLQ (no
                # autoretry is present to absorb it) and lose nothing — the next
                # run re-selects the still-not_hydrated tail from trackid_index.
                logger.warning(
                    "backfill_trackid_sets: cut by soft time limit "
                    "(hydrated sets marked, next run resumes)"
                )
                resolve_set_tracks.delay()
                result = {"status": "interrupted", "deadline_hit": deadline_hit}
                clog.set_stats(result)
                return result

            if selected == 0:
                # Natural termination: every scored set is hydrated (or none is
                # scored yet). No-op — NOT a terminal "done" (scores can be added
                # later by the C12 import); the sentinel stays a manual switch.
                logger.info(
                    "backfill_trackid_sets: no scored un-hydrated set, no-op"
                )
                result = {"status": "idle", "imported": 0, "skipped": 0}
            else:
                if imported > 0:
                    resolve_set_tracks.delay()
                result = {
                    "status": "running",
                    "imported": imported,
                    "skipped": skipped,
                    "selected": selected,
                }

            # Observability (AV9): a deadline exit is a SUCCESS with partial
            # work, distinguishable from a full run in crawl_logs.
            result["deadline_hit"] = deadline_hit
            clog.set_stats(result)

    return result
