"""Tests for server/workers/enrichment.py — async Deezer enrichment logic.

Focus: the private → shared promotion in _enrich_entry_async, which mirrors the
legacy synchronous path in deezer_enrich.enrich_entry (A3-01).
"""
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# redis and curl_cffi are not installed in the test env; enrichment.py and
# async_http.py import them at module load.
# Save the originals so we can restore after the import.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.async_http import DeezerHTTPError, HttpPool  # noqa: E402
from workers.enrichment import (  # noqa: E402
    _enrich_entry_async,
    _search_deezer_async,
    enrich_deezer_batch,
)

# Restore sys.modules immediately — we already imported what we need.
# This prevents polluting other test files collected by pytest.
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


def _make_entry(**overrides):
    """Bare CatalogEntry-like mock; has_artwork=True skips the async cover upload."""
    entry = MagicMock()
    entry.id = 1
    entry.deezer_id = None
    entry.isrc = None
    entry.duration_ms = None
    entry.has_preview = False
    entry.has_artwork = True
    entry.scope = "private"
    entry.owner_id = 42
    entry.deezer_search_attempts = 0
    for key, value in overrides.items():
        setattr(entry, key, value)
    return entry


class TestPromotePrivateToShared:
    async def test_promotes_private_on_deezer_match(self):
        entry = _make_entry(scope="private", owner_id=42)
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}

        changed = await _enrich_entry_async(entry, hit, pool, None, set())

        assert changed is True
        assert entry.deezer_id == "123"
        assert entry.scope == "shared"
        assert entry.owner_id is None

    async def test_keeps_shared_scope(self):
        entry = _make_entry(scope="shared", owner_id=7)
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}

        changed = await _enrich_entry_async(entry, hit, pool, None, set())

        assert changed is True
        assert entry.scope == "shared"
        assert entry.owner_id == 7  # untouched: promotion only fires for 'private'

    async def test_no_change_keeps_private(self):
        # Entry already fully matches the hit → changed=False → no promotion.
        entry = _make_entry(
            scope="private",
            owner_id=42,
            deezer_id="123",
            isrc="US1234",
            duration_ms=180_000,
            has_preview=True,
            has_artwork=True,
        )
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://x"}

        changed = await _enrich_entry_async(entry, hit, pool, None, {"US1234"})

        assert changed is False
        assert entry.scope == "private"
        assert entry.owner_id == 42


def _make_pool(status_code, json_data=None):
    """HttpPool with a mocked httpx transport (no network, no context entry)."""
    pool = HttpPool()
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    pool._client = MagicMock()
    pool._client.request = AsyncMock(return_value=resp)
    return pool


class TestDeezerGetStatusHandling:
    """A3-04: a non-200 must raise instead of masquerading as an empty result."""

    async def test_500_raises_deezer_http_error(self):
        pool = _make_pool(500)
        with pytest.raises(DeezerHTTPError) as exc:
            await pool.deezer_get("/track/123")
        assert exc.value.status_code == 500

    async def test_200_returns_json(self):
        pool = _make_pool(200, {"id": 123, "title": "Track"})
        data = await pool.deezer_get("/track/123")
        assert data == {"id": 123, "title": "Track"}


class TestEnrichOneSearchedAt:
    """A3-04: deezer_searched_at is only set on a real 200 "not found",
    never on an HTTP error — the entry must stay in the nightly pipeline."""

    async def test_empty_200_marks_searched(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={"data": []})

        stats = await enrich_deezer_batch(None, [entry], pool, None, set())

        assert isinstance(entry.deezer_searched_at, datetime)
        assert stats == {"enriched": 0, "errors": 0, "merged": 0}

    async def test_http_error_leaves_unsearched_and_counts_error(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(side_effect=DeezerHTTPError(500, "/search"))

        stats = await enrich_deezer_batch(None, [entry], pool, None, set())

        assert entry.deezer_searched_at is None
        assert stats == {"enriched": 0, "errors": 1, "merged": 0}

    async def test_track_lookup_empty_200_marks_searched(self):
        entry = _make_entry(deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={})

        stats = await enrich_deezer_batch(
            None,
            [entry],
            pool,
            None,
            set(),
            source="deezer",
            ext_id_map={1: "999"},
        )

        assert isinstance(entry.deezer_searched_at, datetime)
        assert stats == {"enriched": 0, "errors": 0, "merged": 0}


class TestSearchAttempts:
    """E1: a completed search (empty 200 or success) increments
    deezer_search_attempts; an HTTP error increments nothing — the entry
    must not burn one of its 3 re-scan attempts on an outage (A3-04)."""

    async def test_empty_200_increments_attempts(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={"data": []})

        await enrich_deezer_batch(None, [entry], pool, None, set())

        assert entry.deezer_search_attempts == 1

    async def test_success_increments_attempts(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}
        pool.deezer_get = AsyncMock(return_value={"data": [hit]})

        await enrich_deezer_batch(None, [entry], pool, None, set())

        assert entry.deezer_search_attempts == 1

    async def test_track_lookup_empty_200_increments_attempts(self):
        entry = _make_entry(deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(return_value={})

        await enrich_deezer_batch(
            None, [entry], pool, None, set(), source="deezer", ext_id_map={1: "999"}
        )

        assert entry.deezer_search_attempts == 1

    async def test_http_error_no_increment_no_searched_at(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(side_effect=DeezerHTTPError(500, "/search"))

        stats = await enrich_deezer_batch(None, [entry], pool, None, set())

        assert stats == {"enriched": 0, "errors": 1, "merged": 0}
        assert entry.deezer_searched_at is None
        assert entry.deezer_search_attempts == 0


class TestEnrichDeezerBatch:
    """A6-04: happy path and error accounting of enrich_deezer_batch."""

    async def test_successful_search_enriches_and_marks_searched(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://p"}
        pool.deezer_get = AsyncMock(return_value={"data": [hit]})

        stats = await enrich_deezer_batch(None, [entry], pool, None, set())

        assert stats == {"enriched": 1, "errors": 0, "merged": 0}
        assert entry.deezer_id == "123"
        assert entry.isrc == "US1234"
        assert entry.duration_ms == 180_000
        assert entry.has_preview is True
        assert isinstance(entry.deezer_searched_at, datetime)

    async def test_unexpected_error_counts_error_and_leaves_unsearched(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(side_effect=ValueError("boom"))

        stats = await enrich_deezer_batch(None, [entry], pool, None, set())

        assert stats == {"enriched": 0, "errors": 1, "merged": 0}
        assert entry.deezer_searched_at is None

    async def test_deezer_source_without_ext_id_skips_entry(self):
        entry = _make_entry(deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock()

        stats = await enrich_deezer_batch(
            None, [entry], pool, None, set(), source="deezer", ext_id_map={99: "1"}
        )

        assert stats == {"enriched": 0, "errors": 0, "merged": 0}
        pool.deezer_get.assert_not_called()
        assert entry.deezer_searched_at is None

    async def test_deezer_source_direct_lookup_enriches(self):
        entry = _make_entry(deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"id": 555, "isrc": "US1", "duration": 60, "preview": ""}
        )

        stats = await enrich_deezer_batch(
            None, [entry], pool, None, set(), source="deezer", ext_id_map={1: "555"}
        )

        assert stats == {"enriched": 1, "errors": 0, "merged": 0}
        assert entry.deezer_id == "555"
        pool.deezer_get.assert_awaited_once_with("/track/555")


def _make_cascade_pool(hits_by_query):
    """Pool whose deezer_get resolves /search from a {query: hit} mapping.

    Records every query string in pool.queries so tests can assert which
    cascade steps ran and in what order.
    """
    pool = MagicMock()
    pool.queries = []

    async def _deezer_get(path, params=None):
        q = params["q"]
        pool.queries.append(q)
        hit = hits_by_query.get(q)
        return {"data": [hit] if hit else []}

    pool.deezer_get = AsyncMock(side_effect=_deezer_get)
    return pool


class TestSearchDeezerCascade:
    """A6-04: cascading search strategy of _search_deezer_async.

    Each step must only fire when the previous ones found nothing:
    1. original title → 2. safe-suffix strip → 3. non-remix parens strip
    → 4. first artist only. Within a step: qualified search first, then
    free query fallback.
    """

    async def test_none_title_returns_none_without_http(self):
        pool = MagicMock()
        pool.deezer_get = AsyncMock()

        assert await _search_deezer_async(pool, "Artist", None) is None
        pool.deezer_get.assert_not_called()

    async def test_qualified_search_hit_returned_as_is(self):
        hit = {"id": 1, "title": "Track"}
        pool = _make_cascade_pool({'artist:"Artist" track:"Track"': hit})

        assert await _search_deezer_async(pool, "Artist", "Track") is hit
        assert pool.queries == ['artist:"Artist" track:"Track"']

    async def test_free_query_fallback_when_qualified_empty(self):
        hit = {"id": 2}
        pool = _make_cascade_pool({"Artist Track": hit})

        assert await _search_deezer_async(pool, "Artist", "Track") is hit
        assert pool.queries == ['artist:"Artist" track:"Track"', "Artist Track"]

    async def test_no_artist_uses_free_query_only(self):
        hit = {"id": 3}
        pool = _make_cascade_pool({"Track": hit})

        assert await _search_deezer_async(pool, None, "Track") is hit
        assert pool.queries == ["Track"]

    async def test_hit_after_safe_suffix_strip(self):
        # Step 2: "(Extended Mix)" is a safe suffix, stripped after step 1 fails.
        hit = {"id": 4}
        pool = _make_cascade_pool({'artist:"Artist" track:"Track"': hit})

        result = await _search_deezer_async(pool, "Artist", "Track (Extended Mix)")

        assert result is hit
        assert pool.queries == [
            'artist:"Artist" track:"Track Extended Mix"',
            "Artist Track Extended Mix",
            'artist:"Artist" track:"Track"',
        ]

    async def test_hit_after_non_remix_paren_strip(self):
        # Step 3: "(Vocal Mix)" is not a safe suffix (step 2 skipped) but only
        # contains generic mixing terms, so it is stripped as a non-remix paren.
        hit = {"id": 5}
        pool = _make_cascade_pool({'artist:"Artist" track:"Track"': hit})

        result = await _search_deezer_async(pool, "Artist", "Track (Vocal Mix)")

        assert result is hit
        assert pool.queries == [
            'artist:"Artist" track:"Track Vocal Mix"',
            "Artist Track Vocal Mix",
            'artist:"Artist" track:"Track"',
        ]

    async def test_hit_with_first_artist_only(self):
        # Step 4: multi-artist "A & B" fails everywhere, first artist "A" matches.
        hit = {"id": 6}
        pool = _make_cascade_pool({'artist:"A" track:"Song"': hit})

        result = await _search_deezer_async(pool, "A & B", "Song")

        assert result is hit
        assert pool.queries == [
            'artist:"A & B" track:"Song"',
            "A & B Song",
            'artist:"A" track:"Song"',
        ]

    async def test_full_cascade_failure_returns_none(self):
        pool = _make_cascade_pool({})

        result = await _search_deezer_async(pool, "A & B", "Track (Extended Mix)")

        assert result is None
        # Steps 1, 2 and 4 each ran qualified + free searches; step 3 was
        # skipped because the parens strip equals the safe-suffix strip.
        assert pool.queries == [
            'artist:"A & B" track:"Track Extended Mix"',
            "A & B Track Extended Mix",
            'artist:"A & B" track:"Track"',
            "A & B Track",
            'artist:"A" track:"Track"',
            "A Track",
        ]

    async def test_clean_strips_parens_and_brackets_from_params(self):
        # Deezer returns 403 on parens/brackets in queries: _clean must drop
        # the characters (keeping their content) from every outgoing query.
        pool = _make_cascade_pool({})

        await _search_deezer_async(pool, "DJ (FR)", "Track [VIP] (Dub)")

        assert pool.queries[0] == 'artist:"DJ FR" track:"Track VIP Dub"'
        for q in pool.queries:
            assert not any(c in q for c in "()[]")
