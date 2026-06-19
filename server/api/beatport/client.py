"""Sync Beatport client — scrapes search pages for track metadata.

Beatport's API v4 requires auth that isn't available to server-side scrapers.
Instead, we scrape the Next.js SSR pages which embed full track data in
__NEXT_DATA__ → dehydratedState.
"""
import json
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.beatport.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
RATE_LIMIT = 1.5  # seconds between page scrapes (conservative)

# Beatport key_name → Camelot notation
_KEY_TO_CAMELOT = {
    "Ab Minor": "1A", "B Major": "1B",
    "Eb Minor": "2A", "F# Major": "2B", "Gb Major": "2B",
    "Bb Minor": "3A", "Db Major": "3B",
    "F Minor": "4A", "Ab Major": "4B",
    "C Minor": "5A", "Eb Major": "5B",
    "G Minor": "6A", "Bb Major": "6B",
    "D Minor": "7A", "F Major": "7B",
    "A Minor": "8A", "C Major": "8B",
    "E Minor": "9A", "G Major": "9B",
    "B Minor": "10A", "D Major": "10B",
    "F# Minor": "11A", "Gb Minor": "11A", "A Major": "11B",
    "Db Minor": "12A", "C# Minor": "12A", "E Major": "12B",
    "G# Minor": "12A",  # enharmonic alias
}


def _key_to_camelot(key_name: str | None) -> str | None:
    """Convert Beatport key_name (e.g. 'Ab Minor') to Camelot (e.g. '1A')."""
    if not key_name:
        return None
    return _KEY_TO_CAMELOT.get(key_name)


def _normalize_track(raw: dict) -> dict:
    """Normalize a scrape-format track to a consistent dict for enrich.py."""
    label_obj = raw.get("label") or {}
    genre_list = raw.get("genre") or []
    release = raw.get("release") or {}
    publish = raw.get("publish_date") or ""

    return {
        "id": raw.get("track_id"),
        "name": raw.get("track_name"),
        "mix_name": raw.get("mix_name"),
        "bpm": raw.get("bpm"),
        "key": _key_to_camelot(raw.get("key_name")),
        "isrc": raw.get("isrc"),
        "label": {"name": label_obj.get("label_name")} if label_obj.get("label_name") else None,
        "genre": {"name": genre_list[0]["genre_name"]} if genre_list else None,
        "release": {
            "name": release.get("release_name"),
            "label": {"name": label_obj.get("label_name")} if label_obj.get("label_name") else None,
            "image": {
                "dynamic_uri": release.get("release_image_dynamic_uri"),
            },
        },
        "publish_date": publish[:10] if publish else None,
        "length_ms": raw.get("length"),
    }


class BeatportClient:
    def __init__(self):
        self._last_request_time = 0.0

    def _scrape_page(self, path: str) -> dict:
        """Fetch a Beatport page and extract __NEXT_DATA__ JSON."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT:
            time.sleep(RATE_LIMIT - elapsed)

        url = f"{BASE_URL}{path}"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        self._last_request_time = time.monotonic()
        resp.raise_for_status()

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not match:
            raise RuntimeError(f"Beatport: __NEXT_DATA__ not found on {path}")
        return json.loads(match.group(1))

    def _extract_queries(self, data: dict) -> list[dict]:
        """Extract dehydratedState queries from __NEXT_DATA__."""
        return (
            data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

    # ── Public methods ──

    def search_track(self, title: str, artist: str | None = None) -> list[dict]:
        """Search Beatport for tracks by title+artist. Returns normalized dicts."""
        q = f"{artist} {title}" if artist else title
        data = self._scrape_page(f"/search?q={requests.utils.quote(q)}&type=tracks")

        for query in self._extract_queries(data):
            state = query.get("state", {}).get("data", {})
            if isinstance(state, dict) and "tracks" in state:
                tracks_data = state["tracks"]
                raw_list = tracks_data.get("data", []) if isinstance(tracks_data, dict) else []
                return [_normalize_track(t) for t in raw_list[:10]]
        return []

    def search_track_by_isrc(self, isrc: str) -> dict | None:
        """Search Beatport using ISRC as query. Returns first match or None."""
        results = self.search_track(isrc)
        for t in results:
            if t.get("isrc") == isrc:
                return t
        return None
