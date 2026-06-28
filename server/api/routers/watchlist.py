import requests
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, exists, case, literal
from sqlalchemy.ext.asyncio import AsyncSession

from celery_client import celery
from database import get_db
from dependencies import get_current_user, get_current_user_optional, require_admin, uid as _uid
from sqlalchemy import func

from models import WatchedEntity, UserFollow, UserOpinion, User, RadarTrack, CatalogEntry
from schemas import (
    WatchedEntityIn, WatchedEntityOut, WatchedEntityBrowseOut,
    WatchedEntityDetailOut, PlaylistTrackOut,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DEEZER_API = "https://api.deezer.com"
PLAYLIST_ARTWORK_BUCKET = "playlist-artworks"


def _fetch_deezer_playlist(external_id: str) -> dict:
    """Fetch playlist metadata from Deezer: title, track_count, owner, picture."""
    try:
        resp = requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=5)
        data = resp.json()
        return {
            "title": data.get("title"),
            "track_count": data.get("nb_tracks"),
            "owner": data.get("creator", {}).get("name") if isinstance(data.get("creator"), dict) else None,
            "picture": data.get("picture_xl") or data.get("picture_big") or data.get("picture_medium"),
        }
    except Exception:
        return {}


def _upload_playlist_artwork(entity_id: int, picture_url: str) -> bool:
    """Download playlist artwork and upload to MinIO. Returns True on success."""
    if not picture_url:
        return False
    try:
        from deezer_enrich import _get_s3, upload_image_to_bucket, _ensure_bucket
        s3 = _get_s3()
        _ensure_bucket(s3, PLAYLIST_ARTWORK_BUCKET)
        return upload_image_to_bucket(s3, picture_url, f"{entity_id}.jpg", PLAYLIST_ARTWORK_BUCKET)
    except Exception:
        return False




async def _trigger_crawl(playlist_id: int, db: AsyncSession):
    """Launch Celery crawl task and store task_id on the entity."""
    result = celery.send_task("workers.tasks.crawl_single_playlist", args=[playlist_id])
    entity_result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == playlist_id))
    entity = entity_result.scalar_one_or_none()
    if entity:
        entity.current_task_id = result.id
        entity.crawl_started_at = datetime.now(timezone.utc)
        await db.commit()


@router.get("/", response_model=list[WatchedEntityOut])
async def list_watched(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)
    result = await db.execute(
        select(WatchedEntity)
        .join(UserFollow, UserFollow.entity_id == WatchedEntity.id)
        .where(UserFollow.user_id == uid)
    )
    return result.scalars().all()


@router.get("/active", response_model=list[WatchedEntityOut])
async def list_active_playlists(
    db: AsyncSession = Depends(get_db),
):
    """All playlists with at least 1 follower. Used by crawl_radar."""
    result = await db.execute(
        select(WatchedEntity).where(
            select(UserFollow.entity_id)
            .where(UserFollow.entity_id == WatchedEntity.id)
            .correlate(WatchedEntity)
            .exists()
        )
    )
    return result.scalars().all()


@router.get("/browse", response_model=list[WatchedEntityBrowseOut])
async def browse_playlists(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """All playlists in the system, with a `followed` flag for the current user."""
    uid = _uid(user)
    follow_exists = (
        select(UserFollow.entity_id)
        .where(UserFollow.entity_id == WatchedEntity.id, UserFollow.user_id == uid)
        .correlate(WatchedEntity)
        .exists()
    )
    result = await db.execute(
        select(WatchedEntity, follow_exists.label("followed"))
        .order_by(WatchedEntity.title)
    )
    rows = result.all()
    return [
        WatchedEntityBrowseOut.model_validate(
            {**entity.__dict__, "followed": followed}
        )
        for entity, followed in rows
    ]


@router.get("/{entry_id}", response_model=WatchedEntityDetailOut)
async def get_playlist_detail(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Playlist detail with its radar tracks (enriched from catalog)."""
    uid = _uid(user)
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Playlist not found")

    # Check if user follows this playlist
    follow_result = await db.execute(
        select(UserFollow).where(UserFollow.user_id == uid, UserFollow.entity_id == entry_id)
    )
    followed = follow_result.scalar_one_or_none() is not None

    # Tracks: radar_tracks joined with catalog, deduped by catalog_id
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
        .where(RadarTrack.watched_entity_id == entry_id, RadarTrack.catalog_id.isnot(None))
        .group_by(CatalogEntry.id)
        .order_by(func.max(RadarTrack.detected_at).desc())
    )
    tracks = [PlaylistTrackOut.model_validate(row._mapping) for row in tracks_result]

    return WatchedEntityDetailOut.model_validate(
        {**entity.__dict__, "followed": followed, "tracks": tracks}
    )


@router.post("/", response_model=WatchedEntityOut, status_code=201)
async def add_watched(
    body: WatchedEntityIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = _uid(user)

    existing = await db.execute(
        select(WatchedEntity).where(WatchedEntity.external_id == body.external_id)
    )
    entity = existing.scalar_one_or_none()

    if entity:
        follow_result = await db.execute(
            select(UserFollow).where(
                UserFollow.user_id == uid,
                UserFollow.entity_id == entity.id,
            )
        )
        if follow_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Playlist already watched")
    else:
        # Fetch metadata inline for Deezer; for other sources the crawl task fills it
        meta = _fetch_deezer_playlist(body.external_id) if body.source == "deezer" else {}
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
        if meta.get("picture") and _upload_playlist_artwork(entity.id, meta["picture"]):
            entity.has_artwork = True

    follow = UserFollow(
        user_id=uid,
        entity_id=entity.id,
        followed_at=datetime.now(timezone.utc),
    )
    db.add(follow)
    await db.commit()
    await db.refresh(entity)

    await _trigger_crawl(entity.id, db)
    return entity


@router.post("/{entry_id}/follow", response_model=WatchedEntityOut)
async def follow_playlist(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Follow (reactivate) an existing playlist."""
    uid = _uid(user)
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Playlist not found")

    follow_result = await db.execute(
        select(UserFollow).where(UserFollow.user_id == uid, UserFollow.entity_id == entry_id)
    )
    if follow_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already following")

    follow = UserFollow(user_id=uid, entity_id=entry_id, followed_at=datetime.now(timezone.utc))
    db.add(follow)
    await db.commit()
    await db.refresh(entity)

    await _trigger_crawl(entity.id, db)
    return entity


@router.post("/{entry_id}/crawl", status_code=202)
async def crawl_playlist(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trigger an immediate crawl of a single playlist. Cooldown: 12h."""
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if entity.last_crawled_at:
        elapsed = datetime.now(timezone.utc) - entity.last_crawled_at.replace(tzinfo=timezone.utc)
        if elapsed.total_seconds() < 12 * 3600:
            remaining_h = int((12 * 3600 - elapsed.total_seconds()) / 3600)
            remaining_m = int(((12 * 3600 - elapsed.total_seconds()) % 3600) / 60)
            raise HTTPException(
                status_code=429,
                detail=f"Crawl cooldown: retry in {remaining_h}h{remaining_m:02d}m",
            )

    await _trigger_crawl(entity.id, db)
    return {"status": "crawl_queued", "playlist_id": entry_id}


@router.patch("/{entry_id}/crawled", response_model=WatchedEntityOut)
async def mark_crawled(entry_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    entry.last_crawled_at = datetime.now(timezone.utc)
    entry.current_task_id = None
    entry.crawl_started_at = None
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/{entry_id}/crawl-status")
async def crawl_status(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Check crawl status for a playlist via Celery task state."""
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Playlist not found")

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
            elapsed = (datetime.now(timezone.utc) - entity.crawl_started_at.replace(tzinfo=timezone.utc)).total_seconds()
            if elapsed > 900:  # 15 min
                entity.current_task_id = None
                entity.crawl_started_at = None
                await db.commit()
                return {"status": None}
        return {"status": "queued"}
    else:
        return {"status": "queued"}


@router.post("/{entry_id}/fetch-artwork")
async def fetch_playlist_artwork(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin: fetch playlist artwork from Deezer and upload to MinIO."""
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Playlist not found")

    if entity.source != "deezer":
        raise HTTPException(status_code=400, detail="Only Deezer playlists supported for artwork fetch")

    meta = _fetch_deezer_playlist(entity.external_id)
    pic_url = meta.get("picture")
    if not pic_url:
        raise HTTPException(status_code=404, detail="No artwork found on Deezer")

    if _upload_playlist_artwork(entity.id, pic_url):
        entity.has_artwork = True
        await db.commit()
        await db.refresh(entity)
        return {"ok": True, "has_artwork": True}

    raise HTTPException(status_code=500, detail="Failed to upload artwork")


@router.delete("/{entry_id}", status_code=204)
async def delete_watched(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    uid = _uid(user)
    result = await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == uid,
            UserFollow.entity_id == entry_id,
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(follow)

    # Sync: remove associated opinion
    await db.execute(
        delete(UserOpinion).where(
            UserOpinion.user_id == uid,
            UserOpinion.entity_type == "playlist",
            UserOpinion.entity_key == str(entry_id),
        )
    )

    await db.commit()
