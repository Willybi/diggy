"""Tests for genres.py — pure function tests (genre_pillar, slug).

Note: The SQL-heavy endpoints and taxonomy-based pillar resolution cannot
run without PostgreSQL. Only pure Python logic is tested here.
The pillar cache is tested with mock data.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from services.genre_service import ALL_PILLARS, _pillar_genre_names, genre_pillar, pillar_map


class TestAllPillars:
    def test_has_expected_pillars(self):
        assert set(ALL_PILLARS) == {
            "house", "techno", "trance", "dnb", "hardcore", "harddance", "autres"
        }


class TestGenrePillar:
    def test_unknown_genre_returns_autres(self):
        assert genre_pillar("Unknown Genre XYZ") == ("autres", 0)

    def test_cached_genre(self):
        cache = pillar_map()
        cache["Test Genre"] = ("house", 1)
        try:
            assert genre_pillar("Test Genre") == ("house", 1)
        finally:
            del cache["Test Genre"]


class TestPillarGenreNames:
    def test_empty_cache_returns_empty(self):
        names = _pillar_genre_names("nonexistent")
        assert names == []

    def test_returns_matching(self):
        cache = pillar_map()
        cache["Foo"] = ("techno", 0)
        cache["Bar"] = ("techno", 1)
        cache["Baz"] = ("house", 0)
        try:
            names = _pillar_genre_names("techno")
            assert "Foo" in names
            assert "Bar" in names
            assert "Baz" not in names
        finally:
            del cache["Foo"]
            del cache["Bar"]
            del cache["Baz"]
