from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import RadarTrack, WatchedPlaylist
from schemas import RadarTrackIn, RadarTrackOut

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("/", response_model=list[RadarTrackOut])
async def list_radar_tracks(
    watched_playlist_id: int | None = Query(None),
    source: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(RadarTrack)
    if watched_playlist_id is not None:
        query = query.where(RadarTrack.watched_playlist_id == watched_playlist_id)
    if source is not None:
        query = query.where(RadarTrack.source == source)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=RadarTrackOut, status_code=201)
async def add_radar_track(body: RadarTrackIn, db: AsyncSession = Depends(get_db)):
    playlist = await db.execute(
        select(WatchedPlaylist).where(WatchedPlaylist.id == body.watched_playlist_id)
    )
    if not playlist.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="watched_playlist not found")

    entry = RadarTrack(
        watched_playlist_id=body.watched_playlist_id,
        external_track_id=body.external_track_id,
        source=body.source,
        title=body.title,
        artist=body.artist,
        isrc=body.isrc,
        detected_at=datetime.utcnow(),
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
