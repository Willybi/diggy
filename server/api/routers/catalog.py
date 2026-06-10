from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from database import get_db
from models import CatalogEntry, LibTrack, RadarTrack
from schemas import CatalogEntryOut, CatalogList

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/", response_model=CatalogList)
async def list_catalog(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    in_lib: bool | None = Query(None),
    min_radar_playlists: int | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Sous-requête : nb de playlists distinctes dans radar_tracks par catalog_id
    radar_count = (
        select(
            RadarTrack.catalog_id,
            func.count(func.distinct(RadarTrack.watched_playlist_id)).label("nb_playlists"),
        )
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(RadarTrack.catalog_id)
        .subquery()
    )

    # Sous-requête : lib_tracks liés
    lib_count = (
        select(LibTrack.catalog_id)
        .where(LibTrack.catalog_id.isnot(None))
        .distinct()
        .subquery()
    )

    query = select(
        CatalogEntry,
        func.coalesce(radar_count.c.nb_playlists, 0).label("nb_radar_playlists"),
        (lib_count.c.catalog_id.isnot(None)).label("in_lib"),
    ).outerjoin(
        radar_count, CatalogEntry.id == radar_count.c.catalog_id
    ).outerjoin(
        lib_count, CatalogEntry.id == lib_count.c.catalog_id
    )

    if in_lib is True:
        query = query.where(lib_count.c.catalog_id.isnot(None))
    elif in_lib is False:
        query = query.where(lib_count.c.catalog_id.is_(None))

    if min_radar_playlists is not None:
        query = query.where(
            func.coalesce(radar_count.c.nb_playlists, 0) >= min_radar_playlists
        )

    if search:
        pattern = f"%{search}%"
        query = query.where(
            CatalogEntry.title.ilike(pattern) | CatalogEntry.artist.ilike(pattern)
        )

    # Total avant pagination
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    entries = []
    for row in rows:
        entry = row[0]
        nb_playlists = row[1]
        is_in_lib = row[2] is not None

        out = CatalogEntryOut(
            id=entry.id,
            title=entry.title,
            artist=entry.artist,
            isrc=entry.isrc,
            bpm=entry.bpm,
            key=entry.key,
            duration_ms=entry.duration_ms,
            genre=entry.genre,
            release_date=entry.release_date,
            preview_url=entry.preview_url,
            has_artwork=entry.has_artwork,
            has_preview=entry.has_preview,
            created_at=entry.created_at,
            in_lib=is_in_lib,
            nb_radar_playlists=nb_playlists or 0,
            nb_radar_sets=0,
        )
        entries.append(out)

    return CatalogList(total=total, items=entries)


@router.get("/{catalog_id}/preview-url")
async def get_preview_url(catalog_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne une preview URL fraîche depuis l'API Deezer (les URLs sont signées et expirent)."""
    r = await db.execute(
        select(RadarTrack.external_track_id)
        .where(RadarTrack.catalog_id == catalog_id)
        .where(RadarTrack.source == "deezer")
        .limit(1)
    )
    row = r.first()
    if not row:
        raise HTTPException(status_code=404, detail="No Deezer source for this entry")

    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(f"https://api.deezer.com/track/{row[0]}")
        resp.raise_for_status()
        data = resp.json()

    preview = data.get("preview", "").strip()
    if not preview:
        raise HTTPException(status_code=404, detail="No preview available")

    return {"preview_url": preview}
