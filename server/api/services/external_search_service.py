"""
External search service: query Deezer + TIDAL in parallel for a manual import
flow, merge and dedup by ISRC (Deezer wins), and flag results that already
exist in the catalog. Read-only — never writes to the DB.

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from schemas import ExternalSearchItem, ExternalSearchResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from utils import make_normalized_key

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"


async def _search_deezer(q: str, limit: int) -> list[dict]:
    """Search Deezer for tracks matching `q`. Returns [] on any network error.

    Deezer's /search does not always include the ISRC — an absent ISRC is
    acceptable (isrc=None), it just means the track can never dedup by ISRC.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{DEEZER_API}/search", params={"q": q, "limit": limit}
            )
            data = resp.json()
    except Exception:
        return []

    hits = data.get("data", []) if isinstance(data, dict) else []
    items: list[dict] = []
    for hit in hits:
        artist = hit.get("artist") if isinstance(hit.get("artist"), dict) else None
        album = hit.get("album") if isinstance(hit.get("album"), dict) else None
        duration = hit.get("duration")
        items.append(
            {
                "source": "deezer",
                "external_id": str(hit["id"]),
                "title": hit.get("title", ""),
                "artist": artist.get("name") if artist else None,
                "isrc": hit.get("isrc") or None,
                "duration_ms": (duration or 0) * 1000 or None,
                "artwork_url": (album.get("cover_medium") or album.get("cover_big"))
                if album
                else None,
            }
        )
    return items


async def _search_tidal(q: str, limit: int) -> list[dict]:
    """Search TIDAL for tracks matching `q`, off the event loop.

    Degrades gracefully: if TIDAL is unavailable (no tokens, network error),
    logs a warning and returns [] so the flow falls back to Deezer only.
    """
    from workers import source_clients

    try:
        return await run_in_threadpool(source_clients.search_tidal, q, limit)
    except Exception as exc:
        logger.warning("TIDAL search unavailable, falling back to Deezer only: %s", exc)
        return []


async def _match_catalog(
    db: AsyncSession, isrcs: set[str], norm_keys: set[str]
) -> tuple[dict[str, int], dict[str, int]]:
    """Batch-lookup catalog entries by ISRC or normalized_key (single query)."""
    from models import CatalogEntry

    conditions = []
    if isrcs:
        conditions.append(CatalogEntry.isrc.in_(isrcs))
    if norm_keys:
        conditions.append(CatalogEntry.normalized_key.in_(norm_keys))
    if not conditions:
        return {}, {}

    result = await db.execute(
        select(
            CatalogEntry.id, CatalogEntry.isrc, CatalogEntry.normalized_key
        ).where(or_(*conditions))
    )
    by_isrc: dict[str, int] = {}
    by_key: dict[str, int] = {}
    for row in result:
        if row.isrc:
            by_isrc[row.isrc] = row.id
        by_key[row.normalized_key] = row.id
    return by_isrc, by_key


async def search_external(
    db: AsyncSession, q: str, limit: int
) -> ExternalSearchResponse:
    """Parallel Deezer + TIDAL search, merged/deduped by ISRC (Deezer wins),
    with a `catalog_id` set on results already present in the catalog."""
    q = q.strip()
    if not q:
        return ExternalSearchResponse(items=[])

    # Each source is protected independently: a source that errors yields [].
    results = await asyncio.gather(
        _search_deezer(q, limit), _search_tidal(q, limit), return_exceptions=True
    )
    deezer_hits = results[0] if isinstance(results[0], list) else []
    tidal_hits = results[1] if isinstance(results[1], list) else []

    # Merge + dedup by ISRC. Deezer first, then remaining TIDAL. Tracks without
    # an ISRC never merge (kept separate) — Deezer order is preserved.
    seen_isrcs = {h["isrc"] for h in deezer_hits if h["isrc"]}
    merged = list(deezer_hits)
    for h in tidal_hits:
        if h["isrc"] and h["isrc"] in seen_isrcs:
            continue
        merged.append(h)

    # Detect existing catalog entries in one batch query.
    isrcs = {h["isrc"] for h in merged if h["isrc"]}
    norm_keys = {
        make_normalized_key(h["title"], h["artist"]) for h in merged if h["title"]
    }
    by_isrc, by_key = await _match_catalog(db, isrcs, norm_keys)

    items: list[ExternalSearchItem] = []
    for h in merged:
        catalog_id = None
        if h["isrc"] and h["isrc"] in by_isrc:
            catalog_id = by_isrc[h["isrc"]]
        elif h["title"]:
            catalog_id = by_key.get(make_normalized_key(h["title"], h["artist"]))
        items.append(
            ExternalSearchItem(
                source=h["source"],
                external_id=h["external_id"],
                title=h["title"],
                artist=h["artist"],
                isrc=h["isrc"],
                duration_ms=h["duration_ms"],
                artwork_url=h["artwork_url"],
                catalog_id=catalog_id,
            )
        )
    return ExternalSearchResponse(items=items)
