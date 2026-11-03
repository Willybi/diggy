"""Watched-channel admin service (C14.b, L3 — YouTube-first slice).

Read + curation surface over the ``channels`` table (the first-class channels we
watch for DJ sets). Mirrors ``cohort_service``: the service raises LookupError /
ValueError and NEVER commits — the thin admin router audits and commits. DB
loaders are awaited SEQUENTIALLY on the one AsyncSession (never asyncio.gather —
a session is not safe for concurrent access).

``list_candidates`` proposes a SEED of channels already known to the base (from
``trackid_index``) but not yet curated into ``channels``, ranked by « discovery
value » (see below).
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from models import Artist, ArtistCohort, Channel, DJSet, SetArtist, TrackIdIndex
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from trackid.reliability import set_reliable
from workers.artist_channel_resolve import resolve_artist_channel
from workers.artist_names import space_fold_key
from workers.set_artist_media_denylist import MEDIA_TITLE_KEYS
from workers.youtube import (
    YOUTUBE_API_KEY,
    default_client,
    fetch_channel_title,
    resolve_channel_id,
    search_channels,
)

logger = logging.getLogger(__name__)

# A candidate name is resolved to YouTube hits AT MOST ONCE, then served from
# Redis: each search.list costs 100 quota units, so the cache TTL is long (60
# days by default) — a candidate's channel rarely changes identity.
CANDIDATE_RESOLVE_TTL_SECONDS = int(
    os.environ.get("CANDIDATE_RESOLVE_TTL_SECONDS", str(60 * 24 * 3600))
)

# How long a « Ne pas suivre » (deferred) artist dismissal keeps hiding the
# candidate before it naturally re-surfaces. A « Pas de chaîne » (no_channel)
# dismissal never expires. Env-tunable; default one year.
CANDIDATE_DEFER_RESURFACE_DAYS = int(
    os.environ.get("CANDIDATE_DEFER_RESURFACE_DAYS", "365")
)

# The two kinds of artist/org dismissal, stored in the marker's ``signals`` JSON
# under ``dismiss_kind``. A legacy marker (``signals`` NULL / no ``dismiss_kind``)
# is treated as :data:`DISMISS_NO_CHANNEL` — the historical permanent behaviour.
DISMISS_NO_CHANNEL = "no_channel"  # « Pas de chaîne » — definitive
DISMISS_DEFERRED = "deferred"  # « Ne pas suivre » — reversible, time-boxed


def _candidate_cache_key(name: str) -> str:
    """Cache key for a candidate name's resolution. ``list_candidates`` (read) and
    ``/resolve`` (read/write) MUST produce the identical key for the exact name."""
    return f"yt:cand:v1:{name}"


def _artist_resolve_cache_key(name: str) -> str:
    """Cache key for an ARTIST → channel cascade resolution (L1). Distinct from
    :func:`_candidate_cache_key` (a raw channel-name search): this is the full
    Wikidata/MusicBrainz/search cascade for an artist name.

    ``v2`` (L1-fix): the official Wikidata/MusicBrainz tiers now reject a
    "… - Topic" auto-channel, so v1 resolutions (which could cache a Topic hit)
    are invalidated by the version bump."""
    return f"yt:artcand:v2:{name}"


def _item(row: Channel) -> dict:
    return {
        "id": row.id,
        "platform": row.platform,
        "external_id": row.external_id,
        "name": row.name,
        "channel_type": row.channel_type,
        "artist_id": row.artist_id,
        "watched": row.watched,
        "excluded": row.excluded,
        "last_checked_at": row.last_checked_at,
    }


async def list_channels(
    db: AsyncSession,
    *,
    platform: str = "youtube",
    watched: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Paginated listing of curated channels for a platform.

    Optional ``watched`` filter (True/False). Stable ordering: name asc then id
    asc, so the page window is deterministic. Returns ``{total, items}``.
    """
    conditions = [Channel.platform == platform]
    if watched is not None:
        conditions.append(Channel.watched.is_(watched))
    # Hide the "no channel" dismiss markers (external_id NULL + excluded) created by
    # dismiss_artist_candidate — bookkeeping rows, not real curated channels.
    conditions.append(
        or_(Channel.external_id.isnot(None), Channel.excluded.is_(False))
    )

    total = await db.scalar(
        select(func.count()).select_from(Channel).where(*conditions)
    )

    rows = (
        await db.execute(
            select(Channel)
            .where(*conditions)
            .order_by(Channel.name.asc(), Channel.id.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()

    return {"total": total or 0, "items": [_item(r) for r in rows]}


async def _curated_external_ids(db: AsyncSession) -> set[str]:
    """The set of platform channel ids already curated into ``channels`` (non-NULL
    ``external_id``). Used to hide a candidate whose already-resolved channel is
    already curated — under ANY name or artist row — which the name-based (org) and
    ``artist_id``-based (artist) exclusions miss on their own (e.g. a channel added
    under its YouTube title rather than its corpus name, or an artist's channel
    already owned by a duplicate artist row)."""
    rows = (
        await db.execute(
            select(Channel.external_id).where(Channel.external_id.isnot(None))
        )
    ).scalars().all()
    return set(rows)


async def list_candidates(db: AsyncSession, *, limit: int = 50, redis=None) -> dict:
    """Propose seed channels known to the base but not yet curated.

    Candidate name universe — WIDENED (🅲): the UNION of two sources, MINUS names
    already curated into ``channels``:

    * every ``trackid_index.channel`` (the indexed TrackID corpus), and
    * every ``sets.channel_canonical`` of a REAL set (roots-only, reliable, not a
      dedup virtual parent, ALL sources — youtube + trackid).

    So a channel seen only through a recently-imported set (absent from the
    ``trackid_index`` snapshot) now surfaces as a candidate too.

    Sort metric — COHORT RELEVANCE (🅰): a candidate's rank is the number of
    DISTINCT watch-cohort artists (``artist_cohort``, non-excluded) credited as a
    DJ (``set_artists.role == 'dj'``) on that channel's sets — the reliable-root
    sets attributed to the name through EITHER path above (a
    ``trackid_index.set_id`` link, or the set's own ``channel_canonical``). Higher
    relevance = a channel whose sets feature more artists we already watch →
    surfaced first. Ties are broken by set VOLUME (indexed trackid rows, then
    attributed sets) then the name for determinism. ``trackid_count`` /
    ``set_count`` stay in the output as informative coverage signals (they no
    longer drive the order). Read-only, no commit.

    When ``redis`` is provided, each candidate is annotated with its cached
    YouTube pre-selection (``preselect``) READ FROM the cache only — this function
    NEVER runs a YouTube search (a search would burn 100 quota units per name on
    every listing render). A resolution happens exclusively on the explicit
    ``resolve_candidate`` path. Fail-open: any Redis error leaves ``preselect``
    at None, never an exception. ``redis=None`` keeps the legacy behaviour.
    """
    # Informative per-name coverage counts (and the trackid arm of the universe).
    tid_agg = (
        select(
            TrackIdIndex.channel.label("name"),
            func.count().label("trackid_count"),
            func.count(TrackIdIndex.set_id).label("set_count"),
        )
        .where(TrackIdIndex.channel.isnot(None))
        .group_by(TrackIdIndex.channel)
        .subquery()
    )

    # Real sets attributed to a channel name through BOTH linkage paths, kept to
    # reliable roots so the relevance count matches the cohort's own set signal.
    tid_link = (
        select(
            TrackIdIndex.channel.label("name"),
            DJSet.id.label("set_id"),
        )
        .join(DJSet, DJSet.id == TrackIdIndex.set_id)
        .where(
            TrackIdIndex.channel.isnot(None),
            DJSet.parent_set_id.is_(None),
            DJSet.is_virtual.is_(False),
            set_reliable(),
        )
    )
    set_link = select(
        DJSet.channel_canonical.label("name"),
        DJSet.id.label("set_id"),
    ).where(
        DJSet.channel_canonical.isnot(None),
        DJSet.parent_set_id.is_(None),
        DJSet.is_virtual.is_(False),
        set_reliable(),
    )
    channel_sets = tid_link.union(set_link).subquery()

    # Per-name relevance + set volume in ONE pass: LEFT JOIN keeps a set even when
    # it has no cohort DJ (relevance 0 but still a candidate). role/exclusion live
    # in the ON clause; set_volume needs DISTINCT because the DJ join fans out.
    channel_stats = (
        select(
            channel_sets.c.name.label("name"),
            func.count(func.distinct(channel_sets.c.set_id)).label("set_volume"),
            func.count(func.distinct(ArtistCohort.artist_id)).label("relevance"),
        )
        .select_from(channel_sets)
        .outerjoin(
            SetArtist,
            and_(
                SetArtist.set_id == channel_sets.c.set_id,
                SetArtist.role == "dj",
            ),
        )
        .outerjoin(
            ArtistCohort,
            and_(
                ArtistCohort.artist_id == SetArtist.artist_id,
                ArtistCohort.excluded.isnot(True),
            ),
        )
        .group_by(channel_sets.c.name)
        .subquery()
    )

    # Universe = all trackid channels ∪ all channels carrying a reliable-root set
    # (the 🅲 widening; the latter is exactly the names in channel_stats).
    universe = (
        select(tid_agg.c.name)
        .union(select(channel_stats.c.name))
        .subquery()
    )

    trackid_count = func.coalesce(tid_agg.c.trackid_count, 0)
    set_count = func.coalesce(tid_agg.c.set_count, 0)
    relevance = func.coalesce(channel_stats.c.relevance, 0)
    set_volume = func.coalesce(channel_stats.c.set_volume, 0)

    stmt = (
        select(
            universe.c.name.label("name"),
            trackid_count.label("trackid_count"),
            set_count.label("set_count"),
        )
        .select_from(universe)
        .outerjoin(tid_agg, tid_agg.c.name == universe.c.name)
        .outerjoin(channel_stats, channel_stats.c.name == universe.c.name)
        .where(universe.c.name.notin_(select(Channel.name)))
        .order_by(
            relevance.desc(),
            trackid_count.desc(),
            set_volume.desc(),
            universe.c.name.asc(),
        )
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()
    items = [
        {
            "name": name,
            "trackid_count": tc,
            "set_count": sc,
            "preselect": None,
        }
        for name, tc, sc in rows
    ]

    if redis is not None:
        curated_ext = await _curated_external_ids(db)
        for it in items:
            try:
                cached = await redis.get(_candidate_cache_key(it["name"]))
            except Exception as exc:  # fail-open: Redis down → no preselect at all
                logger.warning(
                    "candidate preselect cache read skipped (Redis unavailable): %s",
                    exc,
                )
                break
            if cached:
                try:
                    it["preselect"] = json.loads(cached)
                except Exception:  # corrupt/legacy payload → leave preselect None
                    pass
        # Hide a candidate whose SUGGESTED resolved channel (first hit) is already
        # curated — added under any name, so the name-based exclusion missed it.
        items = [
            it
            for it in items
            if not (
                it["preselect"]
                and it["preselect"][0].get("channel_id") in curated_ext
            )
        ]

    return {"items": items}


# ── Artist-candidate gate (C14.b 🅱, L2) ──────────────────────────────────────
# The DEEZER sentinel marking an artist confirmed absent from Deezer — NOT a
# real link, so it must not satisfy the "real artist" signal guard.
_DEEZER_NOT_FOUND = "NOT_FOUND"
# Minimum catalog depth that alone qualifies a cohort member as a real DJ worth a
# channel (mirrors the C14.a T2 catalog threshold).
ARTIST_CANDIDATE_MIN_CATALOG = 10
# Single-token names that are generic scene words, never an artist to watch.
# ≤2-char names are rejected separately; this catches the longer generic mono
# tokens (a real artist name is almost always multi-token or a distinctive word).
_GENERIC_MONO_TOKENS = frozenset(
    {"various", "artist", "artists", "live", "set", "mix", "guest", "unknown",
     "resident", "podcast", "radioshow"}
)


def _deezer_id_valid(deezer_id: str | None) -> bool:
    """A Deezer id that identifies a real artist (present, not the NOT_FOUND sentinel)."""
    return bool(deezer_id) and deezer_id != _DEEZER_NOT_FOUND


def _is_real_artist_name(name: str) -> bool:
    """Name heuristic of the gate: reject a ≤2-char name and a single-token generic
    scene word. Curated media/radio/label/show names are handled separately by the
    denylist (:data:`MEDIA_TITLE_KEYS`)."""
    stripped = (name or "").strip()
    if len(stripped) <= 2:
        return False
    tokens = stripped.split()
    if len(tokens) == 1 and space_fold_key(stripped) in _GENERIC_MONO_TOKENS:
        return False
    return True


def _passes_artist_gate(
    name: str, deezer_id: str | None, nb_catalog: int, nb_sets_12m: int
) -> bool:
    """The 3-guard « real artist » gate (brief §5, mandatory):

    (i)   NOT a curated media/radio/label/show name (:data:`MEDIA_TITLE_KEYS`,
          matched on ``space_fold_key`` — the same key family the set-artist
          extractor rejects on);
    (ii)  carries a real-artist SIGNAL — a valid Deezer link OR enough catalog
          depth (``>= ARTIST_CANDIDATE_MIN_CATALOG``) OR a recent DJ set;
    (iii) passes the name heuristic (no ≤2-char / generic mono-token).
    """
    if space_fold_key(name) in MEDIA_TITLE_KEYS:  # (i)
        return False
    has_signal = (
        _deezer_id_valid(deezer_id)
        or nb_catalog >= ARTIST_CANDIDATE_MIN_CATALOG
        or nb_sets_12m >= 1
    )
    if not has_signal:  # (ii)
        return False
    if not _is_real_artist_name(name):  # (iii)
        return False
    return True


def _sig_int(signals, key: str) -> int:
    """Read an integer signal from the cohort's ``signals`` JSON, defaulting to 0
    (a NULL/absent/non-numeric value)."""
    try:
        return int((signals or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _dismiss_kind(signals) -> str:
    """The dismissal kind recorded on a marker's ``signals`` JSON.

    Defaults to :data:`DISMISS_NO_CHANNEL` for a legacy marker (``signals`` NULL
    or missing ``dismiss_kind``) — those predate the two-action split and were
    permanent « there is no channel » dismissals."""
    return (signals or {}).get("dismiss_kind") or DISMISS_NO_CHANNEL


def _dismissed_at(signals) -> datetime | None:
    """Parse the ``dismissed_at`` ISO timestamp of a 'deferred' marker (UTC-aware).

    Returns None when absent/unparseable. A naive value is assumed UTC."""
    raw = (signals or {}).get("dismissed_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _marker_masks(signals, now: datetime) -> bool:
    """Whether a dismiss marker still hides its candidate at ``now``.

    A 'no_channel' (or legacy) marker masks forever; a 'deferred' marker masks
    only while within the :data:`CANDIDATE_DEFER_RESURFACE_DAYS` window, after
    which the candidate naturally re-surfaces. A 'deferred' marker with no (or an
    unparseable) ``dismissed_at`` masks defensively (treated as fresh)."""
    if _dismiss_kind(signals) != DISMISS_DEFERRED:
        return True
    dt = _dismissed_at(signals)
    if dt is None:
        return True
    return (now - dt) < timedelta(days=CANDIDATE_DEFER_RESURFACE_DAYS)


async def list_artist_candidates(
    db: AsyncSession,
    redis=None,
    *,
    limit: int = 50,
    page: int = 1,
    tier_max: int | None = 1,
    now: datetime | None = None,
) -> dict:
    """Propose cohort artists worth a watched YouTube channel (C14.b 🅱).

    LIVE query over ``artist_cohort`` joined to ``artists``, EXCLUDING excluded
    cohort rows and artists that already have a REAL curated channel (a
    ``channels`` row with a non-NULL ``external_id`` AND ``artist_id``). Each
    remaining member is passed through the 3-guard « real artist » gate
    (:func:`_passes_artist_gate`): denylist, a real-artist signal (Deezer link /
    catalog depth / recent DJ set) and the name heuristic. The relevance signals
    (``followed``/``nb_lib``/``nb_likes``/``nb_sets_12m``/``nb_catalog``) live in
    the cohort's ``signals`` JSON, so the gate + ranking run in Python
    (dialect-neutral) over the fetched rows.

    SCOPE — ``tier_max`` bounds the proposed tiers (default **1** = only the
    "personal + active" T1 members; the full cohort is ~28k artists and must not
    be served whole). ``tier_max=None`` (or 2) widens the scope to include T2.

    TIME-BOXED DISMISS — besides a real channel, a member is also hidden when it
    carries a dismiss marker (a ``channels`` row with a NULL ``external_id`` +
    ``excluded``, matched on ``artist_id``): a « Pas de chaîne » (no_channel)
    marker hides it forever, a « Ne pas suivre » (deferred) marker hides it only
    while within :data:`CANDIDATE_DEFER_RESURFACE_DAYS` — after which it
    re-surfaces naturally. The markers are loaded and the window is evaluated IN
    PYTHON (``now``, default UTC-now) to avoid a cross-dialect JSON query.

    Ranked by PERSONAL RELEVANCE, not set volume: ``tier`` asc, then explicitly
    followed artists first, then by library depth, likes, DJ-set activity and catalog
    depth (all desc), tie-broken by ``artist_id`` for a deterministic page window;
    paginated in memory.

    When ``redis`` is provided, each PAGE item is annotated with its cached
    artist→channel resolution (``preselect``) READ FROM the cache only (key
    ``yt:artcand:v2:{name}``) — this function NEVER resolves (a resolution spends
    100 quota units; that happens exclusively on :func:`resolve_artist_candidate`).
    Fail-open: any Redis error leaves ``preselect`` at None, never an exception.
    Read-only, no commit. Returns ``{total, items}``.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # A member is hidden only by a REAL curated channel (external_id non-NULL);
    # dismiss markers (external_id NULL) are handled by the time-box below.
    real_curated = select(Channel.artist_id).where(
        Channel.artist_id.isnot(None), Channel.external_id.isnot(None)
    )

    # Load the artist dismiss markers (external_id NULL + excluded + artist_id) and
    # evaluate the resurface window in Python → the masked set of artist_ids.
    markers = (
        await db.execute(
            select(Channel.artist_id, Channel.signals).where(
                Channel.external_id.is_(None),
                Channel.excluded.is_(True),
                Channel.artist_id.isnot(None),
            )
        )
    ).all()
    masked_ids = {
        artist_id
        for artist_id, signals in markers
        if _marker_masks(signals, now)
    }

    conditions = [
        ArtistCohort.excluded.isnot(True),
        ArtistCohort.artist_id.notin_(real_curated),
    ]
    if tier_max is not None:
        conditions.append(ArtistCohort.tier <= tier_max)

    rows = (
        await db.execute(
            select(ArtistCohort, Artist.name, Artist.deezer_id)
            .join(Artist, Artist.id == ArtistCohort.artist_id)
            .where(*conditions)
            .order_by(ArtistCohort.tier.asc(), ArtistCohort.artist_id.asc())
        )
    ).all()

    kept: list[dict] = []
    for row, name, deezer_id in rows:
        if row.artist_id in masked_ids:
            continue
        nb_sets = _sig_int(row.signals, "nb_sets_12m")
        nb_lib = _sig_int(row.signals, "nb_lib")
        nb_likes = _sig_int(row.signals, "nb_likes")
        nb_catalog = _sig_int(row.signals, "nb_catalog")
        followed = bool((row.signals or {}).get("followed"))
        if not _passes_artist_gate(name, deezer_id, nb_catalog, nb_sets):
            continue
        kept.append(
            {
                "artist_id": row.artist_id,
                "name": name,
                "tier": row.tier,
                "followed": followed,
                "nb_lib": nb_lib,
                "nb_likes": nb_likes,
                "nb_sets": nb_sets,
                "nb_catalog": nb_catalog,
                "preselect": None,
            }
        )

    # Personal-relevance order (NOT set volume): tier, then explicitly followed
    # artists first, then library depth, likes, DJ-set activity, catalog depth.
    # Hide a candidate whose already-resolved channel (cached) is already curated
    # under ANY artist row — the per-``artist_id`` exclusion misses a duplicate
    # artist row that already owns the channel (e.g. "Marlon Hoffstadt" vs
    # "DJ Daddy Trance"). Reads the resolve cache for every kept candidate (bounded
    # cohort), reusing the hit as the page preselect. Fail-open: a Redis error stops
    # the reads and keeps the remaining candidates unfiltered.
    if redis is not None:
        curated_ext = await _curated_external_ids(db)
        survivors = []
        redis_ok = True
        for it in kept:
            if redis_ok:
                try:
                    cached = await redis.get(_artist_resolve_cache_key(it["name"]))
                except Exception as exc:  # fail-open
                    logger.warning(
                        "artist candidate preselect cache read skipped "
                        "(Redis unavailable): %s",
                        exc,
                    )
                    redis_ok = False
                    cached = None
                if cached is not None:
                    try:
                        resolved = json.loads(cached)
                    except Exception:  # corrupt/legacy payload → leave preselect None
                        resolved = None
                    if resolved and resolved.get("channel_id") in curated_ext:
                        continue  # already curated → no longer a candidate
                    it["preselect"] = resolved
            survivors.append(it)
        kept = survivors

    kept.sort(
        key=lambda c: (
            c["tier"],
            not c["followed"],
            -c["nb_lib"],
            -c["nb_likes"],
            -c["nb_sets"],
            -c["nb_catalog"],
            c["artist_id"],
        )
    )

    total = len(kept)
    start = (page - 1) * limit
    page_items = kept[start : start + limit]

    return {"total": total, "items": page_items}


async def search_youtube(query: str, *, limit: int = 6) -> dict:
    """Search YouTube for channels matching ``query`` → ``{items: [...]}``.

    Read-only add-by-search helper (no DB access, no commit). QUOTA GUARD: a query
    shorter than 2 chars once stripped short-circuits to ``{"items": []}`` WITHOUT
    any network call — each ``search.list`` costs 100 YouTube Data API units, so a
    stray keystroke never spends the quota. Otherwise resolves up to ``limit``
    channel hits via :func:`workers.youtube.search_channels` (in a fresh httpx
    client block, key from ``YOUTUBE_API_KEY`` — falsy degrades to ``[]``).
    """
    cleaned = query.strip()
    if len(cleaned) < 2:
        return {"items": []}
    async with default_client() as client:
        items = await search_channels(client, cleaned, YOUTUBE_API_KEY, limit=limit)
    return {"items": items}


async def resolve_candidate(name: str, redis, *, limit: int = 6) -> dict:
    """Resolve a candidate channel ``name`` to YouTube hits, CACHE-FIRST.

    A ``search.list`` call costs 100 quota units, so a name is resolved at most
    once then served from Redis (TTL :data:`CANDIDATE_RESOLVE_TTL_SECONDS`) — a
    cache HIT spends ZERO quota. No DB access.

    * HIT  → ``{"items": <cached hits>, "cached": True}`` (no search).
    * MISS → runs :func:`search_youtube` (which itself gates names < 2 chars),
      best-effort writes the hits back, returns ``{"items": ..., "cached": False}``.

    Fail-open: any Redis error (read OR write) degrades to a live search / a
    skipped write, never an exception — availability wins over a warm cache.
    """
    key = _candidate_cache_key(name)

    if redis is not None:
        try:
            cached = await redis.get(key)
        except Exception as exc:  # fail-open: Redis down → live search
            logger.warning(
                "candidate resolve cache read skipped (Redis unavailable): %s", exc
            )
            cached = None
        if cached:
            try:
                return {"items": json.loads(cached), "cached": True}
            except Exception:  # corrupt/legacy payload → recompute
                pass

    res = await search_youtube(name, limit=limit)

    if redis is not None:
        try:
            await redis.set(
                key, json.dumps(res["items"]), ex=CANDIDATE_RESOLVE_TTL_SECONDS
            )
        except Exception as exc:  # fail-open: cache write must never fail the call
            logger.warning(
                "candidate resolve cache write skipped (Redis unavailable): %s", exc
            )

    return {**res, "cached": False}


async def resolve_artist_candidate(
    name: str, redis, *, allow_search: bool = True
) -> dict | None:
    """Resolve an ARTIST name to its YouTube channel, CACHE-FIRST (L1, on-demand).

    Runs the full 2-level cascade
    (:func:`workers.artist_channel_resolve.resolve_artist_channel`: Wikidata →
    MusicBrainz → verified YouTube search). Wikidata/MusicBrainz cost no quota; the
    search tier spends 100 quota units, so a name is resolved AT MOST ONCE then
    served from Redis (TTL :data:`CANDIDATE_RESOLVE_TTL_SECONDS`). No DB access.

    * HIT  → the cached result (a dict, or ``None`` when a prior run found nothing).
    * MISS → opens ONE httpx client, runs the cascade, best-effort writes the result
      back (``None`` included, so a fruitless resolution isn't re-attempted every
      render), returns it.

    Fail-open: any Redis error (read OR write) degrades to a live resolution / a
    skipped write, never an exception — availability wins over a warm cache.
    Mirrors :func:`resolve_candidate`.
    """
    key = _artist_resolve_cache_key(name)

    if redis is not None:
        try:
            cached = await redis.get(key)
        except Exception as exc:  # fail-open: Redis down → live resolution
            logger.warning(
                "artist channel resolve cache read skipped (Redis unavailable): %s",
                exc,
            )
            cached = None
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:  # corrupt/legacy payload → recompute
                pass

    async with default_client() as client:
        result = await resolve_artist_channel(
            name,
            wiki_client=client,
            mb_client=client,
            yt_client=client,
            api_key=YOUTUBE_API_KEY,
            allow_search=allow_search,
        )

    if redis is not None:
        try:
            await redis.set(
                key, json.dumps(result), ex=CANDIDATE_RESOLVE_TTL_SECONDS
            )
        except Exception as exc:  # fail-open: a cache write must never fail the call
            logger.warning(
                "artist channel resolve cache write skipped (Redis unavailable): %s",
                exc,
            )

    return result


async def add_channel(db: AsyncSession, body) -> dict:
    """Resolve a YouTube URL/handle to a channel id and upsert a watched row.

    ``body.url`` is resolved to a « UC… » channel id via
    :func:`workers.youtube.resolve_channel_id` (creating a default httpx client).
    An unresolvable URL raises ValueError. The display name is ``body.name`` when
    given, else the channel's real title fetched via
    :func:`workers.youtube.fetch_channel_title` (in the same client block), else a
    fallback to the channel id. The ``channels`` row is upserted idempotently on
    ``(platform='youtube', external_id)`` — created if absent, else re-flagged
    ``watched=True``; on that update path an explicit ``body.name`` is applied, and
    otherwise a placeholder name still equal to the channel id is refreshed to the
    resolved title (a name already curated is never overwritten). Flushes but does
    NOT commit (the router audits + commits). Returns the item.
    """
    async with default_client() as client:
        channel_id = await resolve_channel_id(client, body.url, YOUTUBE_API_KEY)
        if not channel_id:
            raise ValueError(f"channel_id introuvable pour {body.url!r}")
        if body.name:
            display_name = body.name
        else:
            display_name = (
                await fetch_channel_title(client, channel_id, YOUTUBE_API_KEY)
                or channel_id
            )

    row = (
        await db.execute(
            select(Channel).where(
                Channel.platform == "youtube",
                Channel.external_id == channel_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = Channel(
            platform="youtube",
            external_id=channel_id,
            name=display_name,
            channel_type=body.channel_type,
            artist_id=body.artist_id,
            watched=True,
        )
        db.add(row)
    else:
        row.watched = True
        if body.name:
            row.name = body.name
        elif row.name == row.external_id:
            # A placeholder name left on the channel id — refresh to the title.
            row.name = display_name
        if body.channel_type is not None:
            row.channel_type = body.channel_type
        if body.artist_id is not None:
            row.artist_id = body.artist_id

    await db.flush()
    return _item(row)


async def set_override(db: AsyncSession, channel_id: int, *, changes: dict) -> dict:
    """Toggle watched/excluded/type/artist on a channel row (PATCH semantics).

    ``changes`` carries ONLY the explicitly-provided fields (the router builds it
    from ``body.model_dump(exclude_unset=True)``). ``watched``/``excluded`` are
    applied only when present AND non-null (boolean toggles); ``channel_type`` /
    ``artist_id`` are applied whenever their key is present (an explicit None
    clears the value). Raises LookupError if the channel does not exist. Flushes
    but does NOT commit (the router audits + commits). Returns the item dict.
    """
    row = (
        await db.execute(select(Channel).where(Channel.id == channel_id))
    ).scalar_one_or_none()
    if row is None:
        raise LookupError(f"Channel {channel_id} not found")

    if changes.get("watched") is not None:
        row.watched = changes["watched"]
    if changes.get("excluded") is not None:
        row.excluded = changes["excluded"]
    if "channel_type" in changes:
        row.channel_type = changes["channel_type"]
    if "artist_id" in changes:
        row.artist_id = changes["artist_id"]

    await db.flush()
    return _item(row)


async def _upsert_artist_marker(
    db: AsyncSession, artist_id: int, *, signals: dict
) -> dict:
    """Create (idempotently) or refresh the artist's dismiss marker.

    The marker is a placeholder ``channels`` row — ``external_id`` NULL,
    ``channel_type='artist'``, ``watched=False``, ``excluded=True`` — carrying the
    dismissal kind in ``signals``. Matched on NULL ``external_id`` so a REAL
    resolved channel row for the artist is never touched. Raises LookupError on an
    unknown artist. Flushes, does NOT commit. Returns the item dict.
    """
    artist = (
        await db.execute(select(Artist).where(Artist.id == artist_id))
    ).scalar_one_or_none()
    if artist is None:
        raise LookupError(f"Artist {artist_id} not found")

    row = (
        await db.execute(
            select(Channel).where(
                Channel.platform == "youtube",
                Channel.artist_id == artist_id,
                Channel.external_id.is_(None),
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = Channel(
            platform="youtube",
            external_id=None,
            name=artist.name,
            channel_type="artist",
            artist_id=artist_id,
            watched=False,
            excluded=True,
            signals=signals,
        )
        db.add(row)
    else:
        row.excluded = True
        row.watched = False
        row.signals = signals

    await db.flush()
    return _item(row)


async def dismiss_artist_candidate(db: AsyncSession, artist_id: int) -> dict:
    """« Pas de chaîne » — mark a cohort artist as having NO watchable channel.

    Covers the "there is no channel to associate at all" case of the artist-
    candidate list: the artist stops being proposed FOREVER, WITHOUT leaving the
    Deezer-watch cohort. Writes a ``dismiss_kind='no_channel'`` marker (see
    :func:`_upsert_artist_marker`); :func:`list_artist_candidates` masks it
    permanently and :func:`list_channels` hides it. Reversible only through
    :func:`reinstate`. Raises LookupError on an unknown artist. Flushes, does NOT
    commit (the router audits + commits). Returns the item dict.
    """
    return await _upsert_artist_marker(
        db, artist_id, signals={"dismiss_kind": DISMISS_NO_CHANNEL}
    )


async def defer_artist_candidate(
    db: AsyncSession, artist_id: int, *, now: datetime | None = None
) -> dict:
    """« Ne pas suivre » — defer a cohort artist candidate (reversible).

    Hides the artist from the candidate list for :data:`CANDIDATE_DEFER_RESURFACE_DAYS`,
    after which it naturally re-surfaces. Writes a ``dismiss_kind='deferred'``
    marker stamped with ``dismissed_at`` (``now``, default UTC-now) — see
    :func:`_upsert_artist_marker`. Can also be lifted early through
    :func:`reinstate`. Raises LookupError on an unknown artist. Flushes, does NOT
    commit (the router audits + commits). Returns the item dict.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return await _upsert_artist_marker(
        db,
        artist_id,
        signals={
            "dismiss_kind": DISMISS_DEFERRED,
            "dismissed_at": now.isoformat(),
        },
    )


async def dismiss_org_candidate(db: AsyncSession, name: str) -> dict:
    """« Pas de chaîne » for an ORG candidate — a NAME with no ``artist_id``.

    Org candidates (:func:`list_candidates`) are raw channel NAMES, not artists,
    so their dismissal is keyed by name: this creates (idempotently) a placeholder
    ``channels`` marker — ``external_id`` NULL, ``artist_id`` NULL,
    ``watched=False``, ``excluded=True``, ``dismiss_kind='no_channel'`` — matched on
    ``(platform='youtube', name, external_id NULL)``. :func:`list_candidates`
    already excludes it via its ``name NOT IN (SELECT channels.name)`` guard, and
    :func:`list_channels` hides it. Raises ValueError on a blank name. Flushes,
    does NOT commit (the router audits + commits). Returns the item dict.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")

    signals = {"dismiss_kind": DISMISS_NO_CHANNEL}
    row = (
        await db.execute(
            select(Channel).where(
                Channel.platform == "youtube",
                Channel.name == name,
                Channel.external_id.is_(None),
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = Channel(
            platform="youtube",
            external_id=None,
            name=name,
            channel_type=None,
            artist_id=None,
            watched=False,
            excluded=True,
            signals=signals,
        )
        db.add(row)
    else:
        row.excluded = True
        row.watched = False
        row.signals = signals

    await db.flush()
    return _item(row)


async def list_dismissed(db: AsyncSession) -> dict:
    """List the dismiss markers (external_id NULL + excluded), artists AND orgs.

    An artist marker (``artist_id`` set) is joined to ``artist_cohort``/``artists``
    for the current name + cohort tier + relevance signals and ranked by cohort
    relevance (tier asc, then followed / library / likes / set / catalog depth
    desc). An org marker (``artist_id`` NULL) is ranked by name. Artists are
    returned first, then orgs. Each item carries its ``dismiss_kind`` and — for a
    'deferred' marker — its ``dismissed_at`` so the UI can show the kind and date.
    Loaders are awaited SEQUENTIALLY on the one session. Read-only, no commit.
    Returns ``{total, items}``.
    """
    rows = (
        await db.execute(
            select(Channel).where(
                Channel.external_id.is_(None),
                Channel.excluded.is_(True),
            )
        )
    ).scalars().all()

    artist_markers = [r for r in rows if r.artist_id is not None]
    org_markers = [r for r in rows if r.artist_id is None]

    # Cohort tier + relevance signals + current name for the artist markers.
    cohort_by_id: dict[int, ArtistCohort] = {}
    name_by_id: dict[int, str] = {}
    if artist_markers:
        aids = [r.artist_id for r in artist_markers]
        cohort_rows = (
            await db.execute(
                select(ArtistCohort, Artist.name)
                .join(Artist, Artist.id == ArtistCohort.artist_id)
                .where(ArtistCohort.artist_id.in_(aids))
            )
        ).all()
        for cohort, aname in cohort_rows:
            cohort_by_id[cohort.artist_id] = cohort
            name_by_id[cohort.artist_id] = aname
        # Names for artists whose cohort row was pruned since the dismissal.
        missing = [aid for aid in aids if aid not in name_by_id]
        if missing:
            for aid, aname in (
                await db.execute(
                    select(Artist.id, Artist.name).where(Artist.id.in_(missing))
                )
            ).all():
                name_by_id[aid] = aname

    def _artist_item(r: Channel) -> dict:
        cohort = cohort_by_id.get(r.artist_id)
        sig = cohort.signals if cohort is not None else None
        return {
            "kind": "artist",
            "channel_id": r.id,
            "name": name_by_id.get(r.artist_id) or r.name,
            "artist_id": r.artist_id,
            "tier": cohort.tier if cohort is not None else None,
            "dismiss_kind": _dismiss_kind(r.signals),
            "dismissed_at": _dismissed_at(r.signals),
            # kept for the cohort-relevance sort below
            "_followed": bool((sig or {}).get("followed")),
            "_nb_lib": _sig_int(sig, "nb_lib"),
            "_nb_likes": _sig_int(sig, "nb_likes"),
            "_nb_sets": _sig_int(sig, "nb_sets_12m"),
            "_nb_catalog": _sig_int(sig, "nb_catalog"),
        }

    artist_items = [_artist_item(r) for r in artist_markers]
    # Cohort relevance: tier first (a pruned row's NULL tier sinks last), then the
    # same personal-relevance signals list_artist_candidates ranks on.
    artist_items.sort(
        key=lambda c: (
            c["tier"] if c["tier"] is not None else 1_000,
            not c["_followed"],
            -c["_nb_lib"],
            -c["_nb_likes"],
            -c["_nb_sets"],
            -c["_nb_catalog"],
            c["artist_id"],
        )
    )
    for it in artist_items:
        for k in ("_followed", "_nb_lib", "_nb_likes", "_nb_sets", "_nb_catalog"):
            it.pop(k)

    org_items = [
        {
            "kind": "org",
            "channel_id": r.id,
            "name": r.name,
            "artist_id": None,
            "tier": None,
            "dismiss_kind": _dismiss_kind(r.signals),
            "dismissed_at": _dismissed_at(r.signals),
        }
        for r in org_markers
    ]
    org_items.sort(key=lambda c: ((c["name"] or "").lower(), c["channel_id"]))

    items = artist_items + org_items
    return {"total": len(items), "items": items}


async def reinstate(db: AsyncSession, channel_id: int) -> dict:
    """Reinstate a dismissed candidate by DELETING its marker.

    Strict guard: only a dismiss marker (``external_id`` IS NULL AND ``excluded``)
    is removable — a REAL curated channel (non-NULL ``external_id``) or a
    non-excluded row raises LookupError so a genuine channel is never deleted. Once
    the marker is gone the artist/org becomes a candidate again. Raises LookupError
    on an unknown id. Flushes, does NOT commit (the router audits + commits).
    Returns the (now-deleted) item snapshot.
    """
    row = (
        await db.execute(select(Channel).where(Channel.id == channel_id))
    ).scalar_one_or_none()
    if row is None:
        raise LookupError(f"Channel {channel_id} not found")
    if row.external_id is not None or not row.excluded:
        raise LookupError(f"Channel {channel_id} is not a dismiss marker")

    item = _item(row)
    await db.delete(row)
    await db.flush()
    return item
