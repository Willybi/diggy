from typing import Literal

from database import get_db
from dependencies import (
    get_current_user,
    get_current_user_optional,
    get_redis,
)
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, Query
from models import User
from schemas import (
    NewCountResponse,
    RadarFeedList,
    TrendList,
)
from services import radar_service
from sqlalchemy.ext.asyncio import AsyncSession

from routers.catalog import CamelotKey

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("/trends", response_model=TrendList)
async def list_trends(
    family: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    return await radar_service.list_trends(db, _uid(user), family, limit)


@router.get("/feed", response_model=RadarFeedList)
async def radar_feed(
    search: str | None = Query(None, max_length=200),
    genre: list[str] | None = Query(None),
    bpm_min: float | None = Query(None, ge=0),
    bpm_max: float | None = Query(None, ge=0),
    key: list[CamelotKey] | None = Query(None),
    artist_id: list[int] | None = Query(None),
    duration_min: int | None = Query(None, ge=0),
    duration_max: int | None = Query(None, ge=0),
    has_preview: bool | None = Query(None),
    avis: Literal["liked", "disliked", "none"] | None = Query(None),
    year_min: int | None = Query(None, ge=1, le=9999),
    year_max: int | None = Query(None, ge=1, le=9999),
    label: str | None = Query(None, max_length=200),
    in_lib: bool | None = Query(None),
    sort: Literal["tendance", "pour_toi", "bpm", "recent"] = Query("tendance"),
    order: Literal["asc", "desc"] = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """Bi-score recommendation feed (Tendance × Pour toi). JWT required."""
    return await radar_service.list_bi_score(
        db, user.id,
        search=search, genre=genre, bpm_min=bpm_min, bpm_max=bpm_max,
        key=key, artist_id=artist_id,
        duration_min=duration_min, duration_max=duration_max,
        has_preview=has_preview, avis=avis,
        year_min=year_min, year_max=year_max, label=label, in_lib=in_lib,
        sort=sort, order=order, skip=skip, limit=limit, redis=redis,
    )


@router.get("/new-count", response_model=NewCountResponse)
async def radar_new_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await radar_service.new_count(db, user.id)
