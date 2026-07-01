"""Shared async HTTP client for worker tasks.

Provides rate-limited, retrying HTTP methods for all external APIs.
Replaces synchronous `requests` calls in pipeline tasks.

Usage:
    from workers.async_http import HttpPool

    async def my_task():
        pool = HttpPool()
        async with pool:
            data = await pool.deezer_get("/track/123")
            page = await pool.beatport_get("/search?q=test")
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
from curl_cffi import requests as curl_requests
from workers.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"
BEATPORT_URL = "https://www.beatport.com"

# Configurable via env vars
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "20.0"))
HTTP_CONNECT_TIMEOUT = float(os.environ.get("HTTP_CONNECT_TIMEOUT", "10.0"))
HTTP_MAX_CONNECTIONS = int(os.environ.get("HTTP_MAX_CONNECTIONS", "20"))

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF = [1.0, 2.0, 4.0]


class HttpPool:
    """Async HTTP client pool with per-source rate limiting and retry."""

    def __init__(self, limiter: RateLimiter | None = None):
        self.limiter = limiter or RateLimiter()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=HTTP_MAX_CONNECTIONS, max_keepalive_connections=10
            ),
        )
        self._bp_session = curl_requests.Session(impersonate="chrome124")
        self._bp_executor = ThreadPoolExecutor(max_workers=2)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None
        if hasattr(self, "_bp_session"):
            self._bp_session.close()
        if hasattr(self, "_bp_executor"):
            self._bp_executor.shutdown(wait=False)
        return False

    async def _request_with_retry(
        self,
        source: str,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        params: dict | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> httpx.Response:
        """Execute a rate-limited request with exponential backoff retry."""
        last_exc = None
        for attempt in range(max_retries):
            async with self.limiter.acquire(source):
                try:
                    resp = await self._client.request(
                        method, url, headers=headers, params=params
                    )
                    if resp.status_code == 429:
                        wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        logger.warning(
                            "Rate limited by %s (429), retrying in %.1fs", source, wait
                        )
                        await asyncio.sleep(wait)
                        last_exc = httpx.HTTPStatusError(
                            "429", request=resp.request, response=resp
                        )
                        continue
                    return resp
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.ConnectTimeout,
                ) as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                        logger.warning(
                            "%s request failed (%s), retry %d in %.1fs",
                            source,
                            e,
                            attempt + 1,
                            wait,
                        )
                        await asyncio.sleep(wait)
        raise last_exc

    # ── Deezer ──

    async def deezer_get(self, path: str, params: dict | None = None) -> dict:
        """GET request to Deezer API, rate-limited + retrying. Returns parsed JSON."""
        resp = await self._request_with_retry(
            "deezer", "GET", f"{DEEZER_API}{path}", params=params
        )
        if resp.status_code != 200:
            return {}
        return resp.json()

    # ── Beatport ──

    async def beatport_get(self, path: str) -> httpx.Response:
        """GET request to Beatport via curl_cffi in threadpool (bypasses Cloudflare TLS fingerprinting).
        Returns an httpx.Response-compatible object."""
        url = f"{BEATPORT_URL}{path}"
        loop = asyncio.get_event_loop()

        async with self.limiter.acquire("beatport"):

            def _sync_get():
                return self._bp_session.get(url, timeout=15)

            resp = await loop.run_in_executor(self._bp_executor, _sync_get)

        class _Resp:
            def __init__(self, r):
                self.status_code = r.status_code
                self.text = r.text
                self.content = r.content

        return _Resp(resp)

    # ── Generic ──

    async def get(self, url: str, source: str = "deezer", **kwargs) -> httpx.Response:
        """Generic rate-limited GET request."""
        return await self._request_with_retry(source, "GET", url, **kwargs)

    async def download_image(self, url: str) -> bytes | None:
        """Download an image without rate limiting (direct URLs). Returns bytes or None."""
        try:
            resp = await self._client.get(url, timeout=15.0)
            resp.raise_for_status()
            if len(resp.content) < 1000:  # skip placeholder images
                return None
            return resp.content
        except Exception:
            return None
