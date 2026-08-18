"""
Album service: album detail (metadata + tracklist).

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from collections import defaultdict

from models import Album, Artist, CatalogAlbum, CatalogArtist, CatalogEntry, UserTrack
from schemas import AlbumDetailOut, AlbumTrackOut, ArtistRef
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.catalog_service import catalog_visible


async def get_detail(
    db: AsyncSession, album_id: int, user_id: int | None
) -> AlbumDetailOut:
    """Album metadata + its tracklist (catalog rows linked via ``catalog_albums``,
    restricted to the viewer's visible perimeter — C3). Raises ``LookupError``
    when the album does not exist (the router maps that to a 404)."""
    # 1. Album (+ its artist, via artist_id)
    result = await db.execute(select(Album).where(Album.id == album_id))
    album = result.scalar_one_or_none()
    if not album:
        raise LookupError("Album not found")

    artist_ref = None
    if album.artist_id is not None:
        ares = await db.execute(
            select(Artist.id, Artist.name, Artist.has_artwork).where(
                Artist.id == album.artist_id
            )
        )
        arow = ares.first()
        if arow:
            artist_ref = ArtistRef(id=arow.id, name=arow.name, has_artwork=arow.has_artwork)

    # 2. Tracklist: catalog rows linked to this album, visible to the viewer.
    tres = await db.execute(
        select(
            CatalogEntry.id,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.bpm_source,
            CatalogEntry.duration_ms,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
        )
        .join(CatalogAlbum, CatalogAlbum.catalog_id == CatalogEntry.id)
        .where(CatalogAlbum.album_id == album_id, catalog_visible(user_id))
        .order_by(CatalogEntry.id)
    )
    rows = tres.all()
    catalog_ids = [r.id for r in rows]

    # 3. Batch in_lib (scoped to the current user; guests own nothing) + artists.
    lib_set: set[int] = set()
    if user_id is not None and catalog_ids:
        lib_result = await db.execute(
            select(UserTrack.catalog_id).where(
                UserTrack.user_id == user_id,
                UserTrack.catalog_id.in_(catalog_ids),
            )
        )
        lib_set = {r[0] for r in lib_result.all()}

    track_artists_map: dict[int, list[ArtistRef]] = defaultdict(list)
    if catalog_ids:
        ca_result = await db.execute(
            select(
                CatalogArtist.catalog_id,
                Artist.id,
                Artist.name,
                CatalogArtist.role,
                Artist.has_artwork,
            )
            .join(Artist, Artist.id == CatalogArtist.artist_id)
            .where(CatalogArtist.catalog_id.in_(catalog_ids))
            .order_by(CatalogArtist.catalog_id, CatalogArtist.position)
        )
        for ca_cid, a_id, a_name, a_role, a_art in ca_result.all():
            track_artists_map[ca_cid].append(
                ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
            )

    tracklist = [
        AlbumTrackOut(
            id=r.id,
            title=r.title,
            artist=r.artist,
            artists=track_artists_map.get(r.id, []),
            bpm=r.bpm,
            key=r.key,
            bpm_source=r.bpm_source,
            duration_ms=r.duration_ms,
            has_artwork=r.has_artwork,
            has_preview=r.has_preview,
            in_lib=r.id in lib_set,
        )
        for r in rows
    ]

    return AlbumDetailOut(
        id=album.id,
        title=album.title,
        record_type=album.record_type.value if album.record_type else None,
        release_date=album.release_date,
        label=album.label,
        artist=artist_ref,
        has_artwork=bool(album.has_artwork),
        total_tracks=len(tracklist),
        tracklist=tracklist,
    )
