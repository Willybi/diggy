import os
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery = Celery(broker=REDIS_URL, backend=REDIS_URL)
