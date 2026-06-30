from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, Numeric, func, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user_optional, uid as _uid
from models import (
    Artist, ArtistAlias, CatalogEntry, UserTrack,
    DJSet, SetArtist, SetTrack, User, UserRadarState,
)
from routers.genres import genre_pillar, _ALL_PILLARS, _ensure_pillar_cache
from schemas import (
    ArtistDetailOut, ArtistAliasOut, ArtistListOut,
    CatalogEntryOut, ArtistSetOut, GenreRef,
)

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("/")
async def list_artists(
    sort: str = Query("catalog", pattern="^(catalog|lib|liked|disliked|rating|alpha)$"),
    family: str | None = Query(None, max_length=100),
    q: str | None = Query(None, max_length=200),
    no_deezer: bool = False,
    ids: str | None = Query(None, max_length=500),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    user_id = _uid(user)
    await _ensure_pillar_cache(db)
    empty = {"items": [], "total": 0, "pillarCounts": {p: 0 for p in _ALL_PILLARS}}

    # -- name_map: artist_id -> all lowercase name variants --
    name_map = union_all(
        select(Artist.id.label("artist_id"), func.lower(Artist.name).label("artist_lower")),
        select(ArtistAlias.artist_id.label("artist_id"), func.lower(ArtistAlias.alias).label("artist_lower")),
    ).subquery("name_map")

    # -- stats per artist_id via SQL --
    lib_sub = (
        select(UserTrack.catalog_id, UserTrack.rating)
        .where(UserTrack.user_id == user_id)
        .subquery()
    )

    stats_sub = (
        select(
            name_map.c.artist_id,
            func.count(func.distinct(CatalogEntry.id)).label("nb_catalog"),
            func.count(func.distinct(lib_sub.c.catalog_id)).label("nb_lib"),
            func.avg(lib_sub.c.rating.cast(Float)).label("avg_rating"),
        )
        .join(CatalogEntry, func.lower(CatalogEntry.artist) == name_map.c.artist_lower)
        .outerjoin(lib_sub, CatalogEntry.id == lib_sub.c.catalog_id)
        .group_by(name_map.c.artist_id)
        .subquery()
    )

    liked_sub = (
        select(
            name_map.c.artist_id,
            func.count(func.distinct(UserRadarState.catalog_id)).label("nb_liked"),
        )
        .join(CatalogEntry, func.lower(CatalogEntry.artist) == name_map.c.artist_lower)
        .join(UserRadarState, UserRadarState.catalog_id == CatalogEntry.id)
        .where(UserRadarState.status == "added", UserRadarState.user_id == user_id)
        .group_by(name_map.c.artist_id)
        .subquery()
    )

    # -- main query: Artist + stats --
    nb_catalog_col = func.coalesce(stats_sub.c.nb_catalog, 0)
    nb_lib_col = func.coalesce(stats_sub.c.nb_lib, 0)
    nb_liked_col = func.coalesce(liked_sub.c.nb_liked, 0)
    avg_rating_col = func.round(stats_sub.c.avg_rating.cast(Numeric), 1)

    base_query = (
        select(
            Artist.id,
            Artist.name,
            Artist.real_name,
            Artist.country,
            Artist.has_artwork,
            nb_catalog_col.label("nb_catalog"),
            nb_lib_col.label("nb_lib"),
            nb_liked_col.label("nb_liked"),
            avg_rating_col.label("avg_rating"),
        )
        .outerjoin(stats_sub, Artist.id == stats_sub.c.artist_id)
        .outerjoin(liked_sub, Artist.id == liked_sub.c.artist_id)
    )

    # -- filters --
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
        if not id_list:
            return empty
        base_query = base_query.where(Artist.id.in_(id_list))
    if q:
        base_query = base_query.where(Artist.name.ilike(f"%{q}%"))
    if no_deezer:
        base_query = base_query.where(Artist.deezer_id.is_(None))

    # -- genres + family for all matching artists (lightweight: just IDs + genres) --
    # Get all matching artist IDs first
    id_filter_query = select(Artist.id)
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
        if id_list:
            id_filter_query = id_filter_query.where(Artist.id.in_(id_list))
    if q:
        id_filter_query = id_filter_query.where(Artist.name.ilike(f"%{q}%"))
    if no_deezer:
        id_filter_query = id_filter_query.where(Artist.deezer_id.is_(None))

    all_ids_result = await db.execute(id_filter_query)
    all_artist_ids = [r[0] for r in all_ids_result.all()]

    if not all_artist_ids:
        return empty

    # Fetch genres for all matching artists via name_map
    genre_col = func.unnest(CatalogEntry.genres).label("genre")
    genre_result = await db.execute(
        select(
            name_map.c.artist_id,
            genre_col,
            func.count().label("cnt"),
        )
        .join(CatalogEntry, func.lower(CatalogEntry.artist) == name_map.c.artist_lower)
        .where(
            func.coalesce(func.array_length(CatalogEntry.genres, 1), 0) > 0,
            name_map.c.artist_id.in_(all_artist_ids),
        )
        .group_by(name_map.c.artist_id, genre_col)
    )
    genre_by_artist: dict[int, dict[str, int]] = defaultdict(dict)
    total_genre_by_artist: dict[int, int] = defaultdict(int)
    for row in genre_result.all():
        genre_by_artist[row.artist_id][row.genre] = row.cnt
        total_genre_by_artist[row.artist_id] += row.cnt

    def _artist_genres(artist_id: int) -> list[str]:
        gc = genre_by_artist.get(artist_id, {})
        tot = total_genre_by_artist.get(artist_id, 0)
        threshold = max(1, int(tot * 0.2))
        return sorted(
            [g for g, c in gc.items() if c >= threshold],
            key=lambda g: -gc[g],
        )

    def _artist_pillar_key(artist_id: int) -> str:
        genres = _artist_genres(artist_id)
        return genre_pillar(genres[0])[0] if genres else "autres"

    # -- pillarCounts (all matching artists, before pillar filter) --
    pillar_counts: dict[str, int] = {p: 0 for p in _ALL_PILLARS}
    pillar_by_id: dict[int, str] = {}
    for aid in all_artist_ids:
        pil = _artist_pillar_key(aid)
        pillar_by_id[aid] = pil
        pillar_counts[pil] += 1

    # -- apply pillar filter --
    if family and family in _ALL_PILLARS:
        filtered_ids = {aid for aid, pil in pillar_by_id.items() if pil == family}
        base_query = base_query.where(Artist.id.in_(filtered_ids))

    # -- sort --
    if sort == "catalog":
        base_query = base_query.order_by(nb_catalog_col.desc())
    elif sort == "lib":
        base_query = base_query.order_by(nb_lib_col.desc(), nb_catalog_col.desc())
    elif sort == "liked":
        base_query = base_query.order_by(nb_liked_col.desc(), nb_catalog_col.desc())
    elif sort == "disliked":
        base_query = base_query.order_by(func.lower(Artist.name))
    elif sort == "rating":
        base_query = base_query.order_by(func.coalesce(stats_sub.c.avg_rating, -1).desc())
    elif sort == "alpha":
        base_query = base_query.order_by(func.lower(Artist.name))

    # -- count + paginate --
    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar()

    result = await db.execute(base_query.offset(offset).limit(limit))
    rows = result.all()

    # -- top 4 track artworks + artwork count per page artist (PG only) --
    page_ids = [row.id for row in rows]
    artworks_map: dict[int, list[str]] = {aid: [] for aid in page_ids}
    artwork_count_map: dict[int, int] = {aid: 0 for aid in page_ids}
    if page_ids:
        try:
            aw_result = await db.execute(text("""
                WITH artist_names AS (
                    SELECT id AS artist_id, LOWER(name) AS artist_lower FROM artists WHERE id = ANY(:ids)
                    UNION
                    SELECT artist_id, LOWER(alias) AS artist_lower FROM artist_aliases WHERE artist_id = ANY(:ids)
                ),
                matched AS (
                    SELECT an.artist_id, c.id AS catalog_id,
                           ROW_NUMBER() OVER (PARTITION BY an.artist_id ORDER BY c.id DESC) AS rn
                    FROM artist_names an
                    JOIN catalog c ON LOWER(c.artist) = an.artist_lower
                    WHERE c.has_artwork = true
                )
                SELECT artist_id,
                       COUNT(*)::int AS total_with_artwork,
                       ARRAY_AGG(catalog_id ORDER BY rn) FILTER (WHERE rn <= 4) AS top_ids
                FROM matched
                GROUP BY artist_id
            """), {"ids": page_ids})
            for r in aw_result.fetchall():
                artwork_count_map[r.artist_id] = r.total_with_artwork
                artworks_map[r.artist_id] = [
                    f"/storage/catalog-artworks/{cid}.jpg" for cid in (r.top_ids or [])
                ]
        except Exception:
            await db.rollback()

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "name": row.name,
            "real_name": row.real_name,
            "country": row.country,
            "has_artwork": row.has_artwork,
            "nb_catalog": row.nb_catalog,
            "nb_lib": row.nb_lib,
            "nb_liked": row.nb_liked,
            "avg_rating": float(row.avg_rating) if row.avg_rating is not None else None,
            "genres": [
                {"name": g, "pillar": genre_pillar(g)[0], "depth": genre_pillar(g)[1]}
                for g in _artist_genres(row.id)
            ],
            "top_track_artworks": artworks_map.get(row.id, []),
            "tracks_with_artwork": artwork_count_map.get(row.id, 0),
        })

    return {"items": items, "total": total, "pillarCounts": pillar_counts}


@router.get("/random-track")
async def random_artist_track(
    artist_id: int = Query(...),
    exclude: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return a random previewable catalog entry for the given artist."""
    # Collect artist name + aliases
    result = await db.execute(
        select(Artist).options(selectinload(Artist.aliases)).where(Artist.id == artist_id)
    )
    artist = result.scalar_one_or_none()
    if not artist:
        raise HTTPException(404, "Artist not found")

    names = [artist.name]
    for a in artist.aliases:
        names.append(a.alias)

    result = await db.execute(text("""
        SELECT id, title, artist, bpm, key FROM catalog
        WHERE LOWER(artist) = ANY(:names)
          AND has_preview = true
          AND (:has_exclude = false OR id != :exclude_id)
        ORDER BY random()
        LIMIT 1
    """), {
        "names": [n.lower() for n in names],
        "has_exclude": exclude is not None,
        "exclude_id": exclude or 0,
    })
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "No previewable track for this artist")
    return {
        "catalog_id": row.id,
        "title": row.title,
        "artist": row.artist,
        "bpm": row.bpm,
        "key": row.key,
    }


@router.get("/{artist_id}", response_model=ArtistDetailOut)
async def get_artist_detail(artist_id: int, db: AsyncSession = Depends(get_db)):
    await _ensure_pillar_cache(db)
    # 1. Artist + aliases + genres
    result = await db.execute(
        select(Artist)
        .options(selectinload(Artist.aliases))
        .where(Artist.id == artist_id)
    )
    artist = result.scalar_one_or_none()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Build name match list
    from sqlalchemy import or_

    # Exact lower-case matches (display names)
    lower_names = {artist.name.lower()}
    # Normalized matches (no spaces, no punctuation quirks)
    norm_names = {artist.normalized_name}
    for a in artist.aliases:
        lower_names.add(a.alias.lower())
        norm_names.add(a.normalized_alias)

    # 2. Catalog tracks matching artist name or aliases
    # Compare both LOWER(catalog.artist) and stripped version
    catalog_lower = func.lower(CatalogEntry.artist)
    catalog_norm = func.replace(catalog_lower, ' ', '')
    name_filters = (
        [catalog_lower == n for n in lower_names]
        + [catalog_norm == n for n in norm_names]
    )

    lib_sub = (
        select(
            UserTrack.catalog_id,
            UserTrack.rating,
            UserTrack.rb_mytags.label("tags"),
            UserTrack.rb_bpm.label("bpm"),
            UserTrack.rb_key.label("key"),
        )
        .subquery()
    )

    cat_result = await db.execute(
        select(
            CatalogEntry,
            lib_sub.c.catalog_id.label("lib_cid"),
            lib_sub.c.rating.label("lib_rating"),
            lib_sub.c.tags.label("lib_tags"),
            lib_sub.c.bpm.label("lib_bpm"),
            lib_sub.c.key.label("lib_key"),
        )
        .outerjoin(lib_sub, CatalogEntry.id == lib_sub.c.catalog_id)
        .where(or_(*name_filters))
        .order_by(lib_sub.c.rating.desc().nulls_last(), CatalogEntry.title)
        .limit(50)
    )
    cat_rows = cat_result.all()

    import json
    catalog_tracks = []
    nb_lib = 0
    ratings = []
    for row in cat_rows:
        entry = row[0]
        is_in_lib = row[1] is not None
        rating = row[2]
        lib_tags = row[3]
        lib_bpm = row[4]
        lib_key = row[5]

        if is_in_lib:
            nb_lib += 1
        if rating and rating > 0:
            ratings.append(rating)

        lib_style = None
        if lib_tags:
            try:
                tags = json.loads(lib_tags) if isinstance(lib_tags, str) else lib_tags
                lib_style = tags[0] if tags else None
            except Exception:
                pass

        catalog_tracks.append(CatalogEntryOut(
            id=entry.id,
            title=entry.title,
            artist=entry.artist,
            isrc=entry.isrc,
            bpm=lib_bpm if lib_bpm else entry.bpm,
            key=lib_key if lib_key else entry.key,
            duration_ms=entry.duration_ms,
            genres=[GenreRef(name=g, pillar=genre_pillar(g)[0], depth=genre_pillar(g)[1]) for g in (entry.genres or [])],
            release_date=entry.release_date,
            preview_url=entry.preview_url,
            has_artwork=entry.has_artwork,
            has_preview=entry.has_preview,
            created_at=entry.created_at,
            in_lib=is_in_lib,
            style=lib_style,
            rating=rating,
        ))

    # 3. Sets via set_artists
    sets_result = await db.execute(
        select(
            DJSet.id, DJSet.title, DJSet.played_date, DJSet.has_artwork,
            SetArtist.role,
            func.count(SetTrack.id).label("total_tracks"),
            func.count(SetTrack.catalog_id).filter(SetTrack.is_id == False).label("identified_tracks"),
        )
        .join(DJSet, DJSet.id == SetArtist.set_id)
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        .where(SetArtist.artist_id == artist_id)
        .group_by(DJSet.id, DJSet.title, DJSet.played_date, DJSet.has_artwork, SetArtist.role)
        .order_by(DJSet.played_date.desc().nulls_last())
    )
    sets = [
        ArtistSetOut(
            set_id=r[0], title=r[1], played_date=r[2], has_artwork=r[3],
            role=r[4], total_tracks=r[5], identified_tracks=r[6],
        )
        for r in sets_result.all()
    ]

    # 4. Stats + genres from catalog.genres
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    genre_counts: dict[str, int] = {}
    for row in cat_rows:
        for g in (row[0].genres or []):
            genre_counts[g] = genre_counts.get(g, 0) + 1
    total = len(cat_rows)
    threshold = max(1, int(total * 0.2))
    computed_genres = sorted([g for g, c in genre_counts.items() if c >= threshold])

    return ArtistDetailOut(
        id=artist.id,
        name=artist.name,
        normalized_name=artist.normalized_name,
        real_name=artist.real_name,
        country=artist.country,
        deezer_id=artist.deezer_id,
        soundcloud_id=artist.soundcloud_id,
        trackid_id=artist.trackid_id,
        bio=artist.bio,
        has_artwork=artist.has_artwork,
        created_at=artist.created_at,
        aliases=[ArtistAliasOut.model_validate(a) for a in artist.aliases],
        genres=[GenreRef(name=g, pillar=genre_pillar(g)[0], depth=genre_pillar(g)[1]) for g in computed_genres],
        catalog_tracks=catalog_tracks,
        sets=sets,
        stats={
            "nb_catalog": len(catalog_tracks),
            "nb_lib": nb_lib,
            "nb_sets": len(sets),
            "avg_rating": avg_rating,
        },
    )
