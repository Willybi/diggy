from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import LibTrack
from schemas import TrackOut, TrackList, TrackExisting, TrackImport, BulkImportResult
import json
import base64
import tempfile
import os

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/existing-ids", response_model=list[TrackExisting])
async def get_existing_ids(db: AsyncSession = Depends(get_db)):
    """Retourne tous les ids existants avec leur statut has_artwork."""
    result = await db.execute(select(LibTrack.id, LibTrack.has_artwork))
    return [{"id": row.id, "has_artwork": row.has_artwork} for row in result.all()]


@router.post("/bulk", response_model=BulkImportResult)
async def bulk_import(tracks: list[TrackImport], db: AsyncSession = Depends(get_db)):
    """
    Upsert une liste de tracks.
    - Insère les nouveaux, met à jour les existants.
    - Upload l'image dans MinIO si image_base64 est fourni et has_artwork est False.
    """
    from storage import upload_artwork, ensure_bucket
    ensure_bucket()

    existing_result = await db.execute(select(LibTrack.id, LibTrack.has_artwork))
    existing = {row.id: row.has_artwork for row in existing_result.all()}

    inserted = 0
    updated = 0
    artworks_uploaded = 0

    for t in tracks:
        is_new = t.id not in existing
        track = None

        if not is_new:
            result = await db.execute(select(LibTrack).where(LibTrack.id == t.id))
            track = result.scalar_one()

        if is_new:
            track = LibTrack(id=t.id)
            db.add(track)

        track.title = t.title
        track.artist = t.artist
        track.bpm = t.bpm
        track.key = t.key
        track.duration = t.duration
        track.rating = t.rating
        track.file_path = t.file_path
        track.date_added = t.date_added
        track.tags = json.dumps(t.tags)

        # Upload artwork si fourni et pas déjà en base
        already_has_artwork = existing.get(t.id, False)
        if t.image_base64 and not already_has_artwork:
            try:
                img_bytes = base64.b64decode(t.image_base64)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    f.write(img_bytes)
                    tmp_path = f.name
                upload_artwork(tmp_path, f"{t.id}.jpg")
                os.unlink(tmp_path)
                track.has_artwork = True
                artworks_uploaded += 1
            except Exception:
                track.has_artwork = False
        else:
            track.has_artwork = already_has_artwork or False

        if is_new:
            inserted += 1
        else:
            updated += 1

    await db.commit()
    return BulkImportResult(inserted=inserted, updated=updated, artworks_uploaded=artworks_uploaded)


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
        raise HTTPException(status_code=404, detail="Track not found")
    return track
