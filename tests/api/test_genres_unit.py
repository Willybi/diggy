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


class TestListGenresSortParam:
    """Router-level validation of the `sort` query param on GET /api/genres.

    The genre-list SQL (PERCENTILE_CONT, unnest, CROSS JOIN LATERAL) is
    PostgreSQL-specific and does not run on the SQLite harness, so the *ordering*
    produced by sort=lib is covered by a PG-gated integration test in
    test_services/test_genre_service.py. Here we only assert the pattern accepts
    the new `lib` value and still rejects unknown ones (mirrors the sort
    validation style of test_validation.py).
    """

    async def test_sort_lib_not_rejected_as_invalid(self, client):
        # A 422 comes from FastAPI param validation BEFORE the service runs. On
        # SQLite the accepted `lib` value instead reaches the PG-only SQL and
        # raises OperationalError — which itself proves the pattern let `lib`
        # through (on PostgreSQL the same request returns 200). Mirrors
        # TestRadarSortValidation.test_valid_sort_not_rejected_as_invalid.
        from sqlalchemy.exc import OperationalError

        try:
            r = await client.get("/api/genres?sort=lib")
            assert r.status_code != 422
        except OperationalError:
            pass

    async def test_unknown_sort_returns_422(self, client):
        r = await client.get("/api/genres?sort=banana")
        assert r.status_code == 422
