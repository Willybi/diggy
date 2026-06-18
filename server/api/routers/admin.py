from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_admin
from models import Artist, ArtistAlias, ArtistFlag, User

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- Schemas ----------

class ArtistFlagOut(BaseModel):
    id: int
    raw_artist_string: str
    reason: str
    tokens: list[str]
    deezer_ids: dict
    status: str
    resolved_artist_ids: list[int] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SyncResult(BaseModel):
    created: int
    flagged: int
    skipped: int


class ResolveIn(BaseModel):
    action: str  # "split" | "keep" | "skip"


# ---------- Endpoints ----------

@router.post("/artists/sync", response_model=SyncResult)
async def sync_artists(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Trigger artist sync from catalog. Idempotent."""
    from scripts.populate_artists import run_sync
    result = await run_sync(db)
    return SyncResult(**result)


@router.get("/artists/flags", response_model=list[ArtistFlagOut])
async def list_flags(
    status: str = "pending",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        select(ArtistFlag)
        .where(ArtistFlag.status == status)
        .order_by(ArtistFlag.created_at.desc())
    )
    return result.scalars().all()


@router.post("/artists/flags/{flag_id}/resolve", response_model=ArtistFlagOut)
async def resolve_flag(
    flag_id: int,
    body: ResolveIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(ArtistFlag).where(ArtistFlag.id == flag_id))
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    if flag.status != "pending":
        raise HTTPException(status_code=409, detail="Flag already resolved")

    if body.action == "skip":
        flag.status = "skipped"
        flag.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(flag)
        return flag

    if body.action not in ("split", "keep"):
        raise HTTPException(status_code=422, detail="action must be split, keep, or skip")

    from trackid.importer import get_or_create_artist

    names_to_create = flag.tokens if body.action == "split" else [flag.raw_artist_string]
    deezer_map = flag.deezer_ids or {}

    created_ids = []
    for name in names_to_create:
        artist = await get_or_create_artist(db, name)
        if not artist.deezer_id and deezer_map.get(name):
            artist.deezer_id = deezer_map[name]
        created_ids.append(artist.id)

    flag.status = "validated"
    flag.resolved_artist_ids = created_ids
    flag.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(flag)
    return flag
