"""Tests for channel_service.resolve_artist_candidate (C14.b 🅱 L1, cache layer).

Covers the CACHE-FIRST behaviour + fail-open, mirroring the resolve_candidate
tests. ``resolve_artist_channel`` (the actual cascade, tested in the worker suite)
is mocked so no network is touched.
"""
import json
from unittest.mock import AsyncMock

from services import channel_service


class _RaisingRedis:
    """A Redis stand-in whose every op raises — exercises the fail-open branches."""

    async def get(self, *a, **k):
        raise RuntimeError("redis down")

    async def set(self, *a, **k):
        raise RuntimeError("redis down")


_RESULT = {
    "channel_id": "UCabc1234567890abcdef12",
    "channel_title": None,
    "url": "https://www.youtube.com/channel/UCabc1234567890abcdef12",
    "method": "wikidata",
    "confidence": "high",
    "has_soundcloud": False,
}


class TestResolveArtistCandidate:
    async def test_miss_resolves_and_caches(self, fake_redis, mocker):
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=_RESULT,
        )
        out = await channel_service.resolve_artist_candidate("Peggy Gou", fake_redis)
        assert out == _RESULT
        resolve.assert_called_once()
        key = channel_service._artist_resolve_cache_key("Peggy Gou")
        assert key in fake_redis._store
        assert (
            json.loads(fake_redis._store[key])["channel_id"] == _RESULT["channel_id"]
        )

    async def test_hit_returns_cache_without_resolving(self, fake_redis, mocker):
        fake_redis._store[
            channel_service._artist_resolve_cache_key("Cached")
        ] = json.dumps(_RESULT)
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )
        out = await channel_service.resolve_artist_candidate("Cached", fake_redis)
        assert out["channel_id"] == _RESULT["channel_id"]
        # INVARIANT: a cache HIT spends ZERO network — the cascade is never run.
        resolve.assert_not_called()

    async def test_cached_none_returns_none_without_resolving(
        self, fake_redis, mocker
    ):
        # A prior fruitless resolution is cached as `null` — a valid HIT of None.
        fake_redis._store[
            channel_service._artist_resolve_cache_key("NoneCached")
        ] = json.dumps(None)
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=_RESULT,
        )
        out = await channel_service.resolve_artist_candidate("NoneCached", fake_redis)
        assert out is None
        resolve.assert_not_called()

    async def test_failopen_on_raising_redis(self, mocker):
        # Redis read/write raises → fail-open: live resolution, no crash.
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=_RESULT,
        )
        out = await channel_service.resolve_artist_candidate("Boom", _RaisingRedis())
        assert out == _RESULT
        resolve.assert_called_once()

    async def test_redis_none_resolves_no_cache(self, mocker):
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=_RESULT,
        )
        out = await channel_service.resolve_artist_candidate("NoRedis", None)
        assert out == _RESULT
        resolve.assert_called_once()

    async def test_allow_search_forwarded(self, fake_redis, mocker):
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )
        await channel_service.resolve_artist_candidate(
            "X", fake_redis, allow_search=False
        )
        _, kwargs = resolve.call_args
        assert kwargs["allow_search"] is False
