"""
Tests for A3-12 — artists.deezer_searched_at re-search window.
Covers the extracted Pass 1 helpers of workers/tasks/artists.py:
  - _artists_to_research(session, now): 30-day retry window selection
  - _link_artist_deezer(pool, artist, used_ids): stamp on completed searches
    only, never on a Deezer outage (same principle as the catalog A3-04 fix)
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from models import Artist

# Mock celery ecosystem before any worker imports (celery is not installed locally)
for _mod in ["celery", "celery.schedules", "celery.signals", "celery._state"]:
    sys.modules.setdefault(_mod, MagicMock())

# Add server paths
_SERVER = os.path.join(os.path.dirname(__file__), "../../server")
_API = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in [_SERVER, _API]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# redis and curl_cffi are not installed in the test env; async_http imports
# them at module load. Save the originals so we can restore after the import
# (same pattern as tests/api/test_enrichment_async.py).
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.async_http import DeezerHTTPError  # noqa: E402

# Restore sys.modules immediately — workers.async_http is now cached, so the
# deferred import inside _link_artist_deezer will not re-trigger redis/curl_cffi.
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

# Load artists.py directly to avoid workers.tasks.__init__ pulling all task modules
_artists_path = os.path.join(_SERVER, "workers", "tasks", "artists.py")
_spec = importlib.util.spec_from_file_location("workers.tasks.artists", _artists_path)
_artists_mod = importlib.util.module_from_spec(_spec)
sys.modules["workers.tasks.artists"] = _artists_mod
_spec.loader.exec_module(_artists_mod)

ARTIST_RESEARCH_DAYS = _artists_mod.ARTIST_RESEARCH_DAYS
_artists_to_research = _artists_mod._artists_to_research
_link_artist_deezer = _artists_mod._link_artist_deezer


def _artist(name, **kw):
    return Artist(name=name, normalized_name=name.lower(), **kw)


class TestArtistsToResearch:
    """Pass 1 selection: only unlinked artists outside the 30-day window."""

    def test_excludes_recently_searched(self, sync_session):
        now = datetime.now(timezone.utc)
        sync_session.add(
            _artist("Recent", deezer_searched_at=now - timedelta(days=10))
        )
        sync_session.commit()

        assert _artists_to_research(sync_session, now) == []

    def test_includes_searched_long_ago(self, sync_session):
        now = datetime.now(timezone.utc)
        sync_session.add(
            _artist("Stale", deezer_searched_at=now - timedelta(days=40))
        )
        sync_session.commit()

        selected = _artists_to_research(sync_session, now)
        assert [a.name for a in selected] == ["Stale"]

    def test_includes_never_searched(self, sync_session):
        now = datetime.now(timezone.utc)
        sync_session.add(_artist("Never"))
        sync_session.commit()

        selected = _artists_to_research(sync_session, now)
        assert [a.name for a in selected] == ["Never"]

    def test_excludes_already_linked(self, sync_session):
        now = datetime.now(timezone.utc)
        sync_session.add(_artist("Linked", deezer_id="123"))
        sync_session.commit()

        assert _artists_to_research(sync_session, now) == []


class TestLinkArtistDeezer:
    """deezer_searched_at is stamped by completed searches only."""

    async def test_empty_search_marks_searched(self):
        artist = _artist("Unknown DJ")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={"data": []})

        linked = await _link_artist_deezer(pool, artist, set())

        assert linked is False
        assert isinstance(artist.deezer_searched_at, datetime)
        # No match must never auto-set the NOT_FOUND sentinel (human decision)
        assert artist.deezer_id is None

    async def test_http_error_leaves_unsearched(self):
        artist = _artist("Unknown DJ")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            side_effect=DeezerHTTPError(500, "/search/artist")
        )

        linked = await _link_artist_deezer(pool, artist, set())

        assert linked is False
        assert artist.deezer_searched_at is None

    async def test_match_links_and_marks_searched(self):
        artist = _artist("Boris Brejcha")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "Boris Brejcha"}]}
        )
        used_ids = set()

        linked = await _link_artist_deezer(pool, artist, used_ids)

        assert linked is True
        assert artist.deezer_id == "42"
        assert "42" in used_ids
        assert isinstance(artist.deezer_searched_at, datetime)

    async def test_taken_id_not_linked_but_marks_searched(self):
        artist = _artist("Duplicate Name")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "Duplicate Name"}]}
        )

        linked = await _link_artist_deezer(pool, artist, {"42"})

        assert linked is False
        assert artist.deezer_id is None
        assert isinstance(artist.deezer_searched_at, datetime)
