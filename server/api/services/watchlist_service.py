"""
Watchlist service: followed listing, browse, playlist detail, follow lifecycle,
crawl triggering (12h cooldown + Celery task state) and Deezer artwork fetching.

Services raise LookupError (404), ValueError (400/409/429) or RuntimeError (500),
never HTTPException.
"""

from datetime import datetime, timezone

import httpx
from celery_client import celery
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

DEEZER_API = "https://api.deezer.com"


async def _fetch_deezer_playlist(external_id: str) -> dict:
    """Fetch playlist metadata from Deezer: title, track_count, owner, picture."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{DEEZER_API}/playlist/{external_id}")
            data = resp.json()
        return {
            "title": data.get("title"),
            "track_count": data.get("nb_tracks"),
            "owner": data.get("creator", {}).get("name")
            if isinstance(data.get("creator"), dict)
            else None,
            "picture": data.get("picture_xl")
            or data.get("picture_big")
            or data.get("picture_medium"),
        }
    except Exception:
        return {}


async def _upload_playlist_artwork(entity_id: int, picture_url: str) -> bool:
    """Download playlist artwork and upload to MinIO. Returns True on success."""
    if not picture_url:
        return False
    try:
        from services.image_service import BUCKET_PLAYLIST, ImageService

        # ImageService is synchronous (requests + boto3): keep it off the event loop
        await run_in_threadpool(ImageService.ensure_bucket, BUCKET_PLAYLIST)
        return await run_in_threadpool(
            ImageService.upload_from_url, picture_url, BUCKET_PLAYLIST, f"{entity_id}.jpg"
        )
    except Exception:
        return False


async def _trigger_crawl(playlist_id: int, db: AsyncSession):
    """Launch Celery crawl task and store task_id on the entity."""
    from models import WatchedEntity

    result = celery.send_task("workers.tasks.crawl_single_playlist", args=[playlist_id])
    entity_result = await db.execute(
        select(WatchedEntity).where(WatchedEntity.id == playlist_id)
    )
    entity = entity_result.scalar_one_or_none()
    if entity:
        entity.current_task_id = result.id
        entity.crawl_started_at = datetime.now(timezone.utc)
        await db.commit()


async def list_followed(
    db: AsyncSession, user_id: int | None, limit: int, offset: int
):
    """Playlists followed by the given user."""
    from models import UserFollow, WatchedEntity
    from schemas import WatchlistListResponse

    base = (
        select(WatchedEntity)
        .join(UserFollow, UserFollow.entity_id == WatchedEntity.id)
        .where(UserFollow.user_id == user_id)
    )
    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar()
    result = await db.execute(base.offset(offset).limit(limit))
    return WatchlistListResponse(total=total, items=result.scalars().all())


async def browse(db: AsyncSession, user_id: int | None, limit: int, offset: int):
    """All playlists in the system, with a `followed` flag for the given user."""
    from models import UserFollow, WatchedEntity
    from schemas import WatchedEntityBrowseOut, WatchlistBrowseResponse

    follow_exists = (
        select(UserFollow.entity_id)
        .where(UserFollow.entity_id == WatchedEntity.id, UserFollow.user_id == user_id)
        .correlate(WatchedEntity)
        .exists()
    )
    base = select(WatchedEntity, follow_exists.label("followed")).order_by(
        WatchedEntity.title
    )
    count_result = await db.execute(
        select(func.count()).select_from(select(WatchedEntity.id).subquery())
    )
    total = count_result.scalar()
    result = await db.execute(base.offset(offset).limit(limit))
    rows = result.all()
    items = [
        WatchedEntityBrowseOut.model_validate({**entity.__dict__, "followed": followed})
        for entity, followed in rows
    ]
    return WatchlistBrowseResponse(total=total, items=items)


async def get_detail(db: AsyncSession, user_id: int | None, entry_id: int):
    """Playlist detail: its radar tracks (enriched from catalog) plus the
    top artists and dominant genres computed over the same visible tracks."""
    from collections import defaultdict

    from models import (
        Artist,
        CatalogArtist,
        CatalogEntry,
        RadarTrack,
        UserFollow,
        UserTrack,
        WatchedEntity,
    )
    from schemas import (
        ArtistRef,
        PlaylistTrackOut,
        TopArtistOut,
        WatchedEntityDetailOut,
    )

    from services.catalog_service import catalog_visible
    from services.genre_service import aggregate_top_genres, ensure_pillar_cache

    # Warm the pillar cache up front (mirrors list_catalog): its loader rolls the
    # session back on failure, so it must run before we hold any ORM row we still
    # need — never between the entity fetch and the final serialization.
    await ensure_pillar_cache(db)

    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise LookupError("Playlist not found")

    # Check if user follows this playlist
    follow_result = await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == user_id, UserFollow.entity_id == entry_id
        )
    )
    followed = follow_result.scalar_one_or_none() is not None

    # Tracks: radar_tracks joined with catalog, deduped by catalog_id. This is
    # the single visibility-filtered (C3) perimeter every aggregate below reuses.
    tracks_result = await db.execute(
        select(
            CatalogEntry.id.label("catalog_id"),
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.duration_ms,
            CatalogEntry.genres,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            func.max(RadarTrack.detected_at).label("detected_at"),
        )
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .where(
            RadarTrack.watched_entity_id == entry_id,
            RadarTrack.catalog_id.isnot(None),
            catalog_visible(user_id),
        )
        .group_by(CatalogEntry.id)
        .order_by(func.max(RadarTrack.detected_at).desc())
    )
    track_rows = tracks_result.all()
    catalog_ids = [row.catalog_id for row in track_rows]

    # Artists per track: bulk-load in one query, mapped by catalog_id (position order).
    artists_by_catalog: dict[int, list] = defaultdict(list)
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
            artists_by_catalog[ca_cid].append(
                ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
            )

    # in_lib: one query on user_tracks. Guests (user_id None) get all False.
    in_lib_ids: set[int] = set()
    if user_id is not None and catalog_ids:
        ut_result = await db.execute(
            select(UserTrack.catalog_id).where(
                UserTrack.user_id == user_id,
                UserTrack.catalog_id.in_(catalog_ids),
            )
        )
        in_lib_ids = {row[0] for row in ut_result.all()}

    tracks = [
        PlaylistTrackOut(
            catalog_id=row.catalog_id,
            title=row.title,
            artist=row.artist,
            artists=artists_by_catalog.get(row.catalog_id, []),
            bpm=row.bpm,
            key=row.key,
            duration_ms=row.duration_ms,
            has_artwork=row.has_artwork,
            has_preview=row.has_preview,
            in_lib=row.catalog_id in in_lib_ids,
            detected_at=row.detected_at,
        )
        for row in track_rows
    ]

    # top_artists: how many of the playlist's visible tracks each artist appears on.
    top_artists: list[TopArtistOut] = []
    if catalog_ids:
        cnt_col = func.count(func.distinct(CatalogArtist.catalog_id))
        ta_result = await db.execute(
            select(Artist.id, Artist.name, Artist.has_artwork, cnt_col.label("cnt"))
            .join(CatalogArtist, CatalogArtist.artist_id == Artist.id)
            .where(CatalogArtist.catalog_id.in_(catalog_ids))
            .group_by(Artist.id, Artist.name, Artist.has_artwork)
            .order_by(cnt_col.desc(), Artist.name.asc())
            .limit(6)
        )
        top_artists = [
            TopArtistOut(id=a_id, name=a_name, has_artwork=a_art, count=cnt)
            for a_id, a_name, a_art, cnt in ta_result.all()
        ]

    # top_genres: share of visible tracks containing each genre (Python aggregate
    # over the already-loaded rows; playlist volume stays well under a N+1 threshold).
    top_genres = aggregate_top_genres([row.genres or [] for row in track_rows])

    return WatchedEntityDetailOut.model_validate(
        {
            **entity.__dict__,
            "followed": followed,
            "tracks": tracks,
            "top_artists": top_artists,
            "top_genres": top_genres,
        }
    )


async def add_watched(db: AsyncSession, user_id: int | None, body):
    """Create (or reuse) a watched playlist, follow it and queue a crawl.

    Raises ValueError (409) if the user already follows the playlist.
    """
    from models import UserFollow, WatchedEntity

    existing = await db.execute(
        select(WatchedEntity).where(WatchedEntity.external_id == body.external_id)
    )
    entity = existing.scalar_one_or_none()

    if entity:
        follow_result = await db.execute(
            select(UserFollow).where(
                UserFollow.user_id == user_id,
                UserFollow.entity_id == entity.id,
            )
        )
        if follow_result.scalar_one_or_none():
            raise ValueError("Playlist already watched")
    else:
        # Fetch metadata inline for Deezer; for other sources the crawl task fills it
        meta = (
            await _fetch_deezer_playlist(body.external_id)
            if body.source == "deezer"
            else {}
        )
        entity = WatchedEntity(
            external_id=body.external_id,
            source=body.source,
            title=meta.get("title"),
            description=body.description,
            track_count=meta.get("track_count"),
            owner=meta.get("owner"),
            has_artwork=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entity)
        await db.flush()

        # Auto-fetch artwork from Deezer
        if meta.get("picture") and await _upload_playlist_artwork(
            entity.id, meta["picture"]
        ):
            entity.has_artwork = True

    follow = UserFollow(
        user_id=user_id,
        entity_id=entity.id,
        followed_at=datetime.now(timezone.utc),
    )
    db.add(follow)
    await db.commit()
    await db.refresh(entity)

    await _trigger_crawl(entity.id, db)
    return entity


async def follow_playlist(db: AsyncSession, user_id: int | None, entry_id: int):
    """Follow (reactivate) an existing playlist.

    Raises LookupError (404) or ValueError (409) if already following.
    """
    from models import UserFollow, WatchedEntity

    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise LookupError("Playlist not found")

    follow_result = await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == user_id, UserFollow.entity_id == entry_id
        )
    )
    if follow_result.scalar_one_or_none():
        raise ValueError("Already following")

    follow = UserFollow(
        user_id=user_id, entity_id=entry_id, followed_at=datetime.now(timezone.utc)
    )
    db.add(follow)
    await db.commit()
    await db.refresh(entity)

    await _trigger_crawl(entity.id, db)
    return entity


async def request_crawl(db: AsyncSession, entry_id: int) -> dict:
    """Queue an immediate crawl of a single playlist.

    Raises LookupError (404) or ValueError (429) within the 12h cooldown.
    """
    from models import WatchedEntity

    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise LookupError("Playlist not found")

    if entity.last_crawled_at:
        elapsed = datetime.now(timezone.utc) - entity.last_crawled_at.replace(
            tzinfo=timezone.utc
        )
        if elapsed.total_seconds() < 12 * 3600:
            remaining_h = int((12 * 3600 - elapsed.total_seconds()) / 3600)
            remaining_m = int(((12 * 3600 - elapsed.total_seconds()) % 3600) / 60)
            raise ValueError(
                f"Crawl cooldown: retry in {remaining_h}h{remaining_m:02d}m"
            )

    await _trigger_crawl(entity.id, db)
    return {"status": "crawl_queued", "playlist_id": entry_id}


async def get_crawl_status(db: AsyncSession, entry_id: int) -> dict:
    """Check crawl status for a playlist via Celery task state."""
    from models import WatchedEntity

    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise LookupError("Playlist not found")

    if not entity.current_task_id:
        return {"status": None}

    from celery.result import AsyncResult

    task = AsyncResult(entity.current_task_id, app=celery)
    state = task.state  # PENDING, STARTED, SUCCESS, FAILURE, etc.

    if state in ("SUCCESS", "FAILURE", "REVOKED"):
        entity.current_task_id = None
        await db.commit()
        return {"status": "done"}
    elif state == "STARTED":
        return {"status": "running"}
    elif state == "PENDING":
        # PENDING means "queued" OR "unknown/expired task_id".
        # Safety: if task has been PENDING for >15 min, assume it's stale.
        if entity.crawl_started_at:
            elapsed = (
                datetime.now(timezone.utc)
                - entity.crawl_started_at.replace(tzinfo=timezone.utc)
            ).total_seconds()
            if elapsed > 900:  # 15 min
                entity.current_task_id = None
                entity.crawl_started_at = None
                await db.commit()
                return {"status": None}
        return {"status": "queued"}
    else:
        return {"status": "queued"}


async def fetch_artwork(db: AsyncSession, entry_id: int) -> dict:
    """Fetch playlist artwork from Deezer and upload to MinIO (admin action).

    Raises LookupError (404), ValueError (400 non-Deezer source) or
    RuntimeError (500 upload failure).
    """
    from models import WatchedEntity

    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise LookupError("Playlist not found")

    if entity.source != "deezer":
        raise ValueError("Only Deezer playlists supported for artwork fetch")

    meta = await _fetch_deezer_playlist(entity.external_id)
    pic_url = meta.get("picture")
    if not pic_url:
        raise LookupError("No artwork found on Deezer")

    if await _upload_playlist_artwork(entity.id, pic_url):
        entity.has_artwork = True
        await db.commit()
        await db.refresh(entity)
        return {"ok": True, "has_artwork": True}

    raise RuntimeError("Failed to upload artwork")


async def unfollow(db: AsyncSession, user_id: int | None, entry_id: int) -> None:
    """Unfollow a playlist and remove the associated playlist opinion."""
    from models import UserFollow, UserOpinion

    result = await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == user_id,
            UserFollow.entity_id == entry_id,
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        raise LookupError("Not found")
    await db.delete(follow)

    # Sync: remove associated opinion
    await db.execute(
        delete(UserOpinion).where(
            UserOpinion.user_id == user_id,
            UserOpinion.entity_type == "playlist",
            UserOpinion.entity_key == str(entry_id),
        )
    )

    await db.commit()
