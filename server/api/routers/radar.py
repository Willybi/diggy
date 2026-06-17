from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, case, literal, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from catalog import get_or_create_catalog
from database import get_db
from dependencies import get_current_user_optional
from models import RadarTrack, WatchedEntity, UserTrack, UserRadarState, CatalogEntry, User
from schemas import (
    RadarTrackIn,
    RadarTrackOut,
    RadarFullOut,
    RadarFullList,
    RadarStateUpdate,
)

router = APIRouter(prefix="/radar", tags=["radar"])

_DEFAULT_USER_ID = 1
_VALID_STATUSES = {"new", "seen", "added", "ignored"}


def _uid(user: User | None) -> int:
    return user.id if user else _DEFAULT_USER_ID


# ---------- Enriched listing for RadarView ----------


@router.get("/full", response_model=RadarFullList)
async def list_radar_full(
    status: str | None = Query(None),
    playlist_id: int | None = Query(None),
    search: str | None = Query(None),
    sort: str = Query("detected_at"),
    order: str = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)

    urs = aliased(UserRadarState)
    ut = aliased(UserTrack)

    # Subquery: is track in user's lib?
    in_lib_sq = (
        select(literal(True))
        .where(ut.user_id == uid, ut.catalog_id == CatalogEntry.id)
        .correlate(CatalogEntry)
        .exists()
    )

    # Base query: radar_tracks joined with catalog + state + playlist
    base = (
        select(
            CatalogEntry.id.label("catalog_id"),
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.duration_ms,
            CatalogEntry.genre,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            func.max(RadarTrack.detected_at).label("detected_at"),
            func.min(RadarTrack.watched_entity_id).label("playlist_id"),
            func.min(WatchedEntity.title).label("playlist_title"),
            func.coalesce(func.min(urs.status), literal("new")).label("status"),
            in_lib_sq.label("in_lib"),
        )
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(WatchedEntity, RadarTrack.watched_entity_id == WatchedEntity.id)
        .outerjoin(urs, and_(urs.user_id == uid, urs.catalog_id == CatalogEntry.id))
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(CatalogEntry.id, urs.status)
    )

    # Filters
    if status:
        if status == "new":
            base = base.having(func.coalesce(func.min(urs.status), literal("new")) == "new")
        else:
            base = base.having(func.min(urs.status) == status)
    if playlist_id:
        base = base.where(RadarTrack.watched_entity_id == playlist_id)
    if search:
        term = f"%{search}%"
        base = base.where(
            CatalogEntry.title.ilike(term) | CatalogEntry.artist.ilike(term)
        )

    # Count total (before pagination)
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Status counts for tabs
    counts_base = (
        select(
            func.coalesce(urs.status, literal("new")).label("st"),
            func.count(func.distinct(CatalogEntry.id)).label("cnt"),
        )
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(urs, and_(urs.user_id == uid, urs.catalog_id == CatalogEntry.id))
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by("st")
    )
    counts_result = await db.execute(counts_base)
    counts = {row.st: row.cnt for row in counts_result}

    # Sort
    sort_map = {
        "detected_at": func.max(RadarTrack.detected_at),
        "title": CatalogEntry.title,
        "artist": CatalogEntry.artist,
        "bpm": CatalogEntry.bpm,
    }
    sort_col = sort_map.get(sort, func.max(RadarTrack.detected_at))
    if order == "asc":
        base = base.order_by(sort_col.asc())
    else:
        base = base.order_by(sort_col.desc())

    base = base.offset(skip).limit(limit)
    result = await db.execute(base)
    items = [RadarFullOut.model_validate(row._mapping) for row in result]

    return RadarFullList(total=total, items=items, counts=counts)


# ---------- Count new (for sidebar badge) ----------


@router.get("/new-count")
async def radar_new_count(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)
    urs = aliased(UserRadarState)

    q = (
        select(func.count(func.distinct(RadarTrack.catalog_id)))
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(urs, and_(urs.user_id == uid, urs.catalog_id == RadarTrack.catalog_id))
        .where(
            RadarTrack.catalog_id.isnot(None),
            func.coalesce(urs.status, literal("new")) == "new",
        )
    )
    count = (await db.execute(q)).scalar() or 0
    return {"count": count}


# ---------- Update state ----------


@router.patch("/{catalog_id}/state")
async def update_radar_state(
    catalog_id: int,
    body: RadarStateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {_VALID_STATUSES}")

    uid = _uid(user)

    result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == uid,
            UserRadarState.catalog_id == catalog_id,
        )
    )
    state = result.scalar_one_or_none()

    if state:
        state.status = body.status
        state.updated_at = datetime.now(timezone.utc)
    else:
        state = UserRadarState(
            user_id=uid,
            catalog_id=catalog_id,
            status=body.status,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(state)

    await db.commit()
    return {"catalog_id": catalog_id, "status": body.status}


# ---------- Batch update state ----------


@router.patch("/state/batch")
async def batch_update_radar_state(
    body: list[RadarStateUpdate | dict],
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Update state for multiple catalog_ids at once.
    Body: [{"catalog_id": 123, "status": "seen"}, ...]
    """
    uid = _uid(user)
    updated = 0

    for item in body:
        cid = item.get("catalog_id") if isinstance(item, dict) else None
        st = item.get("status") if isinstance(item, dict) else item.status
        if not cid or st not in _VALID_STATUSES:
            continue

        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == uid,
                UserRadarState.catalog_id == cid,
            )
        )
        state = result.scalar_one_or_none()
        if state:
            state.status = st
            state.updated_at = datetime.now(timezone.utc)
        else:
            db.add(UserRadarState(
                user_id=uid, catalog_id=cid, status=st,
                updated_at=datetime.now(timezone.utc),
            ))
        updated += 1

    await db.commit()
    return {"updated": updated}


# ---------- Legacy endpoints (kept for crawl_radar task compat) ----------


@router.get("/", response_model=list[RadarTrackOut])
async def list_radar_tracks(
    watched_playlist_id: int | None = Query(None),
    source: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(RadarTrack)
    if watched_playlist_id is not None:
        query = query.where(RadarTrack.watched_entity_id == watched_playlist_id)
    if source is not None:
        query = query.where(RadarTrack.source == source)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=RadarTrackOut, status_code=201)
async def add_radar_track(body: RadarTrackIn, response: Response, db: AsyncSession = Depends(get_db)):
    entity = await db.execute(
        select(WatchedEntity).where(WatchedEntity.id == body.watched_playlist_id)
    )
    if not entity.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="watched_entity not found")

    existing = await db.execute(
        select(RadarTrack).where(
            RadarTrack.watched_entity_id == body.watched_playlist_id,
            RadarTrack.external_track_id == body.external_track_id,
        )
    )
    existing_entry = existing.scalar_one_or_none()
    if existing_entry:
        response.status_code = 200
        return existing_entry

    catalog_entry = await get_or_create_catalog(
        db,
        title=body.title,
        artist=body.artist,
        isrc=body.isrc,
    )

    entry = RadarTrack(
        watched_entity_id=body.watched_playlist_id,
        external_track_id=body.external_track_id,
        source=body.source,
        title=body.title,
        artist=body.artist,
        isrc=body.isrc,
        detected_at=datetime.now(timezone.utc),
        catalog_id=catalog_entry.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_radar_track(entry_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RadarTrack).where(RadarTrack.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(entry)
    await db.commit()
