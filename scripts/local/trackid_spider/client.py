"""Sync, strictly rate-limited HTTP client for the TrackID.net listing API.

STRICT 1 req/s, NO parallelism — the TrackID fair-use policy depends on it. The
same throttle gate as ``server/api/trackid/client.py`` but synchronous (this
spider is single-threaded by design) and with exponential backoff.

Errors:
  * 429 / 5xx / transport errors  -> retried with exponential backoff
  * other 4xx                     -> raised immediately (a bad request won't heal)
  * retries exhausted             -> PersistentHTTPError (caller marks failed)

The clock (``monotonic``) and ``sleep`` are injectable so tests run instantly and
without real waits; ``transport`` accepts an ``httpx.MockTransport`` so tests hit
no network.
"""

import time

import httpx

BASE_URL = "https://trackid.net/api/public/audiostreams"

# Reuse the exact browser-like headers the server client sends.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://trackid.net",
    "Referer": "https://trackid.net/",
}

# Confirmed against the real API 2026-08-26: pageSize is hard-capped at 100
# server-side (200/500/1000 all return 100), so 100 is the efficient ceiling.
PAGE_SIZE_MAX = 100
RATE_LIMIT = 1.0
TIMEOUT = 20.0
MAX_RETRIES = 5
BACKOFF_BASE = 2.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 408, 522, 524})


class PersistentHTTPError(RuntimeError):
    """Raised when a request keeps failing after MAX_RETRIES attempts."""


class ListingClient:
    def __init__(
        self,
        rate_limit=RATE_LIMIT,
        timeout=TIMEOUT,
        max_retries=MAX_RETRIES,
        backoff_base=BACKOFF_BASE,
        transport=None,
        sleep=time.sleep,
        monotonic=time.monotonic,
    ):
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request = 0.0
        self._client = httpx.Client(
            headers=HEADERS, timeout=timeout, transport=transport
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._client.close()

    def _throttle(self):
        """Block until at least ``rate_limit`` seconds since the last request."""
        elapsed = self._monotonic() - self._last_request
        if elapsed < self.rate_limit:
            self._sleep(self.rate_limit - elapsed)

    def _request(self, params):
        """One rate-limited GET with retry/backoff. Returns the parsed ``result``."""
        attempt = 0
        while True:
            self._throttle()
            try:
                resp = self._client.get(BASE_URL, params=params)
                self._last_request = self._monotonic()
                if resp.status_code in RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()  # non-retryable 4xx -> HTTPStatusError
                return resp.json().get("result", {}) or {}
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response else None
                if status not in RETRYABLE_STATUS:
                    # a non-retryable client error won't heal on retry
                    raise PersistentHTTPError(
                        f"non-retryable HTTP {status} for params={params}"
                    ) from exc
                attempt = self._backoff_or_fail(attempt, params, exc)
            except httpx.TransportError as exc:
                attempt = self._backoff_or_fail(attempt, params, exc)

    def _backoff_or_fail(self, attempt, params, exc):
        attempt += 1
        if attempt > self.max_retries:
            raise PersistentHTTPError(
                f"failed after {self.max_retries} retries for params={params}: {exc}"
            ) from exc
        self._sleep(self.backoff_base**attempt)
        return attempt

    @staticmethod
    def _params(min_added_on, max_added_on, page, page_size, styles):
        params = {"pageSize": page_size, "currentPage": page}
        if min_added_on:
            params["minAddedOn"] = min_added_on
        if max_added_on:
            params["maxAddedOn"] = max_added_on
        if styles:
            params["styles"] = styles
        return params

    def fetch(
        self,
        min_added_on=None,
        max_added_on=None,
        page=0,
        page_size=PAGE_SIZE_MAX,
        styles=None,
    ):
        """Fetch one listing page. Returns ``(items, row_count)``.

        ``row_count`` is the GLOBAL count for the (windowed) query — it is
        returned even at ``page 0`` without consuming the pages, which is what
        makes the volumetry pre-scan (a pageSize=1 probe) nearly free.
        """
        result = self._request(
            self._params(min_added_on, max_added_on, page, page_size, styles)
        )
        return result.get("audiostreams", []) or [], int(result.get("rowCount", 0))

    def count(self, min_added_on=None, max_added_on=None, styles=None):
        """Cheap windowed rowCount probe (one pageSize=1 request)."""
        _items, row_count = self.fetch(
            min_added_on, max_added_on, page=0, page_size=1, styles=styles
        )
        return row_count
