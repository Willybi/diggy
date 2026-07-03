"""Tests for services/similarity_service.py."""

from datetime import date

import pytest

from services.similarity_service import (
    CFG,
    _expand_genre_nodes,
    parse_camelot,
    sim_bpm,
    sim_cooc,
    sim_era,
    sim_genre,
    sim_key,
    sim_label,
)


# ---------------------------------------------------------------------------
# parse_camelot
# ---------------------------------------------------------------------------


class TestParseCamelot:
    def test_valid_key(self):
        assert parse_camelot("8A") == (8, "A")

    def test_valid_key_lowercase(self):
        assert parse_camelot("8a") == (8, "A")

    def test_double_digit(self):
        assert parse_camelot("12B") == (12, "B")

    def test_single_digit(self):
        assert parse_camelot("1A") == (1, "A")

    def test_none(self):
        assert parse_camelot(None) is None

    def test_empty(self):
        assert parse_camelot("") is None

    def test_invalid_number(self):
        assert parse_camelot("13A") is None
        assert parse_camelot("0B") is None

    def test_invalid_format(self):
        assert parse_camelot("Am") is None
        assert parse_camelot("Cmaj") is None


# ---------------------------------------------------------------------------
# sim_bpm
# ---------------------------------------------------------------------------


class TestSimBpm:
    def test_identical(self):
        assert sim_bpm(128.0, 128.0) == 1.0

    def test_close_3bpm(self):
        score = sim_bpm(128.0, 131.0)
        assert 0.75 < score < 0.85

    def test_medium_8bpm(self):
        score = sim_bpm(128.0, 136.0)
        assert 0.4 < score < 0.6

    def test_far_15bpm(self):
        assert sim_bpm(128.0, 143.0) == 0.0

    def test_beyond_max(self):
        assert sim_bpm(128.0, 160.0) == 0.0

    def test_half_time(self):
        # 130 vs 65: half-time match
        score = sim_bpm(130.0, 65.0)
        assert score > 0.8
        # Penalty applied
        assert score <= CFG.HALF_DOUBLE_PENALTY

    def test_double_time(self):
        score = sim_bpm(65.0, 130.0)
        assert score > 0.8
        assert score <= CFG.HALF_DOUBLE_PENALTY

    def test_half_time_with_offset(self):
        # 130 vs 67: half-time with 2 BPM offset
        score = sim_bpm(130.0, 67.0)
        assert score > 0.6


# ---------------------------------------------------------------------------
# sim_key
# ---------------------------------------------------------------------------


class TestSimKey:
    def test_same_key(self):
        assert sim_key("8A", "8A") == 1.0

    def test_relative_major_minor(self):
        assert sim_key("8A", "8B") == 0.9

    def test_neighbor_plus1(self):
        assert sim_key("8A", "9A") == 0.8

    def test_neighbor_minus1(self):
        assert sim_key("8A", "7A") == 0.8

    def test_circular_12_to_1(self):
        assert sim_key("12A", "1A") == 0.8

    def test_circular_1_to_12(self):
        assert sim_key("1A", "12A") == 0.8

    def test_energy_boost(self):
        assert sim_key("6A", "8A") == 0.5

    def test_energy_boost_circular(self):
        assert sim_key("11A", "1A") == 0.5

    def test_diagonal(self):
        assert sim_key("7B", "8A") == 0.4

    def test_diagonal_circular(self):
        assert sim_key("12B", "1A") == 0.4

    def test_far_apart(self):
        assert sim_key("1A", "6A") == 0.0

    def test_none_key(self):
        assert sim_key("8A", "") == 0.0

    def test_invalid_key(self):
        assert sim_key("8A", "Cmaj") == 0.0


# ---------------------------------------------------------------------------
# sim_genre
# ---------------------------------------------------------------------------


class TestSimGenre:
    def test_identical(self):
        a = {1: 1.0, 2: 1.0}
        assert sim_genre(a, a) == 1.0

    def test_disjoint(self):
        assert sim_genre({1: 1.0}, {2: 1.0}) == 0.0

    def test_partial_overlap(self):
        a = {1: 1.0, 2: 1.0}
        b = {2: 1.0, 3: 1.0}
        # intersection = min(1,1) for key 2 = 1
        # union = max(1,0)+max(1,1)+max(0,1) = 1+1+1 = 3
        assert abs(sim_genre(a, b) - 1 / 3) < 0.01

    def test_weighted_parent(self):
        # a has node 1 (direct) + node 10 (parent, 0.5)
        # b has node 2 (direct) + node 10 (parent, 0.5)
        a = {1: 1.0, 10: 0.5}
        b = {2: 1.0, 10: 0.5}
        score = sim_genre(a, b)
        assert score > 0.0
        # min(0.5,0.5)=0.5 / (1+0.5+1) = 0.5/2.5 = 0.2
        assert abs(score - 0.2) < 0.01

    def test_empty_a(self):
        assert sim_genre({}, {1: 1.0}) == 0.0

    def test_empty_b(self):
        assert sim_genre({1: 1.0}, {}) == 0.0

    def test_both_empty(self):
        assert sim_genre({}, {}) == 0.0


class TestExpandGenreNodes:
    def test_basic_resolution(self):
        name_to_node = {"Tech House": 1, "Deep House": 2}
        parent_map = {1: {10}, 2: {10}}  # both children of House (10)
        result = _expand_genre_nodes(["Tech House"], name_to_node, parent_map)
        assert result == {1: 1.0, 10: 0.5}

    def test_unknown_genre_skipped(self):
        result = _expand_genre_nodes(["Unknown"], {}, {})
        assert result == {}

    def test_no_parent(self):
        name_to_node = {"Ambient": 5}
        result = _expand_genre_nodes(["Ambient"], name_to_node, {})
        assert result == {5: 1.0}

    def test_direct_overrides_parent(self):
        # If a genre IS a parent of another genre in the same track,
        # direct weight (1.0) should win over parent weight (0.5)
        name_to_node = {"Tech House": 1, "House": 10}
        parent_map = {1: {10}}
        result = _expand_genre_nodes(["Tech House", "House"], name_to_node, parent_map)
        assert result[10] == 1.0  # direct, not 0.5


# ---------------------------------------------------------------------------
# sim_cooc
# ---------------------------------------------------------------------------


class TestSimCooc:
    def test_identical(self):
        a = frozenset([1, 2, 3])
        assert sim_cooc(a, a) == 1.0

    def test_no_overlap(self):
        assert sim_cooc(frozenset([1, 2]), frozenset([3, 4])) == 0.0

    def test_partial_overlap(self):
        # |{1,2} ∩ {2,3}| = 1, |{1,2} ∪ {2,3}| = 3 → 1/3
        score = sim_cooc(frozenset([1, 2]), frozenset([2, 3]))
        assert abs(score - 1 / 3) < 0.001

    def test_single_shared(self):
        # Jaccard = 1/1 = 1.0 quand les deux ont exactement 1 playlist commune
        assert sim_cooc(frozenset([5]), frozenset([5])) == 1.0

    def test_empty_a(self):
        assert sim_cooc(frozenset(), frozenset([1])) == 0.0

    def test_empty_b(self):
        assert sim_cooc(frozenset([1]), frozenset()) == 0.0

    def test_both_empty(self):
        assert sim_cooc(frozenset(), frozenset()) == 0.0


# ---------------------------------------------------------------------------
# sim_label
# ---------------------------------------------------------------------------


class TestSimLabel:
    def test_exact_match(self):
        assert sim_label("Drumcode", "Drumcode") == 1.0

    def test_case_insensitive(self):
        assert sim_label("drumcode", "Drumcode") == 1.0

    def test_whitespace(self):
        assert sim_label("  Drumcode ", "Drumcode") == 1.0

    def test_different(self):
        assert sim_label("Drumcode", "Toolroom") == 0.0


# ---------------------------------------------------------------------------
# sim_era
# ---------------------------------------------------------------------------


class TestSimEra:
    def test_same_year(self):
        assert sim_era(date(2023, 6, 1), date(2023, 1, 1)) == 1.0

    def test_one_year_diff(self):
        assert sim_era(date(2023, 1, 1), date(2024, 1, 1)) == 1.0

    def test_five_year_diff(self):
        score = sim_era(date(2020, 1, 1), date(2025, 1, 1))
        # diff=5, score = 1 - (5-1)/9 = 1 - 4/9 ≈ 0.556
        assert abs(score - 0.556) < 0.01

    def test_ten_year_diff(self):
        assert sim_era(date(2015, 1, 1), date(2025, 1, 1)) == 0.0

    def test_beyond_ten_years(self):
        assert sim_era(date(2010, 1, 1), date(2025, 1, 1)) == 0.0


# ---------------------------------------------------------------------------
# Integration: get_similar_tracks
# ---------------------------------------------------------------------------


class TestGetSimilarTracks:
    async def _create_tracks(self, db, tracks):
        from models import CatalogEntry

        entries = []
        for i, data in enumerate(tracks):
            entry = CatalogEntry(
                title=data.get("title", f"Track {i}"),
                artist=data.get("artist", "Artist"),
                normalized_key=data.get("normalized_key", f"artist|track{i}"),
                bpm=data.get("bpm"),
                key=data.get("key"),
                label=data.get("label"),
                release_date=data.get("release_date"),
                genres=data.get("genres", []),
            )
            db.add(entry)
            entries.append(entry)
        await db.commit()
        for e in entries:
            await db.refresh(e)
        return entries

    async def test_raises_for_missing_catalog_id(self, db):
        from services import similarity_service

        with pytest.raises(LookupError):
            await similarity_service.get_similar_tracks(db, 999999)

    async def test_empty_when_no_candidates(self, db):
        from services import similarity_service

        entries = await self._create_tracks(db, [
            {"bpm": 128.0, "key": "8A"},
        ])
        result = await similarity_service.get_similar_tracks(db, entries[0].id, min_score=0.0)
        assert result == []

    async def test_returns_similar_tracks(self, db):
        from services import similarity_service

        entries = await self._create_tracks(db, [
            {"title": "Ref", "bpm": 128.0, "key": "8A", "normalized_key": "a|ref"},
            {"title": "Close", "bpm": 129.0, "key": "8A", "normalized_key": "a|close"},
            {"title": "Far", "bpm": 80.0, "key": "3B", "normalized_key": "a|far"},
        ])
        result = await similarity_service.get_similar_tracks(
            db, entries[0].id, min_score=0.0,
        )
        assert len(result) >= 1
        assert result[0]["title"] == "Close"
        assert "similarity" in result[0]
        assert result[0]["similarity"]["score"] > 0

    async def test_similarity_block_structure(self, db):
        from services import similarity_service

        entries = await self._create_tracks(db, [
            {"title": "A", "bpm": 128.0, "key": "8A", "normalized_key": "a|a"},
            {"title": "B", "bpm": 128.0, "key": "8A", "normalized_key": "a|b"},
        ])
        result = await similarity_service.get_similar_tracks(
            db, entries[0].id, min_score=0.0,
        )
        assert len(result) == 1
        sim = result[0]["similarity"]
        assert "score" in sim
        assert "components" in sim
        assert "available_features" in sim
        assert "bpm" in sim["available_features"]
        assert "key" in sim["available_features"]

    async def test_min_score_filter(self, db):
        from services import similarity_service

        entries = await self._create_tracks(db, [
            {"title": "Ref", "bpm": 128.0, "key": "8A", "normalized_key": "a|ref2"},
            {"title": "Different", "bpm": 140.0, "key": "3B", "normalized_key": "a|diff"},
        ])
        result = await similarity_service.get_similar_tracks(
            db, entries[0].id, min_score=0.9,
        )
        assert len(result) == 0

    async def test_limit_respected(self, db):
        from services import similarity_service

        tracks = [{"title": "Ref", "bpm": 128.0, "key": "8A", "normalized_key": "a|reflim"}]
        for i in range(5):
            tracks.append({"title": f"T{i}", "bpm": 128.0 + i, "key": "8A", "normalized_key": f"a|t{i}lim"})
        entries = await self._create_tracks(db, tracks)
        result = await similarity_service.get_similar_tracks(
            db, entries[0].id, limit=2, min_score=0.0,
        )
        assert len(result) == 2

    async def test_min_features_required(self, db):
        from services import similarity_service

        # Tracks with only BPM (1 feature) should be excluded (min 2 required)
        entries = await self._create_tracks(db, [
            {"title": "Ref", "bpm": 128.0, "normalized_key": "a|refmin"},
            {"title": "One", "bpm": 128.0, "normalized_key": "a|onemin"},
        ])
        result = await similarity_service.get_similar_tracks(
            db, entries[0].id, min_score=0.0,
        )
        assert len(result) == 0

    async def test_in_lib_filter(self, db, auth_user):
        from models import UserTrack
        from services import similarity_service

        entries = await self._create_tracks(db, [
            {"title": "Ref", "bpm": 128.0, "key": "8A", "normalized_key": "a|reflib"},
            {"title": "InLib", "bpm": 129.0, "key": "8A", "normalized_key": "a|inlib"},
            {"title": "NotInLib", "bpm": 129.0, "key": "8A", "normalized_key": "a|notinlib"},
        ])
        # Add "InLib" to user library
        db.add(UserTrack(user_id=auth_user.id, catalog_id=entries[1].id))
        await db.commit()

        result = await similarity_service.get_similar_tracks(
            db, entries[0].id, auth_user.id, min_score=0.0, in_lib=True,
        )
        assert len(result) == 1
        assert result[0]["title"] == "InLib"
