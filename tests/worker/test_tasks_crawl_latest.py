"""
Tests for crawl_trackid_latest.

Two layers: pure cursor-filtering helpers replicated without Celery/Redis/async
(TestFilterAudiostreamsByCursor), and a single-instance lock test that drives the
real task with celery/redis mocked (TestCrawlTrackidLatestLock, Lot L5 A3-04).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from trackid.parsing import parse_trackid_date

# Path so the workers package is importable (conftest only adds server/api)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# Mock infra that isn't available outside Docker (same pattern as
# test_task_locks.py — the guard keeps this idempotent across files)
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "requests",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


# Same decorator shape as test_task_locks.py: record task kwargs onto the fn
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
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)


# ---------------------------------------------------------------------------
# Pure helpers that replicate the task logic — testable without Celery
# ---------------------------------------------------------------------------


def _filter_audiostreams_by_cursor(
    audiostreams: list, last_run_ts: datetime
) -> tuple[list, bool]:
    """Replicate the per-page filtering logic from crawl_trackid_latest.

    Returns (to_import, stop_flag).
    stop_flag=True means pagination should stop (an older-than-cursor item was found).
    """
    to_import = []
    stop_flag = False
    for audiostream in audiostreams:
        added_on_str = audiostream.get("addedOn")
        if not added_on_str:
            continue
        added_on = parse_trackid_date(added_on_str)
        if added_on is None:
            continue
        if added_on <= last_run_ts:
            stop_flag = True
            break
        to_import.append(audiostream)
    return to_import, stop_flag


def _get_last_run_ts(cursor_value: str | None) -> datetime:
    """Replicate the cursor-reading logic from crawl_trackid_latest."""
    if not cursor_value:
        return datetime.now(timezone.utc) - timedelta(hours=24)
    dt = datetime.fromisoformat(cursor_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Fixture cursor — 2026-07-07 10:00 UTC
# ---------------------------------------------------------------------------

CURSOR = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFilterAudiostreamsByCursor:
    def test_filter_newer_than_cursor(self):
        """All sets newer than cursor → all imported, stop_flag=False."""
        audiostreams = [
            {"id": 1, "addedOn": "2026-07-08T12:00:00"},
            {"id": 2, "addedOn": "2026-07-08T11:00:00"},
        ]
        to_import, stop_flag = _filter_audiostreams_by_cursor(audiostreams, CURSOR)
        assert len(to_import) == 2
        assert to_import[0]["id"] == 1
        assert to_import[1]["id"] == 2
        assert stop_flag is False

    def test_filter_stops_at_cursor(self):
        """Set older than cursor triggers stop; subsequent items not included."""
        audiostreams = [
            {"id": 1, "addedOn": "2026-07-08T12:00:00"},  # newer → import
            {"id": 2, "addedOn": "2026-07-07T09:00:00"},  # older → stop
            {"id": 3, "addedOn": "2026-07-06T08:00:00"},  # not reached
        ]
        to_import, stop_flag = _filter_audiostreams_by_cursor(audiostreams, CURSOR)
        assert len(to_import) == 1
        assert to_import[0]["id"] == 1
        assert stop_flag is True

    def test_filter_empty_list(self):
        """Empty input → empty output, no stop."""
        to_import, stop_flag = _filter_audiostreams_by_cursor([], CURSOR)
        assert to_import == []
        assert stop_flag is False

    def test_filter_missing_added_on(self):
        """Audiostream without addedOn is silently skipped; others processed normally."""
        audiostreams = [
            {"id": 1, "title": "No date field"},
            {"id": 2, "addedOn": "2026-07-08T12:00:00"},
        ]
        to_import, stop_flag = _filter_audiostreams_by_cursor(audiostreams, CURSOR)
        assert len(to_import) == 1
        assert to_import[0]["id"] == 2
        assert stop_flag is False

    def test_first_run_no_cursor(self):
        """Absent cursor yields last_run_ts ≈ now - 24h."""
        ts = _get_last_run_ts(None)
        age = datetime.now(timezone.utc) - ts
        # Should be approximately 24 hours (test runs in microseconds)
        assert timedelta(hours=23, minutes=59) < age < timedelta(hours=24, minutes=1)
        assert ts.tzinfo is not None


# ---------------------------------------------------------------------------
# Lock test (Lot L5 / A3-04): crawl_trackid_latest is single-instance via
# lock:crawl_trackid_latest — a run started while the lock is held must skip
# without touching the crawl body. Same SET NX EX pattern as resolve_set_tracks
# / recrawl_incomplete_sets (test_task_locks.py).
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    """Configured `redis` module whose from_url returns a controllable client."""
    client = MagicMock()
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def sets_mod(fake_redis):
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.tasks.sets as sets
    return sets


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-crawl"
    return task_self


class TestCrawlTrackidLatestLock:
    def test_skips_when_lock_held(self, sets_mod, fake_redis, fake_self, monkeypatch):
        """A run with lock:crawl_trackid_latest already held returns the skip
        marker and never runs the crawl body."""
        run = MagicMock()
        monkeypatch.setattr(sets_mod, "_run_crawl_trackid_latest", run)
        fake_redis.set.return_value = False  # nx=True: lock already held
        fake_redis.get.return_value = "task-other"

        result = sets_mod.crawl_trackid_latest(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()
        args, kwargs = fake_redis.set.call_args
        assert args[0] == "lock:crawl_trackid_latest"
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == sets_mod.CRAWL_TRACKID_LATEST_LOCK_TTL
