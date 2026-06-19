"""
Source-agnostic playlist fetch clients for Deezer, TIDAL, and Spotify.
Used by crawl tasks to fetch playlist metadata and tracks.
"""

import json
import os
import time
import logging
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"


@dataclass
class PlaylistMeta:
    title: str | None = None
    track_count: int | None = None
    owner: str | None = None
    description: str | None = None
    cover_url: str | None = None


@dataclass
class SourceTrack:
    external_id: str
    title: str
    artist: str | None = None
    isrc: str | None = None
    duration_ms: int | None = None


# ──────────────────────────────────────────────────────────────
# Deezer
# ──────────────────────────────────────────────────────────────

def fetch_deezer_meta(external_id: str) -> PlaylistMeta:
    resp = requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=10).json()
    creator = resp.get("creator")
    owner = creator["name"] if isinstance(creator, dict) and creator.get("name") else None
    return PlaylistMeta(
        title=resp.get("title"),
        track_count=resp.get("nb_tracks"),
        owner=owner,
        description=resp.get("description"),
        cover_url=resp.get("picture_big") or resp.get("picture_medium"),
    )


def fetch_deezer_tracks(external_id: str) -> list[SourceTrack]:
    tracks = []
    url = f"{DEEZER_API}/playlist/{external_id}/tracks?limit=100&index=0"
    while url:
        resp = requests.get(url, timeout=10).json()
        for t in resp.get("data", []):
            artist = t.get("artist", {}).get("name") if isinstance(t.get("artist"), dict) else None
            tracks.append(SourceTrack(
                external_id=str(t["id"]),
                title=t.get("title", ""),
                artist=artist,
                isrc=t.get("isrc") or None,
                duration_ms=(t.get("duration") or 0) * 1000 or None,
            ))
        url = resp.get("next")
    return tracks


def deezer_has_changed(external_id: str, last_crawled_at) -> bool:
    """Check if a Deezer playlist has been modified since last crawl."""
    from datetime import datetime, timezone

    dz_meta = requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=10).json()
    dz_modification_date = dz_meta.get("time_mod") or dz_meta.get("creation_date")

    if not dz_modification_date or not last_crawled_at:
        return True

    last_crawled = datetime.fromisoformat(str(last_crawled_at)).replace(tzinfo=timezone.utc)
    try:
        dz_mod = datetime.fromtimestamp(int(dz_modification_date), tz=timezone.utc)
    except (ValueError, TypeError):
        dz_mod = datetime.fromisoformat(str(dz_modification_date)).replace(tzinfo=timezone.utc)

    return dz_mod > last_crawled


# ──────────────────────────────────────────────────────────────
# TIDAL
# ──────────────────────────────────────────────────────────────

def _parse_expiry(value) -> "datetime | None":
    """Parse expiry_time from env var or JSON (datetime string or timestamp)."""
    from datetime import datetime, timezone
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _get_tidal_session():
    """Load TIDAL session from environment variables or token file."""
    import tidalapi

    session = tidalapi.Session()

    # Try env vars first (production)
    access_token = os.environ.get("TIDAL_ACCESS_TOKEN")
    if access_token:
        session.load_oauth_session(
            token_type=os.environ.get("TIDAL_TOKEN_TYPE", "Bearer"),
            access_token=access_token,
            refresh_token=os.environ.get("TIDAL_REFRESH_TOKEN"),
            expiry_time=_parse_expiry(os.environ.get("TIDAL_EXPIRY")),
        )
        if session.check_login():
            return session
        logger.warning("TIDAL env var tokens expired or invalid")

    # Fallback: token file (dev)
    token_file = Path(__file__).parent.parent / "scripts" / ".tidal_tokens.json"
    if token_file.exists():
        tokens = json.loads(token_file.read_text())
        session.load_oauth_session(
            token_type=tokens.get("token_type", "Bearer"),
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expiry_time=_parse_expiry(tokens.get("expiry_time")),
        )
        if session.check_login():
            return session
        logger.warning("TIDAL token file expired")

    raise RuntimeError("TIDAL: no valid session. Re-run test_sources.py tidal or set TIDAL env vars.")


def fetch_tidal_meta(external_id: str) -> PlaylistMeta:
    session = _get_tidal_session()
    playlist = session.playlist(external_id)
    return PlaylistMeta(
        title=playlist.name,
        track_count=playlist.num_tracks,
        owner=getattr(playlist.creator, "name", None) if playlist.creator else None,
        description=playlist.description,
        cover_url=playlist.image(640) if hasattr(playlist, "image") else None,
    )


def fetch_tidal_tracks(external_id: str) -> list[SourceTrack]:
    session = _get_tidal_session()
    playlist = session.playlist(external_id)
    tidal_tracks = playlist.tracks()

    tracks = []
    for t in tidal_tracks:
        artist_name = t.artist.name if t.artist else None
        tracks.append(SourceTrack(
            external_id=str(t.id),
            title=t.name,
            artist=artist_name,
            isrc=getattr(t, "isrc", None),
            duration_ms=(t.duration or 0) * 1000 or None,
        ))
        time.sleep(0.05)  # gentle rate limiting
    return tracks


def tidal_has_changed(external_id: str, last_crawled_at) -> bool:
    """Check if a TIDAL playlist has been modified since last crawl."""
    from datetime import datetime, timezone

    if not last_crawled_at:
        return True

    session = _get_tidal_session()
    playlist = session.playlist(external_id)
    last_updated = getattr(playlist, "last_updated", None)
    if not last_updated:
        return True

    last_crawled = datetime.fromisoformat(str(last_crawled_at)).replace(tzinfo=timezone.utc)
    if isinstance(last_updated, str):
        last_updated = datetime.fromisoformat(last_updated).replace(tzinfo=timezone.utc)
    elif last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    return last_updated > last_crawled


# ──────────────────────────────────────────────────────────────
# Spotify
# ──────────────────────────────────────────────────────────────

def fetch_spotify_meta(external_id: str) -> PlaylistMeta:
    from spotify_scraper import SpotifyClient

    client = SpotifyClient()
    try:
        playlist = client.get_playlist(external_id, max_tracks=0)
        return PlaylistMeta(
            title=playlist.name,
            track_count=playlist.total_tracks,
            owner=playlist.owner.name if playlist.owner else None,
            description=playlist.description,
            cover_url=playlist.images[0].url if playlist.images else None,
        )
    finally:
        client.close()


def fetch_spotify_tracks(external_id: str) -> list[SourceTrack]:
    from spotify_scraper import SpotifyClient

    client = SpotifyClient()
    try:
        playlist = client.get_playlist(external_id, max_tracks=None)
        tracks = []
        for pt in playlist.tracks:
            t = pt.track
            artist_name = t.artists[0].name if t.artists else None
            tracks.append(SourceTrack(
                external_id=t.id,
                title=t.name,
                artist=artist_name,
                isrc=None,  # not available via spotifyscraper
                duration_ms=t.duration_ms,
            ))
        return tracks
    finally:
        client.close()


def spotify_has_changed(external_id: str, last_crawled_at) -> bool:
    """Spotify scraping has no reliable last-modified signal. Always crawl."""
    return True


# ──────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────

_FETCHERS = {
    "deezer": (fetch_deezer_meta, fetch_deezer_tracks, deezer_has_changed),
    "tidal": (fetch_tidal_meta, fetch_tidal_tracks, tidal_has_changed),
    "spotify": (fetch_spotify_meta, fetch_spotify_tracks, spotify_has_changed),
}


def get_fetchers(source: str):
    """Return (fetch_meta, fetch_tracks, has_changed) for a given source."""
    fetchers = _FETCHERS.get(source)
    if not fetchers:
        raise ValueError(f"Unknown source: {source}")
    return fetchers
