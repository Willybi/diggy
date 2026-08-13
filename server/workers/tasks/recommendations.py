"""
Celery task: nightly precompute of personalised "Pour toi" recommendations.

The reco cold path (candidate pool over the full visible catalog + multi-seed
scoring) is ~30s per user. Computed lazily on the /radar feed it blocked the two
uvicorn workers past the nginx 60s proxy timeout → 504 on every /radar tab
(mesuré 2026-08-13, catalog ~270k rows). This task pre-warms the Redis reco
cache for every active user (a like OR a library track) so the interactive feed
always hits the warm ~1.7s path. Paired with the per-user single-flight lock in
``recommendation_service``, the cold path is only ever hit by a brand-new active
user or right after an opinion change (both single-flighted → never a 504).

No external API → routed to the default ``celery`` queue (diggy_worker), placed
at 05:45 when that worker is idle (crawls done at 04:00, trends at 07:00). A
single ~433 MB compute peaks the worker around ~1 GB over its baseline, so the
worker cap was raised 1G→2G alongside this task.
"""

import asyncio
import logging
import os
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# TTL ≥ time_limit (invariant): the lock must outlast the whole run so it cannot
# expire while a legitimate run is still in progress. 2100s > time_limit 1800s.
RECO_PRECOMPUTE_LOCK_TTL = 2100


@celery_app.task(
    name="workers.tasks.precompute_recommendations",
    bind=True,
    soft_time_limit=1500,
    time_limit=1800,
)
def precompute_recommendations(self):
    """Pre-warm the reco cache for all active users. Single-instance (Redis lock).

    No ``autoretry_for=(Exception,)``: SoftTimeLimitExceeded IS an Exception, so
    that decorator would loop the whole sweep — the lock + the per-user soft-limit
    catch bound the run instead (project invariant).
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:precompute_reco"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=RECO_PRECOMPUTE_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "precompute_recommendations already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return asyncio.run(_run())
    finally:
        # Release only if we still own it (TTL may have expired mid-run).
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


async def _run() -> dict:
    """Compute + cache the reco list for every active user, sequentially.

    A fresh async engine (NullPool) bound to this task's own event loop — the
    api's module-level engine is bound to the uvicorn loop and cannot be reused
    across the fresh loop ``asyncio.run`` creates here.
    """
    import redis.asyncio as aioredis
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    sys.path.insert(0, "/app")
    from celery.exceptions import SoftTimeLimitExceeded
    from models import UserOpinion, UserTrack
    from services import recommendation_service as rs
    from workers.celery_app import REDIS_URL

    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    r = aioredis.from_url(REDIS_URL)

    stats = {"users": 0, "computed": 0, "errors": 0}
    try:
        # Active users = a track "liked" OR a library track. A user with neither
        # yields an empty reco (nothing to warm) → skipped.
        async with Session() as db:
            like_uids = (
                (
                    await db.execute(
                        select(UserOpinion.user_id)
                        .where(
                            UserOpinion.entity_type == "track",
                            UserOpinion.opinion == "liked",
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            lib_uids = (
                (await db.execute(select(UserTrack.user_id).distinct()))
                .scalars()
                .all()
            )
        user_ids = sorted(set(like_uids) | set(lib_uids))
        stats["users"] = len(user_ids)

        # The seed-agnostic similarity context (genre/label/playlist/set maps) is
        # built once by the first _compute (its 6h in-process cache has expired
        # since the previous nightly run) and reused by every subsequent user.
        for uid in user_ids:
            try:
                async with Session() as db:
                    full = await rs._compute(db, uid)
                await rs._cache_set(r, uid, full)
                stats["computed"] += 1
            except SoftTimeLimitExceeded:
                logger.warning(
                    "precompute_recommendations soft limit at user %s; "
                    "flushing partial: %s",
                    uid,
                    stats,
                )
                break
            except Exception:
                logger.exception("reco precompute failed for user %s", uid)
                stats["errors"] += 1
    finally:
        await r.aclose()
        await engine.dispose()

    logger.info("precompute_recommendations done: %s", stats)
    return stats
