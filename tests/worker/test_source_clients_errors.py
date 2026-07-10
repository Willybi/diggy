"""
Tests for typed source-client errors (A3-06 / A3-07).

Covers:
- Deezer sync clients: HTTP status + JSON "error" payload are checked on
  every request, so a mid-pagination failure never yields a partial
  tracklist (which would wrongly mark absent tracks as removed).
- TIDAL: only a confirmed 404 / ObjectNotFound translates into
  PlaylistGoneError; everything else propagates unchanged.
- radar._crawl_single_playlist_inner: the deletion branch triggers on
  PlaylistGoneError only, NOT on arbitrary exceptions mentioning "404".
"""
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import RadarTrack, User, UserFollow, WatchedEntity

# Path so workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# Mock infra that isn't available outside Docker (same pattern as test_task_refactor)
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import workers.tasks.radar as radar_tasks  # noqa: E402
from workers import source_clients  # noqa: E402
from workers.source_clients import (  # noqa: E402
    PlaylistGoneError,
    SourceTrack,
    deezer_has_changed,
    fetch_deezer_meta,
    fetch_deezer_tracks,
)


# ── Deezer helpers ─────────────────────────────────────────────────────────────


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _patch_deezer_responses(monkeypatch, responses):
    """Serve canned responses in order; keeps requests.exceptions intact."""
    queue = list(responses)

    def fake_get(url, timeout=None):
        return queue.pop(0)

    monkeypatch.setattr(
        source_clients,
        "requests",
        SimpleNamespace(get=fake_get, exceptions=requests.exceptions),
    )


def _deezer_track(track_id):
    return {
        "id": track_id,
        "title": f"Track {track_id}",
        "artist": {"name": "Artist"},
        "duration": 200,
    }


GONE_PAYLOAD = {"error": {"type": "DataException", "message": "no data", "code": 800}}
QUOTA_PAYLOAD = {"error": {"type": "QuotaException", "message": "quota", "code": 4}}


class TestDeezerTypedErrors:
    def test_fetch_tracks_happy_path_paginates_fully(self, monkeypatch):
        _patch_deezer_responses(monkeypatch, [
            _FakeResp({"data": [_deezer_track(1)], "next": "https://api.deezer.com/p2"}),
            _FakeResp({"data": [_deezer_track(2)]}),
        ])
        tracks = fetch_deezer_tracks("42")
        assert [t.external_id for t in tracks] == ["1", "2"]
        assert all(isinstance(t, SourceTrack) for t in tracks)

    def test_fetch_tracks_page_error_raises_instead_of_partial_list(self, monkeypatch):
        """A3-06: an HTTP error on page 2 must raise, never return page 1 alone."""
        _patch_deezer_responses(monkeypatch, [
            _FakeResp({"data": [_deezer_track(1)], "next": "https://api.deezer.com/p2"}),
            _FakeResp({}, status_code=500),
        ])
        with pytest.raises(RuntimeError):
            fetch_deezer_tracks("42")

    def test_fetch_tracks_json_error_on_page_raises(self, monkeypatch):
        """Deezer returns HTTP 200 with an error body: same rule, no partial list."""
        _patch_deezer_responses(monkeypatch, [
            _FakeResp({"data": [_deezer_track(1)], "next": "https://api.deezer.com/p2"}),
            _FakeResp(QUOTA_PAYLOAD),
        ])
        with pytest.raises(RuntimeError):
            fetch_deezer_tracks("42")

    def test_fetch_tracks_no_data_error_raises_playlist_gone(self, monkeypatch):
        _patch_deezer_responses(monkeypatch, [_FakeResp(GONE_PAYLOAD)])
        with pytest.raises(PlaylistGoneError) as exc_info:
            fetch_deezer_tracks("42")
        assert exc_info.value.source == "deezer"
        assert exc_info.value.external_id == "42"

    def test_fetch_meta_no_data_error_raises_playlist_gone(self, monkeypatch):
        _patch_deezer_responses(monkeypatch, [_FakeResp(GONE_PAYLOAD)])
        with pytest.raises(PlaylistGoneError):
            fetch_deezer_meta("42")

    def test_fetch_meta_http_500_raises_generic_error(self, monkeypatch):
        """A 5xx is transient: generic exception (autoretry), not PlaylistGoneError."""
        _patch_deezer_responses(monkeypatch, [_FakeResp({}, status_code=500)])
        with pytest.raises(RuntimeError):
            fetch_deezer_meta("42")

    def test_fetch_meta_other_error_code_raises_generic_error(self, monkeypatch):
        _patch_deezer_responses(monkeypatch, [_FakeResp(QUOTA_PAYLOAD)])
        with pytest.raises(RuntimeError):
            fetch_deezer_meta("42")

    def test_has_changed_no_data_error_raises_playlist_gone(self, monkeypatch):
        _patch_deezer_responses(monkeypatch, [_FakeResp(GONE_PAYLOAD)])
        with pytest.raises(PlaylistGoneError):
            deezer_has_changed("42", None)

    def test_data_exception_without_code_800_raises_playlist_gone(self, monkeypatch):
        """Any DataException means the resource is absent, whatever the code."""
        _patch_deezer_responses(monkeypatch, [
            _FakeResp({"error": {"type": "DataException", "message": "x", "code": 801}}),
        ])
        with pytest.raises(PlaylistGoneError):
            fetch_deezer_meta("42")


# ── TIDAL translation ──────────────────────────────────────────────────────────


class TestTidalTranslation:
    """_tidal_playlist translates confirmed 404s only (A3-07)."""

    @pytest.fixture(autouse=True)
    def _require_tidalapi(self):
        # tidalapi is a runtime dep (not in requirements-test.txt); the helper
        # imports ObjectNotFound lazily, so skip when unavailable.
        pytest.importorskip("tidalapi")

    def _session_raising(self, exc):
        session = MagicMock()
        session.playlist.side_effect = exc
        return session

    def test_object_not_found_translates_to_playlist_gone(self, monkeypatch):
        from tidalapi.exceptions import ObjectNotFound

        monkeypatch.setattr(
            source_clients,
            "_get_tidal_session",
            lambda: self._session_raising(ObjectNotFound("Object not found")),
        )
        with pytest.raises(PlaylistGoneError) as exc_info:
            source_clients.fetch_tidal_meta("pl-1")
        assert exc_info.value.source == "tidal"
        assert exc_info.value.external_id == "pl-1"

    def test_http_404_translates_to_playlist_gone(self, monkeypatch):
        err = requests.exceptions.HTTPError(
            "404 Client Error", response=MagicMock(status_code=404)
        )
        monkeypatch.setattr(
            source_clients, "_get_tidal_session", lambda: self._session_raising(err)
        )
        with pytest.raises(PlaylistGoneError):
            source_clients.fetch_tidal_tracks("pl-1")

    def test_http_500_propagates_unchanged(self, monkeypatch):
        err = requests.exceptions.HTTPError(
            "500 Server Error", response=MagicMock(status_code=500)
        )
        monkeypatch.setattr(
            source_clients, "_get_tidal_session", lambda: self._session_raising(err)
        )
        with pytest.raises(requests.exceptions.HTTPError):
            source_clients.fetch_tidal_meta("pl-1")

    def test_error_message_mentioning_404_propagates_unchanged(self, monkeypatch):
        """A3-07: '404' in a message is not proof the playlist is gone."""
        monkeypatch.setattr(
            source_clients,
            "_get_tidal_session",
            lambda: self._session_raising(RuntimeError("server said 404 not found")),
        )
        with pytest.raises(RuntimeError):
            source_clients.tidal_has_changed("pl-1", "2024-01-01")


# ── radar deletion branch ──────────────────────────────────────────────────────


class TestPlaylistGoneDeletion:
    """The watched_entity purge triggers on PlaylistGoneError only."""

    def _seed(self, session):
        user = User(email="x@x.com", username="x", google_id="gx", is_active=True)
        entity = WatchedEntity(external_id="dz-42", source="deezer", title="Gone")
        session.add_all([user, entity])
        session.flush()
        session.add(
            RadarTrack(
                watched_entity_id=entity.id,
                external_track_id="1",
                source="deezer",
                title="T",
            )
        )
        session.add(
            UserFollow(
                user_id=user.id,
                entity_id=entity.id,
                followed_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        return entity.id

    def _run_inner(self, sync_engine, monkeypatch, fetch_meta, playlist_id):
        import workers.db as workers_db
        from services.image_service import ImageService

        monkeypatch.setattr(workers_db, "get_engine", lambda: sync_engine)
        monkeypatch.setattr(
            source_clients,
            "get_fetchers",
            lambda source: (fetch_meta, MagicMock(), MagicMock()),
        )
        monkeypatch.setattr(ImageService, "ensure_bucket", lambda bucket: None)
        return radar_tasks._crawl_single_playlist_inner(MagicMock(), playlist_id)

    def test_playlist_gone_triggers_deletion(self, sync_engine, sync_session, monkeypatch):
        entity_id = self._seed(sync_session)

        def gone_meta(external_id):
            raise PlaylistGoneError("deezer", external_id)

        result = self._run_inner(sync_engine, monkeypatch, gone_meta, entity_id)

        assert result == {
            "deleted": True,
            "playlist_id": entity_id,
            "source": "deezer",
            "reason": "not_found_on_source",
        }
        with Session(sync_engine) as s:
            assert s.get(WatchedEntity, entity_id) is None
            assert s.execute(
                select(RadarTrack).where(RadarTrack.watched_entity_id == entity_id)
            ).first() is None
            assert s.execute(
                select(UserFollow).where(UserFollow.entity_id == entity_id)
            ).first() is None

    def test_runtime_error_mentioning_404_does_not_delete(
        self, sync_engine, sync_session, monkeypatch
    ):
        """A3-07 regression: '404'/'not found' in a message must NOT purge."""
        entity_id = self._seed(sync_session)

        def flaky_meta(external_id):
            raise RuntimeError("Deezer API returned 404 on https://api.deezer.com/x")

        with pytest.raises(RuntimeError):
            self._run_inner(sync_engine, monkeypatch, flaky_meta, entity_id)

        with Session(sync_engine) as s:
            assert s.get(WatchedEntity, entity_id) is not None
            assert s.execute(
                select(RadarTrack).where(RadarTrack.watched_entity_id == entity_id)
            ).first() is not None
