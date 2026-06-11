from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from database import get_db
from models import CatalogEntry, LibTrack, RadarTrack
from schemas import CatalogEntryOut, CatalogList

router = APIRouter(prefix="/catalog", tags=["catalog"])

SORTABLE_COLS = {
    "title": CatalogEntry.title,
    "bpm": CatalogEntry.bpm,
    "duration_ms": CatalogEntry.duration_ms,
    "nb_radar_playlists": None,  # traité séparément
}


@router.get("/", response_model=CatalogList)
async def list_catalog(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    in_lib: bool | None = Query(None),
    min_radar_playlists: int | None = Query(None),
    search: str | None = Query(None),
    sort: str | None = Query(None),
    order: str | None = Query("desc"),
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

    # Sous-requête : lib_track lié (premier match) pour récupérer rating/bpm/key/tags
    lib_sub = (
        select(
            LibTrack.catalog_id,
            func.min(LibTrack.id).label("lib_track_id"),
        )
        .where(LibTrack.catalog_id.isnot(None))
        .group_by(LibTrack.catalog_id)
        .subquery()
    )

    query = select(
        CatalogEntry,
        func.coalesce(radar_count.c.nb_playlists, 0).label("nb_radar_playlists"),
        lib_sub.c.catalog_id.label("lib_catalog_id"),
        LibTrack.bpm.label("lib_bpm"),
        LibTrack.key.label("lib_key"),
        LibTrack.rating.label("lib_rating"),
        LibTrack.tags.label("lib_tags"),
        LibTrack.duration.label("lib_duration"),
    ).outerjoin(
        radar_count, CatalogEntry.id == radar_count.c.catalog_id
    ).outerjoin(
        lib_sub, CatalogEntry.id == lib_sub.c.catalog_id
    ).outerjoin(
        LibTrack, LibTrack.id == lib_sub.c.lib_track_id
    )

    if in_lib is True:
        query = query.where(lib_sub.c.catalog_id.isnot(None))
    elif in_lib is False:
        query = query.where(lib_sub.c.catalog_id.is_(None))

    if min_radar_playlists is not None:
        query = query.where(
            func.coalesce(radar_count.c.nb_playlists, 0) >= min_radar_playlists
        )

    if search:
        pattern = f"%{search}%"
        query = query.where(
            CatalogEntry.title.ilike(pattern) | CatalogEntry.artist.ilike(pattern)
        )

    # Tri
    nb_radar_col = func.coalesce(radar_count.c.nb_playlists, 0)
    if sort == "nb_radar_playlists":
        sort_col = nb_radar_col
    elif sort in SORTABLE_COLS and SORTABLE_COLS[sort] is not None:
        sort_col = SORTABLE_COLS[sort]
    else:
        sort_col = nb_radar_col  # défaut

    query = query.order_by(sort_col.desc() if order != "asc" else sort_col.asc())

    # Total avant pagination
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    entries = []
    for row in rows:
        entry = row[0]
        nb_playlists = row[1]
        is_in_lib = row[2] is not None  # lib_catalog_id NULL = pas dans lib
        lib_bpm = row[3]
        lib_key = row[4]
        lib_rating = row[5]
        lib_tags = row[6]
        lib_duration = row[7]

        # Style = premier tag RB qui n'est pas un tag fonctionnel
        lib_style = None
        if lib_tags:
            import json
            try:
                tags = json.loads(lib_tags) if isinstance(lib_tags, str) else lib_tags
                # Premier tag (les tags RB sont déjà filtrés côté import)
                lib_style = tags[0] if tags else None
            except Exception:
                pass

        out = CatalogEntryOut(
            id=entry.id,
            title=entry.title,
            artist=entry.artist,
            isrc=entry.isrc,
            bpm=lib_bpm if lib_bpm is not None else entry.bpm,
            key=lib_key if lib_key is not None else entry.key,
            duration_ms=lib_duration if lib_duration is not None else entry.duration_ms,
            genre=entry.genre,
            release_date=entry.release_date,
            preview_url=entry.preview_url,
            has_artwork=entry.has_artwork,
            has_preview=entry.has_preview,
            created_at=entry.created_at,
            in_lib=is_in_lib,
            nb_radar_playlists=nb_playlists or 0,
            nb_radar_sets=0,
            style=lib_style,
            rating=lib_rating,
        )
        entries.append(out)

    return CatalogList(total=total, items=entries)


@router.get("/{catalog_id}/preview-url")
async def get_preview_url(catalog_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne une preview URL fraîche depuis l'API Deezer (les URLs sont signées et expirent)."""
    # Priorité 1 : radar_track Deezer lié
    r = await db.execute(
        select(RadarTrack.external_track_id)
        .where(RadarTrack.catalog_id == catalog_id)
        .where(RadarTrack.source == "deezer")
        .limit(1)
    )
    row = r.first()
    deezer_track_id = row[0] if row else None

    # Priorité 2 : deezer_id stocké directement sur l'entrée catalog
    if not deezer_track_id:
        r2 = await db.execute(
            select(CatalogEntry.deezer_id).where(CatalogEntry.id == catalog_id)
        )
        row2 = r2.first()
        deezer_track_id = row2[0] if row2 and row2[0] else None

    if not deezer_track_id:
        raise HTTPException(status_code=404, detail="No Deezer source for this entry")

    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(f"https://api.deezer.com/track/{deezer_track_id}")
        resp.raise_for_status()
        data = resp.json()

    preview = data.get("preview", "").strip()
    if not preview:
        raise HTTPException(status_code=404, detail="No preview available")

    return {"preview_url": preview}
