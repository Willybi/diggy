from database import get_db
from dependencies import get_current_user_optional
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException
from models import User
from schemas import AlbumDetailOut
from services import album_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/albums", tags=["albums"])


@router.get("/{album_id}", response_model=AlbumDetailOut)
async def get_album_detail(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    try:
        return await album_service.get_detail(db, album_id, _uid(user))
    except LookupError:
        raise HTTPException(status_code=404, detail="Album not found")
