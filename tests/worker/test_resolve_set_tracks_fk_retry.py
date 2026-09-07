"""DIGGY-APP-4 / 1G — resolve_set_tracks must survive a concurrent catalog merge.

A parallel merge_catalog_entries (enrichment dedup) can DELETE a loser catalog
row between resolve_set_tracks' bulk get-or-create snapshot and the final commit,
so the executemany `UPDATE set_tracks SET catalog_id=...` violates the
`set_tracks_catalog_id_fkey` constraint and the whole batch is DLQ'd. The task
now re-resolves from a clean read a bounded number of times ON THAT FK VIOLATION
ONLY (twin of catalog._commit_with_deadlock_retry); any other IntegrityError is
re-raised at once, and a persistent FK race eventually propagates.

_resolve_once is mocked so the retry loop is tested in isolation (no Docker/DB).
"""
import os
import sys
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

# Path so the workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# The module does `from workers.celery_app import celery_app` at import time and
# decorates its tasks — mock the broker infra that isn't available outside Docker.
for _mod in ["celery", "celery.schedules", "celery.signals", "celery._state",
             "celery.exceptions", "redis", "redis.exceptions", "requests"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
if "workers.celery_app" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.task.side_effect = lambda *a, **k: (lambda fn: fn)
    sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

from workers.tasks import sets as sets_task  # noqa: E402


def _fk_error():
    """An IntegrityError whose driver `orig` names the set_tracks catalog FK."""
    orig = Exception(
        'insert or update on table "set_tracks" violates foreign key '
        'constraint "set_tracks_catalog_id_fkey"'
    )
    return IntegrityError("UPDATE set_tracks SET catalog_id=...", {}, orig)


def _other_integrity_error():
    """A different IntegrityError (e.g. a unique violation) — not retryable."""
    orig = Exception('duplicate key value violates unique constraint "uq_foo"')
    return IntegrityError("INSERT INTO foo ...", {}, orig)


class _FakeSession:
    """Stand-in for the log Session context manager (never queried directly)."""

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return MagicMock()

    def __exit__(self, *a):
        return False


class _FakeCrawlLogger:
    def __init__(self, *a, **k):
        self.stats = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_stats(self, stats):
        self.stats = stats


@pytest.fixture(autouse=True)
def _patch_infra(monkeypatch):
    """Neutralise the log Session / CrawlLogger / engine + the backoff sleep."""
    monkeypatch.setitem(
        sys.modules, "workers.crawl_logger", MagicMock(CrawlLogger=_FakeCrawlLogger)
    )
    monkeypatch.setitem(
        sys.modules, "workers.db", MagicMock(get_engine=lambda: object())
    )
    monkeypatch.setattr("sqlalchemy.orm.Session", _FakeSession)
    monkeypatch.setattr(sets_task.time, "sleep", lambda *_: None)


def _task():
    task = MagicMock()
    task.request.id = "test-task-id"
    return task


def test_retries_then_succeeds_after_fk_race(monkeypatch):
    """(a) FK violation once, then a clean pass → retried, correct count returned."""
    resolve = MagicMock(side_effect=[_fk_error(), 7])
    monkeypatch.setattr(sets_task, "_resolve_once", resolve)

    result = sets_task._run_resolve_set_tracks(_task())

    assert result == {"resolved": 7}
    assert resolve.call_count == 2


def test_non_fk_integrity_error_reraised_immediately(monkeypatch):
    """(b) an unrelated IntegrityError propagates without any retry."""
    resolve = MagicMock(side_effect=_other_integrity_error())
    monkeypatch.setattr(sets_task, "_resolve_once", resolve)

    with pytest.raises(IntegrityError):
        sets_task._run_resolve_set_tracks(_task())

    assert resolve.call_count == 1  # no retry on a non-FK violation


def test_persistent_fk_race_propagates_after_bound(monkeypatch):
    """(c) an FK violation on every attempt eventually propagates (bound respected)."""
    resolve = MagicMock(
        side_effect=[_fk_error() for _ in range(sets_task.RESOLVE_FK_MAX_RETRIES)]
    )
    monkeypatch.setattr(sets_task, "_resolve_once", resolve)

    with pytest.raises(IntegrityError):
        sets_task._run_resolve_set_tracks(_task())

    assert resolve.call_count == sets_task.RESOLVE_FK_MAX_RETRIES
