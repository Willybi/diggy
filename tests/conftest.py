"""Root test fixtures shared across tests/api, tests/worker and tests/unit.

Self-healing guard for the shared celery/redis mocks (xdist parallel-safety).
---------------------------------------------------------------------------
``tests/api/conftest.py`` and several worker test modules (e.g.
``test_tasks_observability.py``, ``test_task_refactor.py``) each install their
OWN bare celery/redis mocks into ``sys.modules`` with a "first loader wins"
guard (``setdefault`` / ``if _mod not in sys.modules``). Under CI's
``pytest-xdist --dist loadscope`` those modules co-locate in a single worker
process and SHARE one mock object. When one test patches-then-restores a shared
child attribute (``celery.send_task`` / ``redis.from_url``), ``unittest.mock``
can leave it in the ``_deleted`` state — after which ANY later test in that
process that merely READS the attribute raises ``AttributeError`` (mock.py
``__getattr__``). Which test trips shifts run-to-run with the xdist schedule, so
the suite goes flaky-red on unrelated changes.

The autouse fixture below re-establishes the two attributes the suites rely on
before EVERY test, making the shared mock deterministic regardless of load order
or a previous test's teardown. It is a no-op when the real packages are imported
(``isinstance(..., MagicMock)`` is False) or the module isn't mocked in this
process.
"""
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _heal_shared_infra_mocks():
    # A fresh send_task result carrying a string .id (the shape the API expects).
    task_result = MagicMock()
    task_result.id = "fake-task-id"

    # celery: heal both the shared module mock and the bound celery_client.celery
    # (the object the API router actually calls). setattr re-creates a child left
    # in mock's `_deleted` state by a sibling test's patch/restore.
    cel = sys.modules.get("celery")
    if isinstance(cel, MagicMock):
        try:
            cel.Celery.return_value.send_task = MagicMock(return_value=task_result)
        except Exception:
            pass
    cc = sys.modules.get("celery_client")
    if cc is not None and isinstance(getattr(cc, "celery", None), MagicMock):
        cc.celery.send_task = MagicMock(return_value=task_result)

    # redis: worker tasks do `import redis as redis_lib; redis_lib.from_url(...)`,
    # a call-time attribute lookup on the shared mock module.
    redis_mod = sys.modules.get("redis")
    if isinstance(redis_mod, MagicMock):
        redis_mod.from_url = MagicMock()

    yield
