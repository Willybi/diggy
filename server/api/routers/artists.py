from database import get_db
from dependencies import get_current_user_optional
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException, Query
from models import User
from schemas import ArtistDetailOut
from services import artist_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("/")
async def list_artists(
    sort: str = Query("catalog", pattern="^(catalog|lib|liked|disliked|rating|alpha)$"),
    family: str | None = Query(None, max_length=100),
    q: str | None = Query(None, max_length=200),
    no_deezer: bool = False,
    ids: str | None = Query(None, max_length=500),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    return await artist_service.list_artists(
        db, _uid(user),
        sort=sort, family=family, q=q, no_deezer=no_deezer,
        ids=ids, limit=limit, offset=offset,
    )


@router.get("/random-track")
async def random_artist_track(
    artist_id: int = Query(...),
    exclude: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return a random previewable catalog entry for the given artist."""
    try:
        return await artist_service.random_track(db, artist_id, exclude)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/{artist_id}/connections")
async def get_artist_connections(
    artist_id: int,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    from services import artist_connection_service

    try:
        return await artist_connection_service.get_connections(
            db, artist_id, limit=limit,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/{artist_id}", response_model=ArtistDetailOut)
async def get_artist_detail(artist_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await artist_service.get_detail(db, artist_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
