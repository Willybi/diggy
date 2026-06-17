from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog import get_or_create_catalog
from database import get_db
from models import RadarTrack, WatchedEntity, UserTrack
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
