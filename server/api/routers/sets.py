from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import DJSet, SetTrack, SetArtist, Artist, CatalogEntry, LibTrack
from schemas import (
    DJSetDetailOut, SetTrackDetailOut, SetArtistDetailOut, GenreOut,
)

router = APIRouter(prefix="/sets", tags=["sets"])


@router.get("/{set_id}", response_model=DJSetDetailOut)
async def get_set_detail(set_id: int, db: AsyncSession = Depends(get_db)):
    # 1. DJSet + genres
    result = await db.execute(
        select(DJSet)
        .options(
            selectinload(DJSet.genres),
            selectinload(DJSet.artist_links).selectinload(SetArtist.artist),
            selectinload(DJSet.tracks).selectinload(SetTrack.catalog),
        )
        .where(DJSet.id == set_id)
    )
    dj_set = result.scalar_one_or_none()
    if not dj_set:
        raise HTTPException(status_code=404, detail="Set not found")

    # 2. Artists
    artists = [
        SetArtistDetailOut(
            artist_id=sa.artist_id,
            artist_name=sa.artist.name if sa.artist else "",
            has_artwork=sa.artist.has_artwork if sa.artist else False,
            role=sa.role,
            position=sa.position,
        )
        for sa in sorted(dj_set.artist_links, key=lambda x: x.position or 99)
    ]

    # 3. Collect catalog_ids to batch-check lib status
    catalog_ids = [t.catalog_id for t in dj_set.tracks if t.catalog_id]
    lib_set = set()
    if catalog_ids:
        lib_result = await db.execute(
            select(LibTrack.catalog_id).where(LibTrack.catalog_id.in_(catalog_ids))
        )
        lib_set = {r[0] for r in lib_result.all()}

    # 4. Tracklist
    tracklist = []
    total = 0
    identified = 0
    for t in dj_set.tracks:
        total += 1
        cat = t.catalog
        is_identified = cat is not None and not t.is_id
        if is_identified:
            identified += 1

        tracklist.append(SetTrackDetailOut(
            id=t.id,
            set_id=t.set_id,
            catalog_id=t.catalog_id,
            position=t.position,
            timecode_ms=t.timecode_ms,
            raw_title=t.raw_title,
            raw_artist=t.raw_artist,
            is_id=t.is_id,
            catalog_title=cat.title if cat else None,
            catalog_artist=cat.artist if cat else None,
            has_artwork=cat.has_artwork if cat else False,
            in_lib=t.catalog_id in lib_set if t.catalog_id else False,
            has_preview=cat.has_preview if cat else False,
        ))

    return DJSetDetailOut(
        id=dj_set.id,
        external_id=dj_set.external_id,
        source=dj_set.source,
        source_url=dj_set.source_url,
        title=dj_set.title,
        event=dj_set.event,
        venue=dj_set.venue,
        played_date=dj_set.played_date,
        duration_ms=dj_set.duration_ms,
        description=dj_set.description,
        has_artwork=dj_set.has_artwork,
        created_at=dj_set.created_at,
        last_crawled_at=dj_set.last_crawled_at,
        total_tracks=total,
        identified_tracks=identified,
        artists=artists,
        genres=[GenreOut.model_validate(g) for g in dj_set.genres],
        tracklist=tracklist,
    )
