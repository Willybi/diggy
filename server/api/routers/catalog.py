from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx
import json as _json

from database import get_db
from models import (
    CatalogEntry, LibTrack, RadarTrack, SetTrack,
    DJSet, SetArtist, Artist, WatchedPlaylist,
)
from schemas import (
    CatalogEntryOut, CatalogList, CatalogDetailOut,
    GenreOut, RadarAppearanceOut, SetAppearanceOut, SameArtistTrackOut,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

SORTABLE_COLS = {
    "title": CatalogEntry.title,
    # bpm, rating : depuis lib_tracks avec COALESCE — traités séparément
    "nb_radar_playlists": None,
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

    # Sous-requête : nb de sets distincts dans set_tracks par catalog_id
    set_count = (
        select(
            SetTrack.catalog_id,
            func.count(func.distinct(SetTrack.set_id)).label("nb_sets"),
        )
        .where(SetTrack.catalog_id.isnot(None))
        .group_by(SetTrack.catalog_id)
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
        func.coalesce(set_count.c.nb_sets, 0).label("nb_radar_sets"),
        lib_sub.c.catalog_id.label("lib_catalog_id"),
        lib_sub.c.lib_track_id.label("lib_track_id"),
        LibTrack.bpm.label("lib_bpm"),
        LibTrack.key.label("lib_key"),
        LibTrack.rating.label("lib_rating"),
        LibTrack.tags.label("lib_tags"),
        LibTrack.duration.label("lib_duration"),
        LibTrack.has_artwork.label("lib_has_artwork"),
    ).outerjoin(
        radar_count, CatalogEntry.id == radar_count.c.catalog_id
    ).outerjoin(
        set_count, CatalogEntry.id == set_count.c.catalog_id
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
    elif sort == "rating":
        sort_col = func.coalesce(LibTrack.rating, 0)
    elif sort == "bpm":
        sort_col = func.coalesce(LibTrack.bpm, CatalogEntry.bpm, 0)
    elif sort == "duration_ms":
        sort_col = func.coalesce(LibTrack.duration, CatalogEntry.duration_ms, 0)
    elif sort == "key":
        sort_col = func.coalesce(LibTrack.key, CatalogEntry.key, "")
    elif sort == "style":
        sort_col = func.coalesce(LibTrack.tags, "")
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
        nb_sets = row[2]
        is_in_lib = row[3] is not None  # lib_catalog_id NULL = pas dans lib
        lib_track_id = row[4]
        lib_bpm = row[5]
        lib_key = row[6]
        lib_rating = row[7]
        lib_tags = row[8]
        lib_duration = row[9]
        lib_has_artwork = row[10]

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
            has_artwork=lib_has_artwork if lib_has_artwork else entry.has_artwork,
            lib_track_id=lib_track_id,
            has_preview=entry.has_preview,
            created_at=entry.created_at,
            in_lib=is_in_lib,
            nb_radar_playlists=nb_playlists or 0,
            nb_radar_sets=nb_sets or 0,
            style=lib_style,
            rating=lib_rating,
        )
        entries.append(out)

    return CatalogList(total=total, items=entries)


@router.get("/{catalog_id}", response_model=CatalogDetailOut)
async def get_catalog_detail(catalog_id: int, db: AsyncSession = Depends(get_db)):
    # 1. Main entry + genres
    result = await db.execute(
        select(CatalogEntry)
        .options(selectinload(CatalogEntry.genres))
        .where(CatalogEntry.id == catalog_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")

    # 2. Lib track info
    lib_result = await db.execute(
        select(LibTrack).where(LibTrack.catalog_id == catalog_id).limit(1)
    )
    lib_track = lib_result.scalar_one_or_none()

    in_lib = lib_track is not None
    lib_rating = lib_track.rating if lib_track else None
    lib_tags: list[str] = []
    lib_style = None
    if lib_track and lib_track.tags:
        try:
            lib_tags = _json.loads(lib_track.tags) if isinstance(lib_track.tags, str) else lib_track.tags
            lib_style = lib_tags[0] if lib_tags else None
        except Exception:
            pass

    # 3. Radar appearances
    radar_result = await db.execute(
        select(
            RadarTrack.watched_playlist_id,
            WatchedPlaylist.title,
            WatchedPlaylist.source,
            RadarTrack.detected_at,
        )
        .join(WatchedPlaylist, WatchedPlaylist.id == RadarTrack.watched_playlist_id)
        .where(RadarTrack.catalog_id == catalog_id)
        .order_by(RadarTrack.detected_at.desc())
        .limit(10)
    )
    radar_appearances = [
        RadarAppearanceOut(
            playlist_id=r[0], playlist_title=r[1],
            playlist_source=r[2], detected_at=r[3],
        )
        for r in radar_result.all()
    ]

    # 4. Set appearances
    set_result = await db.execute(
        select(
            DJSet.id, DJSet.title, DJSet.played_date,
            SetTrack.timecode_ms,
        )
        .join(DJSet, DJSet.id == SetTrack.set_id)
        .where(SetTrack.catalog_id == catalog_id)
        .order_by(DJSet.played_date.desc().nullslast())
        .limit(10)
    )
    set_appearances = [
        SetAppearanceOut(
            set_id=r[0], set_title=r[1],
            played_date=r[2], timecode_ms=r[3],
        )
        for r in set_result.all()
    ]

    # 5. Same artist tracks
    same_artist = []
    if entry.artist:
        sa_lib_sub = (
            select(LibTrack.catalog_id, LibTrack.rating)
            .where(LibTrack.catalog_id.isnot(None))
            .subquery()
        )
        sa_result = await db.execute(
            select(
                CatalogEntry.id, CatalogEntry.title, CatalogEntry.artist,
                CatalogEntry.bpm, CatalogEntry.key, CatalogEntry.duration_ms,
                CatalogEntry.has_artwork,
                sa_lib_sub.c.catalog_id.label("sa_lib_cid"),
                sa_lib_sub.c.rating,
            )
            .outerjoin(sa_lib_sub, CatalogEntry.id == sa_lib_sub.c.catalog_id)
            .where(CatalogEntry.artist.ilike(entry.artist))
            .where(CatalogEntry.id != catalog_id)
            .order_by(sa_lib_sub.c.rating.desc().nullslast())
            .limit(10)
        )
        same_artist = [
            SameArtistTrackOut(
                id=r[0], title=r[1], artist=r[2], bpm=r[3], key=r[4],
                duration_ms=r[5], has_artwork=r[6],
                in_lib=r[7] is not None, rating=r[8],
            )
            for r in sa_result.all()
        ]

    # 6. Radar / set counts
    nb_radar = len(radar_appearances)
    nb_sets = len(set_appearances)

    return CatalogDetailOut(
        id=entry.id,
        title=entry.title,
        artist=entry.artist,
        isrc=entry.isrc,
        bpm=lib_track.bpm if lib_track and lib_track.bpm else entry.bpm,
        key=lib_track.key if lib_track and lib_track.key else entry.key,
        duration_ms=lib_track.duration if lib_track and lib_track.duration else entry.duration_ms,
        genre=entry.genre,
        release_date=entry.release_date,
        preview_url=entry.preview_url,
        has_artwork=lib_track.has_artwork if lib_track and lib_track.has_artwork else entry.has_artwork,
        has_preview=entry.has_preview,
        created_at=entry.created_at,
        in_lib=in_lib,
        nb_radar_playlists=nb_radar,
        nb_radar_sets=nb_sets,
        style=lib_style,
        rating=lib_rating,
        lib_track_id=lib_track.id if lib_track else None,
        genres=[GenreOut.model_validate(g) for g in entry.genres],
        radar_appearances=radar_appearances,
        set_appearances=set_appearances,
        same_artist_tracks=same_artist,
        tags=lib_tags,
    )


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
