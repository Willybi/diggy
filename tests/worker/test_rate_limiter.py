"""Tests for server/workers/rate_limiter.py — token bucket and rate limiter."""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/workers"))

import rate_limiter as rate_limiter_module
from rate_limiter import _SHARED_WINDOWS, _SOURCE_CONFIG, RateLimiter, _TokenBucket


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


class _FakeTime:
    """Deterministic clock: sleep() advances time instead of blocking."""

    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class _FakeRedis:
    """Minimal fake Redis: INCR + EXPIRE counters on a dict."""

    def __init__(self):
        self.counters = {}
        self.ttls = {}

    def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key, ttl):
        self.ttls[key] = ttl


class _FakeAsyncRedis(_FakeRedis):
    async def incr(self, key):
        return _FakeRedis.incr(self, key)

    async def expire(self, key, ttl):
        _FakeRedis.expire(self, key, ttl)


class _FailingAsyncRedis:
    """Fake async Redis client that always fails (Redis down)."""

    async def incr(self, key):
        raise ConnectionError("redis down")


class _FailingSyncRedis:
    def incr(self, key):
        raise ConnectionError("redis down")


class TestSharedWindow:
    def test_shared_windows_only_deezer_beatport(self):
        assert set(_SHARED_WINDOWS) == {"deezer", "beatport"}

    def test_window_caps_then_waits_next_window(self, monkeypatch):
        # beatport: window=3s, cap=2. Fake clock starts mid-window.
        fake_time = _FakeTime(start=1000.0)
        monkeypatch.setattr(rate_limiter_module, "time", fake_time)
        limiter = RateLimiter()
        limiter._ensure_sync_source("beatport")
        fake_redis = _FakeRedis()
        limiter._shared["beatport"]._sync_client = fake_redis

        # Two acquisitions fit in the window: no sleep
        for _ in range(2):
            with limiter.acquire_sync("beatport"):
                pass
        assert fake_time.sleeps == []
        assert fake_redis.counters == {"rl:beatport:333": 2}

        # Third exceeds the cap: waits for the next window, then passes
        with limiter.acquire_sync("beatport"):
            pass
        assert len(fake_time.sleeps) == 1
        assert abs(fake_time.sleeps[0] - 2.01) < 0.001  # 3 - (1000 % 3) + 0.01
        assert fake_redis.counters == {"rl:beatport:333": 3, "rl:beatport:334": 1}
        # EXPIRE set with window + margin on the first INCR of each window
        assert fake_redis.ttls == {"rl:beatport:333": 8, "rl:beatport:334": 8}

    def test_async_acquisitions_count_in_redis(self):
        limiter = RateLimiter()
        fake_redis = _FakeAsyncRedis()

        async def _test():
            limiter._ensure_source("deezer")
            limiter._shared["deezer"]._async_client = fake_redis
            for _ in range(3):
                async with limiter.acquire("deezer"):
                    pass

        asyncio.run(_test())
        # Acquisitions may straddle a real 1s window boundary: sum the keys
        assert sum(fake_redis.counters.values()) == 3
        assert all(key.startswith("rl:deezer:") for key in fake_redis.counters)

    def test_tidal_never_touches_redis(self):
        limiter = RateLimiter()
        with limiter.acquire_sync("tidal"):
            pass
        # No shared window created: all Redis access goes through _shared
        assert "tidal" not in _SHARED_WINDOWS
        assert limiter._shared == {}


class TestFailOpen:
    def test_async_fail_open_uses_local_bucket_and_warns_once(
        self, monkeypatch, caplog
    ):
        monkeypatch.setattr(rate_limiter_module, "_redis_warned", False)
        limiter = RateLimiter()

        async def _test():
            limiter._ensure_source("deezer")
            limiter._shared["deezer"]._async_client = _FailingAsyncRedis()
            for _ in range(2):
                async with limiter.acquire("deezer"):
                    pass

        with caplog.at_level(logging.WARNING):
            asyncio.run(_test())
        warnings = [r for r in caplog.records if "Redis unavailable" in r.getMessage()]
        assert len(warnings) == 1

    def test_sync_fail_open_uses_local_bucket_and_warns_once(
        self, monkeypatch, caplog
    ):
        monkeypatch.setattr(rate_limiter_module, "_redis_warned", False)
        limiter = RateLimiter()
        limiter._ensure_sync_source("beatport")
        limiter._shared["beatport"]._sync_client = _FailingSyncRedis()

        with caplog.at_level(logging.WARNING):
            for _ in range(2):
                with limiter.acquire_sync("beatport"):
                    pass
        warnings = [r for r in caplog.records if "Redis unavailable" in r.getMessage()]
        assert len(warnings) == 1

    def test_fail_open_without_redis_lib_installed(self, monkeypatch):
        # In this harness the redis lib is absent: the lazy import itself
        # fails and the limiter must still hand out acquisitions.
        monkeypatch.setattr(rate_limiter_module, "_redis_warned", False)
        limiter = RateLimiter()
        with limiter.acquire_sync("deezer"):
            pass
