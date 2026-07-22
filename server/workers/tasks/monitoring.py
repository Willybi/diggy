"""Celery task: hourly time-series snapshot of enrichment/crawl backlog sizes.

The throughput / error / duration history already lives in ``crawl_logs`` (every
run writes its stats there). The one thing it cannot give is the *size* of each
backlog sampled over time — that is what this task adds, as a single
``metric_snapshots`` row per run.
"""

import logging
import sys
from datetime import datetime, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Artist deezer_id sentinel for "confirmed absent from Deezer" — a non-NULL
# value, so it never falls into the id-missing (link) backlog on its own.
_ARTIST_NOT_FOUND = "NOT_FOUND"


@celery_app.task(name="workers.tasks.snapshot_backlogs", bind=True)
def snapshot_backlogs(self):
    """Sample every enrichment/crawl backlog and persist one MetricSnapshot row.

    Read-only over the domain tables (no external API), so it is loop-safe and
    carries NO autoretry — a transient DB blip is simply retried next hour.
    """
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, CatalogEntry, DJSet, MetricSnapshot
    from workers.db import get_engine
    from workers.enrichment import count_enrich_backlog

    engine = get_engine()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:

        def _count(count_col, *predicates) -> int:
            return (
                session.execute(
                    select(func.count(count_col)).where(*predicates)
                ).scalar()
                or 0
            )

        payload = {
            "enrich": {
                "deezer": count_enrich_backlog(session, source="deezer", now=now),
                "beatport": count_enrich_backlog(session, source="beatport", now=now),
            },
            "artists": {
                # deezer_id IS NULL already excludes the NOT_FOUND sentinel
                # (a non-NULL value), so these are the artists still to link.
                "backlog_link": _count(Artist.id, Artist.deezer_id.is_(None)),
                # Linked (real id, not the sentinel) but still missing artwork.
                # has_artwork is nullable with no server_default → isnot(True)
                # counts both False and NULL (mirror of tasks/artists.py).
                "backlog_artwork": _count(
                    Artist.id,
                    Artist.deezer_id.isnot(None),
                    Artist.deezer_id != _ARTIST_NOT_FOUND,
                    Artist.has_artwork.isnot(True),
                ),
            },
            "sets": {
                # Root sets (parent_set_id IS NULL) still eligible for re-crawl.
                "recrawl_backlog": _count(
                    DJSet.id,
                    DJSet.parent_set_id.is_(None),
                    DJSet.recrawl_status != "final",
                ),
            },
            "catalog": {
                "total": _count(CatalogEntry.id),
            },
        }

        session.add(MetricSnapshot(captured_at=now, payload=payload))
        session.commit()

    logger.info("snapshot_backlogs wrote a metric_snapshots row at %s", now)
    return payload
