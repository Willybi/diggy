from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import Artist, ArtistAlias, CatalogEntry, UserTrack, DJSet, SetArtist, SetTrack
from schemas import (
    ArtistDetailOut, ArtistAliasOut, ArtistListOut, GenreOut,
    CatalogEntryOut, ArtistSetOut,
)

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("/", response_model=list[ArtistListOut])
async def list_artists(
    q: str | None = None,
    no_deezer: bool = False,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    from models import Genre, artist_genres
    from sqlalchemy import Float, case as sa_case

    lib_sub = (
        select(UserTrack.catalog_id, UserTrack.rating)
        .subquery()
    )

    cat_sub = (
        select(
            CatalogEntry.artist.label("artist_name"),
            func.count(CatalogEntry.id).label("nb_catalog"),
            func.count(lib_sub.c.catalog_id).label("nb_lib"),
            func.avg(lib_sub.c.rating.cast(Float)).label("avg_rating"),
        )
        .outerjoin(lib_sub, CatalogEntry.id == lib_sub.c.catalog_id)
        .group_by(CatalogEntry.artist)
        .subquery()
    )

    q_artists = (
        select(Artist)
        .options(selectinload(Artist.aliases), selectinload(Artist.genres))
        .order_by(func.lower(Artist.name))
        .limit(limit)
    )
    if q:
        pattern = f"%{q}%"
        q_artists = q_artists.where(Artist.name.ilike(pattern))
    if no_deezer:
        q_artists = q_artists.where(Artist.deezer_id.is_(None))

    result = await db.execute(q_artists)
    artists = result.scalars().all()

    # Build name → stats map
    all_names: set[str] = set()
    for a in artists:
        all_names.add(a.name.lower())
        for alias in a.aliases:
            all_names.add(alias.alias.lower())

    stats_result = await db.execute(
        select(cat_sub).where(func.lower(cat_sub.c.artist_name).in_(all_names))
    )
    raw_stats = stats_result.all()

    # Group by normalized name → aggregate
    from collections import defaultdict
    stats_by_name: dict[str, dict] = defaultdict(lambda: {"nb_catalog": 0, "nb_lib": 0, "ratings": []})
    for row in raw_stats:
        key = row.artist_name.lower()
        stats_by_name[key]["nb_catalog"] += row.nb_catalog
        stats_by_name[key]["nb_lib"] += row.nb_lib
        if row.avg_rating:
            stats_by_name[key]["ratings"].append(float(row.avg_rating))

    out = []
    for a in artists:
        agg = {"nb_catalog": 0, "nb_lib": 0, "ratings": []}
        for key in [a.name.lower()] + [al.alias.lower() for al in a.aliases]:
            s = stats_by_name.get(key)
            if s:
                agg["nb_catalog"] += s["nb_catalog"]
                agg["nb_lib"] += s["nb_lib"]
                agg["ratings"].extend(s["ratings"])
        avg = round(sum(agg["ratings"]) / len(agg["ratings"]), 1) if agg["ratings"] else None
        out.append(ArtistListOut(
            id=a.id,
            name=a.name,
            real_name=a.real_name,
            country=a.country,
            has_artwork=a.has_artwork,
            nb_catalog=agg["nb_catalog"],
            nb_lib=agg["nb_lib"],
            avg_rating=avg,
            genres=[g.name for g in a.genres],
        ))
    return out


@router.get("/{artist_id}", response_model=ArtistDetailOut)
async def get_artist_detail(artist_id: int, db: AsyncSession = Depends(get_db)):
    # 1. Artist + aliases + genres
    result = await db.execute(
        select(Artist)
        .options(selectinload(Artist.aliases), selectinload(Artist.genres))
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
        .order_by(lib_sub.c.rating.desc().nullslast(), CatalogEntry.title)
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
            genre=entry.genre,
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
        .order_by(DJSet.played_date.desc().nullslast())
    )
    sets = [
        ArtistSetOut(
            set_id=r[0], title=r[1], played_date=r[2], has_artwork=r[3],
            role=r[4], total_tracks=r[5], identified_tracks=r[6],
        )
        for r in sets_result.all()
    ]

    # 4. Stats
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

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
        genres=[GenreOut.model_validate(g) for g in artist.genres],
        catalog_tracks=catalog_tracks,
        sets=sets,
        stats={
            "nb_catalog": len(catalog_tracks),
            "nb_lib": nb_lib,
            "nb_sets": len(sets),
            "avg_rating": avg_rating,
        },
    )
