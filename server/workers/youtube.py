"""Low-level YouTube client for the DJ-set watch (C14.b, YouTube-first slice).

Pure/async building blocks — NO Celery, NO beat, NO lock, NO endpoint. The admin
router (add-by-URL) and the nightly watch task (L5) compose these. HTTP goes
through an INJECTED ``httpx.AsyncClient`` so every core is unit-testable with a
mock; the only convenience factory that creates a client is :func:`default_client`,
kept separate so the cores stay injectable.

Network cores + pure helpers:

- :func:`parse_channel_feed` (PURE) — parse a channel Atom feed into video dicts.
- :func:`fetch_channel_feed` — GET the ``videos.xml`` Atom feed + parse.
- :func:`fetch_video_durations` — YouTube Data API ``videos.list`` → seconds map.
- :func:`uploads_playlist_id` (PURE) — a « UC… » channel id → its « UU… » uploads
  playlist id (no network — a documented YouTube invariant).
- :func:`fetch_channel_uploads` — page the uploads playlist (``playlistItems.list``)
  for the one-shot historical backfill (L7), video dicts shaped like the feed.
- :func:`resolve_channel_id` — a URL/handle → the « UC… » channel id.
- :func:`find_duplicate_set` — ultra-conservative cross-source set dedup.
- :func:`upsert_youtube_set` — dedup-then-upsert a metadata-only YouTube ``DJSet``.

Guiding rule, mirroring the rest of the pipeline (project invariant #4 — err
toward separation): the dedup only skips creation on a match of VERY high
confidence; anything less creates a fresh row (a duplicate is cheap storage, a
bad merge is corruption). And, like :class:`~workers.async_http.DeezerHTTPError`,
an HTTP failure raises a typed error and stamps nothing.
"""

import logging
import os
import re
from datetime import datetime, timezone

import httpx
from defusedxml.ElementTree import fromstring as _xml_fromstring
from models import DJSet
from services.set_dedup_service import normalize_set_title, token_set_ratio
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils import search_fold
from workers.set_title_meta import canonicalize_channel, extract_event_date

logger = logging.getLogger(__name__)

# ── Endpoints & constants ────────────────────────────────────────────────────

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml"
YOUTUBE_DATA_API = "https://www.googleapis.com/youtube/v3"

# Atom + YouTube + Media RSS namespaces used by the channel feed.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_YT_NS = "{http://www.youtube.com/xml/schemas/2015}"
_MEDIA_NS = "{http://search.yahoo.com/mrss/}"

# A YouTube video's thumbnails and its watch page reuse the video id; sets are
# stored metadata-only (no SetTrack), so the same bucket as the TrackID importer.
YOUTUBE_SET_ARTWORK_BUCKET = "set-artworks"

# Data API videos.list caps at 50 ids per call.
_MAX_IDS_PER_CALL = 50

# One-shot historical backfill (L7) cap: how many uploads to page back through the
# channel's « uploads » playlist at add time. Env-tunable; the task passes it to
# :func:`fetch_channel_uploads`.
YOUTUBE_BACKFILL_MAX_VIDEOS = int(os.environ.get("YOUTUBE_BACKFILL_MAX_VIDEOS", "500"))

# A YouTube upload only counts as a DJ set past this duration (env-tunable); the
# GATE itself is applied by the L5 task via :func:`is_set_duration`.
YOUTUBE_MIN_SET_DURATION_SECONDS = int(
    os.environ.get("YOUTUBE_MIN_SET_DURATION_SECONDS", "1800")
)

# Cross-source dedup title threshold — high on purpose (see find_duplicate_set).
YOUTUBE_DEDUP_TITLE_RATIO = float(os.environ.get("YOUTUBE_DEDUP_TITLE_RATIO", "0.8"))

# Callers' canonical default key; the cores take the key as an explicit arg so no
# core reads the env implicitly.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# httpx defaults, aligned with async_http.py.
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "20.0"))
HTTP_CONNECT_TIMEOUT = float(os.environ.get("HTTP_CONNECT_TIMEOUT", "10.0"))

# ── Regexes ──────────────────────────────────────────────────────────────────

# ISO-8601 duration, YouTube form (P#DT#H#M#S). The whole time part is optional
# so a currently-airing live stream's "P0D" parses to 0 rather than failing.
_RE_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)
# A « UC… » channel id is UC + 22 base64url chars.
_RE_CHANNEL_URL = re.compile(r"/channel/(UC[\w-]{22})")
_RE_RAW_UC = re.compile(r"^UC[\w-]{22}$")
# @handle anywhere (with or without the youtube.com/ prefix).
_RE_HANDLE = re.compile(r"@([A-Za-z0-9_.\-]+)")
# /c/name or /user/name legacy path.
_RE_C_PATH = re.compile(
    r"youtube\.com/(?:c|user)/([A-Za-z0-9_.\-]+)", re.IGNORECASE
)


class YouTubeHTTPError(Exception):
    """YouTube (feed or Data API) returned a non-200 status.

    Twin of :class:`~workers.async_http.DeezerHTTPError`: lets callers tell a
    feed/API failure apart from a legitimate empty result, so nothing is stamped
    during an outage.
    """

    def __init__(self, status_code: int, context: str):
        self.status_code = status_code
        self.context = context
        super().__init__(f"YouTube returned {status_code} on {context}")


# ── Pure helpers ─────────────────────────────────────────────────────────────


def _parse_atom_datetime(raw: str | None) -> datetime | None:
    """Parse an Atom ``published`` timestamp to an aware ``datetime`` or ``None``.

    YouTube emits RFC-3339 with a numeric offset ("2021-12-25T18:30:00+00:00");
    a trailing ``Z`` is normalised for ``fromisoformat``. A malformed value
    yields ``None`` (never raises).
    """
    if not raw:
        return None
    txt = raw.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(txt)
    except ValueError:
        return None


# YouTube thumbnails, best-resolution first.
_THUMBNAIL_PREFERENCE = ("maxres", "standard", "high", "medium", "default")


def _best_thumbnail(thumbnails) -> str | None:
    """Pick the highest-resolution thumbnail URL from a Data API ``thumbnails`` map.

    A ``playlistItems`` snippet exposes ``thumbnails`` as a dict keyed by size
    (default/medium/high/standard/maxres), unlike the Atom feed's single URL.
    Returns the best available URL, or ``None`` when absent/malformed.
    """
    if not isinstance(thumbnails, dict):
        return None
    for key in _THUMBNAIL_PREFERENCE:
        thumb = thumbnails.get(key)
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]
    return None


def parse_channel_feed(xml_bytes) -> list[dict]:
    """Parse a channel Atom feed into a list of video dicts (PURE, defusedxml).

    Each dict is ``{video_id, title, published (datetime|None), thumbnail_url}``.
    Entries without a ``yt:videoId`` are skipped (malformed). Accepts ``bytes``
    or ``str``.
    """
    root = _xml_fromstring(xml_bytes)
    out: list[dict] = []
    for entry in root.iter(f"{_ATOM_NS}entry"):
        video_id = entry.findtext(f"{_YT_NS}videoId")
        if not video_id:
            continue
        title = entry.findtext(f"{_ATOM_NS}title")
        published = _parse_atom_datetime(entry.findtext(f"{_ATOM_NS}published"))
        thumbnail_url = None
        group = entry.find(f"{_MEDIA_NS}group")
        if group is not None:
            thumb = group.find(f"{_MEDIA_NS}thumbnail")
            if thumb is not None:
                thumbnail_url = thumb.get("url")
        out.append(
            {
                "video_id": video_id,
                "title": title,
                "published": published,
                "thumbnail_url": thumbnail_url,
            }
        )
    return out


def parse_iso8601_duration(iso: str | None) -> int | None:
    """Parse an ISO-8601 duration ("PT1H30M15S") to whole seconds, else ``None``.

    Handles the YouTube ``P#DT#H#M#S`` shape (days included) and the live-stream
    ``P0D`` → 0. An unparseable value returns ``None``.
    """
    if not iso:
        return None
    m = _RE_ISO_DURATION.match(iso.strip())
    if not m:
        return None
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def is_set_duration(seconds: int | None) -> bool:
    """True when ``seconds`` clears :data:`YOUTUBE_MIN_SET_DURATION_SECONDS`.

    The duration GATE the L5 task applies to keep only full sets (not shorts /
    clips). ``None`` (unknown duration) is treated as NOT a set.
    """
    return seconds is not None and seconds >= YOUTUBE_MIN_SET_DURATION_SECONDS


def watch_url(video_id: str) -> str:
    """Canonical watch URL for a video id."""
    return f"https://www.youtube.com/watch?v={video_id}"


def default_client() -> httpx.AsyncClient:
    """Convenience ``httpx.AsyncClient`` for callers that don't inject one.

    The cores take an INJECTED client (mockable in tests); this factory exists
    only so the router/task have a sane default in prod. Kept separate so no
    core creates hidden I/O.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(HTTP_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT),
        follow_redirects=True,
    )


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ── Network cores (injected client) ──────────────────────────────────────────


async def fetch_channel_feed(client: httpx.AsyncClient, channel_id: str) -> list[dict]:
    """GET a channel's Atom feed and parse it into video dicts.

    Raises :class:`YouTubeHTTPError` on a non-200 (stamps nothing).
    """
    resp = await client.get(YOUTUBE_FEED_URL, params={"channel_id": channel_id})
    if resp.status_code != 200:
        raise YouTubeHTTPError(resp.status_code, f"feed:{channel_id}")
    return parse_channel_feed(resp.content)


async def fetch_video_durations(
    client: httpx.AsyncClient, video_ids, api_key: str
) -> dict[str, int]:
    """Return ``{video_id: duration_seconds}`` via the Data API ``videos.list``.

    Batches ≤50 ids per call and parses ``contentDetails.duration``. A falsy
    ``api_key`` degrades gracefully to ``{}`` (logs a warning, never raises) so a
    missing key never crashes the caller. A non-200 raises
    :class:`YouTubeHTTPError`.
    """
    if not api_key:
        logger.warning(
            "fetch_video_durations: no YouTube Data API key — skipping durations"
        )
        return {}
    ids = [v for v in (video_ids or []) if v]
    if not ids:
        return {}
    out: dict[str, int] = {}
    for batch in _chunks(ids, _MAX_IDS_PER_CALL):
        resp = await client.get(
            f"{YOUTUBE_DATA_API}/videos",
            params={
                "part": "contentDetails",
                "id": ",".join(batch),
                "key": api_key,
            },
        )
        if resp.status_code != 200:
            raise YouTubeHTTPError(resp.status_code, "videos.list")
        for item in resp.json().get("items", []):
            vid = item.get("id")
            iso = (item.get("contentDetails") or {}).get("duration")
            secs = parse_iso8601_duration(iso)
            if vid and secs is not None:
                out[vid] = secs
    return out


def uploads_playlist_id(channel_id: str) -> str:
    """Return the « uploads » playlist id for a « UC… » channel id (PURE, no I/O).

    A YouTube channel's automatic « uploads » playlist reuses the channel id with
    the leading ``UC`` swapped for ``UU`` (a documented YouTube invariant), so no
    API call is needed to find it. The input MUST be a « UC… » channel id — an
    explicit precondition (callers resolve a raw id via :func:`resolve_channel_id`
    first); anything else raises ``ValueError`` rather than silently building a
    bogus playlist id.
    """
    if not channel_id or not channel_id.startswith("UC"):
        raise ValueError(f"not a « UC… » channel id: {channel_id!r}")
    return "UU" + channel_id[2:]


async def fetch_channel_uploads(
    client: httpx.AsyncClient,
    channel_id: str,
    api_key: str,
    *,
    max_videos: int = YOUTUBE_BACKFILL_MAX_VIDEOS,
) -> list[dict]:
    """Page a channel's « uploads » playlist → up to ``max_videos`` video dicts.

    Backs the one-shot historical backfill (L7): where the Atom feed only carries
    the ~15 most recent uploads, the Data API ``playlistItems.list`` on the
    ``UU…`` uploads playlist (:func:`uploads_playlist_id`) walks the whole history,
    most-recent first, paginating on ``nextPageToken`` until ``max_videos`` are
    collected or the playlist ends.

    Each item is mapped to the SAME shape as :func:`parse_channel_feed`
    (``{video_id, title, published (datetime|None), thumbnail_url}``) so
    :func:`upsert_youtube_set` consumes it unchanged. A falsy ``api_key`` degrades
    gracefully to ``[]`` (logs a warning, never raises). A non-200 raises
    :class:`YouTubeHTTPError`. Reaching ``max_videos`` with more uploads still
    pending logs a warning (never a silent truncation).
    """
    if not api_key:
        logger.warning(
            "fetch_channel_uploads: no YouTube Data API key — skipping backfill"
        )
        return []
    playlist_id = uploads_playlist_id(channel_id)
    out: list[dict] = []
    page_token: str | None = None
    while len(out) < max_videos:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": _MAX_IDS_PER_CALL,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = await client.get(f"{YOUTUBE_DATA_API}/playlistItems", params=params)
        if resp.status_code != 200:
            raise YouTubeHTTPError(resp.status_code, "playlistItems.list")
        data = resp.json()
        for item in data.get("items", []):
            snippet = item.get("snippet") or {}
            video_id = (snippet.get("resourceId") or {}).get("videoId")
            if not video_id:
                continue
            out.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title"),
                    "published": _parse_atom_datetime(snippet.get("publishedAt")),
                    "thumbnail_url": _best_thumbnail(snippet.get("thumbnails")),
                }
            )
            if len(out) >= max_videos:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    if page_token and len(out) >= max_videos:
        logger.warning(
            "fetch_channel_uploads: reached max_videos=%d for channel %s "
            "(more uploads remain, not fetched)",
            max_videos,
            channel_id,
        )
    return out


def _extract_handle(text: str) -> str | None:
    """Pull a handle ("@name") or a /c//user/ name out of ``text`` (no network)."""
    m = _RE_HANDLE.search(text)
    if m:
        return "@" + m.group(1)
    m = _RE_C_PATH.search(text)
    if m:
        return m.group(1)
    return None


async def _resolve_by_handle(
    client: httpx.AsyncClient, handle: str, api_key: str
) -> str | None:
    resp = await client.get(
        f"{YOUTUBE_DATA_API}/channels",
        params={"part": "id", "forHandle": handle, "key": api_key},
    )
    if resp.status_code != 200:
        raise YouTubeHTTPError(resp.status_code, "channels.list")
    items = resp.json().get("items", [])
    return items[0].get("id") if items else None


async def _resolve_by_search(
    client: httpx.AsyncClient, query: str, api_key: str
) -> str | None:
    resp = await client.get(
        f"{YOUTUBE_DATA_API}/search",
        params={
            "part": "snippet",
            "type": "channel",
            "q": query,
            "maxResults": 1,
            "key": api_key,
        },
    )
    if resp.status_code != 200:
        raise YouTubeHTTPError(resp.status_code, "search.list")
    items = resp.json().get("items", [])
    if not items:
        return None
    return (items[0].get("id") or {}).get("channelId")


async def resolve_channel_id(
    client: httpx.AsyncClient, url_or_handle: str, api_key: str
) -> str | None:
    """Resolve a channel URL / handle / raw id to a « UC… » channel id, or ``None``.

    A « UC… » id already present (raw, or inside ``/channel/UC…``) is extracted by
    regex WITHOUT any network call. Otherwise a handle (``@name``) or a
    ``/c/``/``/user/`` name is resolved via the Data API (``channels.list``,
    falling back to ``search``). A falsy ``api_key`` with a non-UC input degrades
    gracefully to ``None`` (logs a warning). A non-200 raises
    :class:`YouTubeHTTPError`.
    """
    if not url_or_handle:
        return None
    text = url_or_handle.strip()

    # 1. Direct « UC… » id — no network.
    m = _RE_CHANNEL_URL.search(text)
    if m:
        return m.group(1)
    if _RE_RAW_UC.match(text):
        return text

    # 2. Handle / legacy path → Data API.
    handle = _extract_handle(text)
    if not api_key:
        logger.warning(
            "resolve_channel_id: no API key for non-UC input %r — cannot resolve",
            text,
        )
        return None
    if handle:
        cid = await _resolve_by_handle(client, handle, api_key)
        if cid:
            return cid
    # 3. Last resort: free-text search.
    return await _resolve_by_search(client, handle or text, api_key)


# ── Cross-source dedup + upsert ──────────────────────────────────────────────


def _channel_key(channel: str | None) -> str | None:
    """A canonical, fold-comparable key for a channel, or ``None`` when unknown.

    Runs the raw channel through the C13.e gazetteer canonicaliser, then
    :func:`search_fold` so two spellings of the same channel across sources
    ("Boiler Room" / "boiler room") compare equal.
    """
    canonical = canonicalize_channel(channel)
    if not canonical:
        return None
    return search_fold(canonical) or None


async def find_duplicate_set(
    db: AsyncSession, title: str, channel: str | None, event_date
) -> DJSet | None:
    """Find an existing set (ANY source) that is the SAME performance, or ``None``.

    Ultra-conservative (invariant #4 — err toward separation): the match only
    fires on the CONJUNCTION of three strong gates, so we only ever skip creating
    a fresh row when confidence is very high:

    1. a RELIABLE shared date — ``event_date`` must be present, and a candidate
       matches on ``event_date`` OR (fallback) its historical ``played_date``;
    2. the SAME canonical channel (via :func:`_channel_key`); and
    3. a base-title token overlap ≥ :data:`YOUTUBE_DEDUP_TITLE_RATIO` (0.8),
       computed on :func:`normalize_set_title`'s ``base_title`` (channel/date
       stripped) so cross-source title noise doesn't defeat the match.

    Missing any gate → ``None`` (create a separate row): a duplicate is cheap,
    a bad cross-source merge is corruption. Without a reliable ``event_date`` the
    title alone is too weak to dedup across sources, so we abstain outright.
    """
    if event_date is None:
        return None
    incoming_channel_key = _channel_key(channel)
    if not incoming_channel_key:
        return None
    incoming_base = normalize_set_title(title or "", channel).base_title

    result = await db.execute(
        select(DJSet).where(
            or_(DJSet.event_date == event_date, DJSet.played_date == event_date)
        )
    )
    for cand in result.scalars():
        if _channel_key(cand.channel) != incoming_channel_key:
            continue
        cand_base = normalize_set_title(cand.title or "", cand.channel).base_title
        if token_set_ratio(incoming_base, cand_base) >= YOUTUBE_DEDUP_TITLE_RATIO:
            return cand
    return None


async def upsert_youtube_set(
    db: AsyncSession, *, video: dict, channel_name: str
) -> tuple[DJSet, bool]:
    """Dedup-then-upsert a metadata-only YouTube ``DJSet``. Returns (set, created).

    Cross-source dedup runs first (:func:`find_duplicate_set`): a hit returns
    ``(existing, False)`` and creates nothing. Otherwise the row is upserted on
    ``(external_id=video_id, source='youtube')`` — updated in place if present,
    else added. The set is METADATA-ONLY: no ``SetTrack`` rows. ``duration_ms``
    is taken from ``video`` when the caller (L5) has enriched it. Artwork upload
    from the thumbnail is best-effort (never blocks). The row is flushed so its
    id is available.
    """
    video_id = video["video_id"]
    title = video.get("title") or "Untitled"
    published = video.get("published")
    played_date = published.date() if published else None
    event_date = extract_event_date(title)
    now = datetime.now(timezone.utc)

    # Cross-source dedup — a set already indexed elsewhere is not re-created.
    dup = await find_duplicate_set(db, title, channel_name, event_date)
    if dup is not None:
        return dup, False

    result = await db.execute(
        select(DJSet).where(
            DJSet.external_id == video_id, DJSet.source == "youtube"
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        dj_set = existing
        created = False
    else:
        dj_set = DJSet(
            external_id=video_id,
            source="youtube",
            created_at=now,
        )
        db.add(dj_set)
        created = True

    dj_set.title = title
    dj_set.source_url = watch_url(video_id)
    dj_set.played_date = played_date
    dj_set.duration_ms = video.get("duration_ms")
    dj_set.channel = channel_name
    dj_set.channel_canonical = canonicalize_channel(channel_name)
    dj_set.event_date = event_date
    dj_set.styles = []
    dj_set.search_text = search_fold(title)
    dj_set.last_crawled_at = now

    await db.flush()

    # Artwork best-effort — a failure must never abort the import.
    thumbnail_url = video.get("thumbnail_url")
    if thumbnail_url and not dj_set.has_artwork:
        try:
            from services.image_service import ImageService

            ImageService.ensure_bucket(YOUTUBE_SET_ARTWORK_BUCKET)
            if ImageService.upload_from_url(
                thumbnail_url, YOUTUBE_SET_ARTWORK_BUCKET, f"{dj_set.id}.jpg"
            ):
                dj_set.has_artwork = True
        except Exception:
            logger.warning(
                "youtube artwork upload failed for set %s", dj_set.id, exc_info=True
            )

    return dj_set, created
