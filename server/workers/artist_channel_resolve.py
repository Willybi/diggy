"""Artist → YouTube-channel resolution cascade (C14.b 🅱, L1 — server-side).

The SERVER-SIDE port of the local gate cascade
(``scripts/local/channel_resolve_gate/resolve.py``): given an artist name, resolve
its YouTube channel with a 2-level cascade — official links (auto, high-confidence)
first, then an assisted search fallback (human-confirmed). On-demand only (never a
mass sweep), in-container (the prod YouTube key is restricted to the server's IPv4,
so the search tier ONLY works from the server — by design).

Two precision guards make this trustworthy:

  * an ENTITY guard on Wikidata — a ``P2397`` (YouTube channel id) is trusted ONLY
    when the Wikidata entity actually IS a music entity (``P31`` human/band/ensemble
    OR ``P106`` DJ/musician/composer/producer). A city that happens to carry a
    ``P2397`` (or a generic word) is rejected outright.
  * a fold-match guard on the search fallback — a raw search hit becomes a candidate
    only when its channel title folds-equal-or-contained to the artist name
    (:func:`fold_match`, reusing :func:`workers.artist_names.punct_fold_key`), and a
    "… - Topic" auto-channel (YouTube Music, never real sets) is excluded.

Cascade, stopping at the first that resolves:

  (a) Wikidata    : wbsearchentities → top Q-id → wbgetentities claims → guarded
                    ``P2397``. method="wikidata", confidence="high". Notes ``P3040``
                    (SoundCloud) to size the future SoundCloud volet.
  (b) MusicBrainz : an artist search → url-rels → an official YouTube link →
                    channel id. STRICT 1 req/s. method="musicbrainz",
                    confidence="high". Notes a SoundCloud rel.
  (c) YouTube search (only when ``allow_search`` and an ``api_key`` is set) →
                    filter "- Topic" → verify by :func:`fold_match` →
                    method="search", confidence="NEEDS_VERIFY".

Design, mirroring ``workers/youtube.py``: HTTP goes through INJECTED httpx clients
(mockable in tests, zero real network), each request carries an explicit
User-Agent (Wikidata AND MusicBrainz 403/429 a blank one), and rate is paced by an
INJECTED async ``sleep`` (default :func:`asyncio.sleep`) so tests spend no wall
time. Per-method errors are ISOLATED — a Wikidata outage still lets MusicBrainz and
the search fallback run; :func:`resolve_artist_channel` never raises.
"""

import asyncio
import logging
import os
import re
from urllib.parse import quote

import httpx
from workers.artist_names import punct_fold_key
from workers.youtube import search_channels

logger = logging.getLogger(__name__)

# ── Endpoints & tunables ──────────────────────────────────────────────────────

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"

# Politeness. Wikidata is generous but be gentle; MusicBrainz is a STRICT 1 req/s.
# Env-tunable so an operator can pace an ad-hoc batch without a code change.
WIKIDATA_DELAY = float(os.environ.get("WIKIDATA_RESOLVE_DELAY", "0.5"))
MUSICBRAINZ_DELAY = float(os.environ.get("MUSICBRAINZ_RESOLVE_DELAY", "1.0"))

# A folded name shorter than this is not trusted for an INCLUSION match (a 2-3 char
# fold would trivially match a long channel title). Env-tunable.
SEARCH_FOLD_MIN_LEN = int(os.environ.get("CHANNEL_RESOLVE_FOLD_MIN_LEN", "5"))
# How many YouTube channel hits to verify per name (each search.list costs 100
# quota units — the whole call is single-shot per name, gated on api_key upstream).
SEARCH_LIMIT = int(os.environ.get("CHANNEL_RESOLVE_SEARCH_LIMIT", "6"))

# Wikidata & MusicBrainz both REQUIRE a descriptive, contactable User-Agent (they
# 403/429 a blank one). Env-tunable; keep it identifying with a contact.
RESOLVE_USER_AGENT = os.environ.get(
    "CHANNEL_RESOLVE_USER_AGENT",
    "diggy-channel-resolve/1.0 "
    "(https://diggy-music.fr; williamb.bienvenu@gmail.com) server-preflight",
)

# ── Wikidata entity guard ─────────────────────────────────────────────────────
# P31 (instance of): the entity must BE a person/band/ensemble …
MUSIC_INSTANCE_QIDS = frozenset(
    {
        "Q5",        # human
        "Q215380",   # musical group / band
        "Q2088357",  # musical ensemble
    }
)
# … OR carry a musical P106 (occupation).
MUSIC_OCCUPATION_QIDS = frozenset(
    {
        "Q130857",   # DJ
        "Q639669",   # musician
        "Q36834",    # composer
        "Q183945",   # record producer
    }
)


class ChannelResolveHTTPError(Exception):
    """Wikidata / MusicBrainz returned a non-200.

    Twin of :class:`~workers.youtube.YouTubeHTTPError`: lets the cascade tell an
    outage apart from a legitimate empty result. Raised by the low-level fetch and
    CAUGHT per-method in :func:`resolve_artist_channel` (never a global crash).
    """

    def __init__(self, status_code: int, context: str):
        self.status_code = status_code
        self.context = context
        super().__init__(f"resolve source returned {status_code} on {context}")


# ── YouTube URL parsing / building (ported from the local gate) ───────────────
# youtube.py has no PUBLIC pure URL→ref parser (only the async, network-bound
# ``resolve_channel_id`` and private regexes), so the gate's pure parser is ported
# here — the port the L1 brief asks for. Kept spirit-synced with youtube.py's
# regexes (« UC… » channel id, @handle, /c/, /user/).
_YT_CHANNEL_RE = re.compile(r"youtube\.com/channel/([A-Za-z0-9_-]+)", re.IGNORECASE)
_YT_HANDLE_RE = re.compile(r"youtube\.com/(@[A-Za-z0-9_.-]+)", re.IGNORECASE)
_YT_CUSTOM_RE = re.compile(r"youtube\.com/c/([A-Za-z0-9_.-]+)", re.IGNORECASE)
_YT_USER_RE = re.compile(r"youtube\.com/user/([A-Za-z0-9_.-]+)", re.IGNORECASE)


def parse_youtube_ref(url: str | None) -> tuple[str, str] | None:
    """Extract a ``(kind, ref)`` from a YouTube URL, or ``None``.

    kind ∈ channel_id ("UC…") / handle ("@name") / custom ("/c/Name") / user
    ("/user/Name"). Matched most-specific-first so "/channel/" wins over a bare path.
    """
    if not url:
        return None
    for kind, rx in (
        ("channel_id", _YT_CHANNEL_RE),
        ("handle", _YT_HANDLE_RE),
        ("custom", _YT_CUSTOM_RE),
        ("user", _YT_USER_RE),
    ):
        m = rx.search(url)
        if m:
            return kind, m.group(1)
    return None


def youtube_url_from_ref(kind: str, ref: str) -> str:
    """Canonical YouTube URL for a ``(kind, ref)``."""
    if kind == "channel_id":
        return f"https://www.youtube.com/channel/{ref}"
    if kind == "handle":
        return f"https://www.youtube.com/{ref}"
    if kind == "custom":
        return f"https://www.youtube.com/c/{ref}"
    if kind == "user":
        return f"https://www.youtube.com/user/{ref}"
    return ""


# ── Name folding for the search-fallback verification ─────────────────────────


def _equal_or_included(a: str, b: str, min_len: int) -> bool:
    """Equal, or the shorter of ``a``/``b`` contained in the longer, with a length
    guard. Assumes both non-empty."""
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= min_len and shorter in longer


def fold_match(name: str, title: str, min_len: int = SEARCH_FOLD_MIN_LEN) -> bool:
    """True when the artist ``name`` folds equal to — or is confidently contained
    in — the channel ``title`` (or vice-versa).

    Reuses :func:`workers.artist_names.punct_fold_key` for the fold, then two passes:
    on the folded forms (equal, or an inclusion whose shorter side is ≥ ``min_len``),
    and a SPACE-INSENSITIVE pass with every space removed on both sides
    ("Amelie Lens" vs "AmelieLens", "David Guetta" vs "davidguettaofficial") —
    YouTube titles/handles are often glued together, safe because the search tier
    stays ``NEEDS_VERIFY`` (human-confirmed). A blank fold on either side (fully
    non-Latin name) never matches, in either pass (invariant #4).
    """
    a = punct_fold_key(name)
    b = punct_fold_key(title)
    if not a or not b:
        return False
    if _equal_or_included(a, b, min_len):
        return True
    a_ns = a.replace(" ", "")
    b_ns = b.replace(" ", "")
    if not a_ns or not b_ns:
        return False
    return _equal_or_included(a_ns, b_ns, min_len)


def is_topic_channel(title: str | None) -> bool:
    """True when ``title`` is a YouTube Music "… - Topic" auto-channel.

    These carry only algorithmically-generated audio uploads (never real DJ sets),
    so a hit whose title ends in "- Topic" is EXCLUDED from the search fallback.
    """
    return bool(title) and title.strip().lower().endswith("- topic")


# ── Wikidata helpers ──────────────────────────────────────────────────────────


def _headers(user_agent: str) -> dict[str, str]:
    return {"User-Agent": user_agent, "Accept": "application/json"}


async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict, headers: dict, context: str
) -> dict:
    """GET ``url`` and return parsed JSON; raise :class:`ChannelResolveHTTPError` on
    a non-200. The single network seam the resolvers route through."""
    resp = await client.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        raise ChannelResolveHTTPError(resp.status_code, context)
    return resp.json()


def _claim_string(claims: dict, prop: str) -> str | None:
    """First non-empty STRING value of ``prop`` in a Wikidata claims dict, or None."""
    for c in claims.get(prop) or []:
        try:
            value = c["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _claim_entity_ids(claims: dict, prop: str) -> list[str]:
    """All wikibase-entity Q-ids of ``prop`` in a Wikidata claims dict.

    P31/P106 values are wikibase-entityid objects
    (``{"entity-type": "item", "id": "Q5", …}``) — this pulls the ``id``.
    """
    out: list[str] = []
    for c in claims.get(prop) or []:
        try:
            value = c["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, dict):
            qid = value.get("id")
            if qid:
                out.append(qid)
    return out


def is_music_entity(claims: dict) -> bool:
    """True when a Wikidata claims dict describes a MUSIC entity (the entity guard).

    Guards ``P2397`` against a false positive: only a person/band/ensemble (``P31``)
    OR an entity with a musical occupation (``P106`` DJ/musician/composer/producer)
    is trusted. A city or generic word carrying a stray ``P2397`` fails here.
    """
    if set(_claim_entity_ids(claims, "P31")) & MUSIC_INSTANCE_QIDS:
        return True
    return bool(set(_claim_entity_ids(claims, "P106")) & MUSIC_OCCUPATION_QIDS)


async def resolve_wikidata(
    client: httpx.AsyncClient,
    name: str,
    *,
    sleep=asyncio.sleep,
    user_agent: str = RESOLVE_USER_AGENT,
) -> dict:
    """Resolve ``name`` via Wikidata → ``{channel_id, has_soundcloud, is_music_entity}``.

    wbsearchentities → top Q-id → wbgetentities claims. The ENTITY GUARD
    (:func:`is_music_entity`) gates everything: a non-music top hit returns
    ``channel_id=None`` even if it carries a ``P2397``. Otherwise ``channel_id`` =
    ``P2397`` (the "UC…" YouTube channel id) and ``has_soundcloud`` = ``P3040``
    present. Raises :class:`ChannelResolveHTTPError` on a non-200 (caught upstream).
    """
    empty = {"channel_id": None, "has_soundcloud": False, "is_music_entity": False}
    name = (name or "").strip()
    if not name:
        return empty
    headers = _headers(user_agent)

    await sleep(WIKIDATA_DELAY)
    data = await _get_json(
        client,
        WIKIDATA_API,
        {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "uselang": "en",
            "format": "json",
            "type": "item",
            "limit": 5,
        },
        headers,
        "wikidata:search",
    )
    hits = data.get("search") or []
    qid = hits[0].get("id") if hits else None
    if not qid:
        return empty

    await sleep(WIKIDATA_DELAY)
    data = await _get_json(
        client,
        WIKIDATA_API,
        {"action": "wbgetentities", "ids": qid, "format": "json", "props": "claims"},
        headers,
        "wikidata:claims",
    )
    claims = ((data.get("entities") or {}).get(qid) or {}).get("claims") or {}
    if not is_music_entity(claims):
        return empty

    return {
        "channel_id": _claim_string(claims, "P2397") or None,
        "has_soundcloud": bool(_claim_string(claims, "P3040")),
        "is_music_entity": True,
    }


# ── MusicBrainz helpers ───────────────────────────────────────────────────────


def _scan_rels_for_links(relations: list) -> tuple[str | None, str | None]:
    """Return ``(youtube_url, soundcloud_url)`` — the first of each in url-rels."""
    yt = sc = None
    for rel in relations:
        target = (rel.get("url") or {}).get("resource") or ""
        if not target:
            continue
        low = target.lower()
        if yt is None and "youtube.com" in low:
            yt = target
        if sc is None and "soundcloud.com" in low:
            sc = target
    return yt, sc


async def resolve_musicbrainz(
    client: httpx.AsyncClient,
    name: str,
    mbid: str | None = None,
    *,
    sleep=asyncio.sleep,
    user_agent: str = RESOLVE_USER_AGENT,
) -> dict:
    """Resolve ``name`` via MusicBrainz → ``{channel_id, channel_url, has_soundcloud}``.

    Uses ``mbid`` when supplied, else searches ``ws/2/artist`` for the top hit, then
    reads its ``url-rels`` for an official YouTube link (channel/@handle/c/user →
    :func:`parse_youtube_ref`) and a SoundCloud rel. STRICT 1 req/s (paced by the
    injected ``sleep``). Raises :class:`ChannelResolveHTTPError` on a non-200.
    """
    empty = {"channel_id": None, "channel_url": None, "has_soundcloud": False}
    headers = _headers(user_agent)

    if not mbid:
        name = (name or "").strip()
        if not name:
            return empty
        await sleep(MUSICBRAINZ_DELAY)
        data = await _get_json(
            client,
            f"{MUSICBRAINZ_API}/artist",
            {"query": name, "fmt": "json", "limit": 3},
            headers,
            "musicbrainz:search",
        )
        artists = data.get("artists") or []
        mbid = artists[0].get("id") if artists else None
        if not mbid:
            return empty

    await sleep(MUSICBRAINZ_DELAY)
    data = await _get_json(
        client,
        f"{MUSICBRAINZ_API}/artist/{quote(mbid)}",
        {"inc": "url-rels", "fmt": "json"},
        headers,
        "musicbrainz:rels",
    )
    yt_url, sc_url = _scan_rels_for_links(data.get("relations") or [])
    has_sc = bool(sc_url)
    ref = parse_youtube_ref(yt_url) if yt_url else None
    if not ref:
        return {"channel_id": None, "channel_url": None, "has_soundcloud": has_sc}
    kind, val = ref
    return {
        "channel_id": val,
        "channel_url": youtube_url_from_ref(kind, val),
        "has_soundcloud": has_sc,
    }


# ── Cascade ───────────────────────────────────────────────────────────────────


async def resolve_artist_channel(
    name: str,
    *,
    wiki_client: httpx.AsyncClient,
    mb_client: httpx.AsyncClient,
    yt_client: httpx.AsyncClient,
    api_key: str,
    allow_search: bool = True,
    sleep=asyncio.sleep,
    user_agent: str = RESOLVE_USER_AGENT,
    fold_min_len: int = SEARCH_FOLD_MIN_LEN,
    search_limit: int = SEARCH_LIMIT,
) -> dict | None:
    """Run the 2-level cascade for one artist ``name``.

    Returns ``{channel_id, channel_title, url, method, confidence, has_soundcloud}``
    on the first tier that resolves, else ``None`` (nothing found). ``has_soundcloud``
    accumulates across tiers so a channel found by search still carries a SoundCloud
    signal noted earlier.

    Errors are ISOLATED per tier: a Wikidata/MusicBrainz/search failure is logged and
    the cascade falls through to the next tier — this function never raises.
    """
    name = (name or "").strip()
    if not name:
        return None
    has_soundcloud = False

    # (a) Wikidata — official channel id, high confidence.
    try:
        wiki = await resolve_wikidata(
            wiki_client, name, sleep=sleep, user_agent=user_agent
        )
        has_soundcloud = has_soundcloud or wiki["has_soundcloud"]
        if wiki["channel_id"]:
            return {
                "channel_id": wiki["channel_id"],
                "channel_title": None,
                "url": youtube_url_from_ref("channel_id", wiki["channel_id"]),
                "method": "wikidata",
                "confidence": "high",
                "has_soundcloud": has_soundcloud,
            }
    except Exception as exc:  # per-tier isolation, fall through
        logger.warning(
            "resolve_artist_channel: wikidata failed for %r: %s", name, exc
        )

    # (b) MusicBrainz — official url-rel, high confidence.
    try:
        mb = await resolve_musicbrainz(
            mb_client, name, sleep=sleep, user_agent=user_agent
        )
        has_soundcloud = has_soundcloud or mb["has_soundcloud"]
        if mb["channel_id"]:
            return {
                "channel_id": mb["channel_id"],
                "channel_title": None,
                "url": mb["channel_url"],
                "method": "musicbrainz",
                "confidence": "high",
                "has_soundcloud": has_soundcloud,
            }
    except Exception as exc:  # per-tier isolation, fall through
        logger.warning(
            "resolve_artist_channel: musicbrainz failed for %r: %s", name, exc
        )

    # (c) Verified YouTube search — assisted fallback, NEEDS_VERIFY.
    if allow_search and api_key:
        try:
            items = await search_channels(
                yt_client, name, api_key, limit=search_limit
            )
            for item in items:
                cid = item.get("channel_id")
                title = item.get("title") or ""
                if not cid or not title:
                    continue
                if is_topic_channel(title):
                    continue
                if fold_match(name, title, fold_min_len):
                    return {
                        "channel_id": cid,
                        "channel_title": title,
                        "url": youtube_url_from_ref("channel_id", cid),
                        "method": "search",
                        "confidence": "NEEDS_VERIFY",
                        "has_soundcloud": has_soundcloud,
                    }
        except Exception as exc:  # per-tier isolation, no resolution
            logger.warning(
                "resolve_artist_channel: youtube search failed for %r: %s", name, exc
            )

    return None
