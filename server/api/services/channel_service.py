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

from models import Channel, TrackIdIndex
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
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

    Aggregates ``trackid_index`` by ``channel`` (a channel name known from the
    indexed TrackID corpus), EXCLUDING names already present in ``channels``.

    Sort metric — « discovery value », least-covered first: a channel's value is
    the number of its indexed sets NOT yet linked to a Diggy set, i.e.
    ``trackid_count - set_count`` (``set_count`` = rows with a non-NULL
    ``set_id``). Higher gap = more untapped sets → surfaced first; ties broken by
    the raw trackid volume then the name for determinism. Read-only, no commit.

    When ``redis`` is provided, each candidate is annotated with its cached
    YouTube pre-selection (``preselect``) READ FROM the cache only — this function
    NEVER runs a YouTube search (a search would burn 100 quota units per name on
    every listing render). A resolution happens exclusively on the explicit
    ``resolve_candidate`` path. Fail-open: any Redis error leaves ``preselect``
    at None, never an exception. ``redis=None`` keeps the legacy behaviour.
    """
    trackid_count = func.count()
    set_count = func.count(TrackIdIndex.set_id)

    stmt = (
        select(
            TrackIdIndex.channel.label("name"),
            trackid_count.label("trackid_count"),
            set_count.label("set_count"),
        )
        .where(
            TrackIdIndex.channel.isnot(None),
            TrackIdIndex.channel.notin_(select(Channel.name)),
        )
        .group_by(TrackIdIndex.channel)
        .order_by(
            (trackid_count - set_count).desc(),
            trackid_count.desc(),
            TrackIdIndex.channel.asc(),
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
