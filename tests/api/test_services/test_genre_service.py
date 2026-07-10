"""Tests for services/genre_service.py — pure logic + DB."""
import pytest

from services.genre_service import (
    ALL_PILLARS,
    _pillar_genre_names,
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
