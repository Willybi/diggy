"""
C6.c — tests for the check_followed_artists daily worker.

Runs the real task function (celery ecosystem mocked, same pattern as
test_tasks_observability.py) against an in-memory SQLite engine. The Deezer
side is exercised through a FakePool that stands in for HttpPool (no network):
the task's own release-filtering / idempotence logic runs for real.

Two volets are covered:
  - releases: Deezer albums within the 30-day horizon become artist_activity
    rows; old ones are ignored; a second run creates no duplicate; artists with
    a NULL / NOT_FOUND deezer_id are skipped without any Deezer call; an HTTP
    error on one artist is counted and the run continues.
  - sets: a recently imported set featuring a followed artist becomes an
    activity; sets outside the 48h window or featuring an unfollowed artist do
    not; plus the Redis single-instance lock (SET NX EX, conditional release).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Path so workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Mock infra that isn't available outside Docker (same pattern as
# test_tasks_observability.py). curl_cffi + redis are imported at
# workers.async_http / lock load time but not installed in the test env.
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


# Same attributes as test_task_refactor.py's decorator: several files overwrite
# the shared workers.celery_app mock, so tasks decorated by either mock must
# satisfy every test file's assertions.
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

from database import Base
from models import (
    Artist,
    ArtistActivity,
    CrawlLog,
    DJSet,
    FollowedArtist,
    SetArtist,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def task_engine():
    """In-memory SQLite for the real task.

    AUTOCOMMIT for the same reason as test_tasks_observability.py: the
    CrawlLogger session holds a flushed crawl_logs row while work sessions
    (including the one driven from asyncio.run) open and write on the same DB.
    """
    engine = create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def fake_redis(monkeypatch):
    """Controllable `redis` module. Defaults let the lock be acquired and
    released cleanly; lock tests override set/get."""
    client = MagicMock()
    client.set.return_value = True  # nx acquired
    client.get.return_value = "task-cfa"  # still owned → clean release
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def tasks_env(task_engine, monkeypatch):
    """Import the real artists task module with celery mocked + engine redirected."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.db as workers_db
    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)
    import workers.tasks.artists as artists_mod
    return SimpleNamespace(artists=artists_mod)


class FakePool:
    """Stand-in for workers.async_http.HttpPool.

    Serves three Deezer endpoints the releases volet now uses:
      - ``/artist/{id}/albums`` -> ``albums[deezer_id]``
      - ``/album/{id}``         -> ``{tracks:{data: album_tracks[str(id)]}}``
      - ``/track/{id}``         -> ``tracks[str(id)]`` (raw track hit)

    ``errors`` / ``album_errors`` / ``track_errors`` make the matching endpoint
    raise like a Deezer outage. ``calls`` records every requested path so tests
    can assert that skipped artists / out-of-horizon albums trigger no call.
    """

    def __init__(self):
        self.albums = {}
        self.album_tracks = {}
        self.tracks = {}
        self.errors = set()
        self.album_errors = set()
        self.track_errors = set()
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def deezer_get(self, path, params=None):
        from workers.async_http import DeezerHTTPError

        self.calls.append(path)
        parts = path.strip("/").split("/")
        if parts[0] == "artist" and parts[-1] == "albums":
            deezer_id = parts[1]
            if deezer_id in self.errors:
                raise DeezerHTTPError(500, path)
            return {"data": self.albums.get(deezer_id, [])}
        if parts[0] == "album":
            album_id = parts[1]
            if album_id in self.album_errors:
                raise DeezerHTTPError(500, path)
            return {
                "id": int(album_id),
                "tracks": {"data": self.album_tracks.get(album_id, [])},
            }
        if parts[0] == "track":
            track_id = parts[1]
            if track_id in self.track_errors:
                raise DeezerHTTPError(500, path)
            return self.tracks.get(
                track_id, {"error": {"code": 800, "message": "not found"}}
            )
        return {}


@pytest.fixture
def fake_pool(monkeypatch):
    """Patch HttpPool so _check_releases never hits the network."""
    import workers.async_http as async_http

    pool = FakePool()
    monkeypatch.setattr(async_http, "HttpPool", lambda limiter=None: pool)
    return pool


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-cfa"
    return task_self


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_artist(session, name, deezer_id=None):
    a = Artist(name=name, normalized_name=name.lower(), deezer_id=deezer_id)
    session.add(a)
    session.flush()
    return a


def _follow(session, artist_id, user_id=1):
    session.add(FollowedArtist(user_id=user_id, artist_id=artist_id))


def _make_set(session, ext_id, title, *, hours_ago=1.0, source_url="https://trackid/x"):
    now = datetime.now(timezone.utc)
    dj = DJSet(
        source="trackid",
        title=title,
        external_id=ext_id,
        source_url=source_url,
        created_at=now - timedelta(hours=hours_ago),
    )
    session.add(dj)
    session.flush()
    return dj


def _album(album_id, *, days_ago, title="New EP", record_type="ep"):
    d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return {
        "id": album_id,
        "title": title,
        "link": f"https://www.deezer.com/album/{album_id}",
        "release_date": d,
        "record_type": record_type,
        # a real Deezer payload carries cover_* URLs — they must NOT be stored
        "cover_xl": "https://e-cdn/cover.jpg",
    }


def _track_summary(track_id, title="Track"):
    """A Deezer album-tracklist entry (id + title + link)."""
    return {
        "id": track_id,
        "title": title,
        "link": f"https://www.deezer.com/track/{track_id}",
    }


def _track_hit(track_id, title, artist_name, artist_dz, *, days_ago=5, isrc=None):
    """A raw Deezer /track/{id} payload. No album cover on purpose so the crawl's
    enrich step never reaches the (network) artwork upload in tests."""
    d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return {
        "id": track_id,
        "title": title,
        "link": f"https://www.deezer.com/track/{track_id}",
        "isrc": isrc,
        "duration": 180,
        "preview": "https://e-cdn/preview.mp3",
        "release_date": d,
        "artist": {"id": artist_dz, "name": artist_name},
        "contributors": [{"id": artist_dz, "name": artist_name, "role": "Main"}],
    }


def _catalog_entries(engine):
    from models import CatalogEntry

    with Session(engine) as s:
        return s.execute(select(CatalogEntry)).scalars().all()


def _activities(engine, **filters):
    with Session(engine) as s:
        q = select(ArtistActivity)
        for k, v in filters.items():
            q = q.where(getattr(ArtistActivity, k) == v)
        return s.execute(q).scalars().all()


def _crawl_log(engine):
    with Session(engine) as s:
        return s.execute(
            select(CrawlLog).where(CrawlLog.task_type == "check_followed_artists")
        ).scalar_one()


# ── Releases volet ───────────────────────────────────────────────────────────


class TestReleasesVolet:
    def test_recent_release_crawls_each_track(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        """A recent release is expanded into its tracklist; every track is
        crawled into the catalog and gets its own activity linked by catalog_id."""
        with Session(task_engine) as s:
            a = _make_artist(s, "Boris Brejcha", deezer_id="10")
            _follow(s, a.id)
            s.commit()
            artist_id = a.id
        fake_pool.albums["10"] = [_album(555, days_ago=5)]
        fake_pool.album_tracks["555"] = [
            _track_summary(5551, "Song A"),
            _track_summary(5552, "Song B"),
        ]
        fake_pool.tracks["5551"] = _track_hit(5551, "Song A", "Boris Brejcha", "10")
        fake_pool.tracks["5552"] = _track_hit(5552, "Song B", "Boris Brejcha", "10")

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["artists_checked"] == 1
        assert result["releases_found"] == 2  # one activity per track
        assert result["catalog_created"] == 2
        assert result["crawl_errors"] == 0
        assert result["errors"] == 0

        acts = _activities(task_engine, activity_type="release")
        assert len(acts) == 2
        assert {a.external_id for a in acts} == {"5551", "5552"}
        assert all(a.artist_id == artist_id and a.source == "deezer" for a in acts)
        # Each activity is linked to a real catalog entry
        cat_ids = {a.catalog_id for a in acts}
        assert None not in cat_ids
        # payload carries the album context, never an image URL
        act = next(a for a in acts if a.external_id == "5551")
        assert set(act.payload.keys()) == {
            "release_date",
            "record_type",
            "album_id",
            "album_title",
        }
        assert act.payload["album_id"] == "555"

        # The crawled catalog entries look like any other track
        entries = {e.title: e for e in _catalog_entries(task_engine)}
        assert set(entries) == {"Song A", "Song B"}
        song_a = entries["Song A"]
        assert song_a.deezer_id == "5551"
        assert song_a.has_preview is True
        assert song_a.release_date is not None
        assert song_a.scope == "shared"  # visible to everyone, like radar tracks

        log = _crawl_log(task_engine)
        assert log.status == "success"
        assert log.stats == result

    def test_release_outside_horizon_ignored(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            a = _make_artist(s, "Old Timer", deezer_id="11")
            _follow(s, a.id)
            s.commit()
        fake_pool.albums["11"] = [_album(999, days_ago=60)]

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["artists_checked"] == 1
        assert result["releases_found"] == 0
        assert _activities(task_engine, activity_type="release") == []
        # horizon gate is applied BEFORE any album/track fetch
        assert fake_pool.calls == ["/artist/11/albums"]

    def test_second_run_is_idempotent(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            a = _make_artist(s, "Repeat", deezer_id="12")
            _follow(s, a.id)
            s.commit()
        fake_pool.albums["12"] = [_album(777, days_ago=3)]
        fake_pool.album_tracks["777"] = [_track_summary(7771, "Only Track")]
        fake_pool.tracks["7771"] = _track_hit(7771, "Only Track", "Repeat", "12")

        first = tasks_env.artists.check_followed_artists(fake_self)
        second = tasks_env.artists.check_followed_artists(fake_self)

        assert first["releases_found"] == 1
        assert first["catalog_created"] == 1
        assert second["releases_found"] == 0  # track already recorded
        assert second["catalog_created"] == 0  # catalog entry reused, not duplicated
        assert len(_activities(task_engine, activity_type="release")) == 1
        assert len(_catalog_entries(task_engine)) == 1

    def test_null_and_not_found_deezer_id_skipped_without_call(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            a1 = _make_artist(s, "No Deezer", deezer_id=None)
            a2 = _make_artist(s, "Confirmed Absent", deezer_id="NOT_FOUND")
            _follow(s, a1.id)
            _follow(s, a2.id)
            s.commit()

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["artists_checked"] == 0
        assert result["artists_skipped_no_deezer"] == 2
        assert result["releases_found"] == 0
        # No Deezer call whatsoever for skipped artists
        assert fake_pool.calls == []
        assert _activities(task_engine, activity_type="release") == []

    def test_http_error_on_one_artist_continues(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self, caplog
    ):
        import logging

        with Session(task_engine) as s:
            failing = _make_artist(s, "Flaky", deezer_id="20")
            ok = _make_artist(s, "Fine", deezer_id="21")
            _follow(s, failing.id)
            _follow(s, ok.id)
            s.commit()
        fake_pool.errors.add("20")
        fake_pool.albums["21"] = [_album(321, days_ago=2)]
        fake_pool.album_tracks["321"] = [_track_summary(3211, "Healthy Track")]
        fake_pool.tracks["3211"] = _track_hit(3211, "Healthy Track", "Fine", "21")

        with caplog.at_level(logging.WARNING, logger="workers.tasks.artists"):
            result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["artists_checked"] == 2
        assert result["errors"] == 1
        assert result["releases_found"] == 1  # the healthy artist still recorded
        acts = _activities(task_engine, activity_type="release")
        assert {a.external_id for a in acts} == {"3211"}
        assert any("albums fetch failed" in r.getMessage() for r in caplog.records)
        # A per-artist failure never aborts the run
        assert _crawl_log(task_engine).status == "success"

    def test_track_fetch_failure_records_link_only_card(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        """A track whose detail fetch fails still gets a link-only activity
        (external Deezer URL, no catalog_id) so the release is never lost."""
        with Session(task_engine) as s:
            a = _make_artist(s, "Half Down", deezer_id="50")
            _follow(s, a.id)
            s.commit()
        fake_pool.albums["50"] = [_album(5000, days_ago=2)]
        fake_pool.album_tracks["5000"] = [_track_summary(50001, "Ghost Track")]
        fake_pool.track_errors.add("50001")  # /track/50001 → Deezer outage

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["releases_found"] == 1
        assert result["catalog_created"] == 0
        assert result["errors"] == 1  # the track fetch failure is counted
        acts = _activities(task_engine, activity_type="release")
        assert len(acts) == 1
        act = acts[0]
        assert act.catalog_id is None
        assert act.title == "Ghost Track"
        assert act.external_url == "https://www.deezer.com/track/50001"
        assert _catalog_entries(task_engine) == []

    def test_shared_follow_is_processed_once(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        """Two users following the same artist → one Deezer check (DISTINCT)."""
        with Session(task_engine) as s:
            a = _make_artist(s, "Popular", deezer_id="30")
            _follow(s, a.id, user_id=1)
            _follow(s, a.id, user_id=2)
            s.commit()
        fake_pool.albums["30"] = [_album(30001, days_ago=1)]
        fake_pool.album_tracks["30001"] = [_track_summary(300011, "Hit")]
        fake_pool.tracks["300011"] = _track_hit(300011, "Hit", "Popular", "30")

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["artists_checked"] == 1
        assert fake_pool.calls.count("/artist/30/albums") == 1
        assert len(_activities(task_engine, activity_type="release")) == 1

    def test_legacy_album_card_is_superseded(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        """A pre-crawl album-level release row (external_id = album id) is deleted
        when the album is reprocessed into per-track cards."""
        from models import ArtistActivity

        with Session(task_engine) as s:
            a = _make_artist(s, "Legacy", deezer_id="60")
            _follow(s, a.id)
            # simulate the old behaviour: one activity keyed on the ALBUM id
            s.add(
                ArtistActivity(
                    artist_id=a.id,
                    activity_type="release",
                    source="deezer",
                    external_id="6000",
                    title="Old Album Card",
                    external_url="https://www.deezer.com/album/6000",
                )
            )
            s.commit()
        fake_pool.albums["60"] = [_album(6000, days_ago=4)]
        fake_pool.album_tracks["6000"] = [_track_summary(60001, "Fresh Track")]
        fake_pool.tracks["60001"] = _track_hit(60001, "Fresh Track", "Legacy", "60")

        result = tasks_env.artists.check_followed_artists(fake_self)

        acts = _activities(task_engine, activity_type="release")
        assert result["releases_found"] == 1
        # the album-level card is gone, replaced by the per-track card
        assert {a.external_id for a in acts} == {"60001"}


# ── Sets volet ───────────────────────────────────────────────────────────────


class TestSetsVolet:
    def test_recent_set_creates_activity(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            a = _make_artist(s, "Set DJ", deezer_id="40")
            _follow(s, a.id)
            dj = _make_set(s, "set-1", "Awesome B2B", hours_ago=2.0)
            s.add(SetArtist(set_id=dj.id, artist_id=a.id, role="dj", position=0))
            s.commit()
            artist_id, set_id = a.id, dj.id

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["sets_found"] == 1
        acts = _activities(task_engine, activity_type="set")
        assert len(acts) == 1
        act = acts[0]
        assert act.artist_id == artist_id
        assert act.source == "trackid"
        assert act.external_id == str(set_id)
        assert act.set_id == set_id
        assert act.title == "Awesome B2B"
        assert act.external_url == "https://trackid/x"

    def test_set_outside_window_ignored(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            a = _make_artist(s, "Late DJ", deezer_id="41")
            _follow(s, a.id)
            dj = _make_set(s, "set-old", "Old Set", hours_ago=72.0)
            s.add(SetArtist(set_id=dj.id, artist_id=a.id, role="dj", position=0))
            s.commit()

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["sets_found"] == 0
        assert _activities(task_engine, activity_type="set") == []

    def test_set_with_unfollowed_artist_ignored(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            followed = _make_artist(s, "Followed", deezer_id="42")
            other = _make_artist(s, "Unfollowed", deezer_id="43")
            _follow(s, followed.id)  # only `followed` is followed
            dj = _make_set(s, "set-2", "Someone Else Live", hours_ago=1.0)
            s.add(SetArtist(set_id=dj.id, artist_id=other.id, role="dj", position=0))
            s.commit()

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result["sets_found"] == 0
        assert _activities(task_engine, activity_type="set") == []

    def test_set_second_run_is_idempotent(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        with Session(task_engine) as s:
            a = _make_artist(s, "Repeat Set DJ", deezer_id="44")
            _follow(s, a.id)
            dj = _make_set(s, "set-3", "Repeat Set", hours_ago=1.0)
            s.add(SetArtist(set_id=dj.id, artist_id=a.id, role="dj", position=0))
            s.commit()

        first = tasks_env.artists.check_followed_artists(fake_self)
        second = tasks_env.artists.check_followed_artists(fake_self)

        assert first["sets_found"] == 1
        assert second["sets_found"] == 0
        assert len(_activities(task_engine, activity_type="set")) == 1


# ── Empty run ────────────────────────────────────────────────────────────────


class TestEmptyRun:
    def test_no_followed_artists_writes_success_log(
        self, tasks_env, task_engine, fake_pool, fake_redis, fake_self
    ):
        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result == {
            "artists_checked": 0,
            "artists_skipped_no_deezer": 0,
            "releases_found": 0,
            "catalog_created": 0,
            "crawl_errors": 0,
            "sets_found": 0,
            "errors": 0,
        }
        assert fake_pool.calls == []  # nothing to check → no Deezer traffic
        log = _crawl_log(task_engine)
        assert log.status == "success"
        assert log.stats == result


# ── Redis single-instance lock ───────────────────────────────────────────────


class TestCheckFollowedArtistsLock:
    """Same SET NX EX + conditional-release pattern as resolve_set_tracks."""

    def test_skips_when_lock_held(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock()
        monkeypatch.setattr(
            tasks_env.artists, "_run_check_followed_artists", run
        )
        fake_redis.set.return_value = False  # nx=True: lock already held
        fake_redis.get.return_value = "task-other"

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        fake_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"releases_found": 2})
        monkeypatch.setattr(
            tasks_env.artists, "_run_check_followed_artists", run
        )
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-cfa"  # still owns the lock

        result = tasks_env.artists.check_followed_artists(fake_self)

        assert result == {"releases_found": 2}
        run.assert_called_once_with(fake_self)
        _, kwargs = fake_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == tasks_env.artists.CHECK_FOLLOWED_ARTISTS_LOCK_TTL
        fake_redis.delete.assert_called_once_with("lock:check_followed_artists")

    def test_releases_lock_on_failure(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(
            tasks_env.artists, "_run_check_followed_artists", run
        )
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-cfa"

        with pytest.raises(RuntimeError):
            tasks_env.artists.check_followed_artists(fake_self)

        fake_redis.delete.assert_called_once_with("lock:check_followed_artists")

    def test_does_not_release_lock_it_no_longer_owns(
        self, tasks_env, fake_redis, fake_self, monkeypatch
    ):
        run = MagicMock(return_value={"releases_found": 0})
        monkeypatch.setattr(
            tasks_env.artists, "_run_check_followed_artists", run
        )
        fake_redis.set.return_value = True
        fake_redis.get.return_value = "task-newer"  # someone else owns it now

        tasks_env.artists.check_followed_artists(fake_self)

        fake_redis.delete.assert_not_called()

    def test_lock_ttl_covers_task_time_limit(self, tasks_env):
        assert tasks_env.artists.CHECK_FOLLOWED_ARTISTS_LOCK_TTL > 3900
