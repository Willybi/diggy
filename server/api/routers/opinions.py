from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user_optional, uid as _uid
from models import (
    UserOpinion, UserSetFollow, UserFollow,
    UserTrack, UserRadarState,
    DJSet, WatchedEntity, Artist, User,
)

router = APIRouter(prefix="/opinions", tags=["opinions"])

VALID_TYPES = {"artist", "set", "playlist", "genre", "track"}


class OpinionUpdate(BaseModel):
    entity_type: str
    entity_key: str
    opinion: str | None  # 'liked' | 'disliked' | None (remove)


@router.get("/")
async def get_opinions(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Return all opinions for current user, grouped by entity_type."""
    uid = _uid(user)
    result = await db.execute(
        select(UserOpinion).where(UserOpinion.user_id == uid)
    )
    rows = result.scalars().all()

    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r.entity_type, {})[r.entity_key] = r.opinion
    return out


@router.patch("/")
async def set_opinion(
    body: OpinionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Set, update, or remove an opinion on an entity."""
    uid = _uid(user)

    if body.entity_type not in VALID_TYPES:
        raise HTTPException(422, f"entity_type must be one of {VALID_TYPES}")
    if body.opinion not in (None, "liked", "disliked"):
        raise HTTPException(422, "opinion must be 'liked', 'disliked', or null")

    result = await db.execute(
        select(UserOpinion).where(
            UserOpinion.user_id == uid,
            UserOpinion.entity_type == body.entity_type,
            UserOpinion.entity_key == body.entity_key,
        )
    )
    existing = result.scalar_one_or_none()

    if body.opinion is None:
        # Remove opinion
        if existing:
            await db.delete(existing)
    elif existing:
        existing.opinion = body.opinion
    else:
        db.add(UserOpinion(
            user_id=uid,
            entity_type=body.entity_type,
            entity_key=body.entity_key,
            opinion=body.opinion,
            created_at=datetime.now(timezone.utc),
        ))

    # Sync follow state for sets and playlists
    if body.entity_type == "set":
        await _sync_set_follow(db, uid, int(body.entity_key), body.opinion)
    elif body.entity_type == "playlist":
        await _sync_playlist_follow(db, uid, int(body.entity_key), body.opinion)
    elif body.entity_type == "track":
        await _sync_track_avis(db, uid, int(body.entity_key), body.opinion)

    await db.commit()
    return {"entity_type": body.entity_type, "entity_key": body.entity_key, "opinion": body.opinion}


async def _sync_set_follow(db: AsyncSession, user_id: int, set_id: int, opinion: str | None):
    """Like = follow, anything else = unfollow."""
    result = await db.execute(
        select(UserSetFollow).where(
            UserSetFollow.user_id == user_id,
            UserSetFollow.set_id == set_id,
        )
    )
    follow = result.scalar_one_or_none()

    if opinion == "liked":
        if not follow:
            db.add(UserSetFollow(
                user_id=user_id,
                set_id=set_id,
                followed_at=datetime.now(timezone.utc),
            ))
    else:
        if follow:
            await db.delete(follow)


async def _sync_playlist_follow(db: AsyncSession, user_id: int, entity_id: int, opinion: str | None):
    """Like = follow, anything else = unfollow."""
    result = await db.execute(
        select(UserFollow).where(
            UserFollow.user_id == user_id,
            UserFollow.entity_id == entity_id,
        )
    )
    follow = result.scalar_one_or_none()

    if opinion == "liked":
        if not follow:
            db.add(UserFollow(
                user_id=user_id,
                entity_id=entity_id,
                followed_at=datetime.now(timezone.utc),
            ))
    else:
        if follow:
            await db.delete(follow)


async def _sync_track_avis(db: AsyncSession, user_id: int, catalog_id: int, opinion: str | None):
    """Sync opinion → user_tracks.avis + user_radar_state.status."""
    # Sync user_tracks.avis (if the row exists)
    result = await db.execute(
        select(UserTrack).where(
            UserTrack.user_id == user_id,
            UserTrack.catalog_id == catalog_id,
        )
    )
    ut = result.scalar_one_or_none()
    if ut:
        ut.avis = opinion  # liked | disliked | None

    # Sync user_radar_state.status
    OPINION_TO_RADAR = {"liked": "added", "disliked": "ignored"}
    result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == user_id,
            UserRadarState.catalog_id == catalog_id,
        )
    )
    urs = result.scalar_one_or_none()
    if opinion is None:
        if urs:
            urs.status = "new"
            urs.updated_at = datetime.now(timezone.utc)
    else:
        new_status = OPINION_TO_RADAR.get(opinion, "new")
        if urs:
            urs.status = new_status
            urs.updated_at = datetime.now(timezone.utc)
        else:
            db.add(UserRadarState(
                user_id=user_id,
                catalog_id=catalog_id,
                status=new_status,
                updated_at=datetime.now(timezone.utc),
            ))
