"""Tests for the E1 re-scan selection and attempt accounting in workers/enrichment.

select_enrich_candidates picks entries per tier (never searched first, then
30-day and 90-day backoff retries) under a global budget; not_recently_searched
guards inline enrichment (sets/radar) against re-searching entries the nightly
sweep just covered; _mark_searched increments the attempt counters.
Uses a real sync SQLite session (sync_session fixture) so the tier queries
actually execute.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

# Path so the workers package is importable (same pattern as test_beatport_lock.py)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis and curl_cffi are not installed in the test env; enrichment.py and
# async_http.py import them at module load. Same save/restore dance as
# tests/api/test_enrichment_async.py to avoid polluting other test files.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.enrichment as enrichment_mod  # noqa: E402
from workers.enrichment import (  # noqa: E402
    _mark_searched,
    not_recently_searched,
    select_enrich_candidates,
)

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

from models import CatalogEntry  # noqa: E402

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(days):
    return NOW - timedelta(days=days)


def _make_row(session, n, **overrides):
    entry = CatalogEntry(
        title=f"Track {n}",
        artist="Artist",
        normalized_key=f"track {n} - artist",
        **overrides,
    )
    session.add(entry)
    session.commit()
    return entry


class TestSelectEnrichCandidatesTiers:
    def test_never_searched_selected_newest_first(self, sync_session):
        older = _make_row(sync_session, 1)
        newer = _make_row(sync_session, 2)

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert [e.id for e in result] == [newer.id, older.id]

    def test_attempt1_within_30_days_excluded(self, sync_session):
        _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(20),
            deezer_search_attempts=1,
        )

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert result == []

    def test_attempt1_after_30_days_included(self, sync_session):
        entry = _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(40),
            deezer_search_attempts=1,
        )

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert [e.id for e in result] == [entry.id]

    def test_attempt2_within_90_days_excluded(self, sync_session):
        _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(40),
            deezer_search_attempts=2,
        )

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert result == []

    def test_attempt2_after_90_days_included(self, sync_session):
        entry = _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(100),
            deezer_search_attempts=2,
        )

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert [e.id for e in result] == [entry.id]

    def test_attempt3_abandoned_forever(self, sync_session):
        _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(400),
            deezer_search_attempts=3,
        )

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert result == []

    def test_entries_with_id_never_selected(self, sync_session):
        _make_row(sync_session, 1, deezer_id="123")

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=10, now=NOW
        )

        assert result == []

    def test_beatport_uses_beatport_columns(self, sync_session):
        retry = _make_row(
            sync_session,
            1,
            beatport_searched_at=_days_ago(40),
            beatport_search_attempts=1,
            # Deezer state must not leak into the beatport selection
            deezer_id="123",
            deezer_searched_at=_days_ago(1),
            deezer_search_attempts=3,
        )
        _make_row(sync_session, 2, beatport_id="456")

        result = select_enrich_candidates(
            sync_session, source="beatport", budget=10, now=NOW
        )

        assert [e.id for e in result] == [retry.id]

    def test_unknown_source_raises(self, sync_session):
        with pytest.raises(ValueError):
            select_enrich_candidates(
                sync_session, source="spotify", budget=10, now=NOW
            )


class TestSelectEnrichCandidatesBudget:
    def test_budget_caps_tier1_newest_first(self, sync_session):
        rows = [_make_row(sync_session, n) for n in range(3)]

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=2, now=NOW
        )

        assert [e.id for e in result] == [rows[2].id, rows[1].id]

    def test_retries_only_consume_leftover_budget(self, sync_session):
        oldest_retry = _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(60),
            deezer_search_attempts=1,
        )
        _make_row(
            sync_session,
            2,
            deezer_searched_at=_days_ago(40),
            deezer_search_attempts=1,
        )
        fresh = [_make_row(sync_session, n) for n in range(3, 6)]

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=4, now=NOW
        )

        # Tier 1 first (newest ids), then the single leftover slot goes to
        # the oldest-searched retry
        assert len(result) == 4
        assert [e.id for e in result[:3]] == [e.id for e in reversed(fresh)]
        assert result[3].id == oldest_retry.id

    def test_budget_exhausted_by_tier1_skips_retries(self, sync_session):
        _make_row(
            sync_session,
            1,
            deezer_searched_at=_days_ago(60),
            deezer_search_attempts=1,
        )
        fresh = [_make_row(sync_session, n) for n in range(2, 4)]

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=2, now=NOW
        )

        assert [e.id for e in result] == [e.id for e in reversed(fresh)]

    def test_zero_budget_selects_nothing(self, sync_session):
        _make_row(sync_session, 1)

        result = select_enrich_candidates(
            sync_session, source="deezer", budget=0, now=NOW
        )

        assert result == []


class TestSelectEnrichCandidatesGenreOnly:
    """A3-01: genre_only=True targets rows with NO genre (relaxing the
    id-missing tier guard so a row that already carries a beatport_id but no
    genre is still picked); genre_only=False is the unchanged id-missing path.
    Backs the admin 'auto-classifier' button, which dispatches the task with
    kwargs={'genre_only': True}."""

    def test_genre_only_returns_only_empty_genre_rows(self, sync_session):
        empty = _make_row(sync_session, 1)  # genres default to []
        _make_row(sync_session, 2, genres=["House"])  # classified → excluded

        result = select_enrich_candidates(
            sync_session, source="beatport", budget=10, now=NOW, genre_only=True
        )

        assert [e.id for e in result] == [empty.id]

    def test_genre_only_relaxes_id_guard(self, sync_session):
        # A row already carrying a beatport_id but with no genre IS a candidate
        # under genre_only (the id guard is relaxed to empty-genres)...
        linked_no_genre = _make_row(sync_session, 1, beatport_id="456")

        assert [
            e.id
            for e in select_enrich_candidates(
                sync_session, source="beatport", budget=10, now=NOW, genre_only=True
            )
        ] == [linked_no_genre.id]

        # ...but NOT under the default id-missing selection (unchanged path).
        assert (
            select_enrich_candidates(
                sync_session, source="beatport", budget=10, now=NOW
            )
            == []
        )

    def test_default_path_ignores_genres(self, sync_session):
        # genre_only=False is strictly unchanged: a classified row still missing
        # an id is selected (genres are irrelevant to the default path).
        classified_missing_id = _make_row(sync_session, 1, genres=["Techno"])

        result = select_enrich_candidates(
            sync_session, source="beatport", budget=10, now=NOW
        )

        assert [e.id for e in result] == [classified_missing_id.id]


class TestNotRecentlySearched:
    """E1: inline enrichment (sets/radar) must skip entries the nightly sweep
    searched within the last 24h — same clause as the dz_entries/bp_entries
    selections in tasks/sets.py and tasks/radar.py."""

    def _select(self, session):
        return (
            session.execute(
                select(CatalogEntry).where(
                    CatalogEntry.deezer_id.is_(None),
                    not_recently_searched(CatalogEntry.deezer_searched_at, NOW),
                )
            )
            .scalars()
            .all()
        )

    def test_searched_1h_ago_excluded(self, sync_session):
        _make_row(sync_session, 1, deezer_searched_at=NOW - timedelta(hours=1))

        assert self._select(sync_session) == []

    def test_searched_48h_ago_included(self, sync_session):
        entry = _make_row(
            sync_session, 1, deezer_searched_at=NOW - timedelta(hours=48)
        )

        assert [e.id for e in self._select(sync_session)] == [entry.id]

    def test_never_searched_included(self, sync_session):
        entry = _make_row(sync_session, 1)

        assert [e.id for e in self._select(sync_session)] == [entry.id]


class TestMarkSearched:
    def test_deezer_sets_timestamp_and_increments(self):
        entry = MagicMock(deezer_searched_at=None, deezer_search_attempts=1)

        _mark_searched(entry, "deezer", NOW)

        assert entry.deezer_searched_at == NOW
        assert entry.deezer_search_attempts == 2

    def test_beatport_none_attempts_becomes_one(self):
        # Legacy rows created before the 0033 backfill may carry NULL
        entry = MagicMock(beatport_searched_at=None, beatport_search_attempts=None)

        _mark_searched(entry, "beatport", NOW)

        assert entry.beatport_searched_at == NOW
        assert entry.beatport_search_attempts == 1


class TestBeatportBatchAttempts:
    """enrich_beatport_batch marks + increments on a completed search, and
    leaves the entry untouched on an exception (an outage is not an attempt)."""

    def _entry(self):
        entry = MagicMock()
        entry.id = 1
        entry.title = "Track"
        entry.artist = "Artist"
        entry.isrc = None
        entry.beatport_searched_at = None
        entry.beatport_search_attempts = 0
        return entry

    async def test_not_found_marks_and_increments(self, monkeypatch):
        monkeypatch.setattr(
            enrichment_mod, "_search_beatport_async", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)
        entry = self._entry()

        stats = await enrichment_mod.enrich_beatport_batch(
            None, [entry], MagicMock(), None
        )

        assert stats == {"enriched": 0, "not_found": 1, "errors": 0, "merged": 0}
        assert isinstance(entry.beatport_searched_at, datetime)
        assert entry.beatport_search_attempts == 1

    async def test_error_leaves_unsearched_and_no_increment(self, monkeypatch):
        monkeypatch.setattr(
            enrichment_mod,
            "_search_beatport_async",
            AsyncMock(side_effect=RuntimeError("scrape failed")),
        )
        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)
        entry = self._entry()

        stats = await enrichment_mod.enrich_beatport_batch(
            None, [entry], MagicMock(), None
        )

        assert stats == {"enriched": 0, "not_found": 0, "errors": 1, "merged": 0}
        assert entry.beatport_searched_at is None
        assert entry.beatport_search_attempts == 0
