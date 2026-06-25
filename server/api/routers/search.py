from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text, case, literal
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user_optional, uid as _uid
from models import (
    Artist,
    CatalogEntry,
    DJSet,
    SetTrack,
    UserTrack,
    WatchedEntity,
    User,
)
from routers.genres import genre_family

router = APIRouter(tags=["search"])

GUEST_CAP = 6


# ── Response schemas ──────────────────────────────────────────────

class SearchItem(BaseModel):
    type: str
    # track
    id: int | None = None
    title: str | None = None
    artist: str | None = None
    bpm: float | None = None
    key: str | None = None
    duration_ms: int | None = None
    has_artwork: bool = False
    has_preview: bool = False
    in_lib: bool = False
    # artist
    name: str | None = None
    track_count: int | None = None
    in_lib_count: int = 0
    # set
    played_date: str | None = None
    # playlist
    source: str | None = None
    # genre
    family: str | None = None
    artist_count: int | None = None
    bpm_lo: int | None = None
    bpm_hi: int | None = None


class SearchTotals(BaseModel):
    track: int = 0
    artist: int = 0
    set: int = 0
    playlist: int = 0
    genre: int = 0


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    totals: SearchTotals


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
    db: AsyncSession, q: str, user_id: int, is_guest: bool, limit: int,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    ut_sub = (
        select(UserTrack.catalog_id)
        .where(UserTrack.user_id == user_id)
        .subquery()
    )

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
        .where(
            CatalogEntry.title.ilike(pattern)
            | CatalogEntry.artist.ilike(pattern)
        )
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(SearchItem(
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
        ))
    return items, total


async def _search_artists(
    db: AsyncSession, q: str, user_id: int, is_guest: bool, limit: int,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    base = (
        select(Artist.id, Artist.name, Artist.has_artwork)
        .where(Artist.name.ilike(pattern))
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.limit(limit))).all()
    if not rows:
        return [], total

    artist_ids = [r.id for r in rows]
    artist_names = [r.name.lower() for r in rows]

    # batch track counts
    tc_q = (
        select(
            func.lower(CatalogEntry.artist).label("aname"),
            func.count().label("cnt"),
        )
        .where(func.lower(CatalogEntry.artist).in_(artist_names))
        .group_by(func.lower(CatalogEntry.artist))
    )
    tc_rows = (await db.execute(tc_q)).all()
    tc_map = {r.aname: r.cnt for r in tc_rows}

    # batch in_lib counts
    lib_map: dict[str, int] = {}
    if not is_guest:
        lib_q = (
            select(
                func.lower(CatalogEntry.artist).label("aname"),
                func.count().label("cnt"),
            )
            .join(UserTrack, (UserTrack.catalog_id == CatalogEntry.id) & (UserTrack.user_id == user_id))
            .where(func.lower(CatalogEntry.artist).in_(artist_names))
            .group_by(func.lower(CatalogEntry.artist))
        )
        lib_rows = (await db.execute(lib_q)).all()
        lib_map = {r.aname: r.cnt for r in lib_rows}

    items: list[SearchItem] = []
    for r in rows:
        aname = r.name.lower()
        items.append(SearchItem(
            type="artist",
            id=r.id,
            name=r.name,
            has_artwork=r.has_artwork,
            track_count=tc_map.get(aname, 0),
            in_lib_count=0 if is_guest else lib_map.get(aname, 0),
        ))
    return items, total


async def _search_sets(
    db: AsyncSession, q: str, limit: int,
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
        .where(DJSet.title.ilike(pattern))
        .group_by(DJSet.id)
    )

    # count total matching sets
    count_q = select(func.count()).select_from(
        select(DJSet.id).where(DJSet.title.ilike(pattern)).subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    rows = (await db.execute(base.limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(SearchItem(
            type="set",
            id=r.id,
            title=r.title,
            played_date=r.played_date.isoformat() if r.played_date else None,
            track_count=r.track_count,
            has_artwork=r.has_artwork,
        ))
    return items, total


async def _search_playlists(
    db: AsyncSession, q: str, limit: int,
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
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(SearchItem(
            type="playlist",
            id=r.id,
            title=r.title,
            source=r.source,
            track_count=r.track_count,
            has_artwork=r.has_artwork,
        ))
    return items, total


async def _search_genres(
    db: AsyncSession, q: str, user_id: int, is_guest: bool, limit: int,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{q}%"

    result = await db.execute(text("""
        SELECT
            c.genre AS name,
            COUNT(*)::int AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi
        FROM catalog c
        WHERE c.genre IS NOT NULL AND c.genre != ''
          AND LOWER(c.genre) LIKE LOWER(:pattern)
        GROUP BY c.genre
        ORDER BY COUNT(*) DESC
        LIMIT :lim
    """), {"pattern": pattern, "lim": limit})
    rows = result.all()

    # total distinct genres matching
    total_r = await db.execute(text("""
        SELECT COUNT(DISTINCT c.genre)::int
        FROM catalog c
        WHERE c.genre IS NOT NULL AND c.genre != ''
          AND LOWER(c.genre) LIKE LOWER(:pattern)
    """), {"pattern": pattern})
    total = total_r.scalar() or 0

    items: list[SearchItem] = []
    for r in rows:
        items.append(SearchItem(
            type="genre",
            name=r.name,
            family=genre_family(r.name),
            track_count=r.track_count,
            artist_count=r.artist_count,
            bpm_lo=r.bpm_lo,
            bpm_hi=r.bpm_hi,
        ))
    return items, total


# ── Main endpoint ─────────────────────────────────────────────────

@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", min_length=0),
    scope: str = Query("all"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    user_id = _uid(user)
    is_guest = user is None
    q_lower = q.strip().lower()

    if not q_lower:
        return SearchResponse(items=[], total=0, totals=SearchTotals())

    per_type_limit = limit if scope != "all" else 30

    all_items: list[SearchItem] = []
    totals = SearchTotals()

    if scope in ("all", "track"):
        items, t = await _search_tracks(db, q_lower, user_id, is_guest, per_type_limit)
        all_items.extend(items)
        totals.track = t

    if scope in ("all", "artist"):
        items, t = await _search_artists(db, q_lower, user_id, is_guest, per_type_limit)
        all_items.extend(items)
        totals.artist = t

    if scope in ("all", "set"):
        items, t = await _search_sets(db, q_lower, per_type_limit)
        all_items.extend(items)
        totals.set = t

    if scope in ("all", "playlist"):
        items, t = await _search_playlists(db, q_lower, per_type_limit)
        all_items.extend(items)
        totals.playlist = t

    if scope in ("all", "genre"):
        items, t = await _search_genres(db, q_lower, user_id, is_guest, per_type_limit)
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

    # Paginate
    page = all_items[offset:offset + limit]
    return SearchResponse(items=page, total=total, totals=totals)
