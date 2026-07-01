"""
Celery task for computing radar trend scores.
"""

import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.compute_trends",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def compute_trends(self, window_days=30):
    """Compute trend scores for radar catalog entries.

    Score = sum(detection_count * 0.5^(age_days/14)) per catalog_id.
    Half-life of 14 days: recent detections count more.
    """
    import sys

    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from workers.db import get_engine

    sys.path.insert(0, "/app")

    engine = get_engine()
    with Session(engine) as session:
        from workers.crawl_logger import CrawlLogger

        with CrawlLogger(
            session, task_type="compute_trends", celery_task_id=self.request.id
        ) as clog:
            # Aggregate: for each catalog_id, count distinct playlists and
            # compute a decay-weighted score based on detection recency.
            rows = session.execute(
                text("""
                SELECT
                    rt.catalog_id,
                    COUNT(DISTINCT rt.watched_entity_id) AS detection_count,
                    SUM(
                        POWER(0.5, EXTRACT(EPOCH FROM (NOW() - rt.detected_at)) / 86400.0 / 14.0)
                    ) AS raw_score
                FROM radar_tracks rt
                WHERE rt.catalog_id IS NOT NULL
                  AND rt.detected_at >= NOW() - MAKE_INTERVAL(days => :window)
                GROUP BY rt.catalog_id
            """),
                {"window": window_days},
            ).fetchall()

            if not rows:
                clog.set_stats({"upserted": 0})
                return {"upserted": 0}

            # Upsert into radar_trends
            from datetime import datetime, timezone

            from models import RadarTrend
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            now = datetime.now(timezone.utc)
            values = [
                {
                    "catalog_id": r.catalog_id,
                    "trend_score": round(r.raw_score * r.detection_count, 4),
                    "window_days": window_days,
                    "detection_count": r.detection_count,
                    "computed_at": now,
                }
                for r in rows
            ]

            stmt = pg_insert(RadarTrend).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["catalog_id"],
                set_={
                    "trend_score": stmt.excluded.trend_score,
                    "window_days": stmt.excluded.window_days,
                    "detection_count": stmt.excluded.detection_count,
                    "computed_at": stmt.excluded.computed_at,
                },
            )
            session.execute(stmt)
            session.commit()

            logger.info("compute_trends: upserted %d entries", len(values))
            clog.set_stats({"upserted": len(values)})

    return {"upserted": len(values)}
