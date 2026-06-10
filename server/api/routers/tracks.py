from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import LibTrack, CatalogEntry
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
            except Exception as e:
                import logging
                logging.getLogger("diggy").error(f"Artwork upload failed for track {t.id}: {e}")
                track.has_artwork = False
        else:
            track.has_artwork = already_has_artwork or False

        # Tente de lier au catalog si pas encore fait
        if not track.catalog_id:
            from utils import make_normalized_key
            norm_key = make_normalized_key(t.title or "", t.artist or "")
            cat_result = await db.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
            )
            cat_entry = cat_result.scalar_one_or_none()
            if cat_entry:
                track.catalog_id = cat_entry.id

        if is_new:
            inserted += 1
        else:
            updated += 1

    await db.commit()
    return BulkImportResult(inserted=inserted, updated=updated, artworks_uploaded=artworks_uploaded)


@router.get("/tags", response_model=list[str])
async def list_tags(db: AsyncSession = Depends(get_db)):
    """Retourne tous les tags uniques extraits de lib_tracks."""
    result = await db.execute(select(LibTrack.tags).where(LibTrack.tags != None))
    tags_set = set()
    for (tags_json,) in result.all():
        try:
            for tag in json.loads(tags_json):
                if tag:
                    tags_set.add(tag)
        except (json.JSONDecodeError, TypeError):
            pass
    return sorted(tags_set)


@router.get("/", response_model=TrackList)
async def list_tracks(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    artist: str | None = None,
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(LibTrack, CatalogEntry.has_preview)
        .outerjoin(CatalogEntry, LibTrack.catalog_id == CatalogEntry.id)
    )
    if artist:
        query = query.where(LibTrack.artist.ilike(f"%{artist}%"))
    if tag:
        query = query.where(LibTrack.tags.contains(tag))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    items = []
    for row in rows:
        track, has_preview = row[0], row[1]
        out = TrackOut.model_validate(track)
        out.catalog_id = track.catalog_id
        out.has_preview = has_preview or False
        items.append(out)

    return TrackList(total=total, items=items)


@router.get("/{track_id}", response_model=TrackOut)
async def get_track(track_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LibTrack).where(LibTrack.id == track_id))
    track = result.scalar_one_or_none()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track
