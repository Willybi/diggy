from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import json as _json

from database import get_db
from dependencies import get_current_user, get_current_user_optional, uid as _uid
from datetime import datetime, timezone

CatalogSortField = Literal[
    "title", "nb_radar_playlists", "detected_at", "rating",
    "bpm", "duration_ms", "key", "style", "in_lib", "avis",
]

from models import (
    CatalogEntry, UserTrack, UserRadarState, RadarTrack, SetTrack,
    DJSet, SetArtist, Artist, WatchedEntity, User,
)
from opinion_sync import sync_track_opinion
from schemas import (
    CatalogEntryOut, CatalogList, CatalogDetailOut, CatalogAvisUpdate,
    RadarAppearanceOut, SetAppearanceOut, SameArtistTrackOut,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

SORTABLE_COLS = {
    "title": CatalogEntry.title,
    "nb_radar_playlists": None,
}


@router.get("/genres")
async def list_genres(db: AsyncSession = Depends(get_db)):
    """Return all distinct genres with track counts (unnested from arrays)."""
    from routers.genres import genre_pillar, _ensure_pillar_cache
    await _ensure_pillar_cache(db)
    genre_col = func.unnest(CatalogEntry.genres).label("genre")
    result = await db.execute(
        select(genre_col, func.count())
        .where(func.coalesce(func.array_length(CatalogEntry.genres, 1), 0) > 0)
        .group_by(genre_col)
        .order_by(func.count().desc())
    )
    items = []
    for row in result.all():
        p, d = genre_pillar(row[0])
        items.append({"name": row[0], "count": row[1], "pillar": p, "depth": d})
    return items


@router.get("/", response_model=CatalogList)
async def list_catalog(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    in_lib: bool | None = Query(None),
    min_radar_playlists: int | None = Query(None),
    search: str | None = Query(None, max_length=200),
    genre: str | None = Query(None, max_length=100),
    sort: CatalogSortField | None = Query(None),
    order: Literal["asc", "desc"] | None = Query("desc"),
    view: Literal["radar"] | None = Query(None),
    detected_after: datetime | None = Query(None),
    avis: Literal["liked", "disliked"] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)
    is_radar = view == "radar"

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
            UserTrack.avis.label("ut_avis"),
        )
        .where(UserTrack.user_id == uid)
        .subquery()
    )

    # Sous-requête radar source : playlist/set la plus récente par catalog_id
    radar_src = (
        select(
            RadarTrack.catalog_id,
            func.max(RadarTrack.detected_at).label("max_detected_at"),
        )
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(RadarTrack.catalog_id)
        .subquery()
    )

    # Sous-requête : la source la plus récente (nom + kind)
    latest_radar = (
        select(
            RadarTrack.catalog_id,
            WatchedEntity.title.label("src_name"),
            WatchedEntity.source.label("src_kind"),
        )
        .join(WatchedEntity, WatchedEntity.id == RadarTrack.watched_entity_id)
        .join(
            radar_src,
            (RadarTrack.catalog_id == radar_src.c.catalog_id)
            & (RadarTrack.detected_at == radar_src.c.max_detected_at),
        )
        .distinct(RadarTrack.catalog_id)
        .subquery()
    )

    select_cols = [
        CatalogEntry,
        func.coalesce(radar_count.c.nb_playlists, 0).label("nb_radar_playlists"),
        func.coalesce(set_count.c.nb_sets, 0).label("nb_radar_sets"),
        ut_sub.c.catalog_id.label("ut_catalog_id"),
        ut_sub.c.rating.label("ut_rating"),
        ut_sub.c.rb_bpm.label("ut_bpm"),
        ut_sub.c.rb_key.label("ut_key"),
        ut_sub.c.rb_mytags.label("ut_tags"),
        ut_sub.c.ut_has_artwork.label("ut_has_artwork"),
        ut_sub.c.ut_avis.label("ut_avis"),
    ]

    if is_radar:
        select_cols.extend([
            radar_src.c.max_detected_at.label("detected_at"),
            latest_radar.c.src_name.label("source_name"),
            latest_radar.c.src_kind.label("source_kind"),
        ])

    query = select(*select_cols).outerjoin(
        radar_count, CatalogEntry.id == radar_count.c.catalog_id
    ).outerjoin(
        set_count, CatalogEntry.id == set_count.c.catalog_id
    ).outerjoin(
        ut_sub, CatalogEntry.id == ut_sub.c.catalog_id
    )

    if is_radar:
        query = query.outerjoin(
            radar_src, CatalogEntry.id == radar_src.c.catalog_id
        ).outerjoin(
            latest_radar, CatalogEntry.id == latest_radar.c.catalog_id
        )
        # Only tracks with radar appearances
        query = query.where(radar_count.c.nb_playlists.isnot(None))
        if detected_after:
            query = query.where(radar_src.c.max_detected_at >= detected_after)

    if in_lib is True:
        query = query.where(ut_sub.c.catalog_id.isnot(None))
    elif in_lib is False:
        query = query.where(ut_sub.c.catalog_id.is_(None))

    if min_radar_playlists is not None:
        query = query.where(
            func.coalesce(radar_count.c.nb_playlists, 0) >= min_radar_playlists
        )

    if genre:
        query = query.where(CatalogEntry.genres.any(genre))

    if search:
        pattern = f"%{search}%"
        query = query.where(
            CatalogEntry.title.ilike(pattern) | CatalogEntry.artist.ilike(pattern)
        )

    if avis:
        query = query.where(ut_sub.c.ut_avis == avis)

    # Tri
    nb_radar_col = func.coalesce(radar_count.c.nb_playlists, 0)
    if sort == "detected_at" and is_radar:
        sort_col = func.coalesce(radar_src.c.max_detected_at, datetime(2000, 1, 1))
    elif sort == "nb_radar_playlists":
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
        sort_col = func.coalesce(CatalogEntry.genres[1], ut_sub.c.rb_mytags.op("->>")(0), "")
    elif sort == "in_lib":
        sort_col = case((ut_sub.c.catalog_id.isnot(None), 1), else_=0)
    elif sort == "avis":
        sort_col = func.coalesce(ut_sub.c.ut_avis, "")
    elif sort in SORTABLE_COLS and SORTABLE_COLS[sort] is not None:
        sort_col = SORTABLE_COLS[sort]
    else:
        if is_radar:
            sort_col = func.coalesce(radar_src.c.max_detected_at, datetime(2000, 1, 1))
        else:
            sort_col = nb_radar_col  # défaut

    query = query.order_by(sort_col.desc() if order != "asc" else sort_col.asc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    # Batch-fetch artist_ids for the page's entries (separate query, avoids cartesian product)
    page_artists_lower = {row[0].artist.lower() for row in rows if row[0].artist}
    artist_id_map: dict[str, int] = {}
    if page_artists_lower:
        artist_result = await db.execute(
            select(Artist.id, Artist.normalized_name)
            .where(Artist.normalized_name.in_(page_artists_lower))
        )
        for aid, aname in artist_result.all():
            artist_id_map[aname] = aid

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
        ut_avis = row[9]
        art_id = artist_id_map.get(entry.artist.lower()) if entry.artist else None

        radar_fields = {}
        if is_radar:
            radar_fields = {
                "detected_at": row[10],
                "source_name": row[11],
                "source_kind": row[12],
            }

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
            genres=entry.genres or [],
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
            avis=ut_avis,
            artist_id=art_id,
            **radar_fields,
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

    # 1. Main entry
    result = await db.execute(
        select(CatalogEntry)
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
        genres=entry.genres or [],
        label=entry.label,
        deezer_id=entry.deezer_id,
        beatport_id=entry.beatport_id,
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


@router.patch("/{catalog_id}/avis")
async def update_avis(
    catalog_id: int,
    body: CatalogAvisUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = user.id

    result = await db.execute(
        select(UserTrack).where(UserTrack.user_id == uid, UserTrack.catalog_id == catalog_id)
    )
    ut = result.scalar_one_or_none()

    if ut:
        ut.avis = body.avis
    else:
        # Verify catalog entry exists
        cat = await db.execute(select(CatalogEntry.id).where(CatalogEntry.id == catalog_id))
        if not cat.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Catalog entry not found")
        ut = UserTrack(user_id=uid, catalog_id=catalog_id, avis=body.avis, source="catalog_avis")
        db.add(ut)

    # Sync → user_opinions + user_radar_state
    await sync_track_opinion(db, uid, catalog_id, body.avis)

    await db.commit()
    return {"catalog_id": catalog_id, "avis": body.avis}
