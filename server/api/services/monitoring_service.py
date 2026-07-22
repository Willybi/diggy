"""Monitoring service — reads the backlog time-series (metric_snapshots) and the
throughput/error/duration history (crawl_logs) for the admin monitoring page.

Everything is aggregated in Python: the JSON ``stats`` column is decoded to a
dict by SQLAlchemy on read, so we never reach for a PG-only JSON SQL operator —
the test suite runs on SQLite, prod on PostgreSQL, and both must agree.

Async (AsyncSession) side. DB loaders are awaited SEQUENTIALLY on the one
session (never asyncio.gather on a shared AsyncSession — it wedges asyncpg).
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Latest-run status is reported for these tasks in a fixed order; any other
# task_type present in crawl_logs is appended after them (alphabetically).
_KEY_TASK_TYPES = [
    "enrich_catalog",
    "enrich_beatport",
    "crawl_radar",
    "crawl_single_playlist",
    "recrawl_incomplete_sets",
    "crawl_trackid_latest",
    "backfill_trackid_sets",
    "compute_trends",
    "link_set_artists",
    "check_followed_artists",
]


def _as_int(value) -> int:
    """Coerce a stats value to int, treating anything non-numeric as 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


async def get_backlog_series(db: AsyncSession, since: datetime) -> list[dict]:
    """Backlog snapshots captured on/after ``since``, oldest first."""
    from models import MetricSnapshot

    rows = (
        (
            await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.captured_at >= since)
                .order_by(MetricSnapshot.captured_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {"captured_at": r.captured_at.isoformat(), "payload": r.payload or {}}
        for r in rows
    ]


async def get_throughput_series(db: AsyncSession, since: datetime) -> list[dict]:
    """Aggregate crawl_logs since ``since`` by (day, task_type, source).

    Per group: run count, error-run count (status='error'), summed
    enriched/not_found/merged (from the ``stats`` JSON), average + max
    duration_ms, and the derived hit-rate enriched/(enriched+not_found).
    Aggregated in Python — no JSON SQL operator (dialect-neutral).
    """
    from models import CrawlLog

    logs = (
        (
            await db.execute(
                select(CrawlLog)
                .where(CrawlLog.started_at >= since)
                .order_by(CrawlLog.started_at.asc())
            )
        )
        .scalars()
        .all()
    )

    groups: dict[tuple, dict] = {}
    for log in logs:
        if log.started_at is None:
            continue
        day = log.started_at.date().isoformat()
        key = (day, log.task_type, log.source)
        acc = groups.get(key)
        if acc is None:
            acc = groups[key] = {
                "day": day,
                "task_type": log.task_type,
                "source": log.source,
                "runs": 0,
                "errors": 0,
                "enriched": 0,
                "not_found": 0,
                "merged": 0,
                "_dur_sum": 0,
                "_dur_n": 0,
                "duration_ms_max": None,
            }
        acc["runs"] += 1
        if log.status == "error":
            acc["errors"] += 1
        stats = log.stats or {}
        acc["enriched"] += _as_int(stats.get("enriched"))
        acc["not_found"] += _as_int(stats.get("not_found"))
        acc["merged"] += _as_int(stats.get("merged"))
        if log.duration_ms is not None:
            acc["_dur_sum"] += log.duration_ms
            acc["_dur_n"] += 1
            acc["duration_ms_max"] = (
                log.duration_ms
                if acc["duration_ms_max"] is None
                else max(acc["duration_ms_max"], log.duration_ms)
            )

    series = []
    for acc in groups.values():
        denom = acc["enriched"] + acc["not_found"]
        series.append(
            {
                "day": acc["day"],
                "task_type": acc["task_type"],
                "source": acc["source"],
                "runs": acc["runs"],
                "errors": acc["errors"],
                "enriched": acc["enriched"],
                "not_found": acc["not_found"],
                "merged": acc["merged"],
                "hit_rate": round(acc["enriched"] / denom, 4) if denom else None,
                "duration_ms_avg": (
                    round(acc["_dur_sum"] / acc["_dur_n"]) if acc["_dur_n"] else None
                ),
                "duration_ms_max": acc["duration_ms_max"],
            }
        )
    series.sort(key=lambda r: (r["day"], r["task_type"], r["source"] or ""))
    return series


async def get_current_status(db: AsyncSession) -> dict:
    """Latest run per task_type + the most recent backlog snapshot.

    Key task types (``_KEY_TASK_TYPES``) come first in that fixed order; any
    other task_type present in crawl_logs is appended alphabetically.
    """
    from models import CrawlLog, MetricSnapshot

    task_types = (
        (await db.execute(select(CrawlLog.task_type).distinct())).scalars().all()
    )
    ordered = [t for t in _KEY_TASK_TYPES if t in task_types] + sorted(
        t for t in task_types if t not in _KEY_TASK_TYPES
    )

    last_runs = []
    for tt in ordered:
        row = (
            await db.execute(
                select(CrawlLog)
                .where(CrawlLog.task_type == tt)
                .order_by(CrawlLog.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            last_runs.append(
                {
                    "task_type": row.task_type,
                    "source": row.source,
                    "status": row.status,
                    "started_at": (
                        row.started_at.isoformat() if row.started_at else None
                    ),
                    "finished_at": (
                        row.finished_at.isoformat() if row.finished_at else None
                    ),
                    "duration_ms": row.duration_ms,
                }
            )

    latest = (
        await db.execute(
            select(MetricSnapshot)
            .order_by(MetricSnapshot.captured_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_snapshot = (
        {"captured_at": latest.captured_at.isoformat(), "payload": latest.payload or {}}
        if latest is not None
        else None
    )

    return {"last_runs": last_runs, "latest_snapshot": latest_snapshot}
