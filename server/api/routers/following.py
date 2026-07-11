from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Depends, Query
from models import User
from schemas import (
    ActivityListResponse,
    FollowingListResponse,
    NewCountResponse,
    OkResponse,
)
from services import following_service
from sqlalchemy.ext.asyncio import AsyncSession

# /api/following is absent from the middleware allowlists: every route here
# requires a JWT by default (get_current_user is kept by convention).
router = APIRouter(prefix="/following", tags=["following"])


@router.get("/", response_model=FollowingListResponse)
async def list_followed(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await following_service.list_followed(db, user.id)


@router.get("/activity", response_model=ActivityListResponse)
async def activity_feed(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await following_service.get_activity(
        db, user.id, limit=limit, offset=offset
    )


@router.get("/activity/new-count", response_model=NewCountResponse)
async def activity_new_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await following_service.new_count(db, user.id)


@router.post("/activity/seen", response_model=OkResponse)
async def mark_activity_seen(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await following_service.mark_seen(db, user.id)
    return OkResponse()
