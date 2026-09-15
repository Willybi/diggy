"""Tests for the split admin monitoring API (Observabilité L3):

- GET /api/admin/monitoring — instant status only (latest run per task via ONE
  window query + latest snapshot) + `integrity` read from the snapshot payload
  (computed hourly by snapshot_backlogs since L1, no longer recomputed live).
- GET /api/admin/monitoring/series?days=N — backlog + throughput time-series,
  Redis-cached (monitoring:series:{days}, TTL 600 s, fail-open).

Seeds metric_snapshots / crawl_logs rows through the ORM (which also confirms
the models are picked up by the conftest create_all).
"""
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from dependencies import get_redis
from main import app
from models import CrawlLog, MetricSnapshot


def _now():
    return datetime.now(timezone.utc)


# Payload shaped like snapshot_backlogs writes it since L1 (integrity key on
# board); older snapshots lack the key — covered by dedicated tests below.
_PAYLOAD = {
    "enrich": {
        "deezer": {"total_missing": 5, "total_linked": 100},
        "beatport": {"total_missing": 50, "total_linked": 60},
    },
    "artists": {"backlog_link": 3, "backlog_artwork": 7},
    "sets": {"recrawl_backlog": 2},
    "catalog": {"total": 105},
    "integrity": {"artist_divergence": 4, "missing_m2m_link": 9},
}


async def _seed_snapshot(db, *, captured_at=None, payload=None):
    snap = MetricSnapshot(
        captured_at=captured_at or _now(),
        payload=payload if payload is not None else _PAYLOAD,
    )
    db.add(snap)
    await db.commit()
    return snap


async def _seed_crawl_log(db, **overrides):
    started = overrides.pop("started_at", _now())
    log = CrawlLog(
        task_type=overrides.pop("task_type", "enrich_catalog"),
        source=overrides.pop("source", "deezer"),
        status=overrides.pop("status", "success"),
        started_at=started,
        finished_at=overrides.pop("finished_at", started + timedelta(seconds=5)),
        duration_ms=overrides.pop("duration_ms", 5000),
        stats=overrides.pop("stats", {"enriched": 8, "not_found": 2, "merged": 1}),
        **overrides,
    )
    db.add(log)
    await db.commit()
    return log


class _BrokenRedis:
    """A Redis whose every op raises — exercises the fail-open cache path."""

    def __getattr__(self, name):
        async def _raise(*args, **kwargs):
            raise ConnectionError("redis down")

        return _raise


@pytest_asyncio.fixture
async def broken_redis():
    """Swap the conftest FakeRedis for a raising one (pattern: test_import_rb)."""
    old = app.dependency_overrides.get(get_redis)

    async def _override():
        yield _BrokenRedis()

    app.dependency_overrides[get_redis] = _override
    yield
    if old is not None:
        app.dependency_overrides[get_redis] = old
    else:
        app.dependency_overrides.pop(get_redis, None)


class TestMonitoringAuth:
    async def test_requires_auth(self, client):
        r = await client.get("/api/admin/monitoring")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/monitoring")
        assert r.status_code == 403

    async def test_series_requires_auth(self, client):
        r = await client.get("/api/admin/monitoring/series")
        assert r.status_code == 401

    async def test_series_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/monitoring/series")
        assert r.status_code == 403


class TestMonitoringStatus:
    """GET /admin/monitoring — L3 contract: {status, integrity}, no series."""

    async def test_returns_status_and_integrity_only(self, admin_client, db):
        await _seed_snapshot(db)
        await _seed_crawl_log(db)

        r = await admin_client.get("/api/admin/monitoring")
        assert r.status_code == 200
        data = r.json()
        # The series moved to /monitoring/series (L3 split).
        assert set(data) == {"status", "integrity"}
        assert "last_runs" in data["status"]
        assert "latest_snapshot" in data["status"]
        assert "snapshot_stale" in data["status"]
        assert "snapshot_age_seconds" in data["status"]

    async def test_empty_db_ok(self, admin_client):
        r = await admin_client.get("/api/admin/monitoring")
        assert r.status_code == 200
        data = r.json()
        assert data["status"]["last_runs"] == []
        assert data["status"]["latest_snapshot"] is None
        assert data["status"]["snapshot_stale"] is True
        assert data["integrity"] is None

    async def test_integrity_read_from_snapshot_payload(self, admin_client, db):
        await _seed_snapshot(db)

        r = await admin_client.get("/api/admin/monitoring")
        assert r.json()["integrity"] == {
            "artist_divergence": 4,
            "missing_m2m_link": 9,
        }

    async def test_integrity_none_when_snapshot_lacks_key(self, admin_client, db):
        # Snapshots written before the L1 deploy don't carry "integrity".
        await _seed_snapshot(db, payload={"catalog": {"total": 105}})

        r = await admin_client.get("/api/admin/monitoring")
        assert r.status_code == 200
        assert r.json()["integrity"] is None

    async def test_latest_run_per_task_with_multiple_runs(self, admin_client, db):
        # Window query correctness: several runs per task → the newest one wins.
        now = _now()
        await _seed_crawl_log(db, started_at=now - timedelta(hours=3), status="error")
        await _seed_crawl_log(
            db, started_at=now - timedelta(hours=1), status="success"
        )
        await _seed_crawl_log(
            db,
            task_type="compute_trends",
            source=None,
            started_at=now - timedelta(hours=2),
            status="error",
        )
        await _seed_crawl_log(
            db, task_type="compute_trends", source=None, started_at=now
        )

        r = await admin_client.get("/api/admin/monitoring")
        runs = {row["task_type"]: row for row in r.json()["status"]["last_runs"]}
        assert set(runs) == {"enrich_catalog", "compute_trends"}
        assert runs["enrich_catalog"]["status"] == "success"
        assert runs["compute_trends"]["status"] == "success"

    async def test_key_task_types_ordered_first(self, admin_client, db):
        # An unknown task_type sorts after the _KEY_TASK_TYPES block, and the
        # key ones keep their fixed order regardless of insertion order.
        await _seed_crawl_log(db, task_type="aaa_custom_task", source=None)
        await _seed_crawl_log(db, task_type="compute_trends", source=None)
        await _seed_crawl_log(db, task_type="enrich_catalog")

        r = await admin_client.get("/api/admin/monitoring")
        order = [row["task_type"] for row in r.json()["status"]["last_runs"]]
        assert order == ["enrich_catalog", "compute_trends", "aaa_custom_task"]

    async def test_status_reports_latest_snapshot(self, admin_client, db):
        await _seed_snapshot(db)

        r = await admin_client.get("/api/admin/monitoring")
        status = r.json()["status"]
        assert status["latest_snapshot"]["payload"]["catalog"]["total"] == 105
        assert status["snapshot_stale"] is False


class TestMonitoringSeries:
    """GET /admin/monitoring/series — backlog + throughput, Redis-cached."""

    async def test_returns_sections(self, admin_client, db):
        await _seed_snapshot(db)
        await _seed_crawl_log(db)

        r = await admin_client.get("/api/admin/monitoring/series")
        assert r.status_code == 200
        data = r.json()
        assert set(data) == {"backlog_series", "throughput_series"}

    async def test_empty_db_ok(self, admin_client):
        r = await admin_client.get("/api/admin/monitoring/series")
        assert r.status_code == 200
        data = r.json()
        assert data["backlog_series"] == []
        assert data["throughput_series"] == []

    async def test_backlog_snapshot_returned(self, admin_client, db):
        await _seed_snapshot(db)

        r = await admin_client.get("/api/admin/monitoring/series")
        series = r.json()["backlog_series"]
        assert len(series) == 1
        item = series[0]
        assert item["payload"]["catalog"]["total"] == 105
        assert item["payload"]["artists"]["backlog_link"] == 3

    async def test_throughput_aggregates_and_hit_rate(self, admin_client, db):
        # Two runs of the same task/source on the same day → aggregated into one
        # row (runs=2), hit_rate = enriched/(enriched+not_found).
        now = _now()
        await _seed_crawl_log(db, started_at=now, stats={"enriched": 8, "not_found": 2})
        await _seed_crawl_log(
            db,
            started_at=now,
            stats={"enriched": 2, "not_found": 8},
            duration_ms=3000,
        )

        r = await admin_client.get("/api/admin/monitoring/series")
        series = r.json()["throughput_series"]
        assert len(series) == 1
        row = series[0]
        assert row["task_type"] == "enrich_catalog"
        assert row["source"] == "deezer"
        assert row["runs"] == 2
        assert row["enriched"] == 10
        assert row["not_found"] == 10
        assert row["hit_rate"] == 0.5
        assert row["duration_ms_max"] == 5000
        assert row["duration_ms_avg"] == 4000

    async def test_error_run_counted(self, admin_client, db):
        await _seed_crawl_log(db, status="error", stats=None, error_message="boom")

        r = await admin_client.get("/api/admin/monitoring/series")
        row = r.json()["throughput_series"][0]
        assert row["runs"] == 1
        assert row["errors"] == 1
        # No enriched/not_found → hit_rate undefined
        assert row["hit_rate"] is None

    async def test_days_window_excludes_old_snapshots(self, admin_client, db):
        await _seed_snapshot(db, captured_at=_now() - timedelta(days=40))

        r = await admin_client.get("/api/admin/monitoring/series?days=14")
        assert r.json()["backlog_series"] == []

        r2 = await admin_client.get("/api/admin/monitoring/series?days=60")
        assert len(r2.json()["backlog_series"]) == 1

    async def test_days_bounds_validated(self, admin_client):
        assert (
            await admin_client.get("/api/admin/monitoring/series?days=0")
        ).status_code == 422
        assert (
            await admin_client.get("/api/admin/monitoring/series?days=366")
        ).status_code == 422


class TestMonitoringSeriesCache:
    """Redis result cache (monitoring:series:{days}, TTL 600 s, fail-open)."""

    async def test_second_call_served_from_cache(self, admin_client, db):
        await _seed_crawl_log(db, stats={"enriched": 8, "not_found": 2})

        first = (await admin_client.get("/api/admin/monitoring/series")).json()
        assert first["throughput_series"][0]["runs"] == 1

        # A row added AFTER the first call must NOT show up: the second call is
        # served from the cache written by the first (TTL 600 s ≫ test time).
        await _seed_crawl_log(db, stats={"enriched": 1, "not_found": 0})
        second = (await admin_client.get("/api/admin/monitoring/series")).json()
        assert second == first
        assert second["throughput_series"][0]["runs"] == 1

    async def test_cache_keyed_by_days(self, admin_client, db):
        # A different days window is a different cache entry — no cross-serving.
        await _seed_snapshot(db, captured_at=_now() - timedelta(days=40))

        r14 = await admin_client.get("/api/admin/monitoring/series?days=14")
        assert r14.json()["backlog_series"] == []
        r60 = await admin_client.get("/api/admin/monitoring/series?days=60")
        assert len(r60.json()["backlog_series"]) == 1

    async def test_fail_open_when_redis_raises(self, admin_client, db, broken_redis):
        # get AND setex both raise → direct compute, still a correct 200.
        await _seed_crawl_log(db, stats={"enriched": 8, "not_found": 2})

        r = await admin_client.get("/api/admin/monitoring/series")
        assert r.status_code == 200
        assert r.json()["throughput_series"][0]["enriched"] == 8
