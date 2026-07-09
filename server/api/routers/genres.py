import logging

from database import get_db
from dependencies import get_current_user_optional, require_admin
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException, Query
from models import User
from schemas import (
    GenreArtistListResponse,
    GenreDetailResponse,
    GenreListResponse,
    GenreMergeIn,
    GenreMergeResponse,
    GenreNeighborResponse,
    GenrePlaylistListResponse,
    GenreRenameIn,
    GenreRenameResponse,
    GenreSetListResponse,
    GenreTrackListResponse,
    RandomTrackResponse,
)
from services import genre_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["genres"])
log = logging.getLogger(__name__)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/random-track", response_model=RandomTrackResponse)
async def random_genre_track(
    genre: str = Query(..., max_length=100),
    exclude: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return a random previewable catalog entry for the given genre."""
    try:
        return await genre_service.random_track(db, genre, exclude)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("", response_model=GenreListResponse)
async def list_genres(
    sort: str = Query("tracks", pattern="^(tracks|alpha)$"),
    family: str | None = Query(None, max_length=100),
    q: str | None = Query(None, max_length=200),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Aggregated genre cards with stats, artworks, and artist photos."""
    return await genre_service.list_genres(
        db, _uid(user), family=family, sort=sort, q=q, limit=limit, offset=offset
    )


@router.post("/merge", response_model=GenreMergeResponse)
async def merge_genres(
    body: GenreMergeIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Merge source genre into target: reassign all tracks."""
    try:
        return await genre_service.merge(db, body.source, body.target)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/detail/{name:path}", response_model=GenreDetailResponse)
async def get_genre_detail(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Aggregated stats for a single genre."""
    try:
        return await genre_service.get_detail(db, name, _uid(user))
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/artists/{name:path}", response_model=GenreArtistListResponse)
async def get_genre_artists(
    name: str,
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Artists in this genre, sorted by track count."""
    try:
        return await genre_service.list_genre_artists(db, name, _uid(user), limit, offset)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/sets/{name:path}", response_model=GenreSetListResponse)
async def get_genre_sets(
    name: str,
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Sets containing tracks of this genre."""
    try:
        return await genre_service.list_genre_sets(db, name, limit, offset)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/playlists/{name:path}", response_model=GenrePlaylistListResponse)
async def get_genre_playlists(
    name: str,
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Watched playlists containing tracks of this genre."""
    try:
        return await genre_service.list_genre_playlists(db, name, limit, offset)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/tracks/{name:path}", response_model=GenreTrackListResponse)
async def get_genre_tracks(
    name: str,
    sort: str = Query("recent", pattern="^(recent|bpm|key|alpha)$"),
    q: str | None = Query(None, max_length=200),
    in_lib: int | None = Query(None, alias="inLib"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Paginated tracklist for a genre with sort, search, and in-lib filter."""
    try:
        return await genre_service.list_genre_tracks(
            db, name, _uid(user), sort=sort, q=q, in_lib=in_lib,
            limit=limit, offset=offset
        )
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/neighbors/{name:path}", response_model=GenreNeighborResponse)
async def get_genre_neighbors(
    name: str,
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Neighboring genres by common artists."""
    try:
        return await genre_service.get_neighbors(db, name, limit)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.patch("/rename/{name:path}", response_model=GenreRenameResponse)
async def rename_genre(
    name: str,
    body: GenreRenameIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Rename a genre across all catalog entries. Admin only."""
    try:
        return await genre_service.rename(db, name, body.new_name.strip())
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        code = 409 if "already exists" in str(e) else 400
        raise HTTPException(code, str(e))
