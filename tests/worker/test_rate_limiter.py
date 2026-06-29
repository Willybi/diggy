"""Tests for server/workers/rate_limiter.py — token bucket and rate limiter."""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/workers"))

from rate_limiter import _TokenBucket, RateLimiter, _SOURCE_CONFIG


class TestTokenBucket:
    def test_unlimited_rate_returns_immediately(self):
        bucket = _TokenBucket(0)
        bucket.wait_sync()  # should not block

    def test_first_token_available_immediately(self):
        bucket = _TokenBucket(10.0)
        start = time.monotonic()
        bucket.wait_sync()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # should be instant

    def test_burst_consumes_tokens(self):
        bucket = _TokenBucket(10.0)
        # Consume all initial tokens (max_tokens = rate = 10)
        for _ in range(10):
            bucket.wait_sync()
        # Next call should require waiting
        start = time.monotonic()
        bucket.wait_sync()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.05  # at 10/s, should wait ~0.1s

    def test_async_wait_unlimited(self):
        bucket = _TokenBucket(0)
        asyncio.run(bucket.wait())  # should not block

    def test_async_first_token_immediate(self):
        bucket = _TokenBucket(10.0)
        start = time.monotonic()
        asyncio.run(bucket.wait())
        elapsed = time.monotonic() - start
        assert elapsed < 0.05


class TestRateLimiter:
    def test_acquire_sync_returns_context_manager(self):
        limiter = RateLimiter()
        with limiter.acquire_sync("deezer"):
            pass  # should complete without error

    def test_acquire_sync_unknown_source_uses_defaults(self):
        limiter = RateLimiter()
        with limiter.acquire_sync("unknown_source"):
            pass

    def test_acquire_async_returns_context_manager(self):
        limiter = RateLimiter()

        async def _test():
            async with limiter.acquire("deezer"):
                pass

        asyncio.run(_test())

    def test_source_config_has_expected_sources(self):
        assert "deezer" in _SOURCE_CONFIG
        assert "beatport" in _SOURCE_CONFIG
        assert "tidal" in _SOURCE_CONFIG
        assert "minio" in _SOURCE_CONFIG

    def test_minio_has_no_rate_limit(self):
        _, rate = _SOURCE_CONFIG["minio"]
        assert rate == 0.0

    def test_semaphore_limits_concurrency(self):
        limiter = RateLimiter()
        # Create source with max_concurrent=1
        limiter._ensure_sync_source("trackid")  # trackid has max_concurrent=1
        sem = limiter._sync_semaphores["trackid"]
        assert sem._value == 1
