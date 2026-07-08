"""
Tests for the enrich_catalog_beatport single-instance Redis lock.

The lock prevents two instances (beat run vs admin trigger, or broker
re-delivery) from enriching the catalog concurrently — the root cause of
the 2026-07-08 DeadlockDetected failures and duplicated Beatport scraping.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

# Path so workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# Mock infra that isn't available outside Docker (same pattern as
# test_task_refactor.py — setdefault keeps this idempotent across files)
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


# Same attributes as test_task_refactor.py's decorator: both files overwrite
# the shared workers.celery_app mock, so whichever import order pytest picks,
# tasks decorated by either mock must satisfy both test files' assertions
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


@pytest.fixture
def catalog_mod():
    mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
    for m in mods_to_clear:
        del sys.modules[m]
    import workers.tasks.catalog as catalog
    return catalog


@pytest.fixture
def fake_redis(monkeypatch):
    """Configured `redis` module whose from_url returns a controllable client."""
    client = MagicMock()
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-abc"
    return task_self


class TestBeatportLock:
    def test_skips_when_lock_held(self, catalog_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock()
        monkeypatch.setattr(catalog_mod, "_run_enrich_catalog_beatport", run)
        fake_redis.set.return_value = False  # nx=True: lock already held
        fake_redis.get.return_value = "task-other"

        result = catalog_mod.enrich_catalog_beatport(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(self, catalog_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock(return_value={"enriched": 42})
        monkeypatch.setattr(catalog_mod, "_run_enrich_catalog_beatport", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-abc"  # still owns the lock

        result = catalog_mod.enrich_catalog_beatport(fake_self, 10)

        assert result == {"enriched": 42}
        run.assert_called_once_with(fake_self, 10)
        _, kwargs = fake_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == catalog_mod.BEATPORT_LOCK_TTL
        fake_redis.delete.assert_called_once_with("lock:enrich_beatport")

    def test_releases_lock_on_failure(self, catalog_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(catalog_mod, "_run_enrich_catalog_beatport", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-abc"

        with pytest.raises(RuntimeError):
            catalog_mod.enrich_catalog_beatport(fake_self)

        fake_redis.delete.assert_called_once_with("lock:enrich_beatport")

    def test_does_not_release_lock_it_no_longer_owns(
        self, catalog_mod, fake_redis, fake_self, monkeypatch
    ):
        """If the TTL expired mid-run and another instance took the lock,
        the finished task must not delete the new owner's lock."""
        run = MagicMock(return_value={"enriched": 1})
        monkeypatch.setattr(catalog_mod, "_run_enrich_catalog_beatport", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-newer"  # someone else owns it now

        catalog_mod.enrich_catalog_beatport(fake_self)

        fake_redis.delete.assert_not_called()

    def test_lock_ttl_covers_task_time_limit(self, catalog_mod):
        """The lock must not expire while a legitimate run is in progress."""
        assert catalog_mod.BEATPORT_LOCK_TTL >= 28800
