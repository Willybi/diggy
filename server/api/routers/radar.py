from datetime import datetime
from typing import Literal

from database import get_db
from dependencies import get_current_user, require_admin
from fastapi import APIRouter, Depends, HTTPException, Query
from models import RadarTrack, User
from schemas import (
    RadarBatchItem,
    RadarFullList,
    RadarStateUpdate,
)
from services import radar_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("/full", response_model=RadarFullList)
async def list_radar_full(
    status: Literal["new", "seen", "added", "ignored", "liked", "disliked"]
    | None = Query(None),
    playlist_id: int | None = Query(None),
    search: str | None = Query(None, max_length=200),
    detected_after: datetime | None = Query(None),
    sort: Literal[
        "detected_at", "title", "artist", "bpm", "key",
        "genre", "playlist_title", "trend_score",
    ] = Query("detected_at"),
    order: Literal["asc", "desc"] = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await radar_service.list_full(
        db, user.id,
        status=status, playlist_id=playlist_id, search=search,
        detected_after=detected_after, sort=sort, order=order,
        skip=skip, limit=limit,
    )


@router.get("/new-count")
async def radar_new_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await radar_service.new_count(db, user.id)


@router.patch("/{catalog_id}/state")
async def update_radar_state(
    catalog_id: int,
    body: RadarStateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await radar_service.update_state(db, user.id, catalog_id, body.status)


@router.patch("/state/batch")
async def batch_update_radar_state(
    body: list[RadarBatchItem],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update state for multiple catalog_ids at once."""
    items = [{"catalog_id": b.catalog_id, "status": b.status} for b in body]
    return await radar_service.batch_update_state(db, user.id, items)


@router.delete("/{entry_id}", status_code=204)
async def delete_radar_track(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await db.execute(select(RadarTrack).where(RadarTrack.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(entry)
    await db.commit()
