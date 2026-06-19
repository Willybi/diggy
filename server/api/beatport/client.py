"""Sync Beatport API v4 client with Redis-cached anonymous JWT."""
import json
import logging
import os
import re
import time

import redis
import requests

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
REDIS_KEY = "beatport:anon_token"
REDIS_TTL = 580  # token lives ~600s, cache with margin

BASE_URL = "https://api.beatport.com/v4"
SCRAPE_URL = "https://www.beatport.com/genre/techno/6/tracks"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

RATE_LIMIT = 1.0


class BeatportClient:
    def __init__(self, redis_client: redis.Redis | None = None):
        self._redis = redis_client or redis.Redis.from_url(REDIS_URL)
        self._last_request_time = 0.0

    def _scrape_token(self) -> str:
        resp = requests.get(
            SCRAPE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not match:
            raise RuntimeError("Beatport: __NEXT_DATA__ not found in page")
        data = json.loads(match.group(1))
        try:
            token = data["props"]["pageProps"]["anonSession"]["access_token"]
        except KeyError as exc:
            raise RuntimeError("Beatport: access_token not found in __NEXT_DATA__") from exc
        return token

    def _get_token(self, force_refresh: bool = False) -> str:
        if not force_refresh:
            cached = self._redis.get(REDIS_KEY)
            if cached:
                return cached.decode()
        token = self._scrape_token()
        self._redis.setex(REDIS_KEY, REDIS_TTL, token)
        return token

    def _get(self, path: str, params: dict | None = None) -> dict:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT:
            time.sleep(RATE_LIMIT - elapsed)

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}

        resp = requests.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=15)
        self._last_request_time = time.monotonic()

        if resp.status_code == 401:
            logger.info("Beatport 401 — refreshing token")
            token = self._get_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = requests.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=15)
            self._last_request_time = time.monotonic()

        resp.raise_for_status()
        return resp.json()

    # ── Public methods ──

    def get_track(self, track_id: int) -> dict:
        return self._get(f"/catalog/tracks/{track_id}/")

    def search_track(self, title: str, artist: str | None = None) -> list[dict]:
        q = f"{artist} {title}" if artist else title
        data = self._get("/catalog/search/", params={"q": q, "type": "tracks", "per_page": 5})
        return data.get("tracks", data.get("results", []))

    def get_track_by_isrc(self, isrc: str) -> dict | None:
        data = self._get("/catalog/tracks/", params={"isrc": isrc})
        results = data.get("results", [data] if "id" in data else [])
        return results[0] if results else None

    def get_artist_tracks(self, artist_id: int, per_page: int = 20) -> list[dict]:
        data = self._get(f"/catalog/artists/{artist_id}/tracks/", params={"per_page": per_page})
        return data.get("results", [])
