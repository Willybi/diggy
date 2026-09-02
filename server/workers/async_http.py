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
import threading
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


class DeezerHTTPError(Exception):
    """Deezer API returned a non-200 status (after retries).

    Lets callers distinguish an API failure from a legitimate empty result,
    so entries are not marked as searched during a Deezer outage.
    """

    def __init__(self, status_code: int, path: str):
        self.status_code = status_code
        self.path = path
        super().__init__(f"Deezer API returned {status_code} on {path}")


class BeatportHTTPError(Exception):
    """Beatport returned a non-200 status (e.g. a 403 Cloudflare block/outage).

    Twin of :class:`DeezerHTTPError`: lets callers distinguish a scrape failure
    from a legitimate empty result, so entries are not marked as searched during
    a Beatport outage.
    """

    def __init__(self, status_code: int, path: str):
        self.status_code = status_code
        self.path = path
        super().__init__(f"Beatport returned {status_code} on {path}")


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
        # Beatport scraping runs curl_cffi (a sync client) in a threadpool.
        # The executor width is env-tunable via BEATPORT_CONCURRENCY (SAME env +
        # default 2 as the rate limiter's beatport semaphore — see rate_limiter.py
        # — so executor width and the concurrency cap stay aligned). Default 2 →
        # PROD is unchanged. The LOCAL residential-IP scraper posts it higher.
        bp_concurrency = int(os.environ.get("BEATPORT_CONCURRENCY", "2"))
        # curl_cffi Sessions are NOT thread-safe, so each executor thread gets its
        # OWN session (thread-local) instead of one shared instance. At the default
        # width of 2 this is functionally identical to before — just 2 thread-local
        # sessions rather than 1 shared — and it stays correct when the width is
        # raised above 2. threading.local can't enumerate its per-thread values, so
        # we also track every created session in a lock-guarded list to close them
        # all on exit.
        self._bp_local = threading.local()
        self._bp_sessions: list = []
        self._bp_sessions_lock = threading.Lock()
        self._bp_executor = ThreadPoolExecutor(max_workers=bp_concurrency)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None
        if hasattr(self, "_bp_sessions"):
            with self._bp_sessions_lock:
                for session in self._bp_sessions:
                    try:
                        session.close()
                    except Exception:
                        pass
                self._bp_sessions.clear()
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
        """GET request to Deezer API, rate-limited + retrying. Returns parsed JSON.

        Raises DeezerHTTPError on any non-200 final response, so callers can
        tell an API failure apart from a valid empty result.
        """
        resp = await self._request_with_retry(
            "deezer", "GET", f"{DEEZER_API}{path}", params=params
        )
        if resp.status_code != 200:
            raise DeezerHTTPError(resp.status_code, path)
        return resp.json()

    # ── Beatport ──

    async def beatport_get(self, path: str) -> httpx.Response:
        """GET request to Beatport via curl_cffi in threadpool (bypasses Cloudflare TLS fingerprinting).
        Returns an httpx.Response-compatible object."""
        url = f"{BEATPORT_URL}{path}"
        loop = asyncio.get_event_loop()

        async with self.limiter.acquire("beatport"):

            def _sync_get():
                # Get-or-create a curl_cffi session for THIS executor thread:
                # curl_cffi Sessions are not thread-safe, so each thread owns its
                # own. Track it under the lock so __aexit__ can close them all.
                session = getattr(self._bp_local, "session", None)
                if session is None:
                    session = curl_requests.Session(impersonate="chrome124")
                    with self._bp_sessions_lock:
                        self._bp_sessions.append(session)
                    self._bp_local.session = session
                return session.get(url, timeout=15)

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

    async def download_audio(self, url: str) -> bytes | None:
        """Download an audio file (e.g. a Deezer 30s preview MP3) without rate
        limiting (direct CDN URL). Returns bytes, or None on failure/empty.

        Mirror of :meth:`download_image` minus the tiny-file placeholder guard:
        an audio preview has no placeholder equivalent and a short clip is still
        analyzable, so any non-empty body is returned. A longer timeout than the
        image path accommodates the larger payload (~0.5-1 MB).

        Logs the failure reason (type + message) before swallowing it: the caller
        (`_analyze_one`) only sees ``None`` and counts a silent ``errors``, so
        without this the nightly ~50% failure rate is undiagnosable (is it a CDN
        429, a timeout, a reset?). Kept non-raising so one dead preview never
        aborts a batch."""
        try:
            resp = await self._client.get(url, timeout=30.0)
            resp.raise_for_status()
            return resp.content or None
        except Exception as e:
            logger.warning(
                "preview download failed (%s): %s", type(e).__name__, e
            )
            return None
