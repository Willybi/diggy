from __future__ import annotations

from database import get_db
from dependencies import get_current_user_optional
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, Query
from models import (
    Artist,
    CatalogArtist,
    CatalogEntry,
    DJSet,
    SetTrack,
    User,
    UserTrack,
    WatchedEntity,
)
from schemas import SearchItem, SearchResponse, SearchTotals
from services.genre_service import _ensure_pillar_cache, genre_pillar
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["search"])

GUEST_CAP = 6


# ── Relevance scoring ────────────────────────────────────────────


def _relevance(value: str, q: str) -> int:
    v = value.lower()
    if v == q:
        return 3
    if v.startswith(q):
        return 2
    return 1


# ── Per-type search helpers ──────────────────────────────────────


async def _search_tracks(
    db: AsyncSession,
    q: str,
    user_id: int | None,
    is_guest: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    ut_sub = select(UserTrack.catalog_id).where(UserTrack.user_id == user_id).subquery()

    base = (
        select(
            CatalogEntry.id,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.duration_ms,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            ut_sub.c.catalog_id.label("ut_cid"),
        )
        .outerjoin(ut_sub, CatalogEntry.id == ut_sub.c.catalog_id)
        .where(CatalogEntry.title.ilike(pattern) | CatalogEntry.artist.ilike(pattern))
        .order_by(CatalogEntry.title, CatalogEntry.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="track",
                id=r.id,
                title=r.title,
                artist=r.artist,
                bpm=r.bpm,
                key=r.key,
                duration_ms=r.duration_ms,
                has_artwork=r.has_artwork,
                has_preview=r.has_preview,
                in_lib=False if is_guest else (r.ut_cid is not None),
            )
        )
    return items, total


async def _search_artists(
    db: AsyncSession,
    q: str,
    user_id: int | None,
    is_guest: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    base = (
        select(Artist.id, Artist.name, Artist.has_artwork)
        .where(Artist.name.ilike(pattern))
        .order_by(Artist.name, Artist.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()
    if not rows:
        return [], total

    artist_ids = [r.id for r in rows]

    # batch track counts via catalog_artists
    tc_q = (
        select(
            CatalogArtist.artist_id,
            func.count().label("cnt"),
        )
        .where(CatalogArtist.artist_id.in_(artist_ids))
        .group_by(CatalogArtist.artist_id)
    )
    tc_rows = (await db.execute(tc_q)).all()
    tc_map = {r.artist_id: r.cnt for r in tc_rows}

    # batch in_lib counts via catalog_artists
    lib_map: dict[int, int] = {}
    if not is_guest:
        lib_q = (
            select(
                CatalogArtist.artist_id,
                func.count().label("cnt"),
            )
            .join(
                UserTrack,
                (UserTrack.catalog_id == CatalogArtist.catalog_id)
                & (UserTrack.user_id == user_id),
            )
            .where(CatalogArtist.artist_id.in_(artist_ids))
            .group_by(CatalogArtist.artist_id)
        )
        lib_rows = (await db.execute(lib_q)).all()
        lib_map = {r.artist_id: r.cnt for r in lib_rows}

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="artist",
                id=r.id,
                name=r.name,
                has_artwork=r.has_artwork,
                track_count=tc_map.get(r.id, 0),
                in_lib_count=0 if is_guest else lib_map.get(r.id, 0),
            )
        )
    return items, total


async def _search_sets(
    db: AsyncSession,
    q: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    base = (
        select(
            DJSet.id,
            DJSet.title,
            DJSet.played_date,
            DJSet.has_artwork,
            func.count(SetTrack.id).label("track_count"),
        )
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        .where(DJSet.title.ilike(pattern), DJSet.parent_set_id.is_(None))
        .group_by(DJSet.id)
        .order_by(DJSet.played_date.desc().nulls_last(), DJSet.id)
    )

    # count total matching sets
    count_q = select(func.count()).select_from(
        select(DJSet.id)
        .where(DJSet.title.ilike(pattern), DJSet.parent_set_id.is_(None))
        .subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="set",
                id=r.id,
                title=r.title,
                played_date=r.played_date.isoformat() if r.played_date else None,
                track_count=r.track_count,
                has_artwork=r.has_artwork,
            )
        )
    return items, total


async def _search_playlists(
    db: AsyncSession,
    q: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    base = (
        select(
            WatchedEntity.id,
            WatchedEntity.title,
            WatchedEntity.source,
            WatchedEntity.track_count,
            WatchedEntity.has_artwork,
        )
        .where(WatchedEntity.title.ilike(pattern))
        .order_by(WatchedEntity.title, WatchedEntity.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="playlist",
                id=r.id,
                title=r.title,
                source=r.source,
                track_count=r.track_count,
                has_artwork=r.has_artwork,
            )
        )
    return items, total


async def _search_genres(
    db: AsyncSession,
    q: str,
    user_id: int | None,
    is_guest: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    result = await db.execute(
        text("""
        SELECT
            g AS name,
            COUNT(*)::int AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi
        FROM catalog c, unnest(c.genres) AS g
        WHERE LOWER(g) LIKE LOWER(:pattern)
        GROUP BY g
        ORDER BY COUNT(*) DESC, g
        LIMIT :lim OFFSET :off
    """),
        {"pattern": pattern, "lim": limit, "off": offset},
    )
    rows = result.all()

    # total distinct genres matching
    total_r = await db.execute(
        text("""
        SELECT COUNT(DISTINCT g)::int
        FROM catalog c, unnest(c.genres) AS g
        WHERE LOWER(g) LIKE LOWER(:pattern)
    """),
        {"pattern": pattern},
    )
    total = total_r.scalar() or 0

    items: list[SearchItem] = []
    for r in rows:
        p, d = genre_pillar(r.name)
        items.append(
            SearchItem(
                type="genre",
                name=r.name,
                pillar=p,
                depth=d,
                track_count=r.track_count,
                artist_count=r.artist_count,
                bpm_lo=r.bpm_lo,
                bpm_hi=r.bpm_hi,
            )
        )
    return items, total


# ── Main endpoint ─────────────────────────────────────────────────


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", min_length=0, max_length=200),
    scope: str = Query("all", max_length=50),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    user_id = _uid(user)
    is_guest = user is None
    await _ensure_pillar_cache(db)
    q_lower = q.strip().lower()

    if not q_lower:
        return SearchResponse(items=[], total=0, totals=SearchTotals())

    # For a single scope, offset+limit are pushed straight into the DB query
    # (true pagination). For scope="all", results from every type are merged and
    # re-ranked in Python, which forbids a meaningful global DB offset — so offset
    # is ignored there (see pagination block below) and only limit is applied.
    per_type_limit = limit if scope != "all" else 30
    per_type_offset = offset if scope != "all" else 0

    all_items: list[SearchItem] = []
    totals = SearchTotals()

    if scope in ("all", "track"):
        items, t = await _search_tracks(
            db, q_lower, user_id, is_guest, per_type_limit, per_type_offset
        )
        all_items.extend(items)
        totals.track = t

    if scope in ("all", "artist"):
        items, t = await _search_artists(
            db, q_lower, user_id, is_guest, per_type_limit, per_type_offset
        )
        all_items.extend(items)
        totals.artist = t

    if scope in ("all", "set"):
        items, t = await _search_sets(db, q_lower, per_type_limit, per_type_offset)
        all_items.extend(items)
        totals.set = t

    if scope in ("all", "playlist"):
        items, t = await _search_playlists(db, q_lower, per_type_limit, per_type_offset)
        all_items.extend(items)
        totals.playlist = t

    if scope in ("all", "genre"):
        items, t = await _search_genres(
            db, q_lower, user_id, is_guest, per_type_limit, per_type_offset
        )
        all_items.extend(items)
        totals.genre = t

    # Sort by relevance: exact > prefix > substring, tie-break by popularity
    def sort_key(item: SearchItem) -> tuple[int, int]:
        label = (item.name or item.title or "").lower()
        rel = _relevance(label, q_lower)
        pop = item.track_count or 0
        return (-rel, -pop)

    all_items.sort(key=sort_key)

    total = totals.track + totals.artist + totals.set + totals.playlist + totals.genre

    # Guest cap
    if is_guest:
        capped = all_items[:GUEST_CAP]
        return SearchResponse(items=capped, total=total, totals=totals)

    # Paginate. For a single scope the DB already applied offset+limit, so return
    # the merged window as-is. For scope="all" offset is ignored (merge-in-Python
    # can't honor a global offset); only the limit bounds the merged result.
    page = all_items if scope != "all" else all_items[:limit]
    return SearchResponse(items=page, total=total, totals=totals)
