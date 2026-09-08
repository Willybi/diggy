"""
Tests for the C2c-2b link_set_artists task.

The task was rewritten (C2c-2b) around the extractor+resolver chain
(``workers.set_artist_resolve.resolve_link_artist_ids``): candidates from the set
title/channel resolve BASE-FIRST against our own artists, then fall back to Deezer
verification (``_verify_set_artist_via_deezer``). The old verbatim-substring
matcher (and its self-contained replica ``_link_set_artists`` that used to live
here) is gone — those replica tests exercised logic that no longer exists, so they
are replaced by:
  * unit tests of ``_verify_set_artist_via_deezer`` (Deezer mocked: qualifying hit
    → id via ``_resolve_or_create_artist`` / DeezerHTTPError → None / placeholder
    → None / fan floor),
  * end-to-end tests of ``_run_link_set_artists`` against an in-memory engine
    (idempotence, selection cap, skip of already-linked sets), Deezer stubbed so
    no network is touched,
  * the single-instance lock tests (unchanged).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Artist, DJSet, SetArtist  # noqa: F401 (used by the e2e tests)


# ── link_set_artists single-instance lock (Lot L6) ────────────────────────────
# The lock lives entirely in the task wrapper (SET NX EX + conditional release,
# the same pattern as link_artists_deezer); the real work is _run_link_set_artists.
# This section stands up the minimal celery/redis mock harness (identical shape to
# test_task_locks.py / test_tasks_artist_backlog.py) so the real task wrapper can
# be exercised. The pure-logic tests above keep using the real DB session and are
# untouched by it.
import asyncio as _asyncio  # noqa: E402
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402
from datetime import datetime as _datetime, timezone as _timezone  # noqa: E402
from unittest.mock import MagicMock as _MagicMock  # noqa: E402

import pytest as _pytest  # noqa: E402

_SERVER_PATH = _os.path.join(_os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in _sys.path:
    _sys.path.insert(0, _SERVER_PATH)

for _mod in [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions", "requests", "curl_cffi",
]:
    if _mod not in _sys.modules:
        _sys.modules[_mod] = _MagicMock()


# _run_link_set_artists does `from celery.exceptions import SoftTimeLimitExceeded`
# and uses it in an `except` clause — which needs a real class inheriting
# BaseException, not a MagicMock. Expose one (same pattern as test_deadline_exit).
class _FakeSoftTimeLimitExceeded(Exception):
    pass


_celery_exceptions = _sys.modules.setdefault("celery.exceptions", _MagicMock())
_celery_exceptions.SoftTimeLimitExceeded = _FakeSoftTimeLimitExceeded


def _lock_task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.autoretry_for = kwargs.get("autoretry_for", ())
        fn.bind = kwargs.get("bind", False)
        fn.soft_time_limit = kwargs.get("soft_time_limit")
        fn.time_limit = kwargs.get("time_limit")
        fn.delay = _MagicMock()
        fn.s = _MagicMock()
        return fn
    if args and callable(args[0]):
        return _lock_task_decorator()(args[0])
    return decorator


_lock_celery_mock = _MagicMock()
_lock_celery_mock.task.side_effect = _lock_task_decorator
_lock_celery_app_mod = _MagicMock(celery_app=_lock_celery_mock)
_sys.modules["workers.celery_app"] = _lock_celery_app_mod


@_pytest.fixture
def lock_redis(monkeypatch):
    """Controllable redis client; defaults acquire + cleanly release the lock."""
    client = _MagicMock()
    client.set.return_value = True
    client.get.return_value = "task-lsa"
    redis_mod = _MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(_sys.modules, "redis", redis_mod)
    return client


@_pytest.fixture
def artists_mod(monkeypatch):
    """Import the real artists task module with celery mocked."""
    monkeypatch.setitem(_sys.modules, "workers.celery_app", _lock_celery_app_mod)
    for m in [k for k in _sys.modules if k.startswith("workers.tasks")]:
        del _sys.modules[m]
    import workers.tasks.artists as artists
    return artists


@_pytest.fixture
def lock_self():
    task_self = _MagicMock()
    task_self.request.id = "task-lsa"
    return task_self


class TestLinkSetArtistsLock:
    """Same SET NX EX + conditional-release pattern as link_artists_deezer."""

    def test_skips_when_lock_held(
        self, artists_mod, lock_redis, lock_self, monkeypatch
    ):
        run = _MagicMock()
        monkeypatch.setattr(artists_mod, "_run_link_set_artists", run)
        lock_redis.set.return_value = False  # nx=True: lock already held
        lock_redis.get.return_value = "task-other"

        result = artists_mod.link_set_artists(lock_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        lock_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, artists_mod, lock_redis, lock_self, monkeypatch
    ):
        run = _MagicMock(return_value={"linked": 2})
        monkeypatch.setattr(artists_mod, "_run_link_set_artists", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-lsa"  # still owns the lock

        result = artists_mod.link_set_artists(lock_self)

        assert result == {"linked": 2}
        run.assert_called_once_with(lock_self)
        _, kwargs = lock_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == artists_mod.LINK_SET_ARTISTS_LOCK_TTL
        lock_redis.delete.assert_called_once_with("lock:link_set_artists")

    def test_does_not_release_lock_it_no_longer_owns(
        self, artists_mod, lock_redis, lock_self, monkeypatch
    ):
        run = _MagicMock(return_value={"linked": 0})
        monkeypatch.setattr(artists_mod, "_run_link_set_artists", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-newer"  # someone else owns it now

        artists_mod.link_set_artists(lock_self)

        lock_redis.delete.assert_not_called()

    def test_lock_ttl_covers_task_time_limit(self, artists_mod):
        # C2c-2b — link_set_artists now carries an explicit time_limit; the lock
        # TTL must exceed it so the lock cannot expire mid-run.
        assert (
            artists_mod.LINK_SET_ARTISTS_LOCK_TTL
            > artists_mod.LINK_SET_ARTISTS_TIME_LIMIT
        )


# ── _verify_set_artist_via_deezer (Deezer path, network mocked) ───────────────


class _FakePool:
    """Minimal HttpPool stand-in for _verify_set_artist_via_deezer.

    ``data`` is returned by ``deezer_get``; ``raise_http`` makes it raise a real
    ``DeezerHTTPError`` (an outage) instead.
    """

    def __init__(self, data=None, raise_http=False):
        self._data = data if data is not None else {"data": []}
        self._raise = raise_http

    async def deezer_get(self, path, params=None):
        if self._raise:
            from workers.async_http import DeezerHTTPError

            raise DeezerHTTPError(503, path)
        return self._data


@_pytest.fixture
def unit_session(artists_mod):
    """A real in-memory sync session (artists_mod imported first so the celery
    mock + sys.path are in place)."""
    from sqlalchemy import create_engine

    from database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


class TestVerifySetArtistViaDeezer:
    def test_qualifying_hit_creates_and_returns_id(self, artists_mod, unit_session):
        pool = _FakePool(
            {"data": [{"id": 42, "name": "Peggy Gou", "nb_fan": 120000}]}
        )
        aid = _asyncio.run(
            artists_mod._verify_set_artist_via_deezer(
                pool, unit_session, "Peggy Gou", 0
            )
        )
        assert aid is not None
        art = unit_session.get(Artist, aid)
        assert art is not None
        assert art.deezer_id == "42"

    def test_http_error_returns_none_and_creates_nothing(
        self, artists_mod, unit_session
    ):
        pool = _FakePool(raise_http=True)
        aid = _asyncio.run(
            artists_mod._verify_set_artist_via_deezer(
                pool, unit_session, "Some DJ", 0
            )
        )
        assert aid is None
        assert unit_session.execute(select(Artist)).first() is None

    def test_placeholder_hit_returns_none(self, artists_mod, unit_session):
        # An exact-name hit that resolves to a placeholder must NOT spawn an artist.
        pool = _FakePool(
            {"data": [{"id": 1, "name": "Various Artists", "nb_fan": 0}]}
        )
        aid = _asyncio.run(
            artists_mod._verify_set_artist_via_deezer(
                pool, unit_session, "Various Artists", 0
            )
        )
        assert aid is None
        assert unit_session.execute(select(Artist)).first() is None

    def test_no_match_returns_none(self, artists_mod, unit_session):
        # A hit that does not match the queried name (X4 gate) links nothing.
        pool = _FakePool(
            {"data": [{"id": 9, "name": "Totally Different", "nb_fan": 999}]}
        )
        aid = _asyncio.run(
            artists_mod._verify_set_artist_via_deezer(
                pool, unit_session, "Peggy Gou", 0
            )
        )
        assert aid is None

    def test_fan_floor_gates_low_fan_hit(self, artists_mod, unit_session):
        pool = _FakePool({"data": [{"id": 7, "name": "Tiny DJ", "nb_fan": 50}]})
        # Below the floor → refused.
        assert (
            _asyncio.run(
                artists_mod._verify_set_artist_via_deezer(
                    pool, unit_session, "Tiny DJ", 1000
                )
            )
            is None
        )
        # Floor off (0) → the exact-name match links even a small DJ.
        assert (
            _asyncio.run(
                artists_mod._verify_set_artist_via_deezer(
                    pool, unit_session, "Tiny DJ", 0
                )
            )
            is not None
        )

    def test_fan_floor_helper_defaults_to_fan_floor(self, artists_mod, monkeypatch):
        # C2c-3: the default is no longer 0 (off) but workers.artist_names.FAN_FLOOR
        # (1000) — the set-title extractor over-proposes noisy tokens, so a Deezer
        # verification of a set candidate must clear a popularity bar.
        from workers.artist_names import FAN_FLOOR

        monkeypatch.delenv("LINK_SET_ARTIST_FAN_FLOOR", raising=False)
        assert artists_mod._link_set_artist_fan_floor() == FAN_FLOOR == 1000
        # The env overrides it, and an explicit "0" disables the floor entirely.
        monkeypatch.setenv("LINK_SET_ARTIST_FAN_FLOOR", "5000")
        assert artists_mod._link_set_artist_fan_floor() == 5000
        monkeypatch.setenv("LINK_SET_ARTIST_FAN_FLOOR", "0")
        assert artists_mod._link_set_artist_fan_floor() == 0


# ── _run_link_set_artists end-to-end (in-memory engine, Deezer stubbed) ───────


@_pytest.fixture
def task_engine():
    """AUTOCOMMIT in-memory engine (the task overlaps the CrawlLogger session and
    the work session on one connection — same rationale as test_tasks_observability).
    """
    from sqlalchemy import create_engine

    from database import Base

    engine = create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@_pytest.fixture
def linked_env(task_engine, artists_mod, lock_redis, monkeypatch):
    """artists_mod with get_engine redirected to the in-memory task_engine and the
    Deezer verification stubbed to None (no network) by default."""
    import workers.db as workers_db

    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)

    async def _no_deezer(pool, session, name, fan_floor):
        return None

    monkeypatch.setattr(artists_mod, "_verify_set_artist_via_deezer", _no_deezer)
    return artists_mod


class TestRunLinkSetArtists:
    def test_links_leading_artist_and_is_idempotent(
        self, linked_env, task_engine, lock_self
    ):
        with Session(task_engine) as s:
            s.add(
                Artist(
                    name="Ricardo Villalobos",
                    normalized_name="ricardo villalobos",
                )
            )
            s.add(
                DJSet(
                    source="trackid",
                    title="Ricardo Villalobos - Live at Fabric",
                    created_at=_datetime(2026, 9, 1, tzinfo=_timezone.utc),
                )
            )
            s.commit()

        r1 = linked_env.link_set_artists(lock_self)
        assert r1["sets_processed"] == 1
        assert r1["links_created"] == 1
        assert r1["deezer_confirmed"] == 0

        # Re-run: the now-linked set is excluded by the NOT EXISTS guard.
        r2 = linked_env.link_set_artists(lock_self)
        assert r2["sets_processed"] == 0
        assert r2["links_created"] == 0

        with Session(task_engine) as s:
            links = s.execute(select(SetArtist)).scalars().all()
            assert len(links) == 1
            assert links[0].role == "dj"

    def test_caps_and_skips_already_linked(
        self, linked_env, task_engine, lock_self, monkeypatch
    ):
        monkeypatch.setenv("LINK_SET_ARTISTS_MAX_SETS_PER_RUN", "2")
        with Session(task_engine) as s:
            a = Artist(name="ANNA", normalized_name="anna")
            s.add(a)
            s.flush()
            for i in range(3):
                s.add(
                    DJSet(
                        source="trackid",
                        title=f"ANNA - Set {i}",
                        created_at=_datetime(2026, 9, i + 1, tzinfo=_timezone.utc),
                    )
                )
            already = DJSet(
                source="trackid",
                title="ANNA - Old",
                created_at=_datetime(2026, 8, 1, tzinfo=_timezone.utc),
            )
            s.add(already)
            s.flush()
            s.add(
                SetArtist(set_id=already.id, artist_id=a.id, role="dj", position=0)
            )
            s.commit()

        result = linked_env.link_set_artists(lock_self)
        # Cap: only 2 of the 3 fresh roots processed; the pre-linked one excluded.
        assert result["sets_processed"] == 2
        assert result["links_created"] == 2
        with Session(task_engine) as s:
            # 2 new + 1 pre-existing = 3, and the pre-linked set was untouched.
            assert len(s.execute(select(SetArtist)).scalars().all()) == 3

    def test_counts_deezer_confirmations(
        self, linked_env, task_engine, lock_self, monkeypatch
    ):
        with Session(task_engine) as s:
            known = Artist(name="Known DJ", normalized_name="known dj")
            s.add(known)
            s.commit()
            known_id = known.id
            s.add(
                DJSet(
                    source="trackid",
                    title="Mystery Person - Warehouse",
                    created_at=_datetime(2026, 9, 1, tzinfo=_timezone.utc),
                )
            )
            s.commit()

        # Every base-miss candidate is "confirmed" by Deezer to the known artist.
        async def _yes_deezer(pool, session, name, fan_floor):
            return known_id

        monkeypatch.setattr(linked_env, "_verify_set_artist_via_deezer", _yes_deezer)

        result = linked_env.link_set_artists(lock_self)
        assert result["deezer_confirmed"] >= 1
        assert result["links_created"] >= 1
        with Session(task_engine) as s:
            links = s.execute(select(SetArtist)).scalars().all()
            assert any(link.artist_id == known_id for link in links)

    def test_no_resolve_is_counted_and_no_link(
        self, linked_env, task_engine, lock_self
    ):
        # No artist in the base and Deezer stubbed to None → nothing links.
        with Session(task_engine) as s:
            s.add(
                DJSet(
                    source="trackid",
                    title="Nobody Known - Some Track",
                    created_at=_datetime(2026, 9, 1, tzinfo=_timezone.utc),
                )
            )
            s.commit()

        result = linked_env.link_set_artists(lock_self)
        assert result["sets_processed"] == 1
        assert result["links_created"] == 0
        assert result["skipped_no_resolve"] == 1
        with Session(task_engine) as s:
            assert s.execute(select(SetArtist)).first() is None
