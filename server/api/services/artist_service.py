"""
Artist service: list, detail, random track, Deezer linking, flag resolution,
Beatport reset/enrich.

Services raise LookupError (404) or ValueError (400/409), never HTTPException.
"""

from collections import defaultdict

from sqlalchemy import Float, Numeric, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.genre_service import (
    _ALL_PILLARS,
    _ensure_pillar_cache,
    genre_pillar,
)


async def _ensure_alias(db: AsyncSession, artist_id: int, alias_name: str) -> None:
    """Create an ArtistAlias if it doesn't exist yet (by normalized_alias)."""
    from models import ArtistAlias
    from utils import normalize

    norm = normalize(alias_name)
    if not norm:
        return
    existing = await db.execute(
        select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
    )
    if existing.scalar_one_or_none():
        return
    db.add(ArtistAlias(artist_id=artist_id, alias=alias_name, normalized_alias=norm))


async def list_artists(
    db: AsyncSession,
    user_id: int,
    sort: str,
    family: str | None,
    q: str | None,
    no_deezer: bool,
    ids: str | None,
    limit: int,
    offset: int,
) -> dict:
    from models import Artist, CatalogArtist, CatalogEntry, UserRadarState, UserTrack

    await _ensure_pillar_cache(db)
    empty = {"items": [], "total": 0, "pillarCounts": {p: 0 for p in _ALL_PILLARS}}

    lib_sub = (
        select(UserTrack.catalog_id, UserTrack.rating)
        .where(UserTrack.user_id == user_id)
        .subquery()
    )
    stats_sub = (
        select(
            CatalogArtist.artist_id,
            func.count(func.distinct(CatalogArtist.catalog_id)).label("nb_catalog"),
            func.count(func.distinct(lib_sub.c.catalog_id)).label("nb_lib"),
            func.avg(lib_sub.c.rating.cast(Float)).label("avg_rating"),
        )
        .outerjoin(lib_sub, CatalogArtist.catalog_id == lib_sub.c.catalog_id)
        .group_by(CatalogArtist.artist_id)
        .subquery()
    )
    liked_sub = (
        select(
            CatalogArtist.artist_id,
            func.count(func.distinct(UserRadarState.catalog_id)).label("nb_liked"),
        )
        .join(UserRadarState, UserRadarState.catalog_id == CatalogArtist.catalog_id)
        .where(UserRadarState.status == "added", UserRadarState.user_id == user_id)
        .group_by(CatalogArtist.artist_id)
        .subquery()
    )

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

    id_filter_query = select(Artist.id)
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
        if not id_list:
            return empty
        base_query = base_query.where(Artist.id.in_(id_list))
        id_filter_query = id_filter_query.where(Artist.id.in_(id_list))
    if q:
        base_query = base_query.where(Artist.name.ilike(f"%{q}%"))
        id_filter_query = id_filter_query.where(Artist.name.ilike(f"%{q}%"))
    if no_deezer:
        base_query = base_query.where(Artist.deezer_id.is_(None))
        id_filter_query = id_filter_query.where(Artist.deezer_id.is_(None))

    all_ids_result = await db.execute(id_filter_query)
    all_artist_ids = [r[0] for r in all_ids_result.all()]
    if not all_artist_ids:
        return empty

    # Genres per artist via catalog_artists
    genre_col = func.unnest(CatalogEntry.genres).label("genre")
    genre_result = await db.execute(
        select(CatalogArtist.artist_id, genre_col, func.count().label("cnt"))
        .join(CatalogEntry, CatalogEntry.id == CatalogArtist.catalog_id)
        .where(
            func.coalesce(func.array_length(CatalogEntry.genres, 1), 0) > 0,
            CatalogArtist.artist_id.in_(all_artist_ids),
        )
        .group_by(CatalogArtist.artist_id, genre_col)
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
        return sorted([g for g, c in gc.items() if c >= threshold], key=lambda g: -gc[g])

    def _artist_pillar_key(artist_id: int) -> str:
        genres = _artist_genres(artist_id)
        return genre_pillar(genres[0])[0] if genres else "autres"

    pillar_counts: dict[str, int] = {p: 0 for p in _ALL_PILLARS}
    pillar_by_id: dict[int, str] = {}
    for aid in all_artist_ids:
        pil = _artist_pillar_key(aid)
        pillar_by_id[aid] = pil
        pillar_counts[pil] += 1

    if family and family in _ALL_PILLARS:
        filtered_ids = {aid for aid, pil in pillar_by_id.items() if pil == family}
        base_query = base_query.where(Artist.id.in_(filtered_ids))

    if sort == "catalog":
        base_query = base_query.order_by(nb_catalog_col.desc())
    elif sort == "lib":
        base_query = base_query.order_by(nb_lib_col.desc(), nb_catalog_col.desc())
    elif sort == "liked":
        base_query = base_query.order_by(nb_liked_col.desc(), nb_catalog_col.desc())
    elif sort == "disliked":
        base_query = base_query.order_by(func.lower(Artist.name))
    elif sort == "rating":
        base_query = base_query.order_by(
            func.coalesce(stats_sub.c.avg_rating, -1).desc()
        )
    elif sort == "alpha":
        base_query = base_query.order_by(func.lower(Artist.name))

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar()

    result = await db.execute(base_query.offset(offset).limit(limit))
    rows = result.all()

    page_ids = [row.id for row in rows]
    artworks_map: dict[int, list[str]] = {aid: [] for aid in page_ids}
    artwork_count_map: dict[int, int] = {aid: 0 for aid in page_ids}
    if page_ids:
        try:
            aw_result = await db.execute(
                text("""
                WITH matched AS (
                    SELECT ca.artist_id, c.id AS catalog_id,
                           ROW_NUMBER() OVER (PARTITION BY ca.artist_id ORDER BY c.id DESC) AS rn
                    FROM catalog_artists ca
                    JOIN catalog c ON c.id = ca.catalog_id
                    WHERE ca.artist_id = ANY(:ids)
                      AND c.has_artwork = true
                )
                SELECT artist_id,
                       COUNT(*)::int AS total_with_artwork,
                       ARRAY_AGG(catalog_id ORDER BY rn) FILTER (WHERE rn <= 4) AS top_ids
                FROM matched
                GROUP BY artist_id
            """),
                {"ids": page_ids},
            )
            for r in aw_result.fetchall():
                artwork_count_map[r.artist_id] = r.total_with_artwork
                artworks_map[r.artist_id] = [
                    f"/storage/catalog-artworks/{cid}.jpg" for cid in (r.top_ids or [])
                ]
        except Exception:
            await db.rollback()

    items = []
    for row in rows:
        items.append(
            {
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
            }
        )

    return {"items": items, "total": total, "pillarCounts": pillar_counts}


async def get_detail(db: AsyncSession, artist_id: int) -> dict:
    import json

    from models import (
        Artist,
        CatalogArtist,
        CatalogEntry,
        DJSet,
        SetArtist,
        SetTrack,
        UserTrack,
    )
    from schemas import (
        ArtistAliasOut,
        ArtistDetailOut,
        ArtistSetOut,
        CatalogEntryOut,
        GenreRef,
    )

    await _ensure_pillar_cache(db)

    result = await db.execute(
        select(Artist).options(selectinload(Artist.aliases)).where(Artist.id == artist_id)
    )
    artist = result.scalar_one_or_none()
    if not artist:
        raise LookupError("Artist not found")

    lib_sub = select(
        UserTrack.catalog_id,
        UserTrack.rating,
        UserTrack.rb_mytags.label("tags"),
        UserTrack.rb_bpm.label("bpm"),
        UserTrack.rb_key.label("key"),
    ).subquery()

    cat_result = await db.execute(
        select(
            CatalogEntry,
            lib_sub.c.catalog_id.label("lib_cid"),
            lib_sub.c.rating.label("lib_rating"),
            lib_sub.c.tags.label("lib_tags"),
            lib_sub.c.bpm.label("lib_bpm"),
            lib_sub.c.key.label("lib_key"),
        )
        .join(CatalogArtist, CatalogArtist.catalog_id == CatalogEntry.id)
        .outerjoin(lib_sub, CatalogEntry.id == lib_sub.c.catalog_id)
        .where(CatalogArtist.artist_id == artist_id)
        .order_by(lib_sub.c.rating.desc().nulls_last(), CatalogEntry.title)
        .limit(50)
    )
    cat_rows = cat_result.all()

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

        catalog_tracks.append(
            CatalogEntryOut(
                id=entry.id,
                title=entry.title,
                artist=entry.artist,
                isrc=entry.isrc,
                bpm=lib_bpm if lib_bpm else entry.bpm,
                key=lib_key if lib_key else entry.key,
                duration_ms=entry.duration_ms,
                genres=[
                    GenreRef(name=g, pillar=genre_pillar(g)[0], depth=genre_pillar(g)[1])
                    for g in (entry.genres or [])
                ],
                release_date=entry.release_date,
                preview_url=entry.preview_url,
                has_artwork=entry.has_artwork,
                has_preview=entry.has_preview,
                created_at=entry.created_at,
                in_lib=is_in_lib,
                style=lib_style,
                rating=rating,
            )
        )

    sets_result = await db.execute(
        select(
            DJSet.id,
            DJSet.title,
            DJSet.played_date,
            DJSet.has_artwork,
            SetArtist.role,
            func.count(SetTrack.id).label("total_tracks"),
            func.count(SetTrack.catalog_id)
            .filter(SetTrack.is_id.is_(False))
            .label("identified_tracks"),
        )
        .join(DJSet, DJSet.id == SetArtist.set_id)
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        .where(SetArtist.artist_id == artist_id)
        .group_by(
            DJSet.id, DJSet.title, DJSet.played_date, DJSet.has_artwork, SetArtist.role
        )
        .order_by(DJSet.played_date.desc().nulls_last())
    )
    sets = [
        ArtistSetOut(
            set_id=r[0],
            title=r[1],
            played_date=r[2],
            has_artwork=r[3],
            role=r[4],
            total_tracks=r[5],
            identified_tracks=r[6],
        )
        for r in sets_result.all()
    ]

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    genre_counts: dict[str, int] = {}
    for row in cat_rows:
        for g in row[0].genres or []:
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
        genres=[
            GenreRef(name=g, pillar=genre_pillar(g)[0], depth=genre_pillar(g)[1])
            for g in computed_genres
        ],
        catalog_tracks=catalog_tracks,
        sets=sets,
        stats={
            "nb_catalog": len(catalog_tracks),
            "nb_lib": nb_lib,
            "nb_sets": len(sets),
            "avg_rating": avg_rating,
        },
    )


async def random_track(db: AsyncSession, artist_id: int, exclude_id: int | None) -> dict:
    result = await db.execute(
        text("""
        SELECT c.id, c.title, c.artist, c.bpm, c.key FROM catalog c
        JOIN catalog_artists ca ON ca.catalog_id = c.id
        WHERE ca.artist_id = :artist_id
          AND c.has_preview = true
          AND (:has_exclude = false OR c.id != :exclude_id)
        ORDER BY random()
        LIMIT 1
    """),
        {
            "artist_id": artist_id,
            "has_exclude": exclude_id is not None,
            "exclude_id": exclude_id or 0,
        },
    )
    row = result.fetchone()
    if not row:
        raise LookupError("No previewable track for this artist")
    return {
        "catalog_id": row.id,
        "title": row.title,
        "artist": row.artist,
        "bpm": row.bpm,
        "key": row.key,
    }


async def link_to_deezer(
    db: AsyncSession, artist_id: int, deezer_id: str
) -> dict:
    """Manually link a deezer_id to an artist (fetch name + artwork, merge if duplicate)."""
    import requests as req
    from models import Artist, SetArtist
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import update as sa_update
    from utils import normalize

    from services.image_service import BUCKET_ARTIST, ImageService

    result = await db.execute(select(Artist).where(Artist.id == artist_id))
    artist = result.scalar_one_or_none()
    if not artist:
        raise LookupError("Artist not found")

    # Unlink
    if not deezer_id:
        artist.deezer_id = None
        await db.commit()
        await db.refresh(artist)
        return {"id": artist.id, "name": artist.name, "deezer_id": None, "has_artwork": artist.has_artwork, "merged": False}

    # Fetch Deezer data
    deezer_name = None
    pic_url = None
    try:
        resp = req.get(f"https://api.deezer.com/artist/{deezer_id}", timeout=5)
        data = resp.json()
        deezer_name = data.get("name")
        pic_url = data.get("picture_xl") or data.get("picture_big") or data.get("picture")
    except Exception:
        pass

    # Check if another artist already owns this deezer_id → merge
    existing_result = await db.execute(
        select(Artist).where(Artist.deezer_id == deezer_id, Artist.id != artist_id)
    )
    canonical = existing_result.scalar_one_or_none()

    if canonical:
        old_name = artist.name
        if normalize(old_name) != normalize(canonical.name):
            await _ensure_alias(db, canonical.id, old_name)
        conflict_sets = await db.execute(
            select(SetArtist.set_id).where(SetArtist.artist_id == canonical.id)
        )
        conflict_set_ids = {r[0] for r in conflict_sets.all()}
        if conflict_set_ids:
            await db.execute(
                sa_delete(SetArtist).where(
                    SetArtist.artist_id == artist_id,
                    SetArtist.set_id.in_(conflict_set_ids),
                )
            )
        await db.execute(
            sa_update(SetArtist)
            .where(SetArtist.artist_id == artist_id)
            .values(artist_id=canonical.id)
            .execution_options(synchronize_session=False)
        )
        await db.delete(artist)
        await db.flush()
        if pic_url and not canonical.has_artwork:
            if ImageService.upload_from_url(pic_url, BUCKET_ARTIST, f"{canonical.id}.jpg"):
                canonical.has_artwork = True
        await db.commit()
        await db.refresh(canonical)
        return {
            "id": canonical.id,
            "name": canonical.name,
            "deezer_id": canonical.deezer_id,
            "has_artwork": canonical.has_artwork,
            "merged": True,
            "merged_id": artist_id,
            "merged_name": old_name,
        }

    # No duplicate — update this artist
    old_name = artist.name
    artist.deezer_id = deezer_id
    if deezer_name and normalize(deezer_name) != normalize(old_name):
        await _ensure_alias(db, artist.id, old_name)
        artist.name = deezer_name

    if pic_url:
        try:
            if ImageService.upload_from_url(pic_url, BUCKET_ARTIST, f"{artist.id}.jpg"):
                artist.has_artwork = True
        except Exception:
            pass

    await db.commit()
    await db.refresh(artist)
    return {
        "id": artist.id,
        "name": artist.name,
        "deezer_id": artist.deezer_id,
        "has_artwork": artist.has_artwork,
        "merged": False,
    }


async def resolve_flag(db: AsyncSession, flag_id: int, action: str) -> object:
    """Resolve an artist flag (split/keep/skip). Returns the ArtistFlag ORM object."""
    from datetime import datetime, timezone

    from models import ArtistFlag, CatalogArtist, CatalogEntry

    result = await db.execute(select(ArtistFlag).where(ArtistFlag.id == flag_id))
    flag = result.scalar_one_or_none()
    if not flag:
        raise LookupError("Flag not found")
    if flag.status != "pending":
        raise ValueError("Flag already resolved")

    if action == "skip":
        flag.status = "skipped"
        flag.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(flag)
        return flag

    from trackid.importer import get_or_create_artist

    names_to_create = flag.tokens if action == "split" else [flag.raw_artist_string]
    deezer_map = flag.deezer_ids or {}

    created_ids = []
    for name in names_to_create:
        artist = await get_or_create_artist(db, name)
        if not artist.deezer_id and deezer_map.get(name):
            artist.deezer_id = deezer_map[name]
        created_ids.append(artist.id)

    flag.status = "validated"
    flag.resolved_artist_ids = created_ids
    flag.updated_at = datetime.now(timezone.utc)

    cat_entries = await db.execute(
        select(CatalogEntry.id).where(CatalogEntry.artist == flag.raw_artist_string)
    )
    for (cat_id,) in cat_entries.all():
        for pos, artist_id in enumerate(created_ids):
            existing_link = await db.execute(
                select(CatalogArtist).where(
                    CatalogArtist.catalog_id == cat_id,
                    CatalogArtist.artist_id == artist_id,
                )
            )
            if not existing_link.scalar_one_or_none():
                db.add(
                    CatalogArtist(
                        catalog_id=cat_id,
                        artist_id=artist_id,
                        role="primary",
                        position=pos,
                    )
                )

    await db.commit()
    await db.refresh(flag)
    return flag


async def reset_beatport(db: AsyncSession) -> dict:
    """Reset all Beatport-sourced data."""
    from models import CatalogEntry

    r1 = await db.execute(
        update(CatalogEntry).values(beatport_id=None, beatport_searched_at=None)
    )
    r2 = await db.execute(
        update(CatalogEntry)
        .where(CatalogEntry.bpm_source == "beatport")
        .values(bpm=None, bpm_source=None)
    )
    r3 = await db.execute(
        update(CatalogEntry)
        .where(CatalogEntry.key_source == "beatport")
        .values(key=None, key_source=None)
    )
    await db.commit()
    return {
        "status": "reset",
        "cleared": r1.rowcount,
        "bpm_reverted": r2.rowcount,
        "key_reverted": r3.rowcount,
    }


async def enrich_single_beatport(
    db: AsyncSession, catalog_id: int, force_genre: bool = False
) -> dict:
    """Enrich a single catalog entry via Beatport (sync, ~3s)."""
    from beatport.client import BeatportClient
    from beatport.enrich import enrich_from_beatport
    from models import CatalogEntry

    entry = (
        await db.execute(select(CatalogEntry).where(CatalogEntry.id == catalog_id))
    ).scalar_one_or_none()
    if not entry:
        raise LookupError("Track not found")

    client = BeatportClient()
    bp_track = None

    if entry.isrc:
        bp_track = client.search_track_by_isrc(entry.isrc)
    if not bp_track and entry.title:
        bp_track = client.search_track_validated(entry.title, entry.artist)

    if not bp_track:
        if force_genre and entry.genres:
            entry.genres = []
            await db.commit()
        return {"status": "not_found", "catalog_id": catalog_id, "genres": entry.genres}

    if force_genre:
        entry.genres = []

    changed = enrich_from_beatport(entry, bp_track)
    if force_genre or changed:
        await db.commit()

    return {
        "status": "enriched" if changed else "unchanged",
        "catalog_id": catalog_id,
        "bpm": entry.bpm,
        "key": entry.key,
        "label": entry.label,
        "genres": entry.genres or [],
        "beatport_id": entry.beatport_id,
    }
