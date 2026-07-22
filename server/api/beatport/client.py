"""Sync Beatport client — scrapes search pages for track metadata.

Beatport's API v4 requires auth that isn't available to server-side scrapers.
Instead, we scrape the Next.js SSR pages which embed full track data in
__NEXT_DATA__ → dehydratedState.
"""

import json
import logging
import re
import time
import unicodedata

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
    "Ab Minor": "1A",
    "G# Minor": "1A",
    "B Major": "1B",
    "Cb Major": "1B",
    "Eb Minor": "2A",
    "D# Minor": "2A",
    "F# Major": "2B",
    "Gb Major": "2B",
    "Bb Minor": "3A",
    "A# Minor": "3A",
    "Db Major": "3B",
    "C# Major": "3B",
    "F Minor": "4A",
    "Ab Major": "4B",
    "G# Major": "4B",
    "C Minor": "5A",
    "Eb Major": "5B",
    "D# Major": "5B",
    "G Minor": "6A",
    "Bb Major": "6B",
    "A# Major": "6B",
    "D Minor": "7A",
    "F Major": "7B",
    "E# Major": "7B",
    "A Minor": "8A",
    "C Major": "8B",
    "E Minor": "9A",
    "Fb Minor": "9A",
    "G Major": "9B",
    "B Minor": "10A",
    "Cb Minor": "10A",
    "D Major": "10B",
    "F# Minor": "11A",
    "Gb Minor": "11A",
    "A Major": "11B",
    "C# Minor": "12A",
    "Db Minor": "12A",
    "E Major": "12B",
    "Fb Major": "12B",
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
        "artists": [
            {"id": a.get("artist_id"), "name": a.get("artist_name")}
            for a in (raw.get("artists") or [])
        ],
        "bpm": raw.get("bpm"),
        "key": _key_to_camelot(raw.get("key_name")),
        "isrc": raw.get("isrc"),
        "label": {"name": label_obj.get("label_name")}
        if label_obj.get("label_name")
        else None,
        "genre": {"name": genre_list[0]["genre_name"]} if genre_list else None,
        "release": {
            "name": release.get("release_name"),
            "label": {"name": label_obj.get("label_name")}
            if label_obj.get("label_name")
            else None,
            "image": {
                "dynamic_uri": release.get("release_image_dynamic_uri"),
            },
        },
        "publish_date": publish[:10] if publish else None,
        "length_ms": raw.get("length"),
    }


def _normalize_release_page_track(raw: dict) -> dict:
    """Normalize a track from a release page (different field names than search)."""
    release = raw.get("release") or {}
    release_label = release.get("label") or {}
    genre_obj = raw.get("genre") or {}
    key_obj = raw.get("key") or {}

    # Build Camelot key from structured key object
    camelot = None
    if key_obj.get("camelot_number") and key_obj.get("camelot_letter"):
        camelot = f"{key_obj['camelot_number']}{key_obj['camelot_letter']}"

    release_image = release.get("image") or {}

    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "mix_name": raw.get("mix_name"),
        "artists": [
            {"id": a.get("id"), "name": a.get("name")}
            for a in (raw.get("artists") or [])
        ],
        "bpm": raw.get("bpm"),
        "key": camelot,
        "isrc": raw.get("isrc"),
        "label": {"name": release_label.get("name")}
        if release_label.get("name")
        else None,
        "genre": {"name": genre_obj.get("name")} if genre_obj.get("name") else None,
        "release": {
            "name": release.get("name"),
            "label": {"name": release_label.get("name")}
            if release_label.get("name")
            else None,
            "image": {
                "dynamic_uri": release_image.get("dynamic_uri"),
            },
        },
        "publish_date": (raw.get("publish_date") or "")[:10] or None,
        "length_ms": raw.get("length_ms"),
    }


_ARTIST_SEPARATORS = re.compile(
    r"\s*(?:,\s*|\s+&\s+|\s+feat\.?\s+|\s+ft\.?\s+|\s+x\s+|\s+vs\.?\s+)", re.IGNORECASE
)


def _fold(s: str) -> str:
    """Lowercase + strip diacritics for accent-insensitive comparison."""
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _artist_matches(bp_artists: list[dict], catalog_artist: str | None) -> bool:
    """Check if at least one Beatport artist matches the catalog artist string."""
    if not catalog_artist:
        return True
    if not bp_artists:
        return False
    catalog_names = [
        _fold(n.strip()) for n in _ARTIST_SEPARATORS.split(catalog_artist) if n.strip()
    ]
    bp_names = [_fold(a["name"]) for a in bp_artists if a.get("name")]
    for cat in catalog_names:
        for bp in bp_names:
            if cat in bp or bp in cat:
                return True
    return False


def _title_matches(bp_name: str | None, catalog_title: str | None) -> bool:
    """Check if a Beatport track name matches the catalog title (substring)."""
    if not catalog_title or not bp_name:
        return False
    cat = _fold(catalog_title)
    bp = _fold(bp_name)
    return cat in bp or bp in cat


def _release_title_matches(bp_track: dict, catalog_title: str | None) -> bool:
    """Strict, remix-aware title match for the release fallback (Strategy 3).

    A Beatport release shares ONE ``beatport_id`` across its whole tracklist, so
    picking the wrong track out of an EP stamps that id onto a DISTINCT recording
    (the X1 root cause: 94% of beatport_id groups span distinct recordings).
    Unlike the substring ``_title_matches`` (used only AFTER an artist-validated
    track search), this requires the normalized titles to be EQUAL. Version
    markers (remix/edit/extended/…) survive ``normalize_track_title`` while
    feat/original-mix noise is stripped, so an original never matches its remix
    and vice-versa. Beatport keeps the version in a separate ``mix_name`` field,
    so the full title is reconstructed before normalizing.
    """
    from workers.catalog_merge import normalize_track_title

    if not catalog_title:
        return False
    bp_name = bp_track.get("name")
    if not bp_name:
        return False
    mix = (bp_track.get("mix_name") or "").strip()
    full = f"{bp_name} ({mix})" if mix else bp_name
    return normalize_track_title(full) == normalize_track_title(catalog_title)


def _pick_best_track(
    results: list[dict], catalog_artist: str | None, catalog_title: str | None = None
) -> dict | None:
    """Return the first result matching both artist and title."""
    for t in results:
        if not _artist_matches(t.get("artists", []), catalog_artist):
            continue
        if catalog_title and not _title_matches(t.get("name"), catalog_title):
            continue
        return t
    return None


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
                raw_list = (
                    tracks_data.get("data", []) if isinstance(tracks_data, dict) else []
                )
                return [_normalize_track(t) for t in raw_list[:10]]
        return []

    def search_track_by_isrc(self, isrc: str) -> dict | None:
        """Search Beatport using ISRC as query. Returns first match or None."""
        results = self.search_track(isrc)
        for t in results:
            if t.get("isrc") == isrc:
                return t
        return None

    def search_releases(self, title: str, artist: str | None = None) -> list[dict]:
        """Search Beatport releases. Returns normalized release dicts."""
        q = f"{artist} {title}" if artist else title
        data = self._scrape_page(f"/search?q={requests.utils.quote(q)}&type=releases")

        for query in self._extract_queries(data):
            state = query.get("state", {}).get("data", {})
            if isinstance(state, dict) and "releases" in state:
                releases_data = state["releases"]
                raw_list = (
                    releases_data.get("data", [])
                    if isinstance(releases_data, dict)
                    else []
                )
                return [
                    {
                        "id": r.get("release_id"),
                        "name": r.get("release_name"),
                        "slug": re.sub(
                            r"[^a-z0-9]+", "-", (r.get("release_name") or "").lower()
                        ).strip("-"),
                        "artists": [
                            {"id": a.get("artist_id"), "name": a.get("artist_name")}
                            for a in (r.get("artists") or [])
                        ],
                        "tracks": [
                            {"id": t.get("track_id"), "name": t.get("track_name")}
                            for t in (r.get("tracks") or [])
                        ],
                    }
                    for r in raw_list[:10]
                ]
        return []

    def get_release_tracks(self, release_name: str, release_id: int) -> list[dict]:
        """Scrape a release page to get full track details."""
        slug = re.sub(r"[^a-z0-9]+", "-", release_name.lower()).strip("-")
        data = self._scrape_page(f"/release/{slug}/{release_id}")

        for query in self._extract_queries(data):
            state = query.get("state", {}).get("data", {})
            if isinstance(state, dict) and "results" in state:
                return [_normalize_release_page_track(t) for t in state["results"]]
        return []

    def search_release_fallback(
        self, title: str, artist: str | None = None
    ) -> dict | None:
        """Search releases, filter by artist, scrape release page for full track data.

        Only returns a track whose title matches (remix-aware) the requested one;
        a release track that does not match is never returned — not even when the
        release holds a single track, so the shared release ``beatport_id`` is
        never stamped onto the wrong recording.
        """
        releases = self.search_releases(title, artist)
        for rel in releases:
            if not _artist_matches(rel.get("artists", []), artist):
                continue
            tracks = self.get_release_tracks(rel["name"], rel["id"])
            for t in tracks:
                if _release_title_matches(t, title):
                    return t
        return None

    def search_track_validated(
        self, title: str, artist: str | None = None
    ) -> dict | None:
        """Search tracks with artist validation, falling back to releases."""
        # Strategy 1: track search with artist + title matching
        results = self.search_track(title, artist)
        match = _pick_best_track(results, artist, title)
        if match:
            return match

        # Strategy 2: release fallback
        return self.search_release_fallback(title, artist)
