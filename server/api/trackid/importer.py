"""Shared import logic for TrackID.net audiostreams into Diggy DB."""

from datetime import datetime, timezone

from models import Artist, ArtistAlias, DJSet, SetArtist, SetTrack
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils import normalize

from trackid.client import TrackIDClient
from trackid.parsing import is_id_track, parse_timespan_to_ms, parse_trackid_date

SET_ARTWORK_BUCKET = "set-artworks"


async def get_or_create_artist(
    db: AsyncSession, name: str, trackid_id: str | None = None
) -> Artist:
    """Find or create an Artist by normalized_name."""
    norm = normalize(name)

    # Check main name
    result = await db.execute(select(Artist).where(Artist.normalized_name == norm))
    artist = result.scalar_one_or_none()
    if artist:
        if trackid_id and not artist.trackid_id:
            artist.trackid_id = trackid_id
        return artist

    # Check aliases
    result = await db.execute(
        select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
    )
    alias = result.scalar_one_or_none()
    if alias:
        return await db.get(Artist, alias.artist_id)

    # Create new
    artist = Artist(
        name=name,
        normalized_name=norm,
        trackid_id=trackid_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(artist)
    await db.flush()
    return artist


async def import_audiostream(
    db: AsyncSession,
    client: TrackIDClient,
    audiostream: dict,
    artist_id: int | None = None,
    *,
    prefetched_detail: dict | None = None,
    min_age_hours: int = 168,
) -> tuple[DJSet | None, int]:
    """Import a single TrackID audiostream into the database.

    Returns (dj_set, track_count). Returns (None, 0) if skipped.
    min_age_hours: skip re-crawl if last_crawled_at is younger (default 168 = 7 days).
    """
    ext_id = str(audiostream["id"])
    slug = audiostream.get("slug", "")

    # Check if set already exists
    result = await db.execute(
        select(DJSet).where(DJSet.external_id == ext_id, DJSet.source == "trackid")
    )
    existing = result.scalar_one_or_none()

    # Skip if recently crawled
    if existing and existing.last_crawled_at:
        age_hours = (
            datetime.now(timezone.utc) - existing.last_crawled_at
        ).total_seconds() / 3600
        if age_hours < min_age_hours:
            return existing, 0

    # Fetch detail (use prefetched if provided)
    detail = prefetched_detail or await client.get_set_detail(slug)
    if not detail:
        return None, 0

    # Parse fields
    duration_ms = parse_timespan_to_ms(detail.get("duration"))
    played_date = parse_trackid_date(detail.get("createdOn"))
    detail_slug = detail.get("slug") or slug
    now = datetime.now(timezone.utc)

    if existing:
        dj_set = existing
        dj_set.title = detail.get("title", dj_set.title)
        dj_set.source_url = detail.get("url")
        dj_set.duration_ms = duration_ms
        dj_set.last_crawled_at = now
        if detail_slug and not dj_set.external_slug:
            dj_set.external_slug = detail_slug
    else:
        dj_set = DJSet(
            external_id=ext_id,
            source="trackid",
            source_url=detail.get("url"),
            external_slug=detail_slug or None,
            title=detail.get("title", "Untitled"),
            duration_ms=duration_ms,
            played_date=played_date.date() if played_date else None,
            created_at=now,
            last_crawled_at=now,
        )
        db.add(dj_set)
        await db.flush()

    # Fetch artwork from TrackID if available and not yet stored
    artwork_url = detail.get("artworkUrl")
    if artwork_url and not dj_set.has_artwork:
        try:
            from services.image_service import ImageService

            ImageService.ensure_bucket(SET_ARTWORK_BUCKET)
            if ImageService.upload_from_url(artwork_url, SET_ARTWORK_BUCKET, f"{dj_set.id}.jpg"):
                dj_set.has_artwork = True
        except Exception:
            pass

    # Link artist if provided
    if artist_id:
        result = await db.execute(
            select(SetArtist).where(
                SetArtist.set_id == dj_set.id, SetArtist.artist_id == artist_id
            )
        )
        if not result.scalar_one_or_none():
            db.add(
                SetArtist(set_id=dj_set.id, artist_id=artist_id, role="dj", position=0)
            )

    # Import tracklist — delete existing and re-insert
    await db.execute(delete(SetTrack).where(SetTrack.set_id == dj_set.id))

    merged = client.merge_tracklist(detail)
    track_count = 0

    for idx, track in enumerate(merged):
        raw_title = track.get("title")
        raw_artist = track.get("artist")
        timecode_ms = parse_timespan_to_ms(track.get("startTime"))
        mtid = track.get("musicTrackId")

        st = SetTrack(
            set_id=dj_set.id,
            position=idx + 1,
            timecode_ms=timecode_ms,
            raw_title=raw_title,
            raw_artist=raw_artist,
            is_id=is_id_track(raw_title, raw_artist),
            trackid_music_track_id=mtid,
        )
        db.add(st)
        track_count += 1

    await db.flush()

    # Post-import: normalize title then run dedup matching
    try:
        from services.set_dedup_service import (
            apply_match_results,
            backfill_normalized_titles,
            match_set,
        )
        await backfill_normalized_titles(db)
        if dj_set.id is not None and not dj_set.is_virtual:
            results = await match_set(db, dj_set.id)
            if results:
                await apply_match_results(db, dj_set.id, results)
    except Exception:
        pass  # matching failure must never abort import

    return dj_set, track_count
