"""AV9 L1 — internal monotonic deadline on the 3 enrich-drain tasks.

billiard's SoftTimeLimitExceeded can be raised WHILE the asyncio internals are
mid-write and get swallowed by the transport's error handler ("Fatal write
error on socket transport", Sentry DIGGY-APP-J) — it then never reaches the
task's except clause and the run dies at the hard limit (SIGKILL: uncommitted
work lost + orphaned lock). The deadline guard, checked between batches, exits
the loop cleanly WITHOUT depending on signal delivery.

These tests drive the REAL runners with mocked infra (same sys.modules harness
as test_beatport_lock.py). The clock is faked by replacing the task module's
`time` attribute (never the global time module — asyncio's event loop reads
time.monotonic internally and would consume the fake sequence).
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


# The runners do `from celery.exceptions import SoftTimeLimitExceeded` and use
# it in an except clause; expose a REAL Exception subclass (a bare MagicMock
# attribute is not a class). Same technique as test_genres_reclassify.py.
class _FakeSoftTimeLimitExceeded(Exception):
    pass


_celery_exceptions = sys.modules.setdefault("celery.exceptions", MagicMock())
_celery_exceptions.SoftTimeLimitExceeded = _FakeSoftTimeLimitExceeded

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


class _FakeAsyncPool:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeClock:
    """Deterministic time.monotonic stand-in.

    Pops the value sequence one call at a time and keeps returning the last
    value once exhausted (the runner calls monotonic once for the deadline,
    then once per batch-loop iteration).
    """

    def __init__(self, values):
        self._values = list(values)

    def monotonic(self):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


@pytest.fixture
def catalog_mod():
    mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
    for m in mods_to_clear:
        del sys.modules[m]
    import workers.tasks.catalog as catalog
    return catalog


@pytest.fixture
def bpm_mod():
    mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
    for m in mods_to_clear:
        del sys.modules[m]
    import workers.tasks.bpm as bpm
    return bpm


@pytest.fixture
def fake_redis(monkeypatch):
    """Configured `redis` module whose from_url returns a lock-granting client."""
    client = MagicMock()
    client.set.return_value = True
    client.get.return_value = "task-abc"
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-abc"
    return task_self


@pytest.fixture
def run_env(monkeypatch):
    """Everything the _run_* runners import at CALL time, mocked in sys.modules
    (monkeypatch.setitem restores the real modules after each test)."""
    session = MagicMock()
    # The Deezer runner preloads existing ISRCs via session.execute(...).all()
    session.execute.return_value.all.return_value = []
    orm_mod = MagicMock()
    orm_mod.Session.return_value.__enter__.return_value = session

    clog = MagicMock()
    crawl_mod = MagicMock()
    crawl_mod.CrawlLogger.return_value.__enter__.return_value = clog

    monkeypatch.setitem(sys.modules, "sqlalchemy", MagicMock())
    monkeypatch.setitem(sys.modules, "sqlalchemy.orm", orm_mod)
    monkeypatch.setitem(sys.modules, "models", MagicMock())
    monkeypatch.setitem(sys.modules, "workers.db", MagicMock())
    monkeypatch.setitem(sys.modules, "services", MagicMock())
    monkeypatch.setitem(
        sys.modules, "services.image_service", MagicMock(BUCKET_CATALOG="catalog")
    )
    monkeypatch.setitem(sys.modules, "workers.crawl_logger", crawl_mod)
    monkeypatch.setitem(
        sys.modules,
        "workers.async_http",
        MagicMock(HttpPool=MagicMock(side_effect=lambda limiter: _FakeAsyncPool())),
    )
    monkeypatch.setitem(sys.modules, "workers.rate_limiter", MagicMock())
    return SimpleNamespace(session=session, clog=clog)


def _mock_enrichment(monkeypatch, n_entries, batch_stats):
    """workers.enrichment stand-in: n_entries candidates, fixed per-batch stats."""
    mod = MagicMock()
    mod.select_enrich_candidates.return_value = [MagicMock() for _ in range(n_entries)]
    mod.enrich_beatport_batch = AsyncMock(return_value=dict(batch_stats))
    mod.enrich_deezer_batch = AsyncMock(return_value=dict(batch_stats))
    monkeypatch.setitem(sys.modules, "workers.enrichment", mod)
    return mod


def _mock_bpm_analysis(monkeypatch, n_entries, batch_stats):
    """workers.bpm_analysis stand-in: n_entries candidates, fixed per-batch stats."""
    mod = MagicMock()
    mod.select_bpm_candidates.return_value = [MagicMock() for _ in range(n_entries)]
    mod.analyze_bpm_batch = AsyncMock(return_value=dict(batch_stats))
    monkeypatch.setitem(sys.modules, "workers.bpm_analysis", mod)
    return mod


# Clock sequences: 1st value = deadline computation (start), following values =
# per-iteration checks. HIT = the check before batch 2 lands past the deadline;
# NEVER = the clock stays at 0 so the deadline can't be reached.
_HIT_AFTER_FIRST_BATCH = [0.0, 0.0, 10**9]
_NEVER = [0.0]


class TestBeatportDeadline:
    def test_deadline_stops_before_next_batch(
        self, catalog_mod, run_env, fake_redis, fake_self, monkeypatch
    ):
        # 150 candidates → 3 batches of 50; the deadline fires before batch 2.
        enrichment = _mock_enrichment(
            monkeypatch, 150,
            {"enriched": 7, "not_found": 1, "errors": 0, "merged": 0},
        )
        monkeypatch.setattr(catalog_mod, "time", _FakeClock(_HIT_AFTER_FIRST_BATCH))

        result = catalog_mod.enrich_catalog_beatport(fake_self)

        # Only the first batch ran; the loop exited between batches, cleanly.
        assert enrichment.enrich_beatport_batch.await_count == 1
        assert result["deadline_hit"] is True
        assert result["soft_limit_hit"] is False
        assert result["enriched"] == 7
        assert result["total"] == 150
        # Partial stats recorded in crawl_logs, lock released by the wrapper.
        run_env.clog.set_stats.assert_called_once_with(result)
        fake_redis.delete.assert_called_once_with("lock:enrich_beatport")

    def test_nominal_run_unaffected(
        self, catalog_mod, run_env, fake_redis, fake_self, monkeypatch
    ):
        enrichment = _mock_enrichment(
            monkeypatch, 150,
            {"enriched": 7, "not_found": 1, "errors": 0, "merged": 0},
        )
        monkeypatch.setattr(catalog_mod, "time", _FakeClock(_NEVER))

        result = catalog_mod.enrich_catalog_beatport(fake_self)

        assert enrichment.enrich_beatport_batch.await_count == 3
        assert result["deadline_hit"] is False
        assert result["soft_limit_hit"] is False
        assert result["enriched"] == 21


class TestDeezerDeadline:
    def test_deadline_stops_before_next_batch(
        self, catalog_mod, run_env, fake_redis, fake_self, monkeypatch
    ):
        # 250 candidates → 3 batches of 100; the deadline fires before batch 2.
        enrichment = _mock_enrichment(
            monkeypatch, 250, {"enriched": 9, "errors": 1, "merged": 0}
        )
        monkeypatch.setattr(catalog_mod, "time", _FakeClock(_HIT_AFTER_FIRST_BATCH))

        result = catalog_mod.enrich_catalog(fake_self)

        assert enrichment.enrich_deezer_batch.await_count == 1
        assert result["deadline_hit"] is True
        assert result["enriched"] == 9
        run_env.clog.set_stats.assert_called_once_with(result)
        fake_redis.delete.assert_called_once_with("lock:enrich_deezer")

    def test_nominal_run_unaffected(
        self, catalog_mod, run_env, fake_redis, fake_self, monkeypatch
    ):
        enrichment = _mock_enrichment(
            monkeypatch, 250, {"enriched": 9, "errors": 1, "merged": 0}
        )
        monkeypatch.setattr(catalog_mod, "time", _FakeClock(_NEVER))

        result = catalog_mod.enrich_catalog(fake_self)

        assert enrichment.enrich_deezer_batch.await_count == 3
        assert result["deadline_hit"] is False
        assert result["enriched"] == 27


class TestBpmDeadline:
    def test_deadline_stops_before_next_batch(
        self, bpm_mod, run_env, fake_redis, fake_self, monkeypatch
    ):
        # 150 candidates → 3 batches of 50; the deadline fires before batch 2.
        analysis = _mock_bpm_analysis(
            monkeypatch, 150,
            {"estimated": 5, "low_conf": 2, "no_preview": 1, "skipped": 0,
             "errors": 0},
        )
        monkeypatch.setattr(bpm_mod, "time", _FakeClock(_HIT_AFTER_FIRST_BATCH))

        result = bpm_mod.analyze_bpm_previews(fake_self)

        assert analysis.analyze_bpm_batch.await_count == 1
        assert result["deadline_hit"] is True
        assert result["soft_limit_hit"] is False
        assert result["estimated"] == 5
        assert result["total"] == 150
        run_env.clog.set_stats.assert_called_once_with(result)
        fake_redis.delete.assert_called_once_with("lock:analyze_bpm")

    def test_nominal_run_unaffected(
        self, bpm_mod, run_env, fake_redis, fake_self, monkeypatch
    ):
        analysis = _mock_bpm_analysis(
            monkeypatch, 150,
            {"estimated": 5, "low_conf": 2, "no_preview": 1, "skipped": 0,
             "errors": 0},
        )
        monkeypatch.setattr(bpm_mod, "time", _FakeClock(_NEVER))

        result = bpm_mod.analyze_bpm_previews(fake_self)

        assert analysis.analyze_bpm_batch.await_count == 3
        assert result["deadline_hit"] is False
        assert result["estimated"] == 15


class TestConstantsAreSingleSourceOfTruth:
    """The decorators must reference the module constants (one source of truth
    for the decorator AND the deadline computation — never task.soft_time_limit
    at runtime, fragile under this MagicMock harness)."""

    def test_catalog_decorators_reference_constants(self, catalog_mod):
        assert catalog_mod.DEEZER_SOFT_TIME_LIMIT == 7200
        assert (
            catalog_mod.enrich_catalog.soft_time_limit
            == catalog_mod.DEEZER_SOFT_TIME_LIMIT
        )
        assert catalog_mod.BEATPORT_SOFT_TIME_LIMIT == 3000
        assert (
            catalog_mod.enrich_catalog_beatport.soft_time_limit
            == catalog_mod.BEATPORT_SOFT_TIME_LIMIT
        )
        # The margin must leave the run an actual working window.
        assert 0 < catalog_mod.DEADLINE_MARGIN < catalog_mod.BEATPORT_SOFT_TIME_LIMIT

    def test_bpm_decorator_references_constant(self, bpm_mod):
        assert bpm_mod.ANALYSIS_BPM_SOFT_TIME_LIMIT == 3000
        assert (
            bpm_mod.analyze_bpm_previews.soft_time_limit
            == bpm_mod.ANALYSIS_BPM_SOFT_TIME_LIMIT
        )
        assert 0 < bpm_mod.DEADLINE_MARGIN < bpm_mod.ANALYSIS_BPM_SOFT_TIME_LIMIT
