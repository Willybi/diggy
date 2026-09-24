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

from models import Artist, ArtistCohort, Channel, DJSet, SetArtist, TrackIdIndex
from sqlalchemy import and_, func, select
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


async def list_artist_candidates(
    db: AsyncSession, redis=None, *, limit: int = 50, page: int = 1
) -> dict:
    """Propose cohort artists worth a watched YouTube channel (C14.b 🅱).

    LIVE query over ``artist_cohort`` joined to ``artists``, EXCLUDING excluded
    cohort rows and artists already curated into ``channels`` (a non-NULL
    ``channels.artist_id``). Each remaining member is passed through the 3-guard
    « real artist » gate (:func:`_passes_artist_gate`): denylist, a real-artist
    signal (Deezer link / catalog depth / recent DJ set) and the name heuristic.
    The relevance signals (``nb_sets_12m``/``nb_lib``/``nb_catalog``) live in the
    cohort's ``signals`` JSON, so the gate + ranking run in Python (dialect-neutral)
    over the fetched rows.

    Ranked by ``tier`` asc then relevance desc (sets > lib > catalog), tie-broken
    by ``artist_id`` for a deterministic page window; paginated in memory.

    When ``redis`` is provided, each PAGE item is annotated with its cached
    artist→channel resolution (``preselect``) READ FROM the cache only (key
    ``yt:artcand:v2:{name}``) — this function NEVER resolves (a resolution spends
    100 quota units; that happens exclusively on :func:`resolve_artist_candidate`).
    Fail-open: any Redis error leaves ``preselect`` at None, never an exception.
    Read-only, no commit. Returns ``{total, items}``.
    """
    already_curated = select(Channel.artist_id).where(Channel.artist_id.isnot(None))

    rows = (
        await db.execute(
            select(ArtistCohort, Artist.name, Artist.deezer_id)
            .join(Artist, Artist.id == ArtistCohort.artist_id)
            .where(
                ArtistCohort.excluded.isnot(True),
                ArtistCohort.artist_id.notin_(already_curated),
            )
            .order_by(ArtistCohort.tier.asc(), ArtistCohort.artist_id.asc())
        )
    ).all()

    kept: list[dict] = []
    for row, name, deezer_id in rows:
        nb_sets = _sig_int(row.signals, "nb_sets_12m")
        nb_lib = _sig_int(row.signals, "nb_lib")
        nb_catalog = _sig_int(row.signals, "nb_catalog")
        if not _passes_artist_gate(name, deezer_id, nb_catalog, nb_sets):
            continue
        kept.append(
            {
                "artist_id": row.artist_id,
                "name": name,
                "tier": row.tier,
                "nb_sets": nb_sets,
                "nb_lib": nb_lib,
                "nb_catalog": nb_catalog,
                "preselect": None,
            }
        )

    kept.sort(
        key=lambda c: (
            c["tier"],
            -c["nb_sets"],
            -c["nb_lib"],
            -c["nb_catalog"],
            c["artist_id"],
        )
    )

    total = len(kept)
    start = (page - 1) * limit
    page_items = kept[start : start + limit]

    if redis is not None:
        for it in page_items:
            try:
                cached = await redis.get(_artist_resolve_cache_key(it["name"]))
            except Exception as exc:  # fail-open: Redis down → no preselect at all
                logger.warning(
                    "artist candidate preselect cache read skipped "
                    "(Redis unavailable): %s",
                    exc,
                )
                break
            if cached is not None:
                try:
                    it["preselect"] = json.loads(cached)
                except Exception:  # corrupt/legacy payload → leave preselect None
                    pass

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
