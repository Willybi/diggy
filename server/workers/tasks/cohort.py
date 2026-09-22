"""Celery task: recompute the derived artist watch cohort (C14.a).

Thin wrapper around ``workers.cohort.recompute`` — a read-mostly sweep over the
domain tables that materialises the ``artist_cohort`` table (auto-promotion /
rétrogradation without ever overwriting an admin override). Single-instance via a
Redis lock (SET NX EX + conditional release, same pattern as
``check_followed_artists``). NO ``autoretry_for=(Exception,)``:
``SoftTimeLimitExceeded`` IS an ``Exception``, so that decorator would turn a soft
timeout into an infinite retry loop.
"""

import logging
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Must stay strictly above time_limit (2100) so a live run's lock never expires
# under it; a killed worker's orphan lock self-heals within the TTL.
RECOMPUTE_ARTIST_COHORT_LOCK_TTL = 2400


@celery_app.task(
    name="workers.tasks.recompute_artist_cohort",
    bind=True,
    soft_time_limit=1800,
    time_limit=2100,
)
def recompute_artist_cohort(self):
    """Daily: rebuild the derived artist cohort from in-DB signals."""
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:recompute_artist_cohort"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=RECOMPUTE_ARTIST_COHORT_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "recompute_artist_cohort already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_recompute_artist_cohort(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run).
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_recompute_artist_cohort(task):
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from workers.cohort import recompute
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="recompute_artist_cohort",
            celery_task_id=task.request.id,
        ) as clog:
            stats = recompute(engine)
            clog.set_stats(stats)

    return stats
