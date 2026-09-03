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
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import ObjectDeletedError
from workers.async_http import BeatportHTTPError, DeezerHTTPError
from workers.catalog_merge import CatalogEntryMerged

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_BEATPORT_CACHE_TTL = int(os.environ.get("BEATPORT_CACHE_TTL", "86400"))  # default 24h

# E1 — re-scan backoff (BOTH Deezer + Beatport enrichment: select_enrich_candidates
# is source-agnostic). A not-found entry is retried after RESCAN_TIER2_DAYS, then
# RESCAN_TIER3_DAYS, then abandoned for good after MAX_SEARCH_ATTEMPTS. Stretched
# from 30/90 to ~1 year (2026-09-03): a not-found row is mostly genuinely absent
# from the source (Beatport is electronic-only), so re-searching it every month
# was near-zero-yield churn (measured ~3% on the residual). The bulk drain + an
# explicit yearly re-check now run out-of-band (the local worker/beatport_backfill
# tool, --rescan-days 365), so the nightly VPS sweep only needs a yearly cadence.
RESCAN_TIER2_DAYS = 365
RESCAN_TIER3_DAYS = 365
MAX_SEARCH_ATTEMPTS = 3
# E1 — inline enrichment (sets/radar) skips entries searched within this window
INLINE_SEARCH_COOLDOWN_HOURS = 24

# C12 — priority-aware Beatport drain: a catalog row carries an optional
# `enrich_priority` (bigger = enriched first; NULL = not yet stamped). An
# un-stamped row is treated at this median baseline so it is neither starved
# nor jumped ahead of genuinely high-priority work.
PRIORITY_BASELINE = 75


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
    session: Session,
    *,
    source: str,
    budget: int,
    now: datetime,
    genre_only: bool = False,
    order_by_priority: bool = False,
    priority_floor: int | None = None,
) -> list:
    """Pick catalog entries to enrich, under a budget.

    Default (``genre_only=False``): entries missing a ``{source}_id``.
    Tier 1: never searched, newest first (id DESC as freshness proxy).
    Tier 2: 1 attempt, searched more than RESCAN_TIER2_DAYS ago.
    Tier 3: 2 attempts, searched more than RESCAN_TIER3_DAYS ago.
    MAX_SEARCH_ATTEMPTS and beyond: abandoned, never re-selected.
    Retries (tiers 2-3, oldest search first) only consume the budget
    left over by tier 1; total never exceeds ``budget``.

    ``genre_only=True`` (admin "auto-classify", A3-01): target entries with NO
    genre instead of entries missing a ``{source}_id`` — the id-missing tier
    guard is relaxed to an empty-genres one, so a row that already carries a
    beatport_id but no genre is still picked. The re-scan tiering (never / 30d /
    90d backoff, budget split) is otherwise unchanged. The default path is
    strictly untouched (same predicate as ``count_enrich_backlog`` mirrors).

    ``order_by_priority`` / ``priority_floor`` (C12, both falsy by default so
    every existing caller — Deezer included — is unchanged): applied to the
    Tier-1 "fresh" selection ONLY. When ``order_by_priority`` is True, fresh rows
    are ordered by ``coalesce(enrich_priority, PRIORITY_BASELINE)`` DESC (bigger =
    first) with ``id`` DESC kept as the tie-break. When ``priority_floor`` is set,
    fresh rows whose coalesced priority is below it are excluded. Retries (tiers
    2-3) are DELIBERATELY never floored nor re-ordered by priority — that would
    starve the 30/90-day re-scans.
    """
    from models import CatalogEntry
    from models.base import array_is_empty

    id_col, searched_col, attempts_col = _source_columns(source)

    if budget <= 0:
        return []

    # The tier "base" predicate: id-missing (default) or genre-missing (gated).
    base = array_is_empty(CatalogEntry.genres) if genre_only else id_col.is_(None)

    # C12 — un-stamped (NULL) priority folds to the median baseline.
    priority_expr = func.coalesce(CatalogEntry.enrich_priority, PRIORITY_BASELINE)
    fresh_where = [base, searched_col.is_(None)]
    if priority_floor is not None:
        fresh_where.append(priority_expr >= priority_floor)
    fresh_order = (
        (priority_expr.desc(), CatalogEntry.id.desc())
        if order_by_priority
        else (CatalogEntry.id.desc(),)
    )

    fresh = (
        session.execute(
            select(CatalogEntry)
            .where(*fresh_where)
            .order_by(*fresh_order)
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
                base,
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


def count_enrich_backlog(
    session: Session,
    *,
    source: str,
    now: datetime,
    priority_floor: int | None = None,
) -> dict:
    """Count catalog entries by enrichment tier for ``source`` (deezer/beatport).

    Faithful to :func:`select_enrich_candidates`: same columns (``_source_columns``)
    and the same RESCAN_* thresholds, so the monitoring figures match what the
    nightly/hourly sweep would actually pick up. Buckets, over id-missing rows:

      never_tried : never searched (``searched_at`` NULL, i.e. 0 attempts)
      due_retry   : 1 attempt >TIER2 days ago, or 2 attempts >TIER3 days ago
                    (exactly the retry predicate of select_enrich_candidates)
      cooldown    : 1-2 attempts but searched too recently to be due yet
      abandoned   : >= MAX_SEARCH_ATTEMPTS (never re-selected)

    ``total_missing`` = every id-missing row (never+due+cooldown+abandoned);
    ``total_linked`` = rows already carrying a ``{source}_id``. A naive
    "id NULL AND attempts < MAX" over-counts because it swallows the cooldown
    tier — hence the explicit split.

    ``priority_floor`` (C12, default None → counts unchanged): when set, mirrors
    the Tier-1 fresh eligibility of :func:`select_enrich_candidates` by applying
    the same ``coalesce(enrich_priority, PRIORITY_BASELINE) >= priority_floor``
    condition to the ``never_tried`` partition ONLY (retries are never floored),
    so the monitoring never-tried figure reflects what the priority-floored drain
    would actually pick up.
    """
    from models import CatalogEntry

    id_col, searched_col, attempts_col = _source_columns(source)
    missing = id_col.is_(None)

    never_predicates = [missing, searched_col.is_(None)]
    if priority_floor is not None:
        never_predicates.append(
            func.coalesce(CatalogEntry.enrich_priority, PRIORITY_BASELINE)
            >= priority_floor
        )

    def _count(*predicates) -> int:
        return (
            session.execute(
                select(func.count(CatalogEntry.id)).where(*predicates)
            ).scalar()
            or 0
        )

    tier2_cutoff = now - timedelta(days=RESCAN_TIER2_DAYS)
    tier3_cutoff = now - timedelta(days=RESCAN_TIER3_DAYS)
    # due_retry mirrors select_enrich_candidates (`<` cutoff); cooldown is its
    # non-null complement (`>=` cutoff), so never/due/cooldown/abandoned partition
    # the id-missing rows without overlap.
    due_retry = or_(
        and_(attempts_col == 1, searched_col < tier2_cutoff),
        and_(attempts_col == 2, searched_col < tier3_cutoff),
    )
    cooldown = or_(
        and_(attempts_col == 1, searched_col >= tier2_cutoff),
        and_(attempts_col == 2, searched_col >= tier3_cutoff),
    )

    return {
        "never_tried": _count(*never_predicates),
        "due_retry": _count(missing, due_retry),
        "cooldown": _count(missing, cooldown),
        "abandoned": _count(missing, attempts_col >= MAX_SEARCH_ATTEMPTS),
        "total_missing": _count(missing),
        "total_linked": _count(id_col.isnot(None)),
    }


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


def _load_m2m_artist_names(session, entries) -> dict[int, str]:
    """Batch-load the catalog_artists (M2M) names for ``entries`` in ONE query.

    X4.a — the enrichment matcher must validate a platform hit against the
    artists the UI actually shows (the ``catalog_artists`` M2M, via
    ``track.artists``), NOT the denormalized ``catalog.artist`` column. When the
    two diverge, matching on the flat column confirms a hit against an artist the
    user never sees and stamps a WRONG platform id (measured: 1664 rows post-X3).

    Returns ``{catalog_id: "Name1, Name2"}`` — names joined by ", " (the matchers
    already split on that separator), ordered by ``position`` (NULLs last, handled
    defensively). An entry with NO M2M link is simply absent from the map, so the
    caller falls back to ``entry.artist`` — which is correct for inline-crawled
    rows (resolve_set_tracks / radar) whose fresh M2M is still empty and whose
    flat ``artist`` comes straight from the source.

    ONE query on purpose: never ``asyncio.gather`` several ``session.execute`` on
    the same Session (asyncpg wedges on concurrent access) — the map is built
    here, synchronously, BEFORE the async gather in the batch functions.
    """
    from models import Artist, CatalogArtist

    # A row deleted mid-batch by a concurrent merge (a sibling enrich worker or the
    # local beatport_backfill tool) leaves its ORM object expired, so reloading
    # ``e.id`` here raises ObjectDeletedError. Skip the dead row instead of letting
    # it kill the whole batch — the per-entry path in the callers already handles a
    # row that disappears mid-flight (its own ObjectDeletedError / except guard).
    ids = []
    for e in entries:
        try:
            ids.append(e.id)
        except ObjectDeletedError:
            continue
    if not ids:
        return {}

    rows = session.execute(
        select(CatalogArtist.catalog_id, Artist.name)
        .join(Artist, Artist.id == CatalogArtist.artist_id)
        .where(CatalogArtist.catalog_id.in_(ids))
        .order_by(
            CatalogArtist.catalog_id,
            # NULL positions sort last (dialect-neutral: false<true on both PG
            # and SQLite), so a properly-positioned primary artist leads.
            CatalogArtist.position.is_(None),
            CatalogArtist.position,
        )
    ).all()

    grouped: dict[int, list[str]] = {}
    for catalog_id, name in rows:
        if name:
            grouped.setdefault(catalog_id, []).append(name)
    return {cid: ", ".join(names) for cid, names in grouped.items()}


# ── Deezer enrichment (async) ──


async def _search_deezer_async(
    pool, artist: str | None, title: str | None, isrc: str | None = None
) -> dict | None:
    """Async version of deezer_enrich.search_deezer — cascading search strategy.

    Each cascade candidate is validated against the ORIGINAL artist/title (and
    ``isrc`` when known) before being returned, so a non-matching hit (e.g. a
    remix inheriting the original's deezer_id) is skipped and the search yields
    None rather than a wrong recording. Twin of the sync ``search_deezer``.
    """
    if not title:
        return None

    # Import the title-cleaning + validation helpers from deezer_enrich
    from workers.deezer_enrich import (
        _deezer_hit_matches,
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
    if hit and _deezer_hit_matches(hit, artist, title, isrc):
        return hit

    # 2. Strip safe suffixes
    safe = _strip_safe_suffixes(title)
    if safe:
        hit = await _search(safe)
        if hit and _deezer_hit_matches(hit, artist, title, isrc):
            return hit

    # 3. Strip non-remix parens
    stripped = _strip_non_remix_parens(title)
    if stripped and stripped != safe:
        hit = await _search(stripped)
        if hit and _deezer_hit_matches(hit, artist, title, isrc):
            return hit

    # 4. First artist only
    if artist:
        first = _first_artist(artist)
        if first:
            t = stripped or safe or title
            hit = await _search(t, a=first)
            if hit and _deezer_hit_matches(hit, artist, title, isrc):
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

    # X4.a — validate against the artists the UI shows (catalog_artists M2M),
    # not the flat catalog.artist column. Loaded ONCE, synchronously, before the
    # async gather (never gather session.execute on one Session — asyncpg wedges).
    # session is None for legacy callers → fall back to entry.artist everywhere.
    m2m_names = _load_m2m_artist_names(session, entries) if session is not None else {}

    async def _enrich_one(entry):
        nonlocal enriched, errors, merged
        # A row deleted mid-batch by a concurrent merge → any lazy attribute
        # access on it raises ObjectDeletedError. Resolve the PK ONCE, up front,
        # under guard: a benign per-entry race must never bubble out of the
        # gather and fail the whole task (the logging handlers below reuse
        # entry_id, so they never re-trigger the load on a dead row).
        try:
            entry_id = entry.id
        except ObjectDeletedError:
            errors += 1
            return
        try:
            now = datetime.now(timezone.utc)
            if source == "deezer" and ext_id_map:
                ext_id = ext_id_map.get(entry_id)
                if not ext_id:
                    return
                hit = await pool.deezer_get(f"/track/{ext_id}")
                if not hit.get("id"):
                    logger.debug(
                        "Deezer not found for catalog %s (track %s)", entry_id, ext_id
                    )
                    _mark_searched(entry, "deezer", now)
                    return
            else:
                # M2M names when present (the displayed truth), else the flat
                # column — correct for inline-crawled rows whose M2M is empty.
                match_artist = m2m_names.get(entry_id) or entry.artist
                hit = await _search_deezer_async(
                    pool, match_artist, entry.title, isrc=entry.isrc
                )
                if not hit:
                    logger.debug("Deezer not found for catalog %s", entry_id)
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
                    from workers.deezer_enrich import (
                        link_catalog_album_from_hit,
                        link_catalog_artist_from_hit,
                    )

                    link_catalog_artist_from_hit(session, entry_id, hit)
                    # L2: upsert the track's album + cover, fil-de-l'eau. Reuses
                    # the hit already in hand (no extra Deezer call).
                    link_catalog_album_from_hit(session, entry_id, hit)
                except Exception:
                    # non-critical, sync_artists will catch up
                    logger.warning(
                        "artist/album link failed for catalog %s",
                        entry_id,
                        exc_info=True,
                    )
            _mark_searched(entry, "deezer", now)
        except DeezerHTTPError as e:
            # Deezer outage, not a "not found": leave deezer_searched_at unset
            # so the entry is retried by the next nightly run.
            logger.warning("Deezer HTTP error for catalog %s: %s", entry_id, e)
            errors += 1
        except ObjectDeletedError:
            # The row was deleted mid-enrich by a concurrent merge (an attribute
            # access raised after the PK was resolved). Nothing left to re-scan —
            # count it and move on, but NEVER _mark_searched a row that no longer
            # exists (marking an attempt on a deleted line is meaningless).
            logger.warning(
                "catalog %s deleted mid-enrich (concurrent merge), skipping", entry_id
            )
            errors += 1
        except Exception as e:
            logger.warning("Deezer enrich failed for catalog %s: %s", entry_id, e)
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
        _release_title_matches,
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
            raise BeatportHTTPError(resp.status_code, path)
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
            raise BeatportHTTPError(resp.status_code, path)
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
        path = f"/release/{slug}/{release_id}"
        resp = await pool.beatport_get(path)
        if resp.status_code != 200:
            raise BeatportHTTPError(resp.status_code, path)
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

        # Strategy 3: release fallback — require a remix-aware title match so the
        # shared release beatport_id is never stamped onto the wrong EP track (no
        # more blind single-track guess; identical guard to the sync twin).
        releases = await _do_release_search(q)
        for rel in releases:
            if not _artist_matches(rel.get("artists", []), artist):
                continue
            tracks = await _fetch_release_tracks(rel["name"], rel["id"])
            for t in tracks:
                if _release_title_matches(t, title):
                    return t

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

    # X4.a — validate against the artists the UI shows (catalog_artists M2M),
    # not the flat catalog.artist column. Loaded ONCE, synchronously, before the
    # async gather (never gather session.execute on one Session — asyncpg wedges).
    # session is None for legacy callers → fall back to entry.artist everywhere.
    m2m_names = _load_m2m_artist_names(session, entries) if session is not None else {}

    async def _enrich_one(entry):
        nonlocal enriched, not_found, errors, merged
        try:
            # M2M names when present (the displayed truth), else the flat column —
            # correct for inline-crawled rows whose M2M is empty.
            match_artist = m2m_names.get(entry.id) or entry.artist
            bp_track = await _search_beatport_async(
                pool, entry.title, match_artist, entry.isrc, rcache=rcache
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
        except BeatportHTTPError as e:
            # Beatport outage (e.g. 403 Cloudflare), not a "not found": leave
            # beatport_searched_at unset so the entry is retried next drain — an
            # outage must not burn one of the 3 re-scan attempts (twin of the
            # Deezer guard above).
            logger.warning("Beatport HTTP error for catalog %s: %s", entry.id, e)
            errors += 1
        except Exception as e:
            logger.warning("Beatport enrich failed for catalog %s: %s", entry.id, e)
            errors += 1

    # Process concurrently (rate limiter handles concurrency cap at 2)
    await asyncio.gather(*[_enrich_one(e) for e in entries])

    return {"enriched": enriched, "not_found": not_found, "errors": errors, "merged": merged}
