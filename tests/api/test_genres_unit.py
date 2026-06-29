"""Tests for genres.py — pure function tests (genre_family, _slug).

Note: The SQL-heavy endpoints in genres.py use PostgreSQL-specific features
(unnest, PERCENTILE_CONT, array_replace, CROSS JOIN LATERAL) that cannot
run on SQLite. Only pure Python logic is tested here.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from routers.genres import genre_family, _slug, _ALL_FAMILIES, _family_genre_names


class TestSlug:
    def test_basic(self):
        assert _slug("Deep House") == "deep-house"

    def test_special_chars(self):
        assert _slug("Drum & Bass") == "drum-bass"

    def test_leading_trailing_dashes(self):
        assert _slug("  House  ") == "house"

    def test_single_word(self):
        assert _slug("Techno") == "techno"

    def test_slash(self):
        assert _slug("Nu Disco / Disco") == "nu-disco-disco"


class TestGenreFamily:
    def test_house_genres(self):
        assert genre_family("House") == "house"
        assert genre_family("Deep House") == "house"
        assert genre_family("Tech House") == "house"
        assert genre_family("Afro House") == "house"
        assert genre_family("Nu Disco / Disco") == "house"

    def test_techno_genres(self):
        assert genre_family("Techno (Peak Time / Driving)") == "techno"
        assert genre_family("Hard Techno") == "techno"
        assert genre_family("Melodic House & Techno") == "techno"

    def test_trance_genres(self):
        assert genre_family("Trance (Main Floor)") == "trance"
        assert genre_family("Psy-Trance") == "trance"

    def test_other_genres(self):
        assert genre_family("Drum & Bass") == "other"
        assert genre_family("Hip-Hop") == "other"

    def test_misc_genres(self):
        assert genre_family("DJ Tools / Acapellas") == "misc"

    def test_unknown_genre_returns_misc(self):
        assert genre_family("Unknown Genre XYZ") == "misc"

    def test_case_insensitive(self):
        assert genre_family("deep house") == "house"
        assert genre_family("DEEP HOUSE") == "house"


class TestAllFamilies:
    def test_has_expected_families(self):
        assert set(_ALL_FAMILIES) == {"house", "techno", "trance", "other", "misc"}


class TestFamilyGenreNames:
    def test_house_has_entries(self):
        names = _family_genre_names("house")
        assert len(names) > 0
        assert "House" in names
        assert "Deep House" in names

    def test_techno_has_entries(self):
        names = _family_genre_names("techno")
        assert len(names) > 0

    def test_unknown_family_returns_empty(self):
        names = _family_genre_names("nonexistent")
        assert names == []
