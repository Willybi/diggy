from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx
import json as _json

from database import get_db
from dependencies import get_current_user_optional, uid as _uid
from models import (
    CatalogEntry, UserTrack, RadarTrack, SetTrack,
    DJSet, SetArtist, Artist, WatchedEntity, User,
)
from schemas import (
    CatalogEntryOut, CatalogList, CatalogDetailOut,
    GenreOut, RadarAppearanceOut, SetAppearanceOut, SameArtistTrackOut,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

SORTABLE_COLS = {
    "title": CatalogEntry.title,
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
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)

    # Sous-requête : nb de playlists distinctes dans radar_tracks par catalog_id
    radar_count = (
        select(
            RadarTrack.catalog_id,
            func.count(func.distinct(RadarTrack.watched_entity_id)).label("nb_playlists"),
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

    # Sous-requête : user_track lié pour récupérer rating/bpm/key/tags
    ut_sub = (
        select(
            UserTrack.catalog_id,
            UserTrack.rating,
            UserTrack.rb_bpm,
            UserTrack.rb_key,
            UserTrack.rb_mytags,
            UserTrack.has_artwork.label("ut_has_artwork"),
        )
        .where(UserTrack.user_id == uid)
        .subquery()
    )

    query = select(
        CatalogEntry,
        func.coalesce(radar_count.c.nb_playlists, 0).label("nb_radar_playlists"),
        func.coalesce(set_count.c.nb_sets, 0).label("nb_radar_sets"),
        ut_sub.c.catalog_id.label("ut_catalog_id"),
        ut_sub.c.rating.label("ut_rating"),
        ut_sub.c.rb_bpm.label("ut_bpm"),
        ut_sub.c.rb_key.label("ut_key"),
        ut_sub.c.rb_mytags.label("ut_tags"),
        ut_sub.c.ut_has_artwork.label("ut_has_artwork"),
    ).outerjoin(
        radar_count, CatalogEntry.id == radar_count.c.catalog_id
    ).outerjoin(
        set_count, CatalogEntry.id == set_count.c.catalog_id
    ).outerjoin(
        ut_sub, CatalogEntry.id == ut_sub.c.catalog_id
    )

    if in_lib is True:
        query = query.where(ut_sub.c.catalog_id.isnot(None))
    elif in_lib is False:
        query = query.where(ut_sub.c.catalog_id.is_(None))

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
        sort_col = func.coalesce(ut_sub.c.rating, 0)
    elif sort == "bpm":
        sort_col = func.coalesce(ut_sub.c.rb_bpm, CatalogEntry.bpm, 0)
    elif sort == "duration_ms":
        sort_col = func.coalesce(CatalogEntry.duration_ms, 0)
    elif sort == "key":
        sort_col = func.coalesce(ut_sub.c.rb_key, CatalogEntry.key, "")
    elif sort == "style":
        sort_col = func.coalesce(ut_sub.c.rb_mytags.op("->>")(0), "")
    elif sort in SORTABLE_COLS and SORTABLE_COLS[sort] is not None:
        sort_col = SORTABLE_COLS[sort]
    else:
        sort_col = nb_radar_col  # défaut

    query = query.order_by(sort_col.desc() if order != "asc" else sort_col.asc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    entries = []
    for row in rows:
        entry = row[0]
        nb_playlists = row[1]
        nb_sets = row[2]
        is_in_lib = row[3] is not None
        ut_rating = row[4]
        ut_bpm = row[5]
        ut_key = row[6]
        ut_tags = row[7]
        ut_has_artwork = row[8]

        # Style = premier tag RB
        lib_style = None
        if ut_tags:
            try:
                tags = ut_tags if isinstance(ut_tags, list) else _json.loads(ut_tags)
                lib_style = tags[0] if tags else None
            except Exception:
                pass

        out = CatalogEntryOut(
            id=entry.id,
            title=entry.title,
            artist=entry.artist,
            isrc=entry.isrc,
            bpm=ut_bpm if ut_bpm is not None else entry.bpm,
            key=ut_key if ut_key is not None else entry.key,
            duration_ms=entry.duration_ms,
            genre=entry.genre,
            release_date=entry.release_date,
            preview_url=entry.preview_url,
            has_artwork=ut_has_artwork if ut_has_artwork else entry.has_artwork,
            lib_track_id=None,  # rekordbox_id non exposé ici
            has_preview=entry.has_preview,
            created_at=entry.created_at,
            in_lib=is_in_lib,
            nb_radar_playlists=nb_playlists or 0,
            nb_radar_sets=nb_sets or 0,
            style=lib_style,
            rating=ut_rating,
        )
        entries.append(out)

    return CatalogList(total=total, items=entries)


@router.get("/{catalog_id}", response_model=CatalogDetailOut)
async def get_catalog_detail(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)

    # 1. Main entry + genres
    result = await db.execute(
        select(CatalogEntry)
        .options(selectinload(CatalogEntry.genres))
        .where(CatalogEntry.id == catalog_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Catalog entry not found")

    # 2. UserTrack info pour cet user
    ut_result = await db.execute(
        select(UserTrack)
        .where(UserTrack.catalog_id == catalog_id, UserTrack.user_id == uid)
        .limit(1)
    )
    ut = ut_result.scalar_one_or_none()

    in_lib = ut is not None
    ut_rating = ut.rating if ut else None
    ut_tags: list[str] = []
    lib_style = None
    if ut and ut.rb_mytags:
        try:
            ut_tags = ut.rb_mytags if isinstance(ut.rb_mytags, list) else _json.loads(ut.rb_mytags)
            lib_style = ut_tags[0] if ut_tags else None
        except Exception:
            pass

    # 3. Radar appearances
    radar_result = await db.execute(
        select(
            RadarTrack.watched_entity_id,
            WatchedEntity.title,
            WatchedEntity.source,
            RadarTrack.detected_at,
        )
        .join(WatchedEntity, WatchedEntity.id == RadarTrack.watched_entity_id)
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
        .order_by(DJSet.played_date.desc().nulls_last())
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
        sa_ut_sub = (
            select(UserTrack.catalog_id, UserTrack.rating)
            .where(UserTrack.user_id == uid)
            .subquery()
        )
        sa_result = await db.execute(
            select(
                CatalogEntry.id, CatalogEntry.title, CatalogEntry.artist,
                CatalogEntry.bpm, CatalogEntry.key, CatalogEntry.duration_ms,
                CatalogEntry.has_artwork,
                sa_ut_sub.c.catalog_id.label("sa_ut_cid"),
                sa_ut_sub.c.rating,
            )
            .outerjoin(sa_ut_sub, CatalogEntry.id == sa_ut_sub.c.catalog_id)
            .where(CatalogEntry.artist.ilike(entry.artist))
            .where(CatalogEntry.id != catalog_id)
            .order_by(sa_ut_sub.c.rating.desc().nulls_last())
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

    nb_radar = len(radar_appearances)
    nb_sets = len(set_appearances)

    return CatalogDetailOut(
        id=entry.id,
        title=entry.title,
        artist=entry.artist,
        isrc=entry.isrc,
        bpm=ut.rb_bpm if ut and ut.rb_bpm else entry.bpm,
        key=ut.rb_key if ut and ut.rb_key else entry.key,
        duration_ms=entry.duration_ms,
        genre=entry.genre,
        release_date=entry.release_date,
        preview_url=entry.preview_url,
        has_artwork=ut.has_artwork if ut and ut.has_artwork else entry.has_artwork,
        has_preview=entry.has_preview,
        created_at=entry.created_at,
        in_lib=in_lib,
        nb_radar_playlists=nb_radar,
        nb_radar_sets=nb_sets,
        style=lib_style,
        rating=ut_rating,
        lib_track_id=ut.rekordbox_id if ut else None,
        genres=[GenreOut.model_validate(g) for g in entry.genres],
        radar_appearances=radar_appearances,
        set_appearances=set_appearances,
        same_artist_tracks=same_artist,
        tags=ut_tags,
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
