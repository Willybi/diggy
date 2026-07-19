"""Tests for services/genre_service.py — pure logic + DB."""
import pytest

from services.genre_service import (
    ALL_PILLARS,
    _pillar_genre_names,
    aggregate_top_genres,
    genre_pillar,
    lookup_deezer_genres,
    pillar_map,
)


class TestPillars:
    def test_all_pillars_set(self):
        assert set(ALL_PILLARS) == {
            "house", "techno", "trance", "dnb", "hardcore", "harddance", "autres"
        }

    def test_genre_pillar_fallback_for_unknown(self):
        # With an empty or unpopulated cache, unknown genres return "autres"
        result = genre_pillar("completely_unknown_genre_xyz")
        assert result == ("autres", 0)

    def test_genre_pillar_returns_tuple(self):
        result = genre_pillar("anything")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_pillar_genre_names_empty_for_unknown_pillar(self):
        # If no genres are cached under a non-existent pillar name, return []
        result = _pillar_genre_names("nonexistent_pillar")
        assert result == []

    def test_pillar_genre_names_with_populated_cache(self):
        # Temporarily inject a value into the cache
        pillar_map()["Test House Genre"] = ("house", 1)
        try:
            result = _pillar_genre_names("house")
            assert "Test House Genre" in result
        finally:
            pillar_map().pop("Test House Genre", None)

    def test_pillar_genre_names_returns_list(self):
        assert isinstance(_pillar_genre_names("techno"), list)

    def test_all_pillars_is_tuple(self):
        assert isinstance(ALL_PILLARS, tuple)


class TestAggregateTopGenres:
    """Shared helper backing the playlist AND set detail top_genres aggregate."""

    def test_empty_input_returns_empty(self):
        assert aggregate_top_genres([]) == []

    def test_all_genreless_tracks_return_empty(self):
        assert aggregate_top_genres([[], [], []]) == []

    def test_counts_pct_and_alpha_tie_break(self):
        # techno appears on tracks 0,1 -> 2 ; house on tracks 1,2 -> 2 ; track 3
        # is genre-less (excluded from the denominator = 3 genre-bearing tracks).
        out = aggregate_top_genres([["techno"], ["techno", "house"], ["house"], []])
        # tie on count 2 -> alphabetical (house before techno)
        assert [g.name for g in out] == ["house", "techno"]
        assert {g.name: g.pct for g in out} == {"house": 67, "techno": 67}  # round(200/3)

    def test_dedupes_repeated_genre_within_a_track(self):
        out = aggregate_top_genres([["techno", "techno"]])
        assert len(out) == 1
        assert out[0].name == "techno"
        assert out[0].pct == 100  # 1 genre-bearing track

    def test_caps_at_five_by_default(self):
        lists = []
        for genre, cnt in [("g6", 6), ("g5", 5), ("g4", 4), ("g3", 3), ("g2", 2), ("g1", 1)]:
            lists += [[genre]] * cnt
        out = aggregate_top_genres(lists)
        assert [g.name for g in out] == ["g6", "g5", "g4", "g3", "g2"]
        assert len(out) == 5  # "g1" (count 1) dropped by the cap

    def test_cap_is_configurable(self):
        out = aggregate_top_genres([["a"], ["b"], ["c"]], cap=2)
        assert len(out) == 2

    def test_pillar_resolved_from_cache(self):
        pillar_map()["Test Deep House"] = ("house", 2)
        try:
            out = aggregate_top_genres([["Test Deep House"]])
        finally:
            pillar_map().pop("Test Deep House", None)
        assert (out[0].pillar, out[0].depth) == ("house", 2)


class TestLookupDeezerGenres:
    async def test_raises_lookup_error_for_missing_catalog(self, db):
        with pytest.raises(LookupError, match="not found"):
            await lookup_deezer_genres(db, catalog_id=9999999, apply=False)

    async def test_raises_value_error_when_no_deezer_id(self, db):
        from models import CatalogEntry
        c = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        with pytest.raises(ValueError, match="deezer_id"):
            await lookup_deezer_genres(db, catalog_id=c.id, apply=False)
