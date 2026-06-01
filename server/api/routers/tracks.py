from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import LibTrack
from schemas import TrackOut, TrackList

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/", response_model=TrackList)
async def list_tracks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    artist: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(LibTrack)
    if artist:
        query = query.where(LibTrack.artist.ilike(f"%{artist}%"))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    tracks = result.scalars().all()

    return TrackList(total=total, items=tracks)


@router.get("/{track_id}", response_model=TrackOut)
async def get_track(track_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LibTrack).where(LibTrack.id == track_id))
    track = result.scalar_one_or_none()
    if not track:
        raise HTTPException(status_code=404, detail="LibTrack not found")
    return track
