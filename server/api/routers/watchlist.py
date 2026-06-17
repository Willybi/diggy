import requests
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user_optional
from models import WatchedEntity, UserFollow, User
from schemas import WatchedPlaylistIn, WatchedPlaylistOut

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DEEZER_API = "https://api.deezer.com"
_DEFAULT_USER_ID = 1


def _uid(user: User | None) -> int:
    return user.id if user else _DEFAULT_USER_ID


def _fetch_deezer_playlist_title(external_id: str) -> str | None:
    try:
        resp = requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=5)
        data = resp.json()
        return data.get("title")
    except Exception:
        return None


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
        # Entité déjà connue — vérifier si l'user la suit déjà
        follow_result = await db.execute(
            select(UserFollow).where(
                UserFollow.user_id == uid,
                UserFollow.entity_id == entity.id,
            )
        )
        if follow_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Playlist already watched")
    else:
        title = _fetch_deezer_playlist_title(body.external_id)
        entity = WatchedEntity(
            external_id=body.external_id,
            source=body.source,
            title=title,
            description=body.description,
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
    return entity


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
    # Supprimer le follow (pas l'entité elle-même — d'autres users peuvent la suivre)
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
