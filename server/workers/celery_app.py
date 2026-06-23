from celery import Celery
from celery.schedules import crontab
import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

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
    worker_concurrency=4,
    task_soft_time_limit=1800,      # 30 min soft limit
    task_time_limit=3600,           # 60 min hard limit
    task_acks_late=True,            # re-deliver on crash
    worker_prefetch_multiplier=1,   # don't hoard tasks
    # Task routing
    task_routes={
        "workers.tasks.crawl_single_playlist": {"queue": "crawl"},
        "workers.tasks.enrich_catalog_beatport": {"queue": "enrich"},
        "workers.tasks.enrich_catalog": {"queue": "enrich"},
    },
    beat_schedule={
        "crawl-radar-daily": {
            "task": "workers.tasks.crawl_radar",
            "schedule": crontab(hour=8, minute=0),  # tous les jours à 8h
        },
        "check-previews-weekly": {
            "task": "workers.tasks.check_previews",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),  # dimanche à 3h
        },
        "enrich-catalog-weekly": {
            "task": "workers.tasks.enrich_catalog",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # dimanche à 4h
        },
        "crawl-followed-sets-daily": {
            "task": "workers.tasks.crawl_followed_sets",
            "schedule": crontab(hour=9, minute=0),  # tous les jours à 9h
        },
        "enrich-catalog-beatport-weekly": {
            "task": "workers.tasks.enrich_catalog_beatport",
            "schedule": crontab(hour=5, minute=0, day_of_week=0),  # dimanche à 5h
        },
    },
)
