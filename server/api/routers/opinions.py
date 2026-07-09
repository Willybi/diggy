from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from models import User, UserOpinion
from opinion_sync import sync_playlist_opinion, sync_set_opinion, sync_track_opinion
from schemas import OpinionSetResponse, OpinionUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/opinions", tags=["opinions"])

VALID_TYPES = {"artist", "set", "playlist", "genre", "track"}


@router.get("/", response_model=dict[str, dict[str, str]])
async def get_opinions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all opinions for current user, grouped by entity_type."""
    uid = user.id
    result = await db.execute(select(UserOpinion).where(UserOpinion.user_id == uid))
    rows = result.scalars().all()

    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r.entity_type, {})[r.entity_key] = r.opinion
    return out


@router.patch("/", response_model=OpinionSetResponse)
async def set_opinion(
    body: OpinionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set, update, or remove an opinion on an entity."""
    uid = user.id

    if body.entity_type not in VALID_TYPES:
        raise HTTPException(422, f"entity_type must be one of {VALID_TYPES}")
    if body.opinion not in (None, "liked", "disliked"):
        raise HTTPException(422, "opinion must be 'liked', 'disliked', or null")

    # Update UserOpinion
    result = await db.execute(
        select(UserOpinion).where(
            UserOpinion.user_id == uid,
            UserOpinion.entity_type == body.entity_type,
            UserOpinion.entity_key == body.entity_key,
        )
    )
    existing = result.scalar_one_or_none()

    if body.opinion is None:
        if existing:
            await db.delete(existing)
    elif existing:
        existing.opinion = body.opinion
    else:
        from datetime import datetime, timezone

        db.add(
            UserOpinion(
                user_id=uid,
                entity_type=body.entity_type,
                entity_key=body.entity_key,
                opinion=body.opinion,
                created_at=datetime.now(timezone.utc),
            )
        )

    # Sync follow/avis state. set/playlist/track key onto a numeric primary key;
    # a non-numeric entity_key is a client error (422), not a server crash (500).
    if body.entity_type in ("set", "playlist", "track"):
        try:
            entity_id = int(body.entity_key)
        except ValueError:
            raise HTTPException(
                422, f"entity_key must be numeric for entity_type '{body.entity_type}'"
            )
        if body.entity_type == "set":
            await sync_set_opinion(db, uid, entity_id, body.opinion)
        elif body.entity_type == "playlist":
            await sync_playlist_opinion(db, uid, entity_id, body.opinion)
        else:
            await sync_track_opinion(db, uid, entity_id, body.opinion)

    await db.commit()
    return {
        "entity_type": body.entity_type,
        "entity_key": body.entity_key,
        "opinion": body.opinion,
    }
