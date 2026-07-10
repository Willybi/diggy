"""Tests for genre reclassification tasks (AU4-L4 — A3-03 / A3-10).

reclassify_genres_chunk: the four per-entry paths — Beatport hit, Deezer
fallback, legitimate clear (valid empty answers), source error → existing
genres kept (idempotence after a network incident).
finalize_reclassify / reclassify_genres_error: chord callback aggregation
and error visibility in crawl_logs.
"""
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
        genres_tasks.finalize_reclassify.s.reset_mock()

        out = genres_tasks.reclassify_all_genres(MagicMock(), num_chunks=2)

        assert out == {"dispatched": 2, "total": 5}
        genres_tasks.finalize_reclassify.s.assert_called_once_with(total=5)

    def test_empty_catalog_dispatches_nothing(
        self, monkeypatch, sync_engine, sync_session
    ):
        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        genres_tasks.finalize_reclassify.s.reset_mock()

        out = genres_tasks.reclassify_all_genres(MagicMock(), num_chunks=3)

        assert out == {"dispatched": 0, "total": 0}
        genres_tasks.finalize_reclassify.s.assert_not_called()
