"""
Source-agnostic playlist fetch clients for Deezer, TIDAL, and Spotify.
Used by crawl tasks to fetch playlist metadata and tracks.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from workers.rate_limiter import RateLimiter

_limiter = RateLimiter()

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
    owner = (
        creator["name"] if isinstance(creator, dict) and creator.get("name") else None
    )
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
            artist = (
                t.get("artist", {}).get("name")
                if isinstance(t.get("artist"), dict)
                else None
            )
            tracks.append(
                SourceTrack(
                    external_id=str(t["id"]),
                    title=t.get("title", ""),
                    artist=artist,
                    isrc=t.get("isrc") or None,
                    duration_ms=(t.get("duration") or 0) * 1000 or None,
                )
            )
        url = resp.get("next")
    return tracks


def deezer_has_changed(external_id: str, last_crawled_at) -> bool:
    """Check if a Deezer playlist has been modified since last crawl."""
    from datetime import datetime, timezone

    dz_meta = requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=10).json()
    dz_modification_date = dz_meta.get("time_mod") or dz_meta.get("creation_date")

    if not dz_modification_date or not last_crawled_at:
        return True

    last_crawled = datetime.fromisoformat(str(last_crawled_at)).replace(
        tzinfo=timezone.utc
    )
    try:
        dz_mod = datetime.fromtimestamp(int(dz_modification_date), tz=timezone.utc)
    except (ValueError, TypeError):
        dz_mod = datetime.fromisoformat(str(dz_modification_date)).replace(
            tzinfo=timezone.utc
        )

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


def _save_tidal_tokens_to_redis(session):
    """Persist refreshed TIDAL tokens to Redis for cross-restart durability.

    Tokens are stored as a JSON hash at key 'tidal:tokens'. This avoids
    relying on .env (read-only in Docker) or ephemeral env vars.
    """
    from datetime import timezone

    import redis as redis_lib

    try:
        r = redis_lib.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=True,
        )
        expiry_ts = ""
        if session.expiry_time:
            ts = session.expiry_time
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            expiry_ts = str(ts.timestamp())

        r.hset(
            "tidal:tokens",
            mapping={
                "token_type": session.token_type or "Bearer",
                "access_token": session.access_token,
                "refresh_token": session.refresh_token or "",
                "expiry_time": expiry_ts,
            },
        )
        logger.info("TIDAL tokens saved to Redis after refresh")
    except Exception as e:
        logger.warning("Failed to save TIDAL tokens to Redis: %s", e)


def _try_refresh_tidal(session) -> bool:
    """Attempt to refresh an expired TIDAL session and persist new tokens."""
    if not session.refresh_token:
        return False
    try:
        session.token_refresh(session.refresh_token)
        if session.check_login():
            _save_tidal_tokens_to_redis(session)
            logger.info("TIDAL token refreshed successfully")
            return True
    except Exception as e:
        logger.warning("TIDAL token refresh failed: %s", e)
    return False


def _load_tidal_tokens_from_redis():
    """Load TIDAL tokens from Redis (persisted after last refresh)."""
    import redis as redis_lib

    try:
        r = redis_lib.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=True,
        )
        tokens = r.hgetall("tidal:tokens")
        if tokens and tokens.get("access_token"):
            return tokens
    except Exception:
        pass
    return None


def _get_tidal_session():
    """Load TIDAL session with automatic token refresh.

    Resolution order:
    1. Redis (tokens persisted from last successful refresh)
    2. Env vars (initial bootstrap from .env on VPS)
    3. Token file (dev fallback)

    If tokens are expired, attempts refresh via tidalapi and persists
    new tokens to Redis for subsequent calls.
    """
    import tidalapi

    session = tidalapi.Session()

    # 1. Try Redis first (refreshed tokens survive container restarts)
    redis_tokens = _load_tidal_tokens_from_redis()
    if redis_tokens:
        session.load_oauth_session(
            token_type=redis_tokens.get("token_type", "Bearer"),
            access_token=redis_tokens["access_token"],
            refresh_token=redis_tokens.get("refresh_token") or None,
            expiry_time=_parse_expiry(redis_tokens.get("expiry_time")),
        )
        if session.check_login():
            return session
        logger.info("TIDAL Redis tokens expired, attempting refresh")
        if _try_refresh_tidal(session):
            return session

    # 2. Try env vars (production bootstrap)
    access_token = os.environ.get("TIDAL_ACCESS_TOKEN")
    if access_token:
        session.load_oauth_session(
            token_type=os.environ.get("TIDAL_TOKEN_TYPE", "Bearer"),
            access_token=access_token,
            refresh_token=os.environ.get("TIDAL_REFRESH_TOKEN"),
            expiry_time=_parse_expiry(os.environ.get("TIDAL_EXPIRY")),
        )
        if session.check_login():
            _save_tidal_tokens_to_redis(session)
            return session
        logger.info("TIDAL env var tokens expired, attempting refresh")
        if _try_refresh_tidal(session):
            return session

    # 3. Fallback: token file (dev) — path overridable to point outside the repo
    token_file = Path(
        os.environ.get(
            "TIDAL_TOKEN_FILE",
            str(Path(__file__).parent.parent / "scripts" / ".tidal_tokens.json"),
        )
    )
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
        logger.info("TIDAL token file expired, attempting refresh")
        if _try_refresh_tidal(session):
            return session

    raise RuntimeError(
        "TIDAL: no valid session. Re-run test_sources.py tidal or set TIDAL env vars."
    )


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
        with _limiter.acquire_sync("tidal"):
            artist_name = t.artist.name if t.artist else None
            tracks.append(
                SourceTrack(
                    external_id=str(t.id),
                    title=t.name,
                    artist=artist_name,
                    isrc=getattr(t, "isrc", None),
                    duration_ms=(t.duration or 0) * 1000 or None,
                )
            )
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

    last_crawled = datetime.fromisoformat(str(last_crawled_at)).replace(
        tzinfo=timezone.utc
    )
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
            tracks.append(
                SourceTrack(
                    external_id=t.id,
                    title=t.name,
                    artist=artist_name,
                    isrc=None,  # not available via spotifyscraper
                    duration_ms=t.duration_ms,
                )
            )
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
