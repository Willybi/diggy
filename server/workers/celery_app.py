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
    timezone="Europe/Paris",
    enable_utc=True,
    beat_schedule={
        "crawl-radar-daily": {
            "task": "workers.tasks.crawl_radar",
            "schedule": crontab(hour=8, minute=0),  # tous les jours à 8h (Europe/Paris)
        },
    },
)
