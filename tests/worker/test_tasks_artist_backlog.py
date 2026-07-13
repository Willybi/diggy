"""
Artist backlog loop-safe tasks (2026-07-13 incident fix):
  - link_artists_deezer: budget-capped, batch-committing, Redis-locked Deezer
    linking (extracted from the old fetch_artist_artworks Pass 1).
  - fetch_artist_artworks: artwork-only, budget-capped, batch-committing, locked.

Runs the real task functions (celery ecosystem mocked, same harness as
test_tasks_check_followed_artists.py) against an in-memory SQLite engine with a
FakePool standing in for HttpPool (no network) and ImageService patched (no
MinIO). Focus: the properties that make the tasks incapable of looping — cap +
dropped_by_budget accounting, batch commits that survive a mid-run kill, and the
single-instance lock.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "requests",
    "curl_cffi",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


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
_celery_app_mod = MagicMock(celery_app=_celery_mock)
sys.modules["workers.celery_app"] = _celery_app_mod

from database import Base  # noqa: E402
from models import Artist, CrawlLog  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture
def task_engine():
    """In-memory SQLite, AUTOCOMMIT so the CrawlLogger session and the work
    session can coexist (same reason as test_tasks_check_followed_artists.py)."""
    engine = create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def fake_redis(monkeypatch):
    client = MagicMock()
    client.set.return_value = True  # nx acquired
    client.get.return_value = "task-x"  # still owned → clean release
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def tasks_env(task_engine, monkeypatch):
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.db as workers_db
    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)
    import workers.tasks.artists as artists_mod
    # No MinIO in tests: ensure_bucket + upload_bytes are no-ops (upload succeeds)
    import services.image_service as image_service
    monkeypatch.setattr(
        image_service.ImageService, "ensure_bucket", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(
        image_service.ImageService, "upload_bytes", staticmethod(lambda *a, **k: True)
    )
    return SimpleNamespace(artists=artists_mod)


class FakePool:
    """Stand-in for workers.async_http.HttpPool.

    - /search/artist        -> {"data": search[q]}   (q = artist name)
    - /artist/{deezer_id}   -> artist_pics[deezer_id] (a picture payload)
    - download_image(url)   -> images.get(url, default bytes)

    ``search_errors`` (by q) / ``pic_errors`` (by deezer_id) raise a
    DeezerHTTPError. ``boom`` (by q) raises a plain RuntimeError to simulate a
    non-HTTP crash mid-run (batch-commit test).
    """

    def __init__(self):
        self.search = {}
        self.artist_pics = {}
        self.images = {}
        self.search_errors = set()
        self.pic_errors = set()
        self.boom = set()
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def deezer_get(self, path, params=None):
        from workers.async_http import DeezerHTTPError

        self.calls.append(path)
        if path == "/search/artist":
            q = (params or {}).get("q")
            if q in self.boom:
                raise RuntimeError(f"boom on {q}")
            if q in self.search_errors:
                raise DeezerHTTPError(500, path)
            return {"data": self.search.get(q, [])}
        parts = path.strip("/").split("/")
        if parts[0] == "artist":
            dz_id = parts[1]
            if dz_id in self.pic_errors:
                raise DeezerHTTPError(500, path)
            return self.artist_pics.get(dz_id, {})
        return {}

    async def download_image(self, url):
        return self.images.get(url, b"x" * 2000)


@pytest.fixture
def fake_pool(monkeypatch):
    import workers.async_http as async_http

    pool = FakePool()
    monkeypatch.setattr(async_http, "HttpPool", lambda limiter=None: pool)
    return pool


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-x"
    return task_self


def _add_artist(session, name, **kw):
    a = Artist(name=name, normalized_name=name.lower(), **kw)
    session.add(a)
    session.flush()
    return a


def _hit(dz_id, name):
    return {"id": dz_id, "name": name}


def _artists(engine):
    with Session(engine) as s:
        return {a.name: a for a in s.execute(select(Artist)).scalars().all()}


def _crawl_log(engine, task_type):
    with Session(engine) as s:
        return s.execute(
            select(CrawlLog).where(CrawlLog.task_type == task_type)
        ).scalar_one()


# ── Model / migration column presence ────────────────────────────────────────


class TestModelColumn:
    def test_deezer_search_attempts_is_not_null_default_zero(self):
        col = Artist.__table__.columns["deezer_search_attempts"]
        assert col.nullable is False
        assert col.server_default is not None


# ── link_artists_deezer ──────────────────────────────────────────────────────


class TestLinkArtistsDeezer:
    def test_links_matching_artists(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            _add_artist(s, "Boris Brejcha")
            _add_artist(s, "ANNA")
        fake_pool.search["Boris Brejcha"] = [_hit(10, "Boris Brejcha")]
        fake_pool.search["ANNA"] = [_hit(11, "ANNA")]

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result["linked"] == 2
        assert result["searched"] == 2
        assert result["abandoned"] == 0
        assert result["errors"] == 0
        assert result["dropped_by_budget"] == 0

        arts = _artists(task_engine)
        assert arts["Boris Brejcha"].deezer_id == "10"
        assert arts["ANNA"].deezer_id == "11"
        assert arts["Boris Brejcha"].deezer_search_attempts == 1
        assert _crawl_log(task_engine, "link_artists").status == "success"

    def test_no_match_marks_but_does_not_link(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            _add_artist(s, "Nobody")
        # empty search results → no match

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result == {
            "linked": 0, "searched": 1, "abandoned": 0,
            "errors": 0, "dropped_by_budget": 0,
        }
        arts = _artists(task_engine)
        assert arts["Nobody"].deezer_id is None
        assert arts["Nobody"].deezer_search_attempts == 1  # marked, retriable

    def test_budget_caps_and_reports_dropped(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self, monkeypatch
    ):
        monkeypatch.setenv("ARTIST_LINK_NIGHTLY_BUDGET", "2")
        with Session(task_engine) as s:
            for n in range(3):
                _add_artist(s, f"Artist{n}")

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result["searched"] == 2  # only budget=2 processed
        assert result["dropped_by_budget"] == 1  # 3 eligible − 2 selected
        # exactly two artists were marked this run
        marked = [a for a in _artists(task_engine).values()
                  if a.deezer_search_attempts == 1]
        assert len(marked) == 2

    def test_abandons_after_third_attempt(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        now = datetime.now(timezone.utc)
        with Session(task_engine) as s:
            # tier-3 eligible: 2 prior attempts, searched >90d ago
            _add_artist(
                s, "LastChance",
                deezer_searched_at=now - timedelta(days=100),
                deezer_search_attempts=2,
            )
        # no match → this third attempt abandons it

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result["searched"] == 1
        assert result["linked"] == 0
        assert result["abandoned"] == 1
        assert _artists(task_engine)["LastChance"].deezer_search_attempts == 3

    def test_http_error_counted_not_marked(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            _add_artist(s, "Flaky")
        fake_pool.search_errors.add("Flaky")

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result["errors"] == 1
        assert result["searched"] == 0
        # an outage is not an attempt → stays eligible next run
        assert _artists(task_engine)["Flaky"].deezer_searched_at is None
        assert _artists(task_engine)["Flaky"].deezer_search_attempts == 0

    def test_batch_commit_survives_midrun_crash(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self, monkeypatch
    ):
        """A non-HTTP crash in the 2nd batch must not roll back the 1st batch's
        committed progress (the whole point of committing per chunk)."""
        monkeypatch.setattr(tasks_env.artists, "ARTIST_BACKLOG_BATCH", 2)
        with Session(task_engine) as s:
            for n in range(4):  # oldest-id-first → batches [A0,A1] then [A2,A3]
                _add_artist(s, f"A{n}")
        for n in range(4):
            fake_pool.search[f"A{n}"] = []  # no match, just mark
        fake_pool.boom.add("A2")  # crash inside the 2nd batch

        with pytest.raises(RuntimeError):
            tasks_env.artists.link_artists_deezer(fake_self)

        arts = _artists(task_engine)
        # first batch committed before the crash
        assert arts["A0"].deezer_search_attempts == 1
        assert arts["A1"].deezer_search_attempts == 1
        # second batch never committed
        assert arts["A2"].deezer_search_attempts == 0
        assert arts["A3"].deezer_search_attempts == 0
        assert _crawl_log(task_engine, "link_artists").status == "error"


class TestLinkArtistsLock:
    def test_skips_when_lock_held(self, tasks_env, fake_redis, fake_self, monkeypatch):
        run = MagicMock()
        monkeypatch.setattr(tasks_env.artists, "_run_link_artists_deezer", run)
        fake_redis.set.return_value = False
        fake_redis.get.return_value = "task-other"

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"linked": 3})
        monkeypatch.setattr(tasks_env.artists, "_run_link_artists_deezer", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-x"

        result = tasks_env.artists.link_artists_deezer(fake_self)

        assert result == {"linked": 3}
        run.assert_called_once_with(fake_self)
        _, kwargs = fake_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == tasks_env.artists.LINK_ARTISTS_LOCK_TTL
        fake_redis.delete.assert_called_once_with("lock:link_artists")

    def test_does_not_release_lock_it_no_longer_owns(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"linked": 0})
        monkeypatch.setattr(tasks_env.artists, "_run_link_artists_deezer", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-newer"

        tasks_env.artists.link_artists_deezer(fake_self)

        fake_redis.delete.assert_not_called()

    def test_lock_ttl_covers_task_time_limit(self, tasks_env):
        assert tasks_env.artists.LINK_ARTISTS_LOCK_TTL > 1500


# ── fetch_artist_artworks ────────────────────────────────────────────────────


class TestFetchArtistArtworks:
    def test_downloads_artwork_for_linked_artists(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            _add_artist(s, "Linked One", deezer_id="10", has_artwork=False)
            _add_artist(s, "Linked Two", deezer_id="11", has_artwork=False)
        fake_pool.artist_pics["10"] = {"picture_xl": "https://cdn/10.jpg"}
        fake_pool.artist_pics["11"] = {"picture_big": "https://cdn/11.jpg"}

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result["fetched"] == 2
        assert result["errors"] == 0
        assert result["dropped_by_budget"] == 0
        arts = _artists(task_engine)
        assert arts["Linked One"].has_artwork is True
        assert arts["Linked Two"].has_artwork is True
        assert _crawl_log(task_engine, "fetch_artworks").status == "success"

    def test_selection_uses_is_not_true(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        """has_artwork IS NOT TRUE must include NULL rows and exclude TRUE /
        NOT_FOUND ones (== False would silently drop the NULLs)."""
        with Session(task_engine) as s:
            _add_artist(s, "Null Art", deezer_id="20", has_artwork=None)
            _add_artist(s, "Has Art", deezer_id="21", has_artwork=True)
            _add_artist(s, "Absent", deezer_id="NOT_FOUND", has_artwork=False)
            _add_artist(s, "No Deezer", deezer_id=None, has_artwork=False)
        fake_pool.artist_pics["20"] = {"picture": "https://cdn/20.jpg"}

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result["fetched"] == 1  # only the NULL-artwork linked artist
        # only /artist/20 was ever fetched
        assert fake_pool.calls == ["/artist/20"]
        assert _artists(task_engine)["Null Art"].has_artwork is True

    def test_budget_caps_and_reports_dropped(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self, monkeypatch
    ):
        monkeypatch.setenv("ARTIST_ARTWORK_NIGHTLY_BUDGET", "1")
        with Session(task_engine) as s:
            _add_artist(s, "A", deezer_id="30", has_artwork=False)
            _add_artist(s, "B", deezer_id="31", has_artwork=False)
        fake_pool.artist_pics["30"] = {"picture_xl": "https://cdn/30.jpg"}
        fake_pool.artist_pics["31"] = {"picture_xl": "https://cdn/31.jpg"}

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result["fetched"] == 1
        assert result["dropped_by_budget"] == 1

    def test_missing_picture_is_skipped(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            _add_artist(s, "No Pic", deezer_id="40", has_artwork=False)
        fake_pool.artist_pics["40"] = {}  # no picture_* keys

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result["fetched"] == 0
        assert result["skipped"] == 1
        assert _artists(task_engine)["No Pic"].has_artwork in (False, None)

    def test_http_error_counted(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            _add_artist(s, "Flaky", deezer_id="50", has_artwork=False)
        fake_pool.pic_errors.add("50")

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result["errors"] == 1
        assert result["fetched"] == 0

    def test_empty_backlog_writes_success_log(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result == {
            "fetched": 0, "skipped": 0, "errors": 0, "dropped_by_budget": 0,
        }
        assert fake_pool.calls == []
        assert _crawl_log(task_engine, "fetch_artworks").status == "success"


class TestFetchArtworksLock:
    def test_skips_when_lock_held(self, tasks_env, fake_redis, fake_self, monkeypatch):
        run = MagicMock()
        monkeypatch.setattr(tasks_env.artists, "_run_fetch_artist_artworks", run)
        fake_redis.set.return_value = False
        fake_redis.get.return_value = "task-other"

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"fetched": 5})
        monkeypatch.setattr(tasks_env.artists, "_run_fetch_artist_artworks", run)
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-x"

        result = tasks_env.artists.fetch_artist_artworks(fake_self)

        assert result == {"fetched": 5}
        _, kwargs = fake_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == tasks_env.artists.FETCH_ARTIST_ARTWORKS_LOCK_TTL
        fake_redis.delete.assert_called_once_with("lock:fetch_artist_artworks")

    def test_lock_ttl_covers_task_time_limit(self, tasks_env):
        assert tasks_env.artists.FETCH_ARTIST_ARTWORKS_LOCK_TTL > 1500
