"""
Catalog service: list, detail, preview URL, avis update, crawl logs.

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

import json as _json
from collections import defaultdict
from datetime import datetime

import httpx
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.genre_service import _PILLAR_CACHE, _ensure_pillar_cache, genre_pillar


async def list_catalog(
    db: AsyncSession,
    user_id: int | None,
    skip: int,
    limit: int,
    in_lib: bool | None,
    min_radar_playlists: int | None,
    search: str | None,
    genre: str | None,
    sort: str | None,
    order: str,
    view: str | None,
    detected_after: datetime | None,
    avis: str | None,
):
    from models import (
        Artist,
        CatalogArtist,
        CatalogEntry,
        RadarTrack,
        RadarTrend,
        SetTrack,
        UserTrack,
        WatchedEntity,
    )
    from schemas import ArtistRef, CatalogEntryOut, CatalogList, GenreRef
    from sqlalchemy import literal_column

    is_radar = view == "radar"

    radar_count = (
        select(
            RadarTrack.catalog_id,
            func.count(func.distinct(RadarTrack.watched_entity_id)).label("nb_playlists"),
        )
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(RadarTrack.catalog_id)
        .subquery()
    )
    set_count = (
        select(
            SetTrack.catalog_id,
            func.count(func.distinct(SetTrack.set_id)).label("nb_sets"),
        )
        .where(SetTrack.catalog_id.isnot(None))
        .group_by(SetTrack.catalog_id)
        .subquery()
    )
    ut_sub = (
        select(
            UserTrack.catalog_id,
            UserTrack.rating,
            UserTrack.rb_bpm,
            UserTrack.rb_key,
            UserTrack.rb_mytags,
            UserTrack.has_artwork.label("ut_has_artwork"),
            UserTrack.avis.label("ut_avis"),
            UserTrack.date_added.label("ut_date_added"),
        )
        .where(UserTrack.user_id == user_id)
        .subquery()
    )
    radar_src = (
        select(
            RadarTrack.catalog_id,
            func.max(RadarTrack.detected_at).label("max_detected_at"),
        )
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(RadarTrack.catalog_id)
        .subquery()
    )
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

    trend_sub = (
        select(
            RadarTrend.catalog_id,
            RadarTrend.rank_global,
            (
                RadarTrend.trend_score
                / func.nullif(func.max(RadarTrend.trend_score).over(), 0)
                * 10
            ).label("trend_score_10"),
        )
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
        trend_sub.c.rank_global.label("trend_rank"),
        trend_sub.c.trend_score_10.label("trend_score_10"),
    ]
    if is_radar:
        select_cols.extend(
            [
                radar_src.c.max_detected_at.label("detected_at"),
                latest_radar.c.src_name.label("source_name"),
                latest_radar.c.src_kind.label("source_kind"),
            ]
        )

    query = (
        select(*select_cols)
        .outerjoin(radar_count, CatalogEntry.id == radar_count.c.catalog_id)
        .outerjoin(set_count, CatalogEntry.id == set_count.c.catalog_id)
        .outerjoin(ut_sub, CatalogEntry.id == ut_sub.c.catalog_id)
        .outerjoin(trend_sub, CatalogEntry.id == trend_sub.c.catalog_id)
    )

    if is_radar:
        query = query.outerjoin(
            radar_src, CatalogEntry.id == radar_src.c.catalog_id
        ).outerjoin(latest_radar, CatalogEntry.id == latest_radar.c.catalog_id)
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

    await _ensure_pillar_cache(db)

    nb_radar_col = func.coalesce(radar_count.c.nb_playlists, 0)
    sort_col = None

    if sort == "detected_at" and is_radar:
        sort_col = func.coalesce(radar_src.c.max_detected_at, datetime(2000, 1, 1))
    elif sort == "nb_radar_playlists":
        sort_col = nb_radar_col
    elif sort == "trend_score_10":
        sort_col = func.coalesce(trend_sub.c.trend_score_10, 0)
    elif sort == "rating":
        sort_col = func.coalesce(ut_sub.c.rating, 0)
    elif sort == "bpm":
        sort_col = func.coalesce(ut_sub.c.rb_bpm, CatalogEntry.bpm, 0)
    elif sort == "duration_ms":
        sort_col = func.coalesce(CatalogEntry.duration_ms, 0)
    elif sort == "key":
        sort_col = func.coalesce(ut_sub.c.rb_key, CatalogEntry.key, "")
    elif sort == "style":
        first_genre = func.coalesce(literal_column("genres[1]"), "")
        pillar_rank = {
            "house": 0, "techno": 1, "trance": 2,
            "dnb": 3, "hardcore": 4, "harddance": 5, "autres": 6,
        }
        pillar_case = case(
            *[(first_genre == g, pillar_rank.get(p, 6)) for g, (p, _d) in _PILLAR_CACHE.items()],
            else_=6,
        )

        def dir_fn(c):
            return c.desc() if order != "asc" else c.asc()

        query = query.order_by(dir_fn(pillar_case), dir_fn(first_genre))
    elif sort == "in_lib":
        # Sort by rekordbox date_added: most recent first, non-lib tracks last
        dir_fn = (lambda c: c.desc().nulls_last()) if order != "asc" else (lambda c: c.asc().nulls_last())
        query = query.order_by(dir_fn(ut_sub.c.ut_date_added))
    elif sort == "avis":
        sort_col = func.coalesce(ut_sub.c.ut_avis, "")
    elif sort == "title":
        sort_col = CatalogEntry.title
    else:
        if is_radar:
            sort_col = func.coalesce(radar_src.c.max_detected_at, datetime(2000, 1, 1))
        else:
            sort_col = nb_radar_col

    if sort_col is not None:
        query = query.order_by(sort_col.desc() if order != "asc" else sort_col.asc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    page_ids = [row[0].id for row in rows]
    artists_by_catalog: dict[int, list] = defaultdict(list)
    if page_ids:
        ca_result = await db.execute(
            select(
                CatalogArtist.catalog_id,
                Artist.id,
                Artist.name,
                CatalogArtist.role,
                Artist.has_artwork,
            )
            .join(Artist, Artist.id == CatalogArtist.artist_id)
            .where(CatalogArtist.catalog_id.in_(page_ids))
            .order_by(CatalogArtist.catalog_id, CatalogArtist.position)
        )
        for ca_cid, a_id, a_name, a_role, a_art in ca_result.all():
            artists_by_catalog[ca_cid].append(
                ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
            )

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
        t_rank = row[10]
        t_score_10 = row[11]
        entry_artists = artists_by_catalog.get(entry.id, [])
        art_id = entry_artists[0].id if entry_artists else None

        radar_fields = {}
        if is_radar:
            radar_fields = {
                "detected_at": row[12],
                "source_name": row[13],
                "source_kind": row[14],
            }

        lib_style = None
        if ut_tags:
            try:
                tags = ut_tags if isinstance(ut_tags, list) else _json.loads(ut_tags)
                lib_style = tags[0] if tags else None
            except Exception:
                pass

        genre_refs = []
        for g in entry.genres or []:
            p, d = genre_pillar(g)
            genre_refs.append(GenreRef(name=g, pillar=p, depth=d))

        entries.append(
            CatalogEntryOut(
                id=entry.id,
                title=entry.title,
                artist=entry.artist,
                isrc=entry.isrc,
                bpm=ut_bpm if ut_bpm is not None else entry.bpm,
                key=ut_key if ut_key is not None else entry.key,
                duration_ms=entry.duration_ms,
                genres=genre_refs,
                release_date=entry.release_date,
                preview_url=entry.preview_url,
                has_artwork=ut_has_artwork if ut_has_artwork else entry.has_artwork,
                lib_track_id=None,
                has_preview=entry.has_preview,
                created_at=entry.created_at,
                in_lib=is_in_lib,
                nb_radar_playlists=nb_playlists or 0,
                nb_radar_sets=nb_sets or 0,
                style=lib_style,
                rating=ut_rating,
                avis=ut_avis,
                trend_rank=t_rank,
                trend_score_10=round(t_score_10, 1) if t_score_10 is not None else None,
                artist_id=art_id,
                artists=entry_artists,
                **radar_fields,
            )
        )

    return CatalogList(total=total, items=entries)


async def get_detail(db: AsyncSession, catalog_id: int, user_id: int | None):
    from models import (
        Artist,
        CatalogArtist,
        CatalogEntry,
        DJSet,
        RadarTrack,
        SetTrack,
        UserTrack,
        WatchedEntity,
    )
    from schemas import (
        ArtistRef,
        CatalogDetailOut,
        GenreRef,
        RadarAppearanceOut,
        SameArtistTrackOut,
        SetAppearanceOut,
    )

    result = await db.execute(select(CatalogEntry).where(CatalogEntry.id == catalog_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise LookupError("Catalog entry not found")

    ut_result = await db.execute(
        select(UserTrack)
        .where(UserTrack.catalog_id == catalog_id, UserTrack.user_id == user_id)
        .limit(1)
    )
    ut = ut_result.scalar_one_or_none()
    in_lib = ut is not None
    ut_rating = ut.rating if ut else None
    ut_tags: list[str] = []
    lib_style = None
    if ut and ut.rb_mytags:
        try:
            ut_tags = (
                ut.rb_mytags
                if isinstance(ut.rb_mytags, list)
                else _json.loads(ut.rb_mytags)
            )
            lib_style = ut_tags[0] if ut_tags else None
        except Exception:
            pass

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
            playlist_id=r[0],
            playlist_title=r[1],
            playlist_source=r[2],
            detected_at=r[3],
        )
        for r in radar_result.all()
    ]

    set_result = await db.execute(
        select(DJSet.id, DJSet.title, DJSet.played_date, SetTrack.timecode_ms)
        .join(DJSet, DJSet.id == SetTrack.set_id)
        .where(SetTrack.catalog_id == catalog_id)
        .order_by(DJSet.played_date.desc().nulls_last())
        .limit(10)
    )
    set_appearances = [
        SetAppearanceOut(
            set_id=r[0], set_title=r[1], played_date=r[2], timecode_ms=r[3]
        )
        for r in set_result.all()
    ]

    ca_result = await db.execute(
        select(Artist.id, Artist.name, CatalogArtist.role, Artist.has_artwork)
        .join(Artist, Artist.id == CatalogArtist.artist_id)
        .where(CatalogArtist.catalog_id == catalog_id)
        .order_by(CatalogArtist.position)
    )
    entry_artists = [
        ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
        for a_id, a_name, a_role, a_art in ca_result.all()
    ]
    entry_artist_id = entry_artists[0].id if entry_artists else None

    same_artist = []
    entry_artist_ids = [a.id for a in entry_artists]
    if entry_artist_ids:
        shared_catalog_ids = (
            select(CatalogArtist.catalog_id)
            .where(CatalogArtist.artist_id.in_(entry_artist_ids))
            .where(CatalogArtist.catalog_id != catalog_id)
            .distinct()
            .subquery()
        )
        sa_ut_sub = (
            select(UserTrack.catalog_id, UserTrack.rating)
            .where(UserTrack.user_id == user_id)
            .subquery()
        )
        sa_result = await db.execute(
            select(
                CatalogEntry.id,
                CatalogEntry.title,
                CatalogEntry.artist,
                CatalogEntry.bpm,
                CatalogEntry.key,
                CatalogEntry.duration_ms,
                CatalogEntry.has_artwork,
                sa_ut_sub.c.catalog_id.label("sa_ut_cid"),
                sa_ut_sub.c.rating,
            )
            .outerjoin(sa_ut_sub, CatalogEntry.id == sa_ut_sub.c.catalog_id)
            .where(CatalogEntry.id.in_(select(shared_catalog_ids.c.catalog_id)))
            .order_by(sa_ut_sub.c.rating.desc().nulls_last())
            .limit(10)
        )
        sa_rows = sa_result.all()
        sa_ids = [r[0] for r in sa_rows]
        sa_artists_map: dict[int, list] = defaultdict(list)
        if sa_ids:
            sa_ca = await db.execute(
                select(
                    CatalogArtist.catalog_id,
                    Artist.id,
                    Artist.name,
                    CatalogArtist.role,
                    Artist.has_artwork,
                )
                .join(Artist, Artist.id == CatalogArtist.artist_id)
                .where(CatalogArtist.catalog_id.in_(sa_ids))
                .order_by(CatalogArtist.catalog_id, CatalogArtist.position)
            )
            for ca_cid, a_id, a_name, a_role, a_art in sa_ca.all():
                sa_artists_map[ca_cid].append(
                    ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
                )
        same_artist = [
            SameArtistTrackOut(
                id=r[0],
                title=r[1],
                artist=r[2],
                bpm=r[3],
                key=r[4],
                duration_ms=r[5],
                has_artwork=r[6],
                in_lib=r[7] is not None,
                rating=r[8],
                artists=sa_artists_map.get(r[0], []),
            )
            for r in sa_rows
        ]

    genre_refs = [
        GenreRef(name=g, pillar=p, depth=d)
        for g in (entry.genres or [])
        for p, d in [genre_pillar(g)]
    ]

    return CatalogDetailOut(
        id=entry.id,
        title=entry.title,
        artist=entry.artist,
        isrc=entry.isrc,
        bpm=ut.rb_bpm if ut and ut.rb_bpm else entry.bpm,
        key=ut.rb_key if ut and ut.rb_key else entry.key,
        duration_ms=entry.duration_ms,
        genres=genre_refs,
        label=entry.label,
        deezer_id=entry.deezer_id,
        beatport_id=entry.beatport_id,
        release_date=entry.release_date,
        preview_url=entry.preview_url,
        has_artwork=ut.has_artwork if ut and ut.has_artwork else entry.has_artwork,
        has_preview=entry.has_preview,
        created_at=entry.created_at,
        in_lib=in_lib,
        nb_radar_playlists=len(radar_appearances),
        nb_radar_sets=len(set_appearances),
        style=lib_style,
        rating=ut_rating,
        artist_id=entry_artist_id,
        artists=entry_artists,
        lib_track_id=ut.rekordbox_id if ut else None,
        radar_appearances=radar_appearances,
        set_appearances=set_appearances,
        same_artist_tracks=same_artist,
        tags=ut_tags,
    )


async def get_preview_url(db: AsyncSession, catalog_id: int) -> dict:
    from models import CatalogEntry, RadarTrack

    r = await db.execute(
        select(RadarTrack.external_track_id)
        .where(RadarTrack.catalog_id == catalog_id, RadarTrack.source == "deezer")
        .limit(1)
    )
    row = r.first()
    deezer_track_id = row[0] if row else None

    if not deezer_track_id:
        r2 = await db.execute(
            select(CatalogEntry.deezer_id).where(CatalogEntry.id == catalog_id)
        )
        row2 = r2.first()
        deezer_track_id = row2[0] if row2 and row2[0] else None

    if not deezer_track_id:
        raise LookupError("No Deezer source for this entry")

    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(f"https://api.deezer.com/track/{deezer_track_id}")
        resp.raise_for_status()
        data = resp.json()

    preview = data.get("preview", "").strip()
    if not preview:
        raise LookupError("No preview available")

    return {"preview_url": preview}


async def update_avis(
    db: AsyncSession, catalog_id: int, user_id: int, avis: str | None
) -> dict:
    from models import CatalogEntry, UserTrack
    from opinion_sync import sync_track_opinion

    result = await db.execute(
        select(UserTrack).where(
            UserTrack.user_id == user_id, UserTrack.catalog_id == catalog_id
        )
    )
    ut = result.scalar_one_or_none()

    if ut:
        ut.avis = avis
    else:
        cat = await db.execute(
            select(CatalogEntry.id).where(CatalogEntry.id == catalog_id)
        )
        if not cat.scalar_one_or_none():
            raise LookupError("Catalog entry not found")
        ut = UserTrack(
            user_id=user_id, catalog_id=catalog_id, avis=avis, source="catalog_avis"
        )
        db.add(ut)

    await sync_track_opinion(db, user_id, catalog_id, avis)
    await db.commit()
    return {"catalog_id": catalog_id, "avis": avis}


async def get_crawl_logs(
    db: AsyncSession,
    page: int,
    per_page: int,
    task_type: str | None,
    status: str | None,
) -> dict:
    from models import CrawlLog

    query = select(CrawlLog).order_by(CrawlLog.started_at.desc())
    if task_type:
        query = query.where(CrawlLog.task_type == task_type)
    if status:
        query = query.where(CrawlLog.status == status)

    count_query = select(func.count(CrawlLog.id))
    if task_type:
        count_query = count_query.where(CrawlLog.task_type == task_type)
    if status:
        count_query = count_query.where(CrawlLog.status == status)
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    logs = (await db.execute(query.offset(offset).limit(per_page))).scalars().all()

    return {
        "items": [
            {
                "id": log.id,
                "task_type": log.task_type,
                "target_id": log.target_id,
                "target_label": log.target_label,
                "source": log.source,
                "status": log.status,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "finished_at": log.finished_at.isoformat() if log.finished_at else None,
                "duration_ms": log.duration_ms,
                "stats": log.stats,
                "error_message": log.error_message,
                "celery_task_id": log.celery_task_id,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
