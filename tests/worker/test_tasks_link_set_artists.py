"""
Tests for link_set_artists core logic.
Replicates the matching algorithm without Celery/external DB.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Artist, ArtistAlias, DJSet, SetArtist
from utils import normalize


def _link_set_artists(session):
    """Replicate core logic of link_set_artists task."""
    # Build lookup: normalized name/alias -> artist_id
    norm_to_id = {}
    for a in session.execute(select(Artist)).scalars().all():
        norm_to_id[normalize(a.name)] = a.id
    for al in session.execute(select(ArtistAlias)).scalars().all():
        if al.normalized_alias not in norm_to_id:
            norm_to_id[al.normalized_alias] = al.artist_id

    sorted_names = sorted(norm_to_id.keys(), key=len, reverse=True)

    sets = session.execute(select(DJSet)).scalars().all()
    linked = 0
    skipped = 0

    for dj_set in sets:
        title = dj_set.title or ""
        title_lower = title.lower()
        is_b2b = "b2b" in title_lower

        matched_ids = set()
        title_norm = normalize(title)
        title_norm_clean = title_norm.replace("_", " ")

        for norm_name in sorted_names:
            if len(norm_name) < 3:
                continue
            if norm_name in title_norm or norm_name in title_norm_clean:
                aid = norm_to_id[norm_name]
                if aid not in matched_ids:
                    matched_ids.add(aid)

        existing = {
            r[0] for r in session.execute(
                select(SetArtist.artist_id).where(SetArtist.set_id == dj_set.id)
            ).all()
        }

        for aid in matched_ids:
            if aid in existing:
                skipped += 1
                continue
            role = "b2b" if is_b2b else "dj"
            session.add(SetArtist(set_id=dj_set.id, artist_id=aid, role=role, position=0))
            linked += 1

        session.commit()

    return {"linked": linked, "skipped": skipped}


class TestLinkSetArtists:
    def test_matches_artist_in_title(self, sync_session):
        s = sync_session
        a = Artist(name="ANNA", normalized_name="anna")
        s.add(a)
        dj = DJSet(source="trackid", title="ANNA at Boiler Room")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 1

        sa = s.execute(select(SetArtist)).scalar_one()
        assert sa.artist_id == a.id
        assert sa.role == "dj"

    def test_b2b_role(self, sync_session):
        s = sync_session
        a1 = Artist(name="CamelPhat", normalized_name="camelphat")
        a2 = Artist(name="Solardo", normalized_name="solardo")
        s.add_all([a1, a2])
        dj = DJSet(source="trackid", title="CamelPhat B2B Solardo")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 2

        links = s.execute(select(SetArtist)).scalars().all()
        assert all(l.role == "b2b" for l in links)

    def test_skips_short_names(self, sync_session):
        s = sync_session
        a = Artist(name="DJ", normalized_name="dj")
        s.add(a)
        dj = DJSet(source="trackid", title="DJ ANNA at Club")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        # "dj" is < 3 chars, should be skipped
        assert result["linked"] == 0

    def test_skips_existing_links(self, sync_session):
        s = sync_session
        a = Artist(name="ANNA", normalized_name="anna")
        s.add(a)
        dj = DJSet(source="trackid", title="ANNA at Club")
        s.add(dj)
        s.flush()
        s.add(SetArtist(set_id=dj.id, artist_id=a.id, role="dj", position=0))
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 0
        assert result["skipped"] == 1

    def test_matches_via_alias(self, sync_session):
        s = sync_session
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        s.add(a)
        s.flush()
        s.add(ArtistAlias(artist_id=a.id, alias="Camel Phat", normalized_alias="camel phat"))
        dj = DJSet(source="trackid", title="Camel Phat live at Ushuaia")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 1

        sa = s.execute(select(SetArtist)).scalar_one()
        assert sa.artist_id == a.id


# ── link_set_artists single-instance lock (Lot L6) ────────────────────────────
# The lock lives entirely in the task wrapper (SET NX EX + conditional release,
# the same pattern as link_artists_deezer); the real work is _run_link_set_artists.
# This section stands up the minimal celery/redis mock harness (identical shape to
# test_task_locks.py / test_tasks_artist_backlog.py) so the real task wrapper can
# be exercised. The pure-logic tests above keep using the real DB session and are
# untouched by it.
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402
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
        # No explicit time_limit on link_set_artists → global 3600; TTL must exceed it
        assert artists_mod.LINK_SET_ARTISTS_LOCK_TTL > 3600
