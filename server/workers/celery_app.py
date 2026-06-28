from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, setup_logging
import os
import logging

logger = logging.getLogger(__name__)


class CeleryTaskFilter(logging.Filter):
    """Inject task_id into all log records for correlation."""

    def filter(self, record):
        from celery._state import get_current_task
        task = get_current_task()
        if task and task.request:
            record.task_id = task.request.id or "-"
            record.task_name = task.name or "-"
        else:
            record.task_id = "-"
            record.task_name = "-"
        return True


@setup_logging.connect
def configure_worker_logging(**kwargs):
    """Configure structured logging with task_id for all worker log output."""
    handler = logging.StreamHandler()
    handler.addFilter(CeleryTaskFilter())
    formatter = logging.Formatter(
        "[%(asctime)s %(levelname)s] [%(task_name)s:%(task_id)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Configurable via env vars with sensible defaults
WORKER_CONCURRENCY = int(os.environ.get("CELERY_WORKER_CONCURRENCY", "4"))
TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_SOFT_TIME_LIMIT", "1800"))
TASK_TIME_LIMIT = int(os.environ.get("CELERY_TIME_LIMIT", "3600"))

celery_app = Celery(
    "diggy",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="Europe/Paris",
    enable_utc=True,
    # Worker concurrency & reliability
    worker_concurrency=WORKER_CONCURRENCY,
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
    task_time_limit=TASK_TIME_LIMIT,
    task_acks_late=True,            # re-deliver on crash
    worker_prefetch_multiplier=1,   # don't hoard tasks
    task_reject_on_worker_lost=True,  # requeue if worker crashes mid-task
    # Task routing
    task_routes={
        "workers.tasks.crawl_single_playlist": {"queue": "crawl"},
        "workers.tasks.enrich_catalog_beatport": {"queue": "enrich"},
        "workers.tasks.enrich_catalog": {"queue": "enrich"},
    },
    # Dead letter queue — consumed by default queue list, inspectable via Redis
    task_default_queue="celery",
    beat_schedule={
        "crawl-radar-daily": {
            "task": "workers.tasks.crawl_radar",
            "schedule": crontab(hour=3, minute=0),  # tous les jours à 3h
        },
        "crawl-followed-sets-daily": {
            "task": "workers.tasks.crawl_followed_sets",
            "schedule": crontab(hour=4, minute=0),  # tous les jours à 4h
        },
        "enrich-catalog-daily": {
            "task": "workers.tasks.enrich_catalog",
            "schedule": crontab(hour=5, minute=0),  # tous les jours à 5h
        },
        "enrich-catalog-beatport-daily": {
            "task": "workers.tasks.enrich_catalog_beatport",
            "schedule": crontab(hour=6, minute=0),  # tous les jours à 6h
        },
    },
)


# DLQ: on final failure (after all retries exhausted), push task info to dead_letter queue
@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None,
                    args=None, kwargs=None, traceback=None, einfo=None, **kw):
    """Route permanently failed tasks to the dead_letter Redis queue."""
    task = sender
    # Only route to DLQ after all retries are exhausted
    if hasattr(task, 'request') and task.request.retries < task.max_retries:
        return

    import json
    import redis as redis_lib
    from datetime import datetime, timezone

    try:
        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        entry = json.dumps({
            "task_id": task_id,
            "task_name": sender.name if sender else "unknown",
            "args": list(args) if args else [],
            "kwargs": kwargs or {},
            "exception": str(exception),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        })
        r.lpush("dead_letter", entry)
        r.ltrim("dead_letter", 0, 999)  # keep last 1000 entries
        logger.error("Task %s [%s] moved to DLQ after final failure: %s",
                     sender.name if sender else "unknown", task_id, exception)
    except Exception as dlq_err:
        logger.error("Failed to push task %s to DLQ: %s", task_id, dlq_err)
