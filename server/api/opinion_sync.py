"""
Shared sync logic for the opinion system.

Centralises the bidirectional sync between UserOpinion, UserTrack.avis,
UserRadarState, UserFollow, and UserSetFollow so that every router
(opinions, catalog, radar) uses the same code path.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    UserOpinion, UserTrack, UserRadarState,
    UserFollow, UserSetFollow,
)

OPINION_TO_RADAR = {"liked": "added", "disliked": "ignored"}
RADAR_TO_OPINION = {"added": "liked", "ignored": "disliked"}


async def sync_track_opinion(
    db: AsyncSession, user_id: int, catalog_id: int, opinion: str | None,
):
    """Sync a track opinion across UserOpinion, UserTrack.avis, UserRadarState.

    Args:
        opinion: 'liked' | 'disliked' | None (remove).
    """
    # 1. UserOpinion
    result = await db.execute(
        select(UserOpinion).where(
            UserOpinion.user_id == user_id,
            UserOpinion.entity_type == "track",
            UserOpinion.entity_key == str(catalog_id),
        )
    )
    op = result.scalar_one_or_none()
    if opinion is None:
        if op:
            await db.delete(op)
    elif op:
        op.opinion = opinion
    else:
        db.add(UserOpinion(
            user_id=user_id, entity_type="track",
            entity_key=str(catalog_id), opinion=opinion,
            created_at=datetime.now(timezone.utc),
        ))

    # 2. UserTrack.avis (update only if the row exists)
    result = await db.execute(
        select(UserTrack).where(
            UserTrack.user_id == user_id,
            UserTrack.catalog_id == catalog_id,
        )
    )
    ut = result.scalar_one_or_none()
    if ut:
        ut.avis = opinion

    # 3. UserRadarState
    new_status = OPINION_TO_RADAR.get(opinion, "new") if opinion else "new"
    result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == user_id,
            UserRadarState.catalog_id == catalog_id,
        )
    )
    urs = result.scalar_one_or_none()
    if urs:
        urs.status = new_status
        urs.updated_at = datetime.now(timezone.utc)
    else:
        db.add(UserRadarState(
            user_id=user_id, catalog_id=catalog_id,
            status=new_status, updated_at=datetime.now(timezone.utc),
        ))


async def sync_set_opinion(
    db: AsyncSession, user_id: int, set_id: int, opinion: str | None,
):
    """Like = follow (UserSetFollow), anything else = unfollow."""
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
                user_id=user_id, set_id=set_id,
                followed_at=datetime.now(timezone.utc),
            ))
    else:
        if follow:
            await db.delete(follow)


async def sync_playlist_opinion(
    db: AsyncSession, user_id: int, entity_id: int, opinion: str | None,
):
    """Like = follow (UserFollow), anything else = unfollow."""
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
                user_id=user_id, entity_id=entity_id,
                followed_at=datetime.now(timezone.utc),
            ))
    else:
        if follow:
            await db.delete(follow)
