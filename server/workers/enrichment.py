"""Shared async enrichment pipelines for Deezer and Beatport.

Used by all pipeline tasks (crawl_single_playlist, resolve_set_tracks, enrich_catalog, etc.).
Processes entries concurrently using the rate limiter.

Usage:
    async with HttpPool(limiter) as pool:
        stats = await enrich_deezer_batch(session, entries, pool, s3, known_isrcs)
        stats = await enrich_beatport_batch(session, entries, pool, s3)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import redis as redis_lib
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session
from workers.async_http import DeezerHTTPError
from workers.catalog_merge import CatalogEntryMerged

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_BEATPORT_CACHE_TTL = int(os.environ.get("BEATPORT_CACHE_TTL", "86400"))  # default 24h

# E1 — re-scan backoff: a not-found entry is retried after 30 days, then 90,
# then abandoned for good after 3 attempts.
RESCAN_TIER2_DAYS = 30
RESCAN_TIER3_DAYS = 90
MAX_SEARCH_ATTEMPTS = 3
# E1 — inline enrichment (sets/radar) skips entries searched within this window
INLINE_SEARCH_COOLDOWN_HOURS = 24


def _get_redis():
    try:
        return redis_lib.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None


def _cache_key(prefix: str, query: str) -> str:
    h = hashlib.md5(query.lower().strip().encode()).hexdigest()
    return f"bp:{prefix}:{h}"


# ── Candidate selection (E1 re-scan with backoff) ──


def _source_columns(source: str) -> tuple:
    from models import CatalogEntry

    if source == "deezer":
        return (
            CatalogEntry.deezer_id,
            CatalogEntry.deezer_searched_at,
            CatalogEntry.deezer_search_attempts,
        )
    if source == "beatport":
        return (
            CatalogEntry.beatport_id,
            CatalogEntry.beatport_searched_at,
            CatalogEntry.beatport_search_attempts,
        )
    raise ValueError(f"unknown enrichment source: {source}")


def select_enrich_candidates(
    session: Session, *, source: str, budget: int, now: datetime
) -> list:
    """Pick catalog entries missing a {source}_id to enrich, under a budget.

    Tier 1: never searched, newest first (id DESC as freshness proxy).
    Tier 2: 1 attempt, searched more than RESCAN_TIER2_DAYS ago.
    Tier 3: 2 attempts, searched more than RESCAN_TIER3_DAYS ago.
    MAX_SEARCH_ATTEMPTS and beyond: abandoned, never re-selected.
    Retries (tiers 2-3, oldest search first) only consume the budget
    left over by tier 1; total never exceeds ``budget``.
    """
    from models import CatalogEntry

    id_col, searched_col, attempts_col = _source_columns(source)

    if budget <= 0:
        return []

    fresh = (
        session.execute(
            select(CatalogEntry)
            .where(id_col.is_(None), searched_col.is_(None))
            .order_by(CatalogEntry.id.desc())
            .limit(budget)
        )
        .scalars()
        .all()
    )

    remaining = budget - len(fresh)
    if remaining <= 0:
        return list(fresh)

    retries = (
        session.execute(
            select(CatalogEntry)
            .where(
                id_col.is_(None),
                or_(
                    and_(
                        attempts_col == 1,
                        searched_col < now - timedelta(days=RESCAN_TIER2_DAYS),
                    ),
                    and_(
                        attempts_col == 2,
                        searched_col < now - timedelta(days=RESCAN_TIER3_DAYS),
                    ),
                ),
            )
            .order_by(searched_col.asc())
            .limit(remaining)
        )
        .scalars()
        .all()
    )

    return list(fresh) + list(retries)


def not_recently_searched(searched_col, now: datetime):
    """SQL clause: never searched, or searched more than
    INLINE_SEARCH_COOLDOWN_HOURS ago. Guards inline enrichment (sets/radar)
    against re-searching entries the nightly sweep just covered."""
    cutoff = now - timedelta(hours=INLINE_SEARCH_COOLDOWN_HOURS)
    return or_(searched_col.is_(None), searched_col < cutoff)


def _mark_searched(entry, source: str, now: datetime) -> None:
    """Record a completed search attempt (found or not).

    Never called on HTTP errors/exceptions: an outage is not an attempt
    (A3-04), the entry must stay eligible for the next nightly run.
    """
    if source == "deezer":
        entry.deezer_searched_at = now
        entry.deezer_search_attempts = (entry.deezer_search_attempts or 0) + 1
    else:
        entry.beatport_searched_at = now
        entry.beatport_search_attempts = (entry.beatport_search_attempts or 0) + 1


# ── Deezer enrichment (async) ──


async def _search_deezer_async(
    pool, artist: str | None, title: str | None
) -> dict | None:
    """Async version of deezer_enrich.search_deezer — cascading search strategy."""
    if not title:
        return None

    # Import the title-cleaning helpers from deezer_enrich
    from workers.deezer_enrich import (
        _first_artist,
        _strip_non_remix_parens,
        _strip_safe_suffixes,
    )

    def _clean(s):
        return s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")

    async def _search(t, a=artist):
        clean_t = _clean(t)
        clean_a = _clean(a) if a else a
        if clean_a:
            data = await pool.deezer_get(
                "/search",
                params={"q": f'artist:"{clean_a}" track:"{clean_t}"', "limit": 1},
            )
            hits = data.get("data", [])
            if hits:
                return hits[0]
        q = f"{clean_a} {clean_t}" if clean_a else clean_t
        data = await pool.deezer_get("/search", params={"q": q, "limit": 1})
        hits = data.get("data", [])
        return hits[0] if hits else None

    # 1. Original title
    hit = await _search(title)
    if hit:
        return hit

    # 2. Strip safe suffixes
    safe = _strip_safe_suffixes(title)
    if safe:
        hit = await _search(safe)
        if hit:
            return hit

    # 3. Strip non-remix parens
    stripped = _strip_non_remix_parens(title)
    if stripped and stripped != safe:
        hit = await _search(stripped)
        if hit:
            return hit

    # 4. First artist only
    if artist:
        first = _first_artist(artist)
        if first:
            t = stripped or safe or title
            hit = await _search(t, a=first)
            if hit:
                return hit

    return None


async def _enrich_entry_async(
    entry, hit: dict, pool, s3, known_isrcs: set, session=None
) -> bool:
    """Async version of enrich_entry — applies Deezer data to a CatalogEntry."""
    changed = False

    deezer_id = str(hit["id"])
    if entry.deezer_id != deezer_id:
        # X1/L2: never stamp a deezer_id another catalog row already carries —
        # fold this (loser) row into the pre-existing one and signal the caller.
        if session is not None:
            from workers.catalog_dedup import fold_if_platform_id_taken

            fold_if_platform_id_taken(session, entry, "deezer_id", deezer_id)
        entry.deezer_id = deezer_id
        changed = True

    isrc = hit.get("isrc")
    if isrc and not entry.isrc:
        if isrc not in known_isrcs:
            # Use conflict-safe UPDATE to avoid IntegrityError on ISRC unique constraint
            if session is not None:
                result = session.execute(
                    text(
                        "UPDATE catalog SET isrc = :isrc "
                        "WHERE id = :id AND isrc IS NULL "
                        "AND NOT EXISTS (SELECT 1 FROM catalog WHERE isrc = :isrc)"
                    ),
                    {"isrc": isrc, "id": entry.id},
                )
                if result.rowcount > 0:
                    entry.isrc = isrc
                    changed = True
            else:
                entry.isrc = isrc
                changed = True
            known_isrcs.add(isrc)

    duration_s = hit.get("duration")
    if duration_s and not entry.duration_ms:
        entry.duration_ms = duration_s * 1000
        changed = True

    has_preview = bool((hit.get("preview") or "").strip())
    if entry.has_preview != has_preview:
        entry.has_preview = has_preview
        changed = True

    # Upload cover if missing
    if not entry.has_artwork:
        cover_url = (hit.get("album") or {}).get("cover_medium") or (
            hit.get("album") or {}
        ).get("cover_big")
        if cover_url:
            img_data = await pool.download_image(cover_url)
            if img_data:
                from services.image_service import ImageService

                if ImageService.upload_bytes(img_data, "catalog-artworks", f"{entry.id}.jpg"):
                    entry.has_artwork = True
                    changed = True

    # Promote private → shared when Deezer confirms the track exists
    if changed and getattr(entry, "scope", None) == "private" and entry.deezer_id:
        entry.scope = "shared"
        entry.owner_id = None

    return changed


async def enrich_deezer_batch(
    session: Session,
    entries: list,
    pool,
    s3,
    known_isrcs: set,
    *,
    source: str = "cross-search",
    ext_id_map: dict | None = None,
) -> dict:
    """Enrich multiple catalog entries via Deezer concurrently.

    Args:
        entries: list of CatalogEntry objects missing deezer_id
        pool: HttpPool instance (already entered)
        s3: boto3 S3 client
        known_isrcs: set of existing ISRCs to avoid constraint violations
        source: "deezer" (use ext_id_map for direct lookup) or "cross-search" (search by title+artist)
        ext_id_map: dict of {catalog_id: deezer_external_track_id} for direct Deezer lookups
    """
    enriched = 0
    errors = 0
    merged = 0

    async def _enrich_one(entry):
        nonlocal enriched, errors, merged
        try:
            now = datetime.now(timezone.utc)
            if source == "deezer" and ext_id_map:
                ext_id = ext_id_map.get(entry.id)
                if not ext_id:
                    return
                hit = await pool.deezer_get(f"/track/{ext_id}")
                if not hit.get("id"):
                    logger.debug(
                        "Deezer not found for catalog %s (track %s)", entry.id, ext_id
                    )
                    _mark_searched(entry, "deezer", now)
                    return
            else:
                hit = await _search_deezer_async(pool, entry.artist, entry.title)
                if not hit:
                    logger.debug("Deezer not found for catalog %s", entry.id)
                    _mark_searched(entry, "deezer", now)
                    return

            try:
                changed = await _enrich_entry_async(
                    entry, hit, pool, s3, known_isrcs, session=session
                )
            except CatalogEntryMerged as m:
                # X1/L2: entry duplicated an existing row (same deezer_id) and was
                # folded into it. The dead row must NOT be marked/linked — the
                # canonical already carries the id and unified metadata.
                merged += 1
                logger.info(
                    "Deezer enrich: folded a duplicate into canonical catalog %s",
                    m.surviving_id,
                )
                return

            if changed:
                enriched += 1
                # Link artist from Deezer hit to catalog_artists
                try:
                    from workers.deezer_enrich import link_catalog_artist_from_hit

                    link_catalog_artist_from_hit(session, entry.id, hit)
                except Exception:
                    # non-critical, sync_artists will catch up
                    logger.warning(
                        "artist link failed for catalog %s", entry.id, exc_info=True
                    )
            _mark_searched(entry, "deezer", now)
        except DeezerHTTPError as e:
            # Deezer outage, not a "not found": leave deezer_searched_at unset
            # so the entry is retried by the next nightly run.
            logger.warning("Deezer HTTP error for catalog %s: %s", entry.id, e)
            errors += 1
        except Exception as e:
            logger.warning("Deezer enrich failed for catalog %s: %s", entry.id, e)
            errors += 1

    # Process concurrently (rate limiter handles concurrency cap)
    await asyncio.gather(*[_enrich_one(e) for e in entries])

    return {"enriched": enriched, "errors": errors, "merged": merged}


# ── Beatport enrichment (async) ──


async def _search_beatport_async(
    pool, title: str, artist: str | None, isrc: str | None, rcache=None
) -> dict | None:
    """Async Beatport search with ISRC-first strategy, artist validation, and release fallback."""
    import sys
    import urllib.parse

    sys.path.insert(0, "/app")

    from beatport.client import (
        _artist_matches,
        _normalize_release_page_track,
        _normalize_track,
        _pick_best_track,
    )

    def _extract_next_data(html: str) -> dict:
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return {}
        return json.loads(match.group(1))

    def _extract_queries(data: dict) -> list[dict]:
        return (
            data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

    def _extract_tracks(data: dict) -> list[dict]:
        for query in _extract_queries(data):
            state = query.get("state", {}).get("data", {})
            if isinstance(state, dict) and "tracks" in state:
                tracks_data = state["tracks"]
                raw_list = (
                    tracks_data.get("data", []) if isinstance(tracks_data, dict) else []
                )
                return raw_list[:10]
        return []

    async def _do_search(q: str) -> list[dict]:
        if rcache:
            key = _cache_key("tsearch", q)
            try:
                cached = rcache.get(key)
                if cached is not None:
                    return json.loads(cached)
            except Exception:
                pass

        path = f"/search?q={urllib.parse.quote(q)}&type=tracks"
        resp = await pool.beatport_get(path)
        if resp.status_code != 200:
            return []
        data = _extract_next_data(resp.text)
        raw = _extract_tracks(data)
        results = [_normalize_track(t) for t in raw]

        if rcache and results:
            key = _cache_key("tsearch", q)
            try:
                rcache.setex(key, _BEATPORT_CACHE_TTL, json.dumps(results))
            except Exception:
                pass

        return results

    async def _do_release_search(q: str) -> list[dict]:
        if rcache:
            key = _cache_key("rsearch", q)
            try:
                cached = rcache.get(key)
                if cached is not None:
                    return json.loads(cached)
            except Exception:
                pass

        path = f"/search?q={urllib.parse.quote(q)}&type=releases"
        resp = await pool.beatport_get(path)
        if resp.status_code != 200:
            return []
        data = _extract_next_data(resp.text)
        releases = []
        for query in _extract_queries(data):
            state = query.get("state", {}).get("data", {})
            if isinstance(state, dict) and "releases" in state:
                releases_data = state["releases"]
                raw_list = (
                    releases_data.get("data", [])
                    if isinstance(releases_data, dict)
                    else []
                )
                for r in raw_list[:10]:
                    releases.append(
                        {
                            "id": r.get("release_id"),
                            "name": r.get("release_name"),
                            "artists": [
                                {"id": a.get("artist_id"), "name": a.get("artist_name")}
                                for a in (r.get("artists") or [])
                            ],
                        }
                    )
                break

        if rcache and releases:
            key = _cache_key("rsearch", q)
            try:
                rcache.setex(key, _BEATPORT_CACHE_TTL, json.dumps(releases))
            except Exception:
                pass

        return releases

    async def _fetch_release_tracks(release_name: str, release_id: int) -> list[dict]:
        cache_key = f"bp:reltracks:{release_id}"
        if rcache:
            try:
                cached = rcache.get(cache_key)
                if cached is not None:
                    return json.loads(cached)
            except Exception:
                pass

        slug = re.sub(r"[^a-z0-9]+", "-", release_name.lower()).strip("-")
        resp = await pool.beatport_get(f"/release/{slug}/{release_id}")
        if resp.status_code != 200:
            return []
        data = _extract_next_data(resp.text)
        tracks = []
        for query in _extract_queries(data):
            state = query.get("state", {}).get("data", {})
            if isinstance(state, dict) and "results" in state:
                tracks = [_normalize_release_page_track(t) for t in state["results"]]
                break

        if rcache and tracks:
            try:
                rcache.setex(cache_key, _BEATPORT_CACHE_TTL, json.dumps(tracks))
            except Exception:
                pass

        return tracks

    # Strategy 1: ISRC search (most reliable)
    if isrc:
        results = await _do_search(isrc)
        for t in results:
            if t.get("isrc") == isrc:
                return t

    # Strategy 2: title+artist track search WITH artist validation
    if title:
        q = f"{artist} {title}" if artist else title
        results = await _do_search(q)
        match = _pick_best_track(results, artist, title)
        if match:
            return match

        # Strategy 3: release fallback
        releases = await _do_release_search(q)
        title_lower = title.lower()
        for rel in releases:
            if not _artist_matches(rel.get("artists", []), artist):
                continue
            tracks = await _fetch_release_tracks(rel["name"], rel["id"])
            if not tracks:
                continue
            for t in tracks:
                t_name = (t.get("name") or "").lower()
                if title_lower in t_name or t_name in title_lower:
                    return t
            if len(tracks) == 1:
                return tracks[0]

    return None


async def enrich_beatport_batch(
    session: Session,
    entries: list,
    pool,
    s3,
) -> dict:
    """Enrich multiple catalog entries via Beatport concurrently.

    Args:
        entries: list of CatalogEntry objects missing beatport_id
        pool: HttpPool instance (already entered)
        s3: boto3 S3 client
    """
    import sys

    sys.path.insert(0, "/app")
    from beatport.enrich import enrich_from_beatport

    rcache = _get_redis()
    enriched = 0
    not_found = 0
    errors = 0
    merged = 0

    async def _enrich_one(entry):
        nonlocal enriched, not_found, errors, merged
        try:
            bp_track = await _search_beatport_async(
                pool, entry.title, entry.artist, entry.isrc, rcache=rcache
            )
            if bp_track:
                try:
                    matched = enrich_from_beatport(entry, bp_track, s3=s3, session=session)
                except CatalogEntryMerged as m:
                    # X1/L2: entry duplicated an existing row (same beatport_id)
                    # and was folded into it — do NOT mark the dead row.
                    merged += 1
                    logger.info(
                        "Beatport enrich: folded a duplicate into canonical "
                        "catalog %s",
                        m.surviving_id,
                    )
                    return
                if matched:
                    enriched += 1
                else:
                    not_found += 1
            else:
                not_found += 1
            _mark_searched(entry, "beatport", datetime.now(timezone.utc))
        except Exception as e:
            logger.warning("Beatport enrich failed for catalog %s: %s", entry.id, e)
            errors += 1

    # Process concurrently (rate limiter handles concurrency cap at 2)
    await asyncio.gather(*[_enrich_one(e) for e in entries])

    return {"enriched": enriched, "not_found": not_found, "errors": errors, "merged": merged}
