from database import get_db
from dependencies import get_current_user, get_current_user_optional, require_admin
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException, Query
from models import User
from schemas import (
    CrawlQueuedResponse,
    CrawlStatusResponse,
    FetchArtworkResponse,
    WatchedEntityDetailOut,
    WatchedEntityIn,
    WatchedEntityOut,
    WatchlistBrowseResponse,
    WatchlistListResponse,
)
from services import watchlist_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("/", response_model=WatchlistListResponse)
async def list_watched(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    return await watchlist_service.list_followed(
        db, _uid(user), limit=limit, offset=offset
    )


@router.get("/browse", response_model=WatchlistBrowseResponse)
async def browse_playlists(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """All playlists in the system, with a `followed` flag for the current user."""
    return await watchlist_service.browse(db, _uid(user), limit=limit, offset=offset)


@router.get("/{entry_id}", response_model=WatchedEntityDetailOut)
async def get_playlist_detail(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Playlist detail with its radar tracks (enriched from catalog)."""
    try:
        return await watchlist_service.get_detail(db, _uid(user), entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.post("/", response_model=WatchedEntityOut, status_code=201)
async def add_watched(
    body: WatchedEntityIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await watchlist_service.add_watched(db, _uid(user), body)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/{entry_id}/follow", response_model=WatchedEntityOut)
async def follow_playlist(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Follow (reactivate) an existing playlist."""
    try:
        return await watchlist_service.follow_playlist(db, _uid(user), entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/{entry_id}/crawl", status_code=202, response_model=CrawlQueuedResponse)
async def crawl_playlist(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trigger an immediate crawl of a single playlist. Cooldown: 12h."""
    try:
        return await watchlist_service.request_crawl(db, entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(429, str(e))


@router.get("/{entry_id}/crawl-status", response_model=CrawlStatusResponse)
async def crawl_status(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Check crawl status for a playlist via Celery task state."""
    try:
        return await watchlist_service.get_crawl_status(db, entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.post("/{entry_id}/fetch-artwork", response_model=FetchArtworkResponse)
async def fetch_playlist_artwork(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin: fetch playlist artwork from Deezer and upload to MinIO."""
    try:
        return await watchlist_service.fetch_artwork(db, entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.delete("/{entry_id}", status_code=204)
async def delete_watched(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await watchlist_service.unfollow(db, _uid(user), entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
