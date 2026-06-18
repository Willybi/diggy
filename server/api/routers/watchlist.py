import requests
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, exists, case, literal
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user_optional
from sqlalchemy import func

from models import WatchedEntity, UserFollow, User, RadarTrack, CatalogEntry
from schemas import (
    WatchedPlaylistIn, WatchedPlaylistOut, WatchedPlaylistBrowseOut,
    WatchedPlaylistDetailOut, PlaylistTrackOut,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DEEZER_API = "https://api.deezer.com"
_DEFAULT_USER_ID = 1


def _uid(user: User | None) -> int:
    return user.id if user else _DEFAULT_USER_ID


def _fetch_deezer_playlist(external_id: str) -> dict:
    """Fetch playlist metadata from Deezer: title, track_count, owner."""
    try:
        resp = requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=5)
        data = resp.json()
        return {
            "title": data.get("title"),
            "track_count": data.get("nb_tracks"),
            "owner": data.get("creator", {}).get("name") if isinstance(data.get("creator"), dict) else None,
        }
    except Exception:
        return {}


def _trigger_crawl(playlist_id: int):
    """Fire-and-forget Celery task to crawl a single playlist."""
    import os
    from celery import Celery
    _celery = Celery(broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    _celery.send_task("workers.tasks.crawl_single_playlist", args=[playlist_id])


@router.get("/", response_model=list[WatchedPlaylistOut])
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


@router.get("/browse", response_model=list[WatchedPlaylistBrowseOut])
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
        WatchedPlaylistBrowseOut.model_validate(
            {**entity.__dict__, "followed": followed}
        )
        for entity, followed in rows
    ]


@router.get("/{entry_id}", response_model=WatchedPlaylistDetailOut)
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
            CatalogEntry.genre,
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

    return WatchedPlaylistDetailOut.model_validate(
        {**entity.__dict__, "followed": followed, "tracks": tracks}
    )


@router.post("/", response_model=WatchedPlaylistOut, status_code=201)
async def add_watched(
    body: WatchedPlaylistIn,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
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
        meta = _fetch_deezer_playlist(body.external_id)
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

    follow = UserFollow(
        user_id=uid,
        entity_id=entity.id,
        followed_at=datetime.now(timezone.utc),
    )
    db.add(follow)
    await db.commit()
    await db.refresh(entity)

    _trigger_crawl(entity.id)
    return entity


@router.post("/{entry_id}/follow", response_model=WatchedPlaylistOut)
async def follow_playlist(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
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

    _trigger_crawl(entity.id)
    return entity


@router.post("/{entry_id}/crawl", status_code=202)
async def crawl_playlist(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
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

    _trigger_crawl(entity.id)
    return {"status": "crawl_queued", "playlist_id": entry_id}


@router.patch("/{entry_id}/crawled", response_model=WatchedPlaylistOut)
async def mark_crawled(entry_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WatchedEntity).where(WatchedEntity.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    entry.last_crawled_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_watched(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
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
    await db.commit()
