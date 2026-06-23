"""Async rate limiter with per-source token bucket + concurrency semaphore.

Replaces all manual time.sleep() calls in pipeline tasks.
Usage:
    limiter = RateLimiter()
    async with limiter.acquire("deezer"):
        resp = await client.get(...)
"""
import asyncio
import time

# Per-source configuration: (max_concurrent, requests_per_second)
_SOURCE_CONFIG = {
    "deezer": (5, 10.0),      # 50 per 5s window
    "beatport": (2, 0.66),    # ~1 per 1.5s
    "tidal": (2, 2.0),
    "minio": (10, 0.0),       # local bucket, no rate limit
    "trackid": (2, 1.0),
}


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


class RateLimiter:
    """Per-source async rate limiter combining semaphore + token bucket."""

    def __init__(self):
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._buckets: dict[str, _TokenBucket] = {}

    def _ensure_source(self, source: str):
        if source not in self._semaphores:
            max_concurrent, rate = _SOURCE_CONFIG.get(source, (3, 5.0))
            self._semaphores[source] = asyncio.Semaphore(max_concurrent)
            self._buckets[source] = _TokenBucket(rate)

    def acquire(self, source: str) -> "_RateLimitContext":
        self._ensure_source(source)
        return _RateLimitContext(self._semaphores[source], self._buckets[source])


class _RateLimitContext:
    def __init__(self, semaphore: asyncio.Semaphore, bucket: _TokenBucket):
        self._semaphore = semaphore
        self._bucket = bucket

    async def __aenter__(self):
        await self._semaphore.acquire()
        await self._bucket.wait()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._semaphore.release()
        return False
