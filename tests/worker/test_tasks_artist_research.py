"""
Tests for the artist Deezer link backlog helpers of workers/tasks/artists.py
(loop-safe refactor, mirror of the catalog E1 re-scan pattern):
  - select_link_candidates: budget cap, oldest-id-first tier 1, 30/90-day
    backoff tiers, abandonment after 3 attempts.
  - count_link_candidates: total eligible across tiers (drives dropped_by_budget).
  - _mark_link_searched: stamp + increment together.
  - _link_artist_deezer(pool, artist, holder_map, now): marks on a completed
    search only (match, no-match, or a held-id merge), never on a Deezer outage
    (an outage is not an attempt, E1 invariant / catalog A3-04). Returns a
    (status, holder_id) tuple; a match on an already-held id yields
    ("merge", holder_id) so the orchestrator folds the orphan into the holder.
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
_norm_artist_name = _artists_mod._norm_artist_name
_matching_deezer_hits = _artists_mod._matching_deezer_hits

NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(days):
    return NOW - timedelta(days=days)


def _add_artist(session, name, **kw):
    a = Artist(name=name, normalized_name=name.lower(), **kw)
    session.add(a)
    session.commit()
    return a


class TestNormArtistName:
    """The ascii fold folds diacritics for latin names but must collapse a fully
    non-ASCII name to "" — a blank fold carries no identity signal and would
    otherwise "match" any other non-latin name that also folds to blank."""

    def test_japanese_name_folds_to_empty(self):
        # U+3000 full-width space → plain space, ideographs dropped by ascii-fold
        # → "" after strip (before the .strip() fix this returned " ").
        assert _norm_artist_name("桜井　哲夫") == ""

    def test_hebrew_name_folds_to_empty(self):
        assert _norm_artist_name("נוער שוליים") == ""

    def test_whitespace_only_folds_to_empty(self):
        assert _norm_artist_name("   ") == ""

    def test_latin_name_still_folds_diacritics(self):
        # Unchanged: the accent-fold that unifies "Nick León"/"Nick Leon" homonyms.
        assert _norm_artist_name("Nick León") == "nick leon"


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

    def test_attempt3_recent_abandon_not_selected(self, sync_session):
        # >= MAX attempts but searched within the long-retry window (< 180d) →
        # dormant, not yet due for resurrection.
        _add_artist(
            sync_session, "DormantRecent",
            deezer_searched_at=_days_ago(30), deezer_search_attempts=3,
        )

        assert select_link_candidates(sync_session, 10, NOW) == []

    def test_attempt3_resurrected_after_long_retry(self, sync_session):
        # >= MAX attempts AND last searched beyond ARTIST_LONG_RETRY_DAYS (180d) →
        # resurrected (the long-term "is it on Deezer yet?" sweep), no longer
        # abandoned for good.
        a = _add_artist(
            sync_session, "Resurrect",
            deezer_searched_at=_days_ago(400), deezer_search_attempts=3,
        )

        result = select_link_candidates(sync_session, 10, NOW)
        assert [x.id for x in result] == [a.id]

    def test_resurrect_not_found_sentinel_excluded(self, sync_session):
        # A human NOT_FOUND decision keeps deezer_id non-NULL → never resurrected.
        _add_artist(
            sync_session, "AbsentForGood", deezer_id="NOT_FOUND",
            deezer_searched_at=_days_ago(400), deezer_search_attempts=3,
        )

        assert select_link_candidates(sync_session, 10, NOW) == []

    def test_resurrect_is_lowest_priority(self, sync_session):
        # With budget 1, a never-searched tier-1 artist wins over a due resurrection.
        fresh = _add_artist(sync_session, "Fresh")
        _add_artist(
            sync_session, "Resurrect",
            deezer_searched_at=_days_ago(400), deezer_search_attempts=3,
        )

        result = select_link_candidates(sync_session, 1, NOW)
        assert [a.id for a in result] == [fresh.id]


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
            sync_session, "DormantRecent",
            deezer_searched_at=_days_ago(30), deezer_search_attempts=3,
        )  # excluded: abandoned but within the long-retry window

        assert count_link_candidates(sync_session, NOW) == 3

    def test_counts_include_resurrected(self, sync_session):
        _add_artist(sync_session, "Fresh")  # tier 1
        _add_artist(
            sync_session, "Resurrect",
            deezer_searched_at=_days_ago(400), deezer_search_attempts=3,
        )  # resurrect tier (searched beyond the long-retry window)
        _add_artist(
            sync_session, "DormantRecent",
            deezer_searched_at=_days_ago(30), deezer_search_attempts=3,
        )  # excluded: not yet due

        assert count_link_candidates(sync_session, NOW) == 2


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
    """A completed search (match, no-match, or held-id merge) is marked; a Deezer
    outage is not. The helper returns a (status, holder_id) tuple; ``holder_map``
    maps every claimed deezer_id → its holder artist id."""

    def _artist(self, name):
        return Artist(name=name, normalized_name=name.lower(), deezer_search_attempts=0)

    async def test_no_match_marks_and_increments(self):
        artist = self._artist("Unknown DJ")
        pool = MagicMock()
        # HITS present but none fold-match → searched + retriable. (An EMPTY response
        # now takes the NOT_FOUND shortcut instead — see below.)
        pool.deezer_get = AsyncMock(return_value={"data": [{"id": 5, "name": "Other Name"}]})

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "searched"
        assert holder_id is None
        assert artist.deezer_id is None  # no fold-match → never links, stays NULL
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_empty_deezer_marks_not_found(self):
        # Deezer returns ZERO hits for a non-splittable name → sentinel'd NOT_FOUND.
        artist = self._artist("Raoul Konan")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={"data": []})

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "not_found"
        assert holder_id is None
        assert artist.deezer_id == "NOT_FOUND"

    async def test_splittable_empty_is_not_marked_not_found(self):
        # A splittable name whose full-string search is empty is NOT sentinel'd — it
        # belongs in the split lane, stays NULL + retriable.
        artist = self._artist("Alpha & Beta")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={"data": []})

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "searched"
        assert artist.deezer_id is None

    async def test_http_error_leaves_unsearched_and_no_increment(self):
        artist = self._artist("Flaky DJ")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(side_effect=DeezerHTTPError(500, "/search/artist"))

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "error"
        assert holder_id is None
        assert artist.deezer_searched_at is None
        assert artist.deezer_search_attempts == 0

    async def test_match_links_and_marks(self):
        artist = self._artist("Boris Brejcha")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "Boris Brejcha"}]}
        )
        holder_map = {}

        status, holder_id = await _link_artist_deezer(pool, artist, holder_map, NOW)

        assert status == "linked"
        assert holder_id is None
        assert artist.deezer_id == "42"
        assert "42" in holder_map  # freshly published so a same-run sibling merges
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_held_id_returns_merge_and_marks(self):
        """A match on an id ALREADY held by another artist row now yields a merge
        directive (status "merge" + the holder id) instead of the old silent
        "searched" no-op that left the orphan NULL to rot to `abandoned`. The
        orphan is NOT linked in place (the fold happens in the orchestrator), but
        the search is still marked."""
        artist = self._artist("Duplicate Name")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "Duplicate Name"}]}
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {"42": 999}, NOW)

        assert status == "merge"
        assert holder_id == 999  # the row that already owns deezer_id 42
        assert artist.deezer_id is None  # not linked in place — merged by the caller
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_non_ascii_name_never_matches_held_id(self):
        """A fully non-ASCII name folds to "" (no ASCII identity signal). Even when
        Deezer returns a hit whose name ALSO folds to "" and whose id is already
        HELD by another row, the helper must NOT merge (nor link) — it returns
        ("searched", None) and leaves the orphan NULL. Before the blank-fold guard
        both names folded to " " and spuriously "matched", producing a false merge
        onto a held id (invariant #4). The search is still marked."""
        artist = self._artist("桜井　哲夫")  # Japanese, U+3000 full-width space
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            # An unrelated non-latin artist whose name also folds to "".
            return_value={"data": [{"id": 42, "name": "浜崎あゆみ"}]}
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {"42": 999}, NOW)

        assert status == "searched"  # NOT "merge"
        assert holder_id is None
        assert artist.deezer_id is None  # neither linked nor merged
        assert artist.deezer_searched_at == NOW  # but the search is marked
        assert artist.deezer_search_attempts == 1

    async def test_non_ascii_exact_raw_match_merges_into_holder(self):
        """The blank-fold guard must NOT swallow the raw exact-name match: a Deezer
        hit echoing the artist's non-latin name VERBATIM is a valid identity even
        though the fold is "". On an id already HELD by another row this MUST merge
        into the holder — that is exactly how two identical-spelling non-latin rows
        (桜井　哲夫/桜井　哲夫) dedup — not fall through to a signal-less "searched"."""
        artist = self._artist("桜井　哲夫")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 42, "name": "桜井　哲夫"}]}  # verbatim
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {"42": 999}, NOW)

        assert status == "merge"  # raw exact match survives the blank fold
        assert holder_id == 999
        assert artist.deezer_id is None  # merged by the caller, not linked in place
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_non_ascii_exact_raw_match_links_free_id(self):
        """Same raw-exact-match path with a FREE id: the non-latin artist links
        (blank fold does not block an exact equality)."""
        artist = self._artist("小泉今日子")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 77, "name": "小泉今日子"}]}  # verbatim, free
        )
        holder_map = {}

        status, holder_id = await _link_artist_deezer(pool, artist, holder_map, NOW)

        assert status == "linked"
        assert holder_id is None
        assert artist.deezer_id == "77"
        assert "77" in holder_map
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_free_id_preferred_over_held_homonym(self):
        """When the top match is held but a later hit exposes a FREE id, the free
        id wins (link), preserving the old skip-taken-ids preference — the merge is
        only a fallback when no hit offers a free id."""
        artist = self._artist("Homonym")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={
                "data": [
                    {"id": 42, "name": "Homonym"},  # held
                    {"id": 43, "name": "Homonym"},  # free
                ]
            }
        )
        holder_map = {"42": 999}

        status, holder_id = await _link_artist_deezer(pool, artist, holder_map, NOW)

        assert status == "linked"
        assert artist.deezer_id == "43"
        assert "43" in holder_map  # the free id, not the held "42", was published


class TestMatchingDeezerHitsL3:
    """The shared matcher (_matching_deezer_hits) — the pure heart of BOTH the
    nightly link matcher and sync_artists Phase B. Adds the punctuation fold + the
    most-fanned ordering (L3), on top of the pre-L3 raw-exact / accent-fold signals
    and the blank-fold non-latin guard."""

    def test_punct_fold_matches_and_orders_by_fans(self):
        # "St. Germain" (ours) punct-folds to "St Germain" (dots dropped): the fold
        # match fires and the 70k-fan hit is returned first. "St.Germain" (no space)
        # folds to "stgermain" ≠ "st germain" → not a match at all.
        hits = [
            {"id": 11, "name": "St.Germain", "nb_fan": 12},
            {"id": 10, "name": "St Germain", "nb_fan": 70000},
        ]
        matched = _matching_deezer_hits(hits, "St. Germain")
        assert [h["id"] for h in matched] == [10]

    def test_most_fanned_exact_homonym_first(self):
        # Two EXACT homonyms → the most-fanned one leads (not Deezer's first hit).
        hits = [
            {"id": 30, "name": "Homonym Star", "nb_fan": 5},
            {"id": 31, "name": "Homonym Star", "nb_fan": 90000},
        ]
        matched = _matching_deezer_hits(hits, "Homonym Star")
        assert [h["id"] for h in matched] == [31, 30]

    def test_acronym_never_fold_matches_word(self):
        # "L.I.L.Y" reads as initials → the punct fold ("lily") is a false friend
        # for the unrelated word "Lily"; the acronym guard refuses it. No exact, no
        # accent-fold either → zero matches.
        assert _matching_deezer_hits([{"id": 40, "name": "Lily", "nb_fan": 500000}], "L.I.L.Y") == []

    def test_punct_fold_below_fan_floor_refused(self):
        # "Mr. Oizo" punct-folds to "Mr Oizo", but a 12-fan Deezer entry is a
        # parasite: below FAN_FLOOR the fold signal is refused.
        assert _matching_deezer_hits([{"id": 60, "name": "Mr Oizo", "nb_fan": 12}], "Mr. Oizo") == []

    def test_punct_fold_above_fan_floor_matches(self):
        # Same fold, this time a real artist (above the floor) → matches.
        matched = _matching_deezer_hits(
            [{"id": 61, "name": "Mr Oizo", "nb_fan": 5000}], "Mr. Oizo"
        )
        assert [h["id"] for h in matched] == [61]

    def test_exact_match_ignores_fan_floor(self):
        # A raw exact match is a valid identity regardless of fan count: a 3-fan
        # exact hit still matches (the floor gates ONLY the weak punctuation fold).
        matched = _matching_deezer_hits(
            [{"id": 70, "name": "Tiny Exact", "nb_fan": 3}], "Tiny Exact"
        )
        assert [h["id"] for h in matched] == [70]

    def test_no_fan_data_preserves_deezer_order(self):
        # Retro-compat: with no fan signal the stable sort keeps Deezer's order, so
        # the pre-L3 "first hit" pick is unchanged.
        hits = [
            {"id": 80, "name": "Dup Name"},
            {"id": 81, "name": "Dup Name"},
        ]
        matched = _matching_deezer_hits(hits, "Dup Name")
        assert [h["id"] for h in matched] == [80, 81]

    def test_non_ascii_blank_fold_never_matches(self):
        # A fully non-ASCII name folds to "" for BOTH the accent fold and the punct
        # key; an unrelated non-latin hit (also blank-folding) must NOT match.
        assert _matching_deezer_hits([{"id": 90, "name": "浜崎あゆみ"}], "桜井　哲夫") == []

    def test_non_ascii_exact_still_matches(self):
        # …but a verbatim non-latin echo is a valid identity and still matches.
        matched = _matching_deezer_hits([{"id": 91, "name": "桜井　哲夫"}], "桜井　哲夫")
        assert [h["id"] for h in matched] == [91]


class TestLinkArtistDeezerL3:
    """The L3 signals wired through the nightly matcher _link_artist_deezer:
    punctuation fold + most-fanned preference, with the free-id/merge semantics
    and the marking contract preserved."""

    def _artist(self, name):
        return Artist(name=name, normalized_name=name.lower(), deezer_search_attempts=0)

    async def test_punct_fold_links_most_fanned(self):
        # "St. Germain" fold-matches "St Germain" (70k fans) and links it; the
        # 12-fan "St.Germain" parasite is never chosen.
        artist = self._artist("St. Germain")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={
                "data": [
                    {"id": 11, "name": "St.Germain", "nb_fan": 12},
                    {"id": 10, "name": "St Germain", "nb_fan": 70000},
                ]
            }
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "linked"
        assert artist.deezer_id == "10"
        assert artist.deezer_searched_at == NOW
        assert artist.deezer_search_attempts == 1

    async def test_most_fanned_exact_homonym_linked(self):
        artist = self._artist("Homonym Star")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={
                "data": [
                    {"id": 30, "name": "Homonym Star", "nb_fan": 5},
                    {"id": 31, "name": "Homonym Star", "nb_fan": 90000},
                ]
            }
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "linked"
        assert artist.deezer_id == "31"  # 90k fans beats Deezer's first (5-fan) hit

    async def test_acronym_not_fold_matched_marks_only(self):
        artist = self._artist("L.I.L.Y")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 40, "name": "Lily", "nb_fan": 500000}]}
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "searched"  # acronym guard blocks the punct fold
        assert artist.deezer_id is None
        assert artist.deezer_searched_at == NOW  # completed no-match search is marked
        assert artist.deezer_search_attempts == 1

    async def test_exact_match_no_fan_data_unchanged(self):
        # Retro-compat: a lone exact match with no fan field links exactly as before.
        artist = self._artist("Boris Brejcha")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 50, "name": "Boris Brejcha"}]}
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "linked"
        assert artist.deezer_id == "50"

    async def test_punct_fold_below_floor_refused(self):
        artist = self._artist("Mr. Oizo")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"data": [{"id": 60, "name": "Mr Oizo", "nb_fan": 12}]}
        )

        status, holder_id = await _link_artist_deezer(pool, artist, {}, NOW)

        assert status == "searched"  # below FAN_FLOOR → not a match
        assert artist.deezer_id is None
        assert artist.deezer_search_attempts == 1

    async def test_fan_preference_still_prefers_free_id(self):
        # Fan ordering does NOT override the free-id-over-merge rule: the top-fanned
        # hit is HELD, a lower-fanned homonym is FREE → link the free one (merge is
        # only a fallback when no hit exposes a free id).
        artist = self._artist("Collab Star")
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={
                "data": [
                    {"id": 42, "name": "Collab Star", "nb_fan": 90000},  # held
                    {"id": 43, "name": "Collab Star", "nb_fan": 100},  # free
                ]
            }
        )
        holder_map = {"42": 999}

        status, holder_id = await _link_artist_deezer(pool, artist, holder_map, NOW)

        assert status == "linked"
        assert artist.deezer_id == "43"
        assert "43" in holder_map
