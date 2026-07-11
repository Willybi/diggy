"""
Tests for the AU4-L1 task locks (A3-11 / A3-14).

- resolve_set_tracks: single-instance Redis lock (SET NX EX) — the task is
  dispatched fire-and-forget by three beat tasks and the API, so overlapping
  runs used to double external enrichment traffic.
- import_rekordbox_xml: the finally block must only delete the per-user
  import lock it still owns (the router may have granted it to a newer import
  after TTL expiry).
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
def fake_redis(monkeypatch):
    """Configured `redis` module whose from_url returns a controllable client."""
    client = MagicMock()
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def sets_mod(fake_redis):
    mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
    for m in mods_to_clear:
        del sys.modules[m]
    import workers.tasks.sets as sets
    return sets


# import_rb binds `redis` at module level, so the mocked module must be in
# place (fake_redis) before the import happens
@pytest.fixture
def import_mod(fake_redis):
    mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
    for m in mods_to_clear:
        del sys.modules[m]
    import workers.tasks.import_rb as import_rb
    return import_rb


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-abc"
    return task_self


class TestResolveSetTracksLock:
    def test_skips_when_lock_held(self, sets_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock()
        monkeypatch.setattr(sets_mod, "_run_resolve_set_tracks", run)
        fake_redis.set.return_value = False  # nx=True: lock already held
        fake_redis.get.return_value = "task-other"

        result = sets_mod.resolve_set_tracks(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(self, sets_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock(return_value={"resolved": 7})
        monkeypatch.setattr(sets_mod, "_run_resolve_set_tracks", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-abc"  # still owns the lock

        result = sets_mod.resolve_set_tracks(fake_self)

        assert result == {"resolved": 7}
        run.assert_called_once_with(fake_self)
        _, kwargs = fake_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == sets_mod.RESOLVE_SET_TRACKS_LOCK_TTL
        fake_redis.delete.assert_called_once_with("lock:resolve_set_tracks")

    def test_releases_lock_on_failure(self, sets_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(sets_mod, "_run_resolve_set_tracks", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-abc"

        with pytest.raises(RuntimeError):
            sets_mod.resolve_set_tracks(fake_self)

        fake_redis.delete.assert_called_once_with("lock:resolve_set_tracks")

    def test_does_not_release_lock_it_no_longer_owns(
        self, sets_mod, fake_redis, fake_self, monkeypatch
    ):
        """If the TTL expired mid-run and another instance took the lock,
        the finished task must not delete the new owner's lock."""
        run = MagicMock(return_value={"resolved": 1})
        monkeypatch.setattr(sets_mod, "_run_resolve_set_tracks", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-newer"  # someone else owns it now

        sets_mod.resolve_set_tracks(fake_self)

        fake_redis.delete.assert_not_called()

    def test_lock_ttl_covers_task_time_limit(self, sets_mod):
        """The lock must not expire while a legitimate run is in progress."""
        assert sets_mod.RESOLVE_SET_TRACKS_LOCK_TTL > 7500


class TestRecrawlIncompleteSetsLock:
    """Same single-instance SET NX EX pattern as resolve_set_tracks (C6.b)."""

    def test_skips_when_lock_held(self, sets_mod, fake_redis, fake_self, monkeypatch):
        run = MagicMock()
        monkeypatch.setattr(sets_mod, "_run_recrawl_incomplete_sets", run)
        fake_redis.set.return_value = False  # nx=True: lock already held
        fake_redis.get.return_value = "task-other"

        result = sets_mod.recrawl_incomplete_sets(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, sets_mod, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"crawled": 3})
        monkeypatch.setattr(sets_mod, "_run_recrawl_incomplete_sets", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-abc"  # still owns the lock

        result = sets_mod.recrawl_incomplete_sets(fake_self)

        assert result == {"crawled": 3}
        run.assert_called_once_with(fake_self)
        _, kwargs = fake_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == sets_mod.RECRAWL_INCOMPLETE_SETS_LOCK_TTL
        fake_redis.delete.assert_called_once_with("lock:recrawl_incomplete_sets")

    def test_releases_lock_on_failure(
        self, sets_mod, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(sets_mod, "_run_recrawl_incomplete_sets", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-abc"

        with pytest.raises(RuntimeError):
            sets_mod.recrawl_incomplete_sets(fake_self)

        fake_redis.delete.assert_called_once_with("lock:recrawl_incomplete_sets")

    def test_does_not_release_lock_it_no_longer_owns(
        self, sets_mod, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"crawled": 1})
        monkeypatch.setattr(sets_mod, "_run_recrawl_incomplete_sets", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-newer"  # someone else owns it now

        sets_mod.recrawl_incomplete_sets(fake_self)

        fake_redis.delete.assert_not_called()

    def test_lock_ttl_covers_task_time_limit(self, sets_mod):
        """The lock must not expire while a legitimate run is in progress."""
        assert sets_mod.RECRAWL_INCOMPLETE_SETS_LOCK_TTL > 3900


class TestImportLockConditionalRelease:
    """The import task's finally only deletes the lock it still owns."""

    def _run_failing_import(self, import_mod, fake_redis, fake_self, monkeypatch,
                            task_id, user_id, lock_holder):
        """Run the task with a failing S3 download so it hits except + finally."""
        s3 = MagicMock()
        s3.get_object.side_effect = RuntimeError("minio down")
        monkeypatch.setattr(import_mod, "_get_s3", lambda: s3)
        # Progress key reads return None (empty progress); lock key reads
        # return the current holder
        fake_redis.get.side_effect = lambda key: (
            lock_holder if key == f"import:lock:{user_id}" else None
        )

        with pytest.raises(RuntimeError):
            import_mod.import_rekordbox_xml(fake_self, task_id, user_id)

    def test_finally_releases_owned_lock(
        self, import_mod, fake_redis, fake_self, monkeypatch
    ):
        self._run_failing_import(
            import_mod, fake_redis, fake_self, monkeypatch,
            task_id="task-42", user_id=7, lock_holder="task-42",
        )

        fake_redis.delete.assert_called_once_with("import:lock:7")

    def test_finally_keeps_lock_owned_by_newer_import(
        self, import_mod, fake_redis, fake_self, monkeypatch
    ):
        """A lock re-acquired by a newer import (after TTL expiry) must survive
        the old task's finally block."""
        self._run_failing_import(
            import_mod, fake_redis, fake_self, monkeypatch,
            task_id="task-42", user_id=7, lock_holder="task-newer",
        )

        fake_redis.delete.assert_not_called()
