import base64
import os
import tempfile

from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from models import CatalogEntry, User, UserTrack
from schemas import BulkImportResult, TrackExisting, TrackImport, TrackList, TrackOut
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_BULK_IMPORT_SIZE = 5000

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/existing-ids", response_model=list[TrackExisting])
async def get_existing_ids(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne tous les rekordbox_id existants avec leur statut has_artwork."""
    result = await db.execute(
        select(UserTrack.rekordbox_id, UserTrack.has_artwork)
        .where(UserTrack.user_id == user.id)
        .where(UserTrack.rekordbox_id.isnot(None))
    )
    return [
        {"id": row.rekordbox_id, "has_artwork": row.has_artwork} for row in result.all()
    ]


@router.post("/bulk", response_model=BulkImportResult)
async def bulk_import(
    tracks: list[TrackImport] = Body(max_length=MAX_BULK_IMPORT_SIZE),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Upsert une liste de tracks dans user_tracks.
    - Match catalog via normalized_key.
    - Upload l'artwork dans MinIO si image_base64 fourni et has_artwork False.
    """
    from services.image_service import BUCKET_ARTWORKS, ImageService
    from utils import make_normalized_key

    ImageService.ensure_bucket(BUCKET_ARTWORKS)

    uid = user.id

    # Chargement des user_tracks existants (rekordbox_id → (catalog_id, has_artwork))
    existing_result = await db.execute(
        select(UserTrack.rekordbox_id, UserTrack.catalog_id, UserTrack.has_artwork)
        .where(UserTrack.user_id == uid)
        .where(UserTrack.rekordbox_id.isnot(None))
    )
    existing: dict[int, tuple[int, bool]] = {
        row.rekordbox_id: (row.catalog_id, row.has_artwork)
        for row in existing_result.all()
    }

    inserted = 0
    updated = 0
    artworks_uploaded = 0

    for t in tracks:
        rb_id = t.id
        tags = t.tags or []

        if rb_id in existing:
            # --- UPDATE : track déjà connu par rekordbox_id ---
            existing_catalog_id, already_has_artwork = existing[rb_id]
            has_artwork = already_has_artwork

            if t.image_base64 and not already_has_artwork:
                tmp_path = None
                try:
                    img_bytes = base64.b64decode(t.image_base64)
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                        f.write(img_bytes)
                        tmp_path = f.name
                    ImageService.upload_file(tmp_path, BUCKET_ARTWORKS, f"{rb_id}.jpg")
                    has_artwork = True
                    artworks_uploaded += 1
                except Exception as e:
                    import logging

                    logging.getLogger("diggy").error(
                        f"Artwork upload failed for track {rb_id}: {e}"
                    )
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            ut_result = await db.execute(
                select(UserTrack).where(
                    UserTrack.user_id == uid,
                    UserTrack.catalog_id == existing_catalog_id,
                )
            )
            ut = ut_result.scalar_one_or_none()
            if ut:
                ut.date_added = t.date_added
                ut.file_path = t.file_path
                ut.rb_bpm = t.bpm
                ut.rb_key = t.key
                ut.rb_mytags = tags
                ut.rating = t.rating
                ut.has_artwork = has_artwork
                # Mettre à jour le catalog private si titre/artiste changent
                cat_result = await db.execute(
                    select(CatalogEntry).where(CatalogEntry.id == existing_catalog_id)
                )
                cat_entry = cat_result.scalar_one_or_none()
                if cat_entry and cat_entry.scope == "private":
                    new_norm_key = make_normalized_key(t.title or "", t.artist or "")
                    cat_entry.normalized_key = new_norm_key
                    cat_entry.title = t.title or cat_entry.title
                    cat_entry.artist = t.artist or cat_entry.artist
                updated += 1

        else:
            # --- INSERT : nouveau track ---
            norm_key = make_normalized_key(t.title or "", t.artist or "")
            cat_result = await db.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
            )
            cat_entry = cat_result.scalar_one_or_none()

            if cat_entry is None:
                cat_entry = CatalogEntry(
                    title=t.title or "",
                    artist=t.artist,
                    normalized_key=norm_key,
                    scope="private",
                    owner_id=uid,
                    origin="rekordbox",
                )
                db.add(cat_entry)
                await db.flush()

            catalog_id = cat_entry.id
            has_artwork = False

            if t.image_base64:
                tmp_path = None
                try:
                    img_bytes = base64.b64decode(t.image_base64)
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                        f.write(img_bytes)
                        tmp_path = f.name
                    ImageService.upload_file(tmp_path, BUCKET_ARTWORKS, f"{rb_id}.jpg")
                    has_artwork = True
                    artworks_uploaded += 1
                except Exception as e:
                    import logging

                    logging.getLogger("diggy").error(
                        f"Artwork upload failed for track {rb_id}: {e}"
                    )
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            ut = UserTrack(
                user_id=uid,
                catalog_id=catalog_id,
                rekordbox_id=rb_id,
                date_added=t.date_added,
                source="rekordbox_import",
                file_path=t.file_path,
                rb_bpm=t.bpm,
                rb_key=t.key,
                rb_mytags=tags,
                rating=t.rating,
                has_artwork=has_artwork,
            )
            db.add(ut)
            inserted += 1

    await db.commit()
    return BulkImportResult(
        inserted=inserted, updated=updated, artworks_uploaded=artworks_uploaded
    )


@router.get("/tags", response_model=list[str])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne tous les tags uniques extraits de user_tracks."""
    uid = user.id
    result = await db.execute(
        text(
            "SELECT DISTINCT jsonb_array_elements_text(rb_mytags::jsonb) AS tag "
            "FROM user_tracks "
            "WHERE user_id = :uid AND rb_mytags IS NOT NULL "
            "ORDER BY tag"
        ).bindparams(uid=uid)
    )
    return [row[0] for row in result.all()]


@router.get("/", response_model=TrackList)
async def list_tracks(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    artist: str | None = None,
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = user.id

    query = (
        select(
            UserTrack.rekordbox_id,
            UserTrack.catalog_id,
            UserTrack.rb_bpm,
            UserTrack.rb_key,
            UserTrack.rb_mytags,
            UserTrack.rating,
            UserTrack.file_path,
            UserTrack.date_added,
            UserTrack.has_artwork,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.duration_ms,
            CatalogEntry.has_preview,
        )
        .join(CatalogEntry, UserTrack.catalog_id == CatalogEntry.id)
        .where(UserTrack.user_id == uid)
    )

    if artist:
        query = query.where(CatalogEntry.artist.ilike(f"%{artist}%"))

    if tag:
        query = query.where(text("rb_mytags::jsonb ? :tag").bindparams(tag=tag))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(UserTrack.date_added.desc()).offset(skip).limit(limit)
    )
    rows = result.all()

    items = []
    for row in rows:
        (
            rb_id,
            cat_id,
            rb_bpm,
            rb_key,
            rb_mytags,
            rating,
            file_path,
            date_added,
            has_artwork,
            title,
            artist_name,
            duration_ms,
            has_preview,
        ) = row

        out = TrackOut(
            id=rb_id or cat_id,
            title=title,
            artist=artist_name,
            bpm=rb_bpm,
            key=rb_key,
            duration=duration_ms,
            rating=rating,
            file_path=file_path,
            date_added=date_added,
            tags=rb_mytags or [],
            has_artwork=has_artwork or False,
            catalog_id=cat_id,
            has_preview=has_preview or False,
        )
        items.append(out)

    return TrackList(total=total, items=items)


@router.get("/{track_id}", response_model=TrackOut)
async def get_track(
    track_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Récupère un track par rekordbox_id."""
    uid = user.id
    result = await db.execute(
        select(
            UserTrack.rekordbox_id,
            UserTrack.catalog_id,
            UserTrack.rb_bpm,
            UserTrack.rb_key,
            UserTrack.rb_mytags,
            UserTrack.rating,
            UserTrack.file_path,
            UserTrack.date_added,
            UserTrack.has_artwork,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.duration_ms,
            CatalogEntry.has_preview,
        )
        .join(CatalogEntry, UserTrack.catalog_id == CatalogEntry.id)
        .where(UserTrack.user_id == uid)
        .where(UserTrack.rekordbox_id == track_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Track not found")

    (
        rb_id,
        cat_id,
        rb_bpm,
        rb_key,
        rb_mytags,
        rating,
        file_path,
        date_added,
        has_artwork,
        title,
        artist_name,
        duration_ms,
        has_preview,
    ) = row
    return TrackOut(
        id=rb_id or cat_id,
        title=title,
        artist=artist_name,
        bpm=rb_bpm,
        key=rb_key,
        duration=duration_ms,
        rating=rating,
        file_path=file_path,
        date_added=date_added,
        tags=rb_mytags or [],
        has_artwork=has_artwork or False,
        catalog_id=cat_id,
        has_preview=has_preview or False,
    )
