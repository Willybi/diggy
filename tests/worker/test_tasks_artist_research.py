"""
Tests for the artist Deezer link backlog helpers of workers/tasks/artists.py
(loop-safe refactor, mirror of the catalog E1 re-scan pattern):
  - select_link_candidates: budget cap, oldest-id-first tier 1, 30/90-day
    backoff tiers, abandonment after 3 attempts.
  - count_link_candidates: total eligible across tiers (drives dropped_by_budget).
  - _mark_link_searched: stamp + increment together.
  - _link_artist_deezer(pool, artist, used_ids, now): marks on a completed
    search only (match or no-match), never on a Deezer outage (an outage is not
    an attempt, E1 invariant / catalog A3-04).
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

select_link_candidates = _artists_mod.select_link_candidates
count_link_candidates = _artists_mod.count_link_candidates
_mark_link_searched = _artists_mod._mark_link_searched
_link_artist_deezer = _artists_mod._link_artist_deezer

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(days):
    return NOW - timedelta(days=days)


def _add_artist(session, name, **kw):
    a = Artist(name=name, normalized_name=name.lower(), **kw)
    session.add(a)
    session.commit()
    return a


class TestSelectLinkCandidatesTiers:
    def test_never_searched_selected_oldest_first(self, sync_session):
        first = _add_artist(sync_session, "Alpha")
        second = _add_artist(sync_session, "Beta")

        result = select_link_candidates(sync_session, 10, NOW)

        # OLDEST id first so the backlog tail is not starved by new artists
        assert [a.id for a in result] == [first.id, second.id]

    def test_linked_artist_never_selected(self, sync_session):
        _add_artist(sync_session, "Linked", deezer_id="123")

        assert select_link_candidates(sync_session, 10, NOW) == []

    def test_not_found_sentinel_excluded(self, sync_session):
        # NOT_FOUND keeps deezer_id non-NULL → excluded (human decision)
        _add_artist(sync_session, "Absent", deezer_id="NOT_FOUND")

        assert select_link_candidates(sync_session, 10, NOW) == []

    def test_attempt1_within_30_days_excluded(self, sync_session):
        _add_artist(
            sync_session, "Recent",
            deezer_searched_at=_days_ago(20), deezer_search_attempts=1,
        )

        assert select_link_candidates(sync_session, 10, NOW) == []

    def test_attempt1_after_30_days_included(self, sync_session):
        a = _add_artist(
            sync_session, "Stale",
            deezer_searched_at=_days_ago(40), deezer_search_attempts=1,
        )

        result = select_link_candidates(sync_session, 10, NOW)
        assert [x.id for x in result] == [a.id]

    def test_attempt2_within_90_days_excluded(self, sync_session):
        _add_artist(
            sync_session, "Mid",
            deezer_searched_at=_days_ago(40), deezer_search_attempts=2,
        )

        assert select_link_candidates(sync_session, 10, NOW) == []

    def test_attempt2_after_90_days_included(self, sync_session):
        a = _add_artist(
            sync_session, "VeryStale",
            deezer_searched_at=_days_ago(100), deezer_search_attempts=2,
        )

        result = select_link_candidates(sync_session, 10, NOW)
        assert [x.id for x in result] == [a.id]

    def test_attempt3_abandoned_forever(self, sync_session):
        _add_artist(
            sync_session, "Abandoned",
            deezer_searched_at=_days_ago(400), deezer_search_attempts=3,
        )

        assert select_link_candidates(sync_session, 10, NOW) == []


class TestSelectLinkCandidatesBudget:
    def test_budget_caps_tier1_oldest_first(self, sync_session):
        a1 = _add_artist(sync_session, "One")
        a2 = _add_artist(sync_session, "Two")
        _add_artist(sync_session, "Three")

        result = select_link_candidates(sync_session, 2, NOW)

        assert [a.id for a in result] == [a1.id, a2.id]

    def test_retries_only_consume_leftover_budget(self, sync_session):
        oldest_retry = _add_artist(
            sync_session, "OldRetry",
            deezer_searched_at=_days_ago(60), deezer_search_attempts=1,
        )
        _add_artist(
            sync_session, "NewerRetry",
            deezer_searched_at=_days_ago(40), deezer_search_attempts=1,
        )
        fresh = [_add_artist(sync_session, f"Fresh{n}") for n in range(3)]

        result = select_link_candidates(sync_session, 4, NOW)

        # tier 1 first (oldest ids), then the single leftover slot goes to the
        # oldest-searched retry
        assert len(result) == 4
        assert [a.id for a in result[:3]] == [a.id for a in fresh]
        assert result[3].id == oldest_retry.id

    def test_budget_exhausted_by_tier1_skips_retries(self, sync_session):
        _add_artist(
            sync_session, "Retry",
            deezer_searched_at=_days_ago(60), deezer_search_attempts=1,
        )
        fresh = [_add_artist(sync_session, f"F{n}") for n in range(2)]

        result = select_link_candidates(sync_session, 2, NOW)

        assert [a.id for a in result] == [a.id for a in fresh]

    def test_zero_budget_selects_nothing(self, sync_session):
        _add_artist(sync_session, "One")

        assert select_link_candidates(sync_session, 0, NOW) == []


class TestCountLinkCandidates:
    def test_counts_all_tiers(self, sync_session):
        _add_artist(sync_session, "Fresh")  # tier 1
        _add_artist(
            sync_session, "Retry2",
            deezer_searched_at=_days_ago(40), deezer_search_attempts=1,
        )  # tier 2
        _add_artist(
            sync_session, "Retry3",
            deezer_searched_at=_days_ago(100), deezer_search_attempts=2,
        )  # tier 3
        _add_artist(sync_session, "Linked", deezer_id="9")  # excluded
        _add_artist(
            sync_session, "Abandoned",
            deezer_searched_at=_days_ago(400), deezer_search_attempts=3,
        )  # excluded

        assert count_link_candidates(sync_session, NOW) == 3


class TestMarkLinkSearched:
    def test_sets_timestamp_and_increments(self):
        artist = Artist(name="x", normalized_name="x", deezer_search_attempts=1)

        _mark_link_searched(artist, NOW)

        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 2

    def test_none_attempts_becomes_one(self):
        artist = Artist(name="x", normalized_name="x")
        artist.deezer_search_attempts = None

        _mark_link_searched(artist, NOW)

        assert artist.deezer_search_attempts == 1


class TestLinkArtistDeezer:
    """A completed search (match or no-match) is marked; a Deezer outage is not."""

    def _artist(self, name):
        return Artist(name=name, normalized_name=name.lower(), deezer_search_attempts=0)

    async def test_no_match_marks_and_increments(self):
        artist = self._artist("Unknown DJ")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={"data": []})

        status = await _link_artist_deezer(pool, artist, set(), NOW)

        assert status == "searched"
        assert artist.deezer_id is None  # no-match must never set NOT_FOUND
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_http_error_leaves_unsearched_and_no_increment(self):
        artist = self._artist("Flaky DJ")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(side_effect=DeezerHTTPError(500, "/search/artist"))

        status = await _link_artist_deezer(pool, artist, set(), NOW)

        assert status == "error"
        assert artist.deezer_searched_at is None
        assert artist.deezer_search_attempts == 0

    async def test_match_links_and_marks(self):
        artist = self._artist("Boris Brejcha")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "Boris Brejcha"}]}
        )
        used_ids = set()

        status = await _link_artist_deezer(pool, artist, used_ids, NOW)

        assert status == "linked"
        assert artist.deezer_id == "42"
        assert "42" in used_ids
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_taken_id_not_linked_but_marks(self):
        artist = self._artist("Duplicate Name")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "Duplicate Name"}]}
        )

        status = await _link_artist_deezer(pool, artist, {"42"}, NOW)

        assert status == "searched"
        assert artist.deezer_id is None
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1
