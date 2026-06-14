from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import Artist, ArtistAlias, CatalogEntry, LibTrack, DJSet, SetArtist, SetTrack
from schemas import (
    ArtistDetailOut, ArtistAliasOut, GenreOut,
    CatalogEntryOut, ArtistSetOut,
)

router = APIRouter(prefix="/artists", tags=["artists"])


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

    # Build name match list (normalized + display name)
    names = [artist.normalized_name, artist.name.lower()]
    for a in artist.aliases:
        names.append(a.normalized_alias)
        names.append(a.alias.lower())

    # 2. Catalog tracks matching artist name or aliases
    name_filters = [func.lower(CatalogEntry.artist) == n for n in names]
    from sqlalchemy import or_

    lib_sub = (
        select(LibTrack.catalog_id, LibTrack.rating, LibTrack.tags, LibTrack.bpm, LibTrack.key, LibTrack.duration)
        .where(LibTrack.catalog_id.isnot(None))
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
            lib_sub.c.duration.label("lib_duration"),
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
        lib_duration = row[6]

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
            duration_ms=lib_duration if lib_duration else entry.duration_ms,
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
