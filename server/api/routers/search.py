from __future__ import annotations

from database import get_db
from dependencies import get_current_user, get_current_user_optional
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, Query
from models import User
from schemas import ExternalSearchResponse, SearchResponse
from services import external_search_service, search_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", min_length=0, max_length=200),
    scope: str = Query("all", max_length=50),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    return await search_service.search(
        db,
        q,
        scope=scope,
        limit=limit,
        offset=offset,
        user_id=_uid(user),
        is_guest=user is None,
    )


@router.get("/search/external", response_model=ExternalSearchResponse)
async def search_external(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search external sources (Deezer + TIDAL) for a manual import. Auth required."""
    return await external_search_service.search_external(db, q, limit)
