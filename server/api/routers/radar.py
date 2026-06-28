from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, case, literal, and_, desc as sa_desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from catalog import get_or_create_catalog
from database import get_db
from dependencies import get_current_user_optional, uid as _uid
from models import RadarTrack, WatchedEntity, UserTrack, UserRadarState, CatalogEntry, User
from opinion_sync import sync_track_opinion, RADAR_TO_OPINION
from schemas import (
    RadarTrackIn,
    RadarTrackOut,
    RadarFullOut,
    RadarFullList,
    RadarStateUpdate,
)

router = APIRouter(prefix="/radar", tags=["radar"])

_VALID_STATUSES = {"new", "seen", "added", "ignored", "liked", "disliked"}
_STATUS_ALIAS = {"liked": "added", "disliked": "ignored"}


# ---------- Enriched listing for RadarView ----------


@router.get("/full", response_model=RadarFullList)
async def list_radar_full(
    status: str | None = Query(None),
    playlist_id: int | None = Query(None),
    search: str | None = Query(None),
    detected_after: datetime | None = Query(None),
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

    # Subquery: most recent playlist for each catalog entry
    _lr = RadarTrack.__table__.alias("lr")
    _lw = WatchedEntity.__table__.alias("lw")
    latest_playlist_title = (
        select(_lw.c.title)
        .select_from(
            _lr.join(_lw, _lr.c.watched_entity_id == _lw.c.id)
        )
        .where(_lr.c.catalog_id == CatalogEntry.id)
        .order_by(sa_desc(_lr.c.detected_at))
        .limit(1)
        .correlate(CatalogEntry)
        .scalar_subquery()
    )
    latest_playlist_id = (
        select(_lr.c.watched_entity_id)
        .select_from(_lr)
        .where(_lr.c.catalog_id == CatalogEntry.id)
        .order_by(sa_desc(_lr.c.detected_at))
        .limit(1)
        .correlate(CatalogEntry)
        .scalar_subquery()
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
            CatalogEntry.genres,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            func.max(RadarTrack.detected_at).label("detected_at"),
            latest_playlist_id.label("playlist_id"),
            latest_playlist_title.label("playlist_title"),
            func.coalesce(func.min(urs.status), literal("new")).label("status"),
            in_lib_sq.label("in_lib"),
        )
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(urs, and_(urs.user_id == uid, urs.catalog_id == CatalogEntry.id))
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(CatalogEntry.id, urs.status)
    )

    # Filters
    resolved_status = _STATUS_ALIAS.get(status, status) if status else None
    if resolved_status:
        if resolved_status == "new":
            base = base.having(func.coalesce(func.min(urs.status), literal("new")) == "new")
        else:
            base = base.having(func.min(urs.status) == resolved_status)
    if detected_after:
        base = base.where(RadarTrack.detected_at >= detected_after)
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
        "key": CatalogEntry.key,
        "genre": CatalogEntry.genres[1],
        "playlist_title": latest_playlist_title,
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

    resolved = _STATUS_ALIAS.get(body.status, body.status)
    uid = _uid(user)

    result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == uid,
            UserRadarState.catalog_id == catalog_id,
        )
    )
    state = result.scalar_one_or_none()

    if state:
        state.status = resolved
        state.updated_at = datetime.now(timezone.utc)
    else:
        state = UserRadarState(
            user_id=uid,
            catalog_id=catalog_id,
            status=resolved,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(state)

    # Sync → user_opinions + user_tracks.avis
    opinion_val = RADAR_TO_OPINION.get(resolved)
    await sync_track_opinion(db, uid, catalog_id, opinion_val)

    await db.commit()
    return {"catalog_id": catalog_id, "status": body.status}


# ---------- Batch update state ----------


@router.patch("/state/batch")
async def batch_update_radar_state(
    body: list[dict],
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Update state for multiple catalog_ids at once.
    Body: [{"catalog_id": 123, "status": "seen"}, ...]
    """
    uid = _uid(user)
    now = datetime.now(timezone.utc)

    # Validate & resolve statuses upfront
    valid_items = []
    for item in body:
        cid = item.get("catalog_id")
        st = item.get("status")
        if not cid or st not in _VALID_STATUSES:
            continue
        valid_items.append((cid, _STATUS_ALIAS.get(st, st)))

    if not valid_items:
        return {"updated": 0}

    catalog_ids = [cid for cid, _ in valid_items]

    # Single SELECT for all existing states
    existing_result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == uid,
            UserRadarState.catalog_id.in_(catalog_ids),
        )
    )
    existing_map = {s.catalog_id: s for s in existing_result.scalars()}

    # Update or insert without individual queries
    for cid, resolved in valid_items:
        if cid in existing_map:
            existing_map[cid].status = resolved
            existing_map[cid].updated_at = now
        else:
            db.add(UserRadarState(
                user_id=uid, catalog_id=cid, status=resolved,
                updated_at=now,
            ))

        # Sync → user_opinions + user_tracks.avis
        opinion_val = RADAR_TO_OPINION.get(resolved)
        await sync_track_opinion(db, uid, cid, opinion_val)

    await db.commit()
    return {"updated": len(valid_items)}


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
