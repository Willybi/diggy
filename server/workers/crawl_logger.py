"""CrawlLogger — context manager that records crawl runs to the crawl_logs table.

Usage:
    with CrawlLogger(session, task_type="crawl_playlist", target_id=123,
                      target_label="My Playlist", source="deezer") as log:
        # ... pipeline logic ...
        log.set_stats({"inserted": 12, "enriched": 8})
    # Auto-commits with duration_ms and status="success"
    # On exception: status="error", error_message=str(e)
"""

import logging
import sys
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

sys.path.insert(0, "/app")
from models import CrawlLog

logger = logging.getLogger(__name__)


class CrawlLogger:
    def __init__(
        self,
        session: Session,
        task_type: str,
        target_id: int | None = None,
        target_label: str | None = None,
        source: str | None = None,
        celery_task_id: str | None = None,
    ):
        self._session = session
        self._log = CrawlLog(
            task_type=task_type,
            target_id=target_id,
            target_label=target_label,
            source=source,
            status="running",
            started_at=datetime.now(timezone.utc),
            celery_task_id=celery_task_id,
        )
        self._start_mono = 0.0

    def set_stats(self, stats: dict):
        self._log.stats = stats

    def update_stats(self, **kwargs):
        if self._log.stats is None:
            self._log.stats = {}
        self._log.stats.update(kwargs)

    def __enter__(self):
        self._session.add(self._log)
        self._session.flush()
        self._start_mono = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.monotonic() - self._start_mono) * 1000)
        self._log.finished_at = datetime.now(timezone.utc)
        self._log.duration_ms = elapsed_ms

        if exc_type is not None:
            self._log.status = "error"
            self._log.error_message = str(exc_val)[:2000]
            logger.error(
                "CrawlLog[%s] %s failed after %dms: %s",
                self._log.task_type,
                self._log.target_label,
                elapsed_ms,
                exc_val,
            )
        else:
            self._log.status = "success"

        try:
            self._session.commit()
        except Exception:
            self._session.rollback()

        return False  # don't suppress exceptions

    @property
    def log_id(self) -> int | None:
        return self._log.id
