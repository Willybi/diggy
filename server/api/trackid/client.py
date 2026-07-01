"""Async client for TrackID.net public API."""

import asyncio
import time

import httpx

from .parsing import parse_timespan_to_ms


class TrackIDClient:
    BASE_URL = "https://trackid.net/api/public"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://trackid.net",
        "Referer": "https://trackid.net/",
    }
    RATE_LIMIT = 1.0  # seconds between requests
    TIMEOUT = 15.0

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owns_client = client is None
        self._last_request_time = 0.0

    async def __aenter__(self):
        if self._owns_client:
            self._client = httpx.AsyncClient(headers=self.HEADERS, timeout=self.TIMEOUT)
        return self

    async def __aexit__(self, *args):
        if self._owns_client and self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Rate-limited GET request."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.RATE_LIMIT:
            await asyncio.sleep(self.RATE_LIMIT - elapsed)

        resp = await self._client.get(f"{self.BASE_URL}{path}", params=params)
        self._last_request_time = time.monotonic()
        resp.raise_for_status()
        return resp.json()

    async def search_sets(
        self,
        keywords: str | None = None,
        channel: str | None = None,
        styles: str | None = None,
        music_track_id: int | None = None,
        page_size: int = 20,
        current_page: int = 0,
        sort_field: str | None = None,
        sort_direction: str | None = None,
    ) -> tuple[list[dict], int]:
        """Search audiostreams. Returns (audiostreams, total_count)."""
        params = {"pageSize": page_size, "currentPage": current_page}
        if keywords:
            params["keywords"] = keywords
        if channel:
            params["channel"] = channel
        if styles:
            params["styles"] = styles
        if music_track_id is not None:
            params["musicTrackId"] = music_track_id
        if sort_field:
            params["sortField"] = sort_field
        if sort_direction:
            params["sortDirection"] = sort_direction

        data = await self._get("/audiostreams", params)
        result = data.get("result", {})
        return result.get("audiostreams", []), result.get("rowCount", 0)

    async def get_set_detail(self, slug: str) -> dict:
        """Get full audiostream detail with tracklist."""
        data = await self._get(f"/audiostreams/{slug}")
        return data.get("result", {})

    async def search_tracks(
        self,
        keywords: str,
        page_size: int = 20,
        current_page: int = 0,
    ) -> tuple[list[dict], int]:
        """Search music tracks. Returns (tracks, total_count)."""
        params = {
            "keywords": keywords,
            "pageSize": page_size,
            "currentPage": current_page,
        }
        data = await self._get("/musictracks", params)
        result = data.get("result", {})
        return result.get("musicTracks", []), result.get("rowCount", 0)

    async def get_styles(self) -> list[dict]:
        """Get all available styles/genres."""
        data = await self._get("/styles")
        return data.get("result", [])

    def merge_tracklist(self, detail: dict) -> list[dict]:
        """Merge all detectionProcesses, deduplicate on musicTrackId, sort by startTime."""
        seen = {}
        for process in detail.get("detectionProcesses", []):
            for track in process.get("detectionProcessMusicTracks", []):
                mtid = track.get("musicTrackId")
                if mtid is None:
                    continue
                if mtid not in seen:
                    seen[mtid] = track
                else:
                    # Keep the one with earliest startTime
                    existing_ms = parse_timespan_to_ms(seen[mtid].get("startTime"))
                    new_ms = parse_timespan_to_ms(track.get("startTime"))
                    if new_ms is not None and (
                        existing_ms is None or new_ms < existing_ms
                    ):
                        seen[mtid] = track

        tracks = list(seen.values())
        tracks.sort(key=lambda t: parse_timespan_to_ms(t.get("startTime")) or 0)
        return tracks
