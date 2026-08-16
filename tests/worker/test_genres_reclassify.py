"""Tests for genre reclassification tasks (AU4-L4 — A3-03 / A3-10).

reclassify_genres_chunk: the four per-entry paths — Beatport hit, Deezer
fallback, legitimate clear (valid empty answers), source error → existing
genres kept (idempotence after a network incident).
finalize_reclassify / reclassify_genres_error: chord callback aggregation
and error visibility in crawl_logs.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock

from sqlalchemy import select

# Path so the workers package is importable (same pattern as test_task_refactor.py)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# Mock infra that isn't available outside Docker (same pattern as test_task_refactor.py)
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "requests",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# reclassify_genres_chunk now imports SoftTimeLimitExceeded from celery.exceptions
# to catch the soft limit gracefully (L3 / AV8-02). celery is absent in the test
# env, so expose a REAL exception subclass — a bare MagicMock attribute would
# break both the `except SoftTimeLimitExceeded` clause (needs a class inheriting
# BaseException) and the `from celery.exceptions import ...` every chunk call
# runs. Same technique as test_tasks_recrawl_sets.py.
class _FakeSoftTimeLimitExceeded(Exception):
    pass


_celery_exceptions = sys.modules.setdefault("celery.exceptions", MagicMock())
_celery_exceptions.SoftTimeLimitExceeded = _FakeSoftTimeLimitExceeded

_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn

    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

# Force a fresh import so the genre tasks are decorated by the mock above
for _m in [k for k in list(sys.modules) if k.startswith("workers.tasks")]:
    del sys.modules[_m]

# redis and curl_cffi are not installed in the test env; enrichment.py and
# async_http.py import them at module load. Same save/restore dance as
# test_enrichment_isrc.py to avoid polluting other test files. Both modules
# stay cached in sys.modules for the tasks' lazy imports at call time.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.async_http  # noqa: E402,F401
import workers.enrichment  # noqa: E402
import workers.tasks.genres as genres_tasks  # noqa: E402

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl
del _saved_curl

import workers.db as workers_db  # noqa: E402
from models import CatalogEntry, CrawlLog  # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient (Deezer calls + HttpPool internals).

    Serves canned payloads keyed by URL substring; raises `error` on any
    request when set. The instance is its own factory so a preconfigured
    object can be monkeypatched over the httpx.AsyncClient class.
    """

    def __init__(self, responses=None, error=None):
        self._responses = responses or {}
        self._error = error
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def aclose(self):
        return None

    async def get(self, url, **kwargs):
        self.calls.append(url)
        if self._error is not None:
            raise self._error
        for fragment, payload in self._responses.items():
            if fragment in url:
                return _FakeResponse(payload)
        return _FakeResponse({})


def _make_entry(session, **overrides):
    defaults = {
        "title": "Track",
        "artist": "Artist",
        "normalized_key": "track - artist",
        "genres": ["Old Genre"],
    }
    defaults.update(overrides)
    entry = CatalogEntry(**defaults)
    session.add(entry)
    session.commit()
    return entry


def _install_redis(monkeypatch, *, acquired=True, holder=None):
    """Install a redis mock so the reclassify orchestrator lock (A8-03) is
    exercised. ``acquired`` is the SET NX EX result (True = lock taken); ``holder``
    is what GET returns (the current owner — read by the skip branch and by the
    conditional release). Returns the fake client for assertions.

    from_url always returns the SAME client, so the orchestrator's acquire client
    and _release_reclassify_lock's fresh client are the same mock object.
    """
    client = MagicMock()
    client.set.return_value = acquired
    client.get.return_value = holder
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


def _run_chunk(monkeypatch, sync_engine, catalog_ids, beatport=None, deezer=None):
    """Run reclassify_genres_chunk with both sources faked.

    beatport: dict returned by _search_beatport_async, None for a valid
    empty answer, or an Exception instance to raise.
    deezer: a _FakeAsyncClient (defaults to valid empty answers).
    """
    import httpx

    monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)

    async def _fake_beatport(pool, title, artist, isrc, rcache=None):
        if isinstance(beatport, Exception):
            raise beatport
        return beatport

    monkeypatch.setattr(workers.enrichment, "_search_beatport_async", _fake_beatport)
    monkeypatch.setattr(httpx, "AsyncClient", deezer or _FakeAsyncClient())

    return genres_tasks.reclassify_genres_chunk(MagicMock(), catalog_ids, 0)


_DEEZER_HIT = {
    "/track/999": {"album": {"id": 42}},
    "/album/42": {"genres": {"data": [{"name": "House"}, {"name": "Dance"}]}},
}


class TestReclassifyChunkIdempotence:
    """A3-03: entry.genres must never be destroyed by a source failure."""

    def test_beatport_hit_replaces_genres(self, monkeypatch, sync_engine, sync_session):
        entry = _make_entry(sync_session)

        stats = _run_chunk(
            monkeypatch, sync_engine, [entry.id],
            beatport={"genre": {"name": "Melodic Techno"}},
        )

        assert stats["beatport"] == 1
        assert stats["cleared"] == 0
        assert stats["errors"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == ["Melodic Techno"]

    def test_deezer_fallback_replaces_genres(self, monkeypatch, sync_engine, sync_session):
        entry = _make_entry(sync_session, deezer_id="999")

        stats = _run_chunk(
            monkeypatch, sync_engine, [entry.id],
            beatport=None, deezer=_FakeAsyncClient(responses=_DEEZER_HIT),
        )

        assert stats["deezer"] == 1
        assert stats["cleared"] == 0
        assert stats["errors"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == ["House", "Dance"]

    def test_both_sources_empty_without_error_clears_genres(
        self, monkeypatch, sync_engine, sync_session
    ):
        entry = _make_entry(sync_session, deezer_id="999")
        deezer = _FakeAsyncClient(responses={
            "/track/999": {"album": {"id": 42}},
            "/album/42": {"genres": {"data": []}},
        })

        stats = _run_chunk(
            monkeypatch, sync_engine, [entry.id], beatport=None, deezer=deezer
        )

        assert stats["cleared"] == 1
        assert stats["errors"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == []

    def test_beatport_empty_without_deezer_id_is_legitimate_clear(
        self, monkeypatch, sync_engine, sync_session
    ):
        entry = _make_entry(sync_session, deezer_id=None)

        stats = _run_chunk(monkeypatch, sync_engine, [entry.id], beatport=None)

        assert stats["cleared"] == 1
        assert stats["errors"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == []

    def test_beatport_error_keeps_existing_genres(
        self, monkeypatch, sync_engine, sync_session
    ):
        entry = _make_entry(sync_session, deezer_id=None)

        stats = _run_chunk(
            monkeypatch, sync_engine, [entry.id],
            beatport=RuntimeError("beatport 503"),
        )

        assert stats["errors"] == 1
        assert stats["cleared"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == ["Old Genre"]

    def test_deezer_error_keeps_existing_genres(
        self, monkeypatch, sync_engine, sync_session
    ):
        entry = _make_entry(sync_session, deezer_id="999")

        stats = _run_chunk(
            monkeypatch, sync_engine, [entry.id],
            beatport=None, deezer=_FakeAsyncClient(error=RuntimeError("deezer timeout")),
        )

        assert stats["errors"] == 1
        assert stats["cleared"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == ["Old Genre"]

    def test_beatport_error_then_deezer_hit_still_classifies(
        self, monkeypatch, sync_engine, sync_session
    ):
        entry = _make_entry(sync_session, deezer_id="999")

        stats = _run_chunk(
            monkeypatch, sync_engine, [entry.id],
            beatport=RuntimeError("beatport down"),
            deezer=_FakeAsyncClient(responses=_DEEZER_HIT),
        )

        assert stats["errors"] == 1
        assert stats["deezer"] == 1
        assert stats["cleared"] == 0
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == ["House", "Dance"]


class TestReclassifyItemTimeout:
    """AV8-02: a hung external call for one item must not freeze the chunk."""

    def test_item_timeout_is_source_error_keeps_genres_and_continues(
        self, monkeypatch, sync_engine, sync_session
    ):
        import httpx

        slow = _make_entry(sync_session, title="Slow", normalized_key="slow - a")
        fast = _make_entry(sync_session, title="Fast", normalized_key="fast - a")

        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        # Tiny per-item ceiling; the module global is read at call time.
        monkeypatch.setattr(genres_tasks, "RECLASSIFY_ITEM_TIMEOUT", 0.05)

        async def _slow_or_hit(pool, title, artist, isrc, rcache=None):
            if title == "Slow":
                await asyncio.sleep(2)  # far above the 0.05s per-item timeout
                return {"genre": {"name": "NeverApplied"}}
            return {"genre": {"name": "Techno"}}

        monkeypatch.setattr(workers.enrichment, "_search_beatport_async", _slow_or_hit)
        monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient())

        stats = genres_tasks.reclassify_genres_chunk(
            MagicMock(), [slow.id, fast.id], 0
        )

        # the hung item is counted as a source error, never cleared...
        assert stats["errors"] == 1
        assert stats["cleared"] == 0
        # ...and the chunk keeps going: the next (fast) item is still classified
        assert stats["beatport"] == 1
        sync_session.expire_all()
        # genres of the timed-out entry are left INTACT (source-error semantics)
        assert sync_session.get(CatalogEntry, slow.id).genres == ["Old Genre"]
        assert sync_session.get(CatalogEntry, fast.id).genres == ["Techno"]


class TestReclassifySoftLimit:
    """AV8-02: SoftTimeLimitExceeded ends the chunk cleanly with partial stats
    (does not propagate → acks_late would otherwise crash-loop the chunk)."""

    def test_soft_limit_returns_partial_stats_without_raising(
        self, monkeypatch, sync_engine, sync_session
    ):
        import httpx

        entry = _make_entry(sync_session)
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)

        async def _fake_beatport(pool, title, artist, isrc, rcache=None):
            return {"genre": {"name": "Techno"}}

        monkeypatch.setattr(workers.enrichment, "_search_beatport_async", _fake_beatport)
        monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient())

        # Drive the real coroutine (so the work commits), THEN raise the soft
        # limit out of asyncio.run — as celery would once the soft limit fires.
        # Raise the SAME class the task catches (read from celery.exceptions at
        # call time): a sibling test file may have overwritten the registered
        # SoftTimeLimitExceeded, so our module-local class isn't guaranteed to be
        # the one `except SoftTimeLimitExceeded` matches under the full suite.
        from celery.exceptions import SoftTimeLimitExceeded

        _orig_run = genres_tasks.asyncio.run

        def _run_then_soft_limit(coro):
            _orig_run(coro)
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(genres_tasks.asyncio, "run", _run_then_soft_limit)

        result = genres_tasks.reclassify_genres_chunk(MagicMock(), [entry.id], 0)

        # graceful: returns partial stats instead of propagating the soft limit
        assert result["soft_limit_hit"] is True
        assert result["beatport"] == 1
        # the work committed before the limit fired is durable
        sync_session.expire_all()
        assert sync_session.get(CatalogEntry, entry.id).genres == ["Techno"]


class TestFinalizeReclassify:
    """A3-10: the chord callback owns the aggregation + crawl_logs line."""

    def test_aggregates_stats_and_writes_crawl_log(
        self, monkeypatch, sync_engine, sync_session
    ):
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        self_mock = MagicMock()
        self_mock.request.id = "task-123"
        results = [
            {"total": 3, "deezer": 1, "beatport": 1, "cleared": 1, "errors": 0},
            {"total": 2, "deezer": 0, "beatport": 2, "cleared": 0, "errors": 2},
            None,  # a non-dict slot must be skipped, not crash the callback
        ]

        agg = genres_tasks.finalize_reclassify(self_mock, results, total=5)

        assert agg == {"total": 5, "deezer": 1, "beatport": 3, "cleared": 1, "errors": 2}
        sync_session.expire_all()
        log = sync_session.execute(select(CrawlLog)).scalar_one()
        assert log.task_type == "reclassify_genres"
        assert log.source == "beatport+deezer"
        assert log.status == "success"
        assert log.stats == agg
        assert log.celery_task_id == "task-123"

    def test_empty_results_still_writes_crawl_log(
        self, monkeypatch, sync_engine, sync_session
    ):
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        self_mock = MagicMock()
        self_mock.request.id = "task-empty"

        agg = genres_tasks.finalize_reclassify(self_mock, [], total=0)

        assert agg == {"total": 0, "deezer": 0, "beatport": 0, "cleared": 0, "errors": 0}
        sync_session.expire_all()
        log = sync_session.execute(select(CrawlLog)).scalar_one()
        assert log.status == "success"


class TestReclassifyErrback:
    def test_chord_failure_writes_error_crawl_log(
        self, monkeypatch, sync_engine, sync_session
    ):
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        request = MagicMock()
        request.id = "failed-task-id"

        genres_tasks.reclassify_genres_error(
            MagicMock(), request, RuntimeError("chunk exploded"), None
        )

        sync_session.expire_all()
        log = sync_session.execute(select(CrawlLog)).scalar_one()
        assert log.task_type == "reclassify_genres"
        assert log.source == "beatport+deezer"
        assert log.status == "error"
        assert "chunk exploded" in log.error_message
        assert log.celery_task_id == "failed-task-id"


class TestReclassifyOrchestrator:
    def test_dispatches_chord_and_returns_immediately(
        self, monkeypatch, sync_engine, sync_session
    ):
        for i in range(5):
            _make_entry(
                sync_session, title=f"T{i}", normalized_key=f"t{i} - artist"
            )
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        _install_redis(monkeypatch, acquired=True)
        genres_tasks.finalize_reclassify.s.reset_mock()

        self_mock = MagicMock()
        self_mock.request.id = "orch-1"
        # chunk_size=3 over 5 entries → ceil(5/3) = 2 chunks
        out = genres_tasks.reclassify_all_genres(self_mock, chunk_size=3)

        assert out == {"dispatched": 2, "total": 5}
        # the owner token is threaded to the callback for a conditional release
        genres_tasks.finalize_reclassify.s.assert_called_once_with(
            total=5, lock_token="orch-1"
        )

    def test_default_chunk_size_is_200(
        self, monkeypatch, sync_engine, sync_session
    ):
        # 201 entries → the new default (200) splits into 2 chunks; the old
        # default (500) would have produced a single chunk (AV8-02 guard).
        sync_session.add_all(
            [
                CatalogEntry(title=f"T{i}", artist="A", normalized_key=f"t{i} - a")
                for i in range(201)
            ]
        )
        sync_session.commit()
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        _install_redis(monkeypatch, acquired=True)
        genres_tasks.finalize_reclassify.s.reset_mock()

        self_mock = MagicMock()
        self_mock.request.id = "orch-default"
        # no chunk_size argument → the task's default (200) must apply
        out = genres_tasks.reclassify_all_genres(self_mock)

        assert out == {"dispatched": 2, "total": 201}

    def test_empty_catalog_dispatches_nothing(
        self, monkeypatch, sync_engine, sync_session
    ):
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        client = _install_redis(monkeypatch, acquired=True, holder="orch-empty")
        genres_tasks.finalize_reclassify.s.reset_mock()

        self_mock = MagicMock()
        self_mock.request.id = "orch-empty"
        out = genres_tasks.reclassify_all_genres(self_mock, chunk_size=3)

        assert out == {"dispatched": 0, "total": 0}
        genres_tasks.finalize_reclassify.s.assert_not_called()
        # no chord/callback fires → the empty path must release the lock itself
        client.delete.assert_called_once_with(genres_tasks.RECLASSIFY_LOCK_KEY)


class TestReclassifyOrchestratorLock:
    """A8-03: reclassify_all_genres is single-instance via lock:reclassify_genres,
    released by the chord callback (finalize) or the errback."""

    def test_skips_when_lock_already_held(
        self, monkeypatch, sync_engine, sync_session
    ):
        # Even with a full catalog, a held lock must short-circuit before dispatch
        for i in range(5):
            _make_entry(
                sync_session, title=f"T{i}", normalized_key=f"t{i} - artist"
            )
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        client = _install_redis(monkeypatch, acquired=False, holder="other-task")
        genres_tasks.finalize_reclassify.s.reset_mock()

        self_mock = MagicMock()
        self_mock.request.id = "orch-blocked"
        out = genres_tasks.reclassify_all_genres(self_mock, chunk_size=3)

        assert out == {"skipped": "already_running", "holder": "other-task"}
        genres_tasks.finalize_reclassify.s.assert_not_called()
        # the lock belongs to another run → we must never delete it
        client.delete.assert_not_called()

    def test_finalize_releases_lock_when_token_matches(
        self, monkeypatch, sync_engine, sync_session
    ):
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        client = _install_redis(monkeypatch, holder="orch-token")
        self_mock = MagicMock()
        self_mock.request.id = "finalize-task"

        genres_tasks.finalize_reclassify(
            self_mock, [], total=0, lock_token="orch-token"
        )

        client.delete.assert_called_once_with(genres_tasks.RECLASSIFY_LOCK_KEY)

    def test_finalize_keeps_lock_when_token_mismatches(
        self, monkeypatch, sync_engine, sync_session
    ):
        # TTL expired mid-run and another run took the lock → do NOT steal it
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        client = _install_redis(monkeypatch, holder="someone-else")
        self_mock = MagicMock()
        self_mock.request.id = "finalize-task"

        genres_tasks.finalize_reclassify(
            self_mock, [], total=0, lock_token="orch-token"
        )

        client.delete.assert_not_called()

    def test_finalize_without_token_never_touches_redis(
        self, monkeypatch, sync_engine, sync_session
    ):
        # Back-compat: a manual finalize with no lock held must not touch redis
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        client = _install_redis(monkeypatch, holder="whatever")
        self_mock = MagicMock()
        self_mock.request.id = "finalize-task"

        genres_tasks.finalize_reclassify(self_mock, [], total=0)

        client.get.assert_not_called()
        client.delete.assert_not_called()
