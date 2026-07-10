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

from workers.async_http import DeezerHTTPError, HttpPool
from workers.enrichment import _enrich_entry_async, enrich_deezer_batch

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
        assert stats == {"enriched": 0, "errors": 0}

    async def test_http_error_leaves_unsearched_and_counts_error(self):
        entry = _make_entry(artist="Artist", title="Track", deezer_searched_at=None)
        pool = MagicMock()
        pool.deezer_get = AsyncMock(side_effect=DeezerHTTPError(500, "/search"))

        stats = await enrich_deezer_batch(None, [entry], pool, None, set())

        assert entry.deezer_searched_at is None
        assert stats == {"enriched": 0, "errors": 1}

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
        assert stats == {"enriched": 0, "errors": 0}
