"""
Catalog service: list, detail, preview URL, avis update, crawl logs.

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

import json as _json
import logging
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from services.genre_service import ensure_pillar_cache, genre_pillar, pillar_map

logger = logging.getLogger(__name__)

DEEZER_API = "https://api.deezer.com"


def catalog_visible(user_id: int | None):
    """SQLAlchemy predicate limiting catalog rows to those visible to a viewer.

    A guest (``user_id is None``) sees only shared rows. An authenticated user
    sees shared rows, their own private rows, plus any row they hold a
    ``user_track`` for (their imported library). We branch explicitly on
    ``user_id is None`` rather than matching ``owner_id IS NULL`` for guests, so a
    private row mistagged with a NULL owner never leaks.

    The ``user_track`` clause is what un-blinds a Rekordbox importer whose track,
    deduped on the globally-UNIQUE ``normalized_key``, already points at another
    user's private row: the importer sees it through their own ``user_track``
    without that foreign row ever being mutated or promoted.
    """
    from models import CatalogEntry, UserTrack
    from sqlalchemy import or_

    if user_id is None:
        return CatalogEntry.scope == "shared"
    return or_(
        CatalogEntry.scope == "shared",
        CatalogEntry.owner_id == user_id,
        select(UserTrack.user_id)
        .where(
            UserTrack.catalog_id == CatalogEntry.id,
            UserTrack.user_id == user_id,
        )
        .exists(),
    )


def catalog_visible_sql(user_id: int | None, alias: str = "c") -> str:
    """Raw-SQL twin of :func:`catalog_visible` for ``text()`` queries.

    Returns a boolean SQL fragment scoping the catalog rows of table ``alias``.
    When ``user_id`` is not None the caller must bind ``:viewer_id`` to it — the
    same bind is reused by the ``user_track`` EXISTS clause, so no extra parameter
    is introduced. The subquery's internal alias ``utv`` is chosen to avoid any
    collision with the catalog aliases used at the call sites (``c`` / ``catalog``).
    """
    if user_id is None:
        return f"{alias}.scope = 'shared'"
    return (
        f"({alias}.scope = 'shared' OR {alias}.owner_id = :viewer_id"
        f" OR EXISTS (SELECT 1 FROM user_tracks utv"
        f" WHERE utv.catalog_id = {alias}.id AND utv.user_id = :viewer_id))"
    )


def resolve_import_catalog_entry(existing, user_id: int, title, artist):
    """Bind an incoming Rekordbox track to a catalog row, honouring scope.

    ``existing`` is the row matched on ``normalized_key`` (globally UNIQUE, so at
    most one) or ``None``. Returns the row the importer's ``user_track`` should
    point at — or ``None`` when the caller must create a fresh ``private`` row
    owned by ``user_id``. Kept free of any session so the sync import worker and
    the async test suite share one decision.

    Rules:

    * no match           -> ``None`` (caller creates a private row, owner = importer)
    * ``shared`` match     -> reuse as-is; a shared canonical row is never mutated
      by an import
    * own ``private``      -> reuse and refresh its title/artist
    * foreign ``private``  -> reuse as-is, WITHOUT any mutation

    ``normalized_key`` is globally UNIQUE, so two users cannot each hold a private
    row for the same track: we cannot "separate" the importer onto a second
    private row. We also never mutate another user's row — not scope, not
    ``owner_id``, not title/artist: promoting it would leak A's private track to
    guests and every other user. The importer's blindness is fixed at the read
    layer instead — :func:`catalog_visible` grants sight of any row the viewer
    holds a ``user_track`` for, so the importer sees the track through their own
    ``user_track`` while the row stays ``private`` and owned by A. This honours
    "err toward separation": the foreign row is left completely untouched.
    """
    if existing is None:
        return None

    if existing.scope == "shared":
        return existing  # shared canonical row: never mutated by an import

    # existing.scope == "private"
    if existing.owner_id != user_id:
        # Another user's private row. Never mutate it (no promotion, no field
        # write) — that would leak their track. The importer sees it through
        # their own user_track via catalog_visible's user_track clause.
        return existing

    # The importer's own private row: refresh its title/artist.
    existing.title = title or existing.title
    existing.artist = artist or existing.artist
    return existing


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
        UserOpinion,
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
    # Canonical opinions: covers tracks outside the library (no user_tracks row)
    uo_sub = (
        select(
            UserOpinion.entity_key,
            UserOpinion.opinion,
        )
        .where(UserOpinion.user_id == user_id, UserOpinion.entity_type == "track")
        .subquery()
    )
    avis_col = func.coalesce(uo_sub.c.opinion, ut_sub.c.ut_avis)
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
        avis_col.label("avis"),
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
        .outerjoin(uo_sub, uo_sub.c.entity_key == cast(CatalogEntry.id, String))
        .outerjoin(trend_sub, CatalogEntry.id == trend_sub.c.catalog_id)
        .where(catalog_visible(user_id))
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
        query = query.where(avis_col == avis)

    await ensure_pillar_cache(db)

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
            *[(first_genre == g, pillar_rank.get(p, 6)) for g, (p, _d) in pillar_map().items()],
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
        sort_col = func.coalesce(avis_col, "")
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
        row_avis = row[9]
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
                has_artwork=ut_has_artwork if ut_has_artwork else entry.has_artwork,
                lib_track_id=None,
                has_preview=entry.has_preview,
                created_at=entry.created_at,
                in_lib=is_in_lib,
                nb_radar_playlists=nb_playlists or 0,
                nb_radar_sets=nb_sets or 0,
                style=lib_style,
                rating=ut_rating,
                avis=row_avis,
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
        UserOpinion,
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

    result = await db.execute(
        select(CatalogEntry).where(
            CatalogEntry.id == catalog_id, catalog_visible(user_id)
        )
    )
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

    # Canonical opinion (covers tracks outside the library); fall back to
    # the denormalized user_tracks.avis for consistency with list_catalog.
    avis = None
    if user_id is not None:
        op_result = await db.execute(
            select(UserOpinion)
            .where(
                UserOpinion.user_id == user_id,
                UserOpinion.entity_type == "track",
                UserOpinion.entity_key == str(catalog_id),
            )
            .limit(1)
        )
        op = op_result.scalar_one_or_none()
        avis = op.opinion if op else (ut.avis if ut else None)
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
                CatalogEntry.has_preview,
                sa_ut_sub.c.catalog_id.label("sa_ut_cid"),
                sa_ut_sub.c.rating,
            )
            .outerjoin(sa_ut_sub, CatalogEntry.id == sa_ut_sub.c.catalog_id)
            .where(CatalogEntry.id.in_(select(shared_catalog_ids.c.catalog_id)))
            .where(catalog_visible(user_id))
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
                has_preview=r[7],
                in_lib=r[8] is not None,
                rating=r[9],
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
        has_artwork=ut.has_artwork if ut and ut.has_artwork else entry.has_artwork,
        has_preview=entry.has_preview,
        created_at=entry.created_at,
        in_lib=in_lib,
        nb_radar_playlists=len(radar_appearances),
        nb_radar_sets=len(set_appearances),
        style=lib_style,
        rating=ut_rating,
        avis=avis,
        artist_id=entry_artist_id,
        artists=entry_artists,
        lib_track_id=ut.rekordbox_id if ut else None,
        radar_appearances=radar_appearances,
        set_appearances=set_appearances,
        same_artist_tracks=same_artist,
        tags=ut_tags,
    )


async def get_preview_url(db: AsyncSession, catalog_id: int, user_id: int | None) -> dict:
    from models import CatalogEntry, RadarTrack

    # Visibility guard: a private entry owned by someone else is "not found".
    vis = await db.execute(
        select(CatalogEntry.id).where(
            CatalogEntry.id == catalog_id, catalog_visible(user_id)
        )
    )
    if not vis.scalar_one_or_none():
        raise LookupError("Catalog entry not found")

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

    from services.opinion_sync import sync_track_opinion

    # Verify catalog entry exists and is visible to this user
    cat = await db.execute(
        select(CatalogEntry.id).where(
            CatalogEntry.id == catalog_id, catalog_visible(user_id)
        )
    )
    if not cat.scalar_one_or_none():
        raise LookupError("Catalog entry not found")

    # Update avis on existing UserTrack if present (don't create one)
    result = await db.execute(
        select(UserTrack).where(
            UserTrack.user_id == user_id, UserTrack.catalog_id == catalog_id
        )
    )
    ut = result.scalar_one_or_none()
    if ut:
        ut.avis = avis

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


async def get_or_create_catalog(
    db: AsyncSession,
    title: str,
    artist: str | None,
    isrc: str | None = None,
    duration_ms: int | None = None,
    genres: list[str] | None = None,
    release_date=None,
):
    """Find a catalog entry by ISRC or normalized_key, or create it (flushed, not committed)."""
    from models import CatalogEntry
    from utils import make_normalized_key

    # 1. Cherche par ISRC si dispo
    if isrc:
        result = await db.execute(select(CatalogEntry).where(CatalogEntry.isrc == isrc))
        entry = result.scalar_one_or_none()
        if entry:
            return entry

    # 2. Cherche par normalized_key
    norm_key = make_normalized_key(title, artist)
    result = await db.execute(
        select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
    )
    entry = result.scalar_one_or_none()
    if entry:
        # Met à jour l'ISRC si on l'a maintenant et qu'il manquait
        if isrc and not entry.isrc:
            entry.isrc = isrc
        return entry

    # 3. Crée une nouvelle entrée
    new = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=norm_key,
        isrc=isrc or None,
        duration_ms=duration_ms,
        genres=genres or [],
        release_date=release_date,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new)
    await db.flush()
    return new


# ── Manual import (POST /catalog/import) ──────────────────────────────────────

# Deezer contributor role → CatalogArtist role (mirrors deezer_enrich._DEEZER_ROLE_MAP)
_DEEZER_ROLE_MAP = {"Main": "primary", "Featured": "featured"}


def _parse_release_date(value):
    """Parse Deezer's 'YYYY-MM-DD' release_date into a date, or None."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def _fetch_deezer_track(deezer_id: str) -> dict:
    """Fetch a Deezer track's full detail. Raises LookupError if it doesn't exist.

    Deezer answers an unknown id with HTTP 200 + an {"error": ...} body, so the
    payload must be inspected, not just the status code.
    """
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(f"{DEEZER_API}/track/{deezer_id}")
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict) or data.get("error"):
        raise LookupError("Track not found on Deezer")

    artist = data.get("artist") if isinstance(data.get("artist"), dict) else None
    album = data.get("album") if isinstance(data.get("album"), dict) else None
    duration = data.get("duration")
    cover = None
    if album:
        cover = (
            album.get("cover_xl")
            or album.get("cover_big")
            or album.get("cover_medium")
        )
    return {
        "deezer_id": str(data.get("id") or deezer_id),
        "title": data.get("title", ""),
        "artist": artist.get("name") if artist else None,
        "artists": [],
        "isrc": data.get("isrc") or None,
        "duration_ms": (duration or 0) * 1000 or None,
        "cover_url": cover,
        "release_date": _parse_release_date(data.get("release_date")),
        "preview": (data.get("preview") or "").strip() or None,
        "contributors": data.get("contributors") or [],
    }


async def _fetch_tidal_track(tidal_id: str) -> dict:
    """Fetch a TIDAL track's detail off the event loop (tidalapi is blocking)."""
    from workers import source_clients

    return await run_in_threadpool(source_clients.fetch_tidal_track, tidal_id)


async def _resolve_or_create_artist_async(db, name: str, deezer_id: str | None = None):
    """Async twin of deezer_enrich._resolve_or_create_artist.

    Lookup order — deezer_id FIRST (this is what keeps us from violating the
    partial-unique uq_artists_deezer_id), then normalized_name, then alias, then
    create (with deezer_id only when supplied).
    """
    from models import Artist, ArtistAlias
    from utils import normalize

    if deezer_id:
        result = await db.execute(select(Artist).where(Artist.deezer_id == deezer_id))
        artist = result.scalar_one_or_none()
        if artist:
            return artist

    norm = normalize(name)
    result = await db.execute(
        select(Artist).where(Artist.normalized_name == norm)
    )
    artist = result.scalar_one_or_none()

    if not artist:
        result = await db.execute(
            select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
        )
        alias = result.scalar_one_or_none()
        if alias:
            artist = await db.get(Artist, alias.artist_id)

    if not artist:
        artist = Artist(
            name=name,
            normalized_name=norm,
            created_at=datetime.now(timezone.utc),
        )
        if deezer_id:
            artist.deezer_id = deezer_id
        db.add(artist)
        await db.flush()

    return artist


async def _link_artist_async(
    db, catalog_id: int, artist_id: int, role: str, position: int
):
    """Insert a CatalogArtist link if it doesn't already exist (async)."""
    from models import CatalogArtist

    result = await db.execute(
        select(CatalogArtist).where(
            CatalogArtist.catalog_id == catalog_id,
            CatalogArtist.artist_id == artist_id,
        )
    )
    if not result.scalar_one_or_none():
        db.add(
            CatalogArtist(
                catalog_id=catalog_id,
                artist_id=artist_id,
                role=role,
                position=position,
            )
        )


async def import_external(db: AsyncSession, *, deezer_id=None, tidal_id=None):
    """Import a track from an external source into the shared catalog.

    Dedups by ISRC then normalized_key: an already-present track is returned as-is
    (created=False) without re-enriching or downgrading it. A newly created entry
    is enriched (scope, deezer_id, artwork, preview) and gets its artist links.
    Raises ValueError (bad input) or LookupError (track absent on the source).
    """
    from models import CatalogEntry
    from schemas import CatalogImportOut
    from utils import make_normalized_key

    if bool(deezer_id) == bool(tidal_id):
        raise ValueError("Provide exactly one of deezer_id or tidal_id")

    detail = (
        await _fetch_deezer_track(deezer_id)
        if deezer_id
        else await _fetch_tidal_track(tidal_id)
    )

    title = detail["title"]
    artist = detail.get("artist")
    isrc = detail.get("isrc")

    # Determine existence BEFORE create so `created` is accurate. Mirrors the
    # get_or_create_catalog lookup order (ISRC first, then normalized_key).
    existing = None
    if isrc:
        result = await db.execute(
            select(CatalogEntry).where(CatalogEntry.isrc == isrc)
        )
        existing = result.scalar_one_or_none()
    if not existing:
        norm_key = make_normalized_key(title, artist)
        result = await db.execute(
            select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
        )
        existing = result.scalar_one_or_none()

    if existing:
        # Never re-enrich or downgrade an entry that already exists.
        return CatalogImportOut(
            catalog_id=existing.id,
            created=False,
            title=existing.title,
            artist=existing.artist,
        )

    entry = await get_or_create_catalog(
        db,
        title,
        artist,
        isrc=isrc,
        duration_ms=detail.get("duration_ms"),
        release_date=detail.get("release_date"),
    )

    entry.scope = "shared"
    entry.owner_id = None
    if deezer_id:
        entry.deezer_id = detail.get("deezer_id") or str(deezer_id)
    if detail.get("preview"):
        entry.has_preview = True

    # Artwork upload is best-effort — a failure must never abort the import.
    cover_url = detail.get("cover_url")
    if cover_url:
        try:
            from services.image_service import BUCKET_CATALOG, ImageService

            await run_in_threadpool(ImageService.ensure_bucket, BUCKET_CATALOG)
            if await run_in_threadpool(
                ImageService.upload_from_url,
                cover_url,
                BUCKET_CATALOG,
                f"{entry.id}.jpg",
            ):
                entry.has_artwork = True
        except Exception:
            logger.warning(
                "catalog artwork upload failed for %s", entry.id, exc_info=True
            )

    # Link artists: Deezer contributors carry roles/positions; TIDAL (and Deezer
    # tracks with no contributor list) fall back to a plain artist-name list.
    contributors = detail.get("contributors") or []
    if contributors:
        seen_ids = set()
        for position, contrib in enumerate(contributors):
            name = contrib.get("name")
            dz_id = str(contrib["id"]) if contrib.get("id") else None
            if not name or (dz_id and dz_id in seen_ids):
                continue
            if dz_id:
                seen_ids.add(dz_id)
            art = await _resolve_or_create_artist_async(db, name, dz_id)
            role = _DEEZER_ROLE_MAP.get(contrib.get("role", ""), "primary")
            await _link_artist_async(db, entry.id, art.id, role, position)
    else:
        # TIDAL fallback: no deezer_id available on this path — resolve by name
        # only. Passing the TIDAL artist id as deezer_id would corrupt the
        # enrichment lookup and could violate uq_artists_deezer_id.
        for position, a in enumerate(detail.get("artists") or []):
            name = a.get("name")
            if not name:
                continue
            art = await _resolve_or_create_artist_async(db, name, None)
            await _link_artist_async(db, entry.id, art.id, "primary", position)

    await db.commit()
    return CatalogImportOut(
        catalog_id=entry.id,
        created=True,
        title=entry.title,
        artist=entry.artist,
    )
