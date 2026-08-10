"""Test for the snapshot_backlogs Celery task (workers/tasks/monitoring).

Runs the real task function (celery ecosystem mocked, same pattern as
test_tasks_observability.py) against an in-memory SQLite engine and asserts it
writes ONE metric_snapshots row whose payload is structured by domain.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Mock infra that isn't available outside Docker (same pattern as
# test_tasks_observability.py — the shared workers.celery_app mock is overwritten
# below, and re-imported per-test via the tasks_env fixture).
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "curl_cffi", "curl_cffi.requests",
    "requests",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.autoretry_for = kwargs.get("autoretry_for", ())
        fn.bind = kwargs.get("bind", False)
        fn.soft_time_limit = kwargs.get("soft_time_limit")
        fn.time_limit = kwargs.get("time_limit")
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
_celery_app_mod = MagicMock(celery_app=_celery_mock)
sys.modules["workers.celery_app"] = _celery_app_mod

from datetime import datetime, timedelta, timezone  # noqa: E402

from database import Base  # noqa: E402
from models import Artist, CatalogEntry, CrawlLog, DJSet, MetricSnapshot  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture
def task_engine():
    engine = create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def monitoring_task(task_engine, monkeypatch):
    """Import the real monitoring task with celery mocked + engine redirected."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.db as workers_db
    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)
    import workers.tasks.monitoring as monitoring_mod
    return SimpleNamespace(mod=monitoring_mod, engine=task_engine)


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-snapshot"
    return task_self


class TestSnapshotBacklogs:
    def test_writes_one_snapshot_with_domain_payload(self, monitoring_task, fake_self):
        engine = monitoring_task.engine
        with Session(engine) as s:
            # never_tried deezer backlog + a linked artwork-missing artist +
            # an active root set + a plain catalog row.
            s.add(
                CatalogEntry(
                    title="Track", artist="A", normalized_key="track - a"
                )
            )
            # BPM analysis candidate: preview + real deezer_id + no bpm + not yet
            # analyzed → bpm_analysis_candidate_filter() matches it.
            s.add(
                CatalogEntry(
                    title="Preview",
                    artist="B",
                    normalized_key="preview - b",
                    has_preview=True,
                    deezer_id="dz-preview",
                )
            )
            s.add(
                Artist(name="Linked", normalized_name="linked", deezer_id="dz-1")
            )  # backlog_artwork (has_artwork NULL/False)
            s.add(
                Artist(name="Unlinked", normalized_name="unlinked")
            )  # backlog_link (deezer_id NULL)
            s.add(DJSet(source="trackid", title="Root set"))  # recrawl_backlog
            s.commit()

        result = monitoring_task.mod.snapshot_backlogs(fake_self)

        # Exactly one snapshot row persisted
        with Session(engine) as s:
            rows = s.execute(select(MetricSnapshot)).scalars().all()
        assert len(rows) == 1
        snap = rows[0]
        assert snap.captured_at is not None

        payload = snap.payload
        # Same object is returned by the task
        assert result == payload
        # Structured by domain
        assert set(payload) == {"enrich", "artists", "sets", "catalog"}
        assert set(payload["enrich"]) == {"deezer", "beatport"}
        assert set(payload["enrich"]["deezer"]) == {
            "never_tried",
            "due_retry",
            "cooldown",
            "abandoned",
            "total_missing",
            "total_linked",
        }
        # The seeded rows land in the right buckets
        assert payload["enrich"]["deezer"]["never_tried"] == 1
        assert payload["artists"]["backlog_link"] == 1
        assert payload["artists"]["backlog_artwork"] == 1
        assert payload["sets"]["recrawl_backlog"] == 1
        assert payload["catalog"]["total"] == 2
        # E2.c: only the preview-without-bpm row is a BPM-analysis candidate.
        assert payload["catalog"]["bpm_missing"] == 1

    def test_runs_on_empty_db(self, monitoring_task, fake_self):
        result = monitoring_task.mod.snapshot_backlogs(fake_self)

        with Session(monitoring_task.engine) as s:
            assert len(s.execute(select(MetricSnapshot)).scalars().all()) == 1
        assert result["catalog"]["total"] == 0
        assert result["catalog"]["bpm_missing"] == 0
        assert result["enrich"]["deezer"]["total_missing"] == 0

    def test_task_has_no_autoretry(self, monitoring_task):
        # Loop-safe: a transient DB blip is retried next hour, never re-looped.
        assert monitoring_task.mod.snapshot_backlogs.autoretry_for == ()


class TestRetentionPurge:
    """AV3: metric_snapshots + crawl_logs are purged past RETENTION_DAYS."""

    def test_purges_old_rows_keeps_recent(self, monitoring_task, fake_self):
        engine = monitoring_task.engine
        retention_days = monitoring_task.mod.RETENTION_DAYS
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=retention_days + 30)  # well past the cutoff
        recent_ts = now - timedelta(days=10)  # comfortably inside the window

        with Session(engine) as s:
            s.add(MetricSnapshot(captured_at=old_ts, payload={"old": True}))
            s.add(MetricSnapshot(captured_at=recent_ts, payload={"recent": True}))
            s.add(
                CrawlLog(task_type="enrich_catalog", started_at=old_ts, status="success")
            )
            s.add(
                CrawlLog(
                    task_type="enrich_catalog", started_at=recent_ts, status="success"
                )
            )
            s.commit()

        monitoring_task.mod.snapshot_backlogs(fake_self)

        with Session(engine) as s:
            snap_dates = s.execute(
                select(MetricSnapshot.captured_at)
            ).scalars().all()
            log_dates = s.execute(select(CrawlLog.started_at)).scalars().all()

        # No row older than the cutoff survives on either table. SQLite reads
        # tz-aware columns back as naive, so compare on a naive UTC basis.
        def _naive(d):
            return d.replace(tzinfo=None) if d.tzinfo else d

        cutoff = (now - timedelta(days=retention_days)).replace(tzinfo=None)
        assert all(_naive(d) >= cutoff for d in snap_dates), snap_dates
        assert all(_naive(d) >= cutoff for d in log_dates), log_dates
        # The recent seed + the snapshot the run just wrote remain; the old is gone.
        assert len(snap_dates) == 2
        assert len(log_dates) == 1

    def test_purge_is_idempotent_on_second_run(self, monitoring_task, fake_self):
        engine = monitoring_task.engine
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=monitoring_task.mod.RETENTION_DAYS + 30)
        with Session(engine) as s:
            s.add(MetricSnapshot(captured_at=old_ts, payload={"old": True}))
            s.commit()

        monitoring_task.mod.snapshot_backlogs(fake_self)  # purges the old row
        monitoring_task.mod.snapshot_backlogs(fake_self)  # nothing old left to purge

        with Session(engine) as s:
            rows = s.execute(select(MetricSnapshot)).scalars().all()
        # Two runs → two fresh snapshots, the pre-existing old one is gone.
        assert len(rows) == 2
        assert all(r.payload != {"old": True} for r in rows)
