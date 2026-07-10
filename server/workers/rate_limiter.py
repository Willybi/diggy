"""Rate limiter with per-source token bucket + concurrency semaphore.

Replaces all manual time.sleep() calls in pipeline tasks.

Sources listed in _SHARED_WINDOWS (deezer, beatport) are additionally
throttled through a Redis fixed-window counter shared across all worker
processes, replacing their local token bucket. On any Redis error the
limiter fails open to the local bucket (warning logged once per process).

Usage (async):
    limiter = RateLimiter()
    async with limiter.acquire("deezer"):
        resp = await client.get(...)

Usage (sync):
    limiter = RateLimiter()
    with limiter.acquire_sync("tidal"):
        resp = requests.get(...)
"""

import asyncio
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Per-source configuration: (max_concurrent, requests_per_second)
_SOURCE_CONFIG = {
    "deezer": (5, 10.0),  # 50 per 5s window
    "beatport": (2, 0.66),  # ~1 per 1.5s
    "tidal": (2, 2.0),
    "minio": (10, 0.0),  # local bucket, no rate limit
    "trackid": (1, 0.66),  # ~1 per 1.5s (sequential crawl)
}

# Sources rate-limited globally across worker processes via Redis:
# source -> (window_seconds, max_requests_per_window).
# Caps mirror the _SOURCE_CONFIG rates (10 rps deezer, ~0.66 rps beatport).
_SHARED_WINDOWS = {
    "deezer": (1, 10),
    "beatport": (3, 2),
}

# Redis socket timeouts: fail fast so a Redis outage never stalls tasks.
_REDIS_TIMEOUT = 1.0

# Warn once per process when falling open (Redis unreachable).
_redis_warned = False


def _warn_fail_open(source: str, exc: Exception):
    global _redis_warned
    if not _redis_warned:
        _redis_warned = True
        logger.warning(
            "Shared rate limiting for %s skipped (Redis unavailable), "
            "falling back to local bucket: %s",
            source,
            exc,
        )


class _TokenBucket:
    """Simple token bucket for sustained rate control."""

    def __init__(self, rate: float):
        self._rate = rate  # tokens per second (0 = unlimited)
        self._max_tokens = max(rate, 1.0) if rate > 0 else 0
        self._tokens = self._max_tokens
        self._last_refill = time.monotonic()

    async def wait(self):
        if self._rate <= 0:
            return
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait_time = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait_time)

    def wait_sync(self):
        if self._rate <= 0:
            return
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait_time = (1.0 - self._tokens) / self._rate
            time.sleep(wait_time)


class _SharedWindow:
    """Fixed-window counter in Redis, shared across worker processes.

    Key rl:{source}:{window_index}, INCR + EXPIRE. When the counter
    exceeds the cap, wait for the next window and retry. Wall clock
    (time.time) so all processes agree on window boundaries.
    """

    def __init__(self, source: str, window: int, cap: int):
        self._source = source
        self._window = window
        self._cap = cap
        self._async_client = None
        self._sync_client = None

    def _key(self, now: float) -> str:
        return f"rl:{self._source}:{int(now // self._window)}"

    def _next_window_delay(self, now: float) -> float:
        return self._window - (now % self._window) + 0.01

    async def wait(self):
        if self._async_client is None:
            import redis.asyncio as redis_async

            self._async_client = redis_async.from_url(
                REDIS_URL,
                socket_connect_timeout=_REDIS_TIMEOUT,
                socket_timeout=_REDIS_TIMEOUT,
            )
        while True:
            now = time.time()
            key = self._key(now)
            count = await self._async_client.incr(key)
            if count == 1:
                await self._async_client.expire(key, self._window + 5)
            if count <= self._cap:
                return
            await asyncio.sleep(self._next_window_delay(now))

    def wait_sync(self):
        if self._sync_client is None:
            import redis as redis_lib

            self._sync_client = redis_lib.from_url(
                REDIS_URL,
                socket_connect_timeout=_REDIS_TIMEOUT,
                socket_timeout=_REDIS_TIMEOUT,
            )
        while True:
            now = time.time()
            key = self._key(now)
            count = self._sync_client.incr(key)
            if count == 1:
                self._sync_client.expire(key, self._window + 5)
            if count <= self._cap:
                return
            time.sleep(self._next_window_delay(now))


class RateLimiter:
    """Per-source rate limiter combining semaphore + rate gate.

    Semaphores stay process-local (they bound in-flight requests per
    process); the rate gate is the Redis shared window for sources in
    _SHARED_WINDOWS, the local token bucket otherwise.
    Supports both async (acquire) and sync (acquire_sync) usage.
    """

    def __init__(self):
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._buckets: dict[str, _TokenBucket] = {}
        self._sync_semaphores: dict[str, threading.Semaphore] = {}
        self._shared: dict[str, _SharedWindow] = {}

    def _ensure_shared(self, source: str):
        if source in _SHARED_WINDOWS and source not in self._shared:
            window, cap = _SHARED_WINDOWS[source]
            self._shared[source] = _SharedWindow(source, window, cap)

    def _ensure_source(self, source: str):
        if source not in self._semaphores:
            max_concurrent, rate = _SOURCE_CONFIG.get(source, (3, 5.0))
            self._semaphores[source] = asyncio.Semaphore(max_concurrent)
            self._buckets[source] = _TokenBucket(rate)
        self._ensure_shared(source)

    def _ensure_sync_source(self, source: str):
        if source not in self._sync_semaphores:
            max_concurrent, _ = _SOURCE_CONFIG.get(source, (3, 5.0))
            self._sync_semaphores[source] = threading.Semaphore(max_concurrent)
        if source not in self._buckets:
            _, rate = _SOURCE_CONFIG.get(source, (3, 5.0))
            self._buckets[source] = _TokenBucket(rate)
        self._ensure_shared(source)

    def acquire(self, source: str) -> "_RateLimitContext":
        self._ensure_source(source)
        return _RateLimitContext(
            self._semaphores[source],
            self._buckets[source],
            self._shared.get(source),
        )

    def acquire_sync(self, source: str) -> "_SyncRateLimitContext":
        self._ensure_sync_source(source)
        return _SyncRateLimitContext(
            self._sync_semaphores[source],
            self._buckets[source],
            self._shared.get(source),
        )


class _RateLimitContext:
    def __init__(
        self,
        semaphore: asyncio.Semaphore,
        bucket: _TokenBucket,
        shared: _SharedWindow | None = None,
    ):
        self._semaphore = semaphore
        self._bucket = bucket
        self._shared = shared

    async def __aenter__(self):
        await self._semaphore.acquire()
        if self._shared is not None:
            try:
                await self._shared.wait()
                return self
            except Exception as exc:  # fail-open: Redis down must not stop tasks
                _warn_fail_open(self._shared._source, exc)
        await self._bucket.wait()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._semaphore.release()
        return False


class _SyncRateLimitContext:
    def __init__(
        self,
        semaphore: threading.Semaphore,
        bucket: _TokenBucket,
        shared: _SharedWindow | None = None,
    ):
        self._semaphore = semaphore
        self._bucket = bucket
        self._shared = shared

    def __enter__(self):
        self._semaphore.acquire()
        if self._shared is not None:
            try:
                self._shared.wait_sync()
                return self
            except Exception as exc:  # fail-open: Redis down must not stop tasks
                _warn_fail_open(self._shared._source, exc)
        self._bucket.wait_sync()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._semaphore.release()
        return False
