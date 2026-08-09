"""A3-06 — the dead-letter queue must capture FINAL task failures.

The old ``on_task_failure`` guard ``task.request.retries < task.max_retries``
dropped every modern task WITHOUT ``autoretry_for`` (Celery's default
``max_retries=3`` but they fail with ``retries=0 < 3``), leaving the DLQ
structurally empty — the admin card ``LLEN dead_letter`` never moved.

These tests import the REAL ``workers.celery_app`` (celery stubbed just enough
that each signal's ``.connect`` stays an identity decorator, so
``on_task_failure`` remains the real function, and ``Retry`` is a real class for
the isinstance guard) and drive the handler directly.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)


class _FakeRetry(Exception):
    """Stand-in for celery.exceptions.Retry (celery is absent in the test env)."""


def _celery_stubs():
    """Minimal celery module stubs so the REAL workers.celery_app imports:
    Celery()/crontab() are callable, each signal's ``.connect`` is an identity
    decorator (keeps ``on_task_failure`` the real function, not a MagicMock),
    and ``Retry`` is a real exception class for the isinstance guard."""
    celery = MagicMock()
    schedules = MagicMock()
    signals = MagicMock()
    for name in ("celeryd_init", "setup_logging", "task_failure"):
        sig = MagicMock()
        sig.connect = lambda fn: fn  # identity: keep the real receiver function
        setattr(signals, name, sig)
    exceptions = MagicMock()
    exceptions.Retry = _FakeRetry
    # Reachable both as submodules (sys.modules) and parent attributes
    celery.schedules = schedules
    celery.signals = signals
    celery.exceptions = exceptions
    return {
        "celery": celery,
        "celery.schedules": schedules,
        "celery.signals": signals,
        "celery.exceptions": exceptions,
    }


@pytest.fixture
def celery_app_mod():
    """Import the REAL workers.celery_app with celery stubbed, restoring the
    prior sys.modules afterwards so sibling worker tests keep their own mocks."""
    keys = [
        "celery",
        "celery.schedules",
        "celery.signals",
        "celery.exceptions",
        "workers.celery_app",
    ]
    saved = {k: sys.modules.get(k) for k in keys}
    try:
        for k, v in _celery_stubs().items():
            sys.modules[k] = v
        sys.modules.pop("workers.celery_app", None)
        import workers.celery_app as mod

        yield mod
    finally:
        for k in keys:
            if saved[k] is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = saved[k]


@pytest.fixture
def fake_redis(monkeypatch):
    """`redis.from_url` returns a controllable client."""
    client = MagicMock()
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


def _sender(name="workers.tasks.enrich_catalog_beatport"):
    """A task that never retries: Celery's default max_retries=3 but it fails at
    retries=0 — the exact shape the old guard wrongly dropped from the DLQ."""
    sender = MagicMock()
    sender.name = name
    sender.request.retries = 0
    sender.max_retries = 3
    return sender


class TestDeadLetterQueue:
    def test_final_failure_pushed_to_dlq(self, celery_app_mod, fake_redis):
        celery_app_mod.on_task_failure(
            sender=_sender(),
            task_id="task-xyz",
            exception=RuntimeError("boom"),
            args=[],
            kwargs={"genre_only": True},
        )

        fake_redis.lpush.assert_called_once()
        queue, payload = fake_redis.lpush.call_args.args
        assert queue == "dead_letter"
        assert '"task_id": "task-xyz"' in payload
        assert '"task_name": "workers.tasks.enrich_catalog_beatport"' in payload
        # ltrim bounds the list growth (kept last 1000)
        fake_redis.ltrim.assert_called_once_with("dead_letter", 0, 999)

    def test_retry_exception_is_ignored(self, celery_app_mod, fake_redis):
        # A Retry is celery's internal "retry me" signal, not a terminal failure
        celery_app_mod.on_task_failure(
            sender=_sender(),
            task_id="task-retry",
            exception=_FakeRetry("retrying"),
        )

        fake_redis.lpush.assert_not_called()
