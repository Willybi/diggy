"""DIGGY-APP-H — the Beatport drain's per-batch commit must survive a transient
Postgres deadlock (SQLSTATE 40P01) caused by the LOCAL Beatport backfill tool
writing the same `catalog` rows in a crossed lock order in parallel with the VPS
drain. `_commit_with_deadlock_retry` rolls back and re-issues the commit a bounded
number of times ON A DEADLOCK ONLY; any other OperationalError is re-raised at
once, and a persistent deadlock eventually propagates.

The helper is a pure module-level function, so it is tested in isolation with a
mock session + fake OperationalError (no Docker infra, no asyncio).
"""
import os
import sys
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

# Path so the workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# The module does `from workers.celery_app import celery_app` at import time and
# decorates its tasks — mock the broker infra that isn't available outside Docker
# (setdefault keeps this idempotent across sibling test files).
for _mod in ["celery", "celery.schedules", "celery.signals", "celery._state",
             "celery.exceptions", "redis", "redis.exceptions", "requests"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
if "workers.celery_app" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.task.side_effect = lambda *a, **k: (lambda fn: fn)
    sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

from workers.tasks import catalog as catalog_task  # noqa: E402


def _deadlock_error():
    """An OperationalError whose driver `orig` carries the deadlock SQLSTATE."""
    orig = MagicMock()
    orig.pgcode = "40P01"  # deadlock_detected
    return OperationalError("UPDATE catalog ...", {}, orig)


def _other_operational_error():
    """A non-deadlock OperationalError (e.g. connection reset, SQLSTATE 08006)."""
    orig = MagicMock()
    orig.pgcode = "08006"
    return OperationalError("UPDATE catalog ...", {}, orig)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Patch the module's time.sleep so the backoff doesn't slow the suite."""
    monkeypatch.setattr(catalog_task.time, "sleep", lambda *_: None)


def test_retries_then_succeeds_after_deadlock():
    """(a) commit deadlocks once, then succeeds → retried, rollback in between."""
    session = MagicMock()
    session.commit.side_effect = [_deadlock_error(), None]

    catalog_task._commit_with_deadlock_retry(session)

    assert session.commit.call_count == 2
    assert session.rollback.call_count == 1


def test_non_deadlock_operational_error_reraised_immediately():
    """(b) a non-deadlock OperationalError propagates without any retry."""
    session = MagicMock()
    session.commit.side_effect = _other_operational_error()

    with pytest.raises(OperationalError) as exc:
        catalog_task._commit_with_deadlock_retry(session)

    assert exc.value.orig.pgcode == "08006"
    assert session.commit.call_count == 1  # no retry
    session.rollback.assert_not_called()


def test_persistent_deadlock_propagates_after_bound():
    """(c) a deadlock on every attempt eventually propagates (bound respected)."""
    session = MagicMock()
    session.commit.side_effect = [
        _deadlock_error() for _ in range(catalog_task.COMMIT_DEADLOCK_MAX_RETRIES)
    ]

    with pytest.raises(OperationalError) as exc:
        catalog_task._commit_with_deadlock_retry(session)

    assert exc.value.orig.pgcode == "40P01"
    assert session.commit.call_count == catalog_task.COMMIT_DEADLOCK_MAX_RETRIES
    # Each failed attempt rolled back, including the last before propagation.
    assert session.rollback.call_count == catalog_task.COMMIT_DEADLOCK_MAX_RETRIES
