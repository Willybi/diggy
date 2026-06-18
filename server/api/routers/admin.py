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


class SyncQueued(BaseModel):
    status: str
    task_id: str


class SyncResult(BaseModel):
    created: int
    flagged: int
    skipped: int


class SyncStatus(BaseModel):
    status: str  # pending | running | done | error
    result: SyncResult | None = None
    error: str | None = None


class ResolveIn(BaseModel):
    action: str  # "split" | "keep" | "skip"


# ---------- Endpoints ----------

def _send_sync_task() -> str:
    import os
    from celery import Celery
    _celery = Celery(
        broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        backend=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    )
    result = _celery.send_task("workers.tasks.sync_artists")
    return result.id


@router.post("/artists/sync", response_model=SyncQueued)
async def sync_artists(
    _: User = Depends(require_admin),
):
    """Fire-and-forget artist sync. Returns task_id for polling."""
    task_id = _send_sync_task()
    return SyncQueued(status="queued", task_id=task_id)


@router.get("/artists/sync/status/{task_id}", response_model=SyncStatus)
async def sync_status(
    task_id: str,
    _: User = Depends(require_admin),
):
    """Poll Celery task result."""
    import os
    from celery import Celery
    from celery.result import AsyncResult
    _celery = Celery(
        broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        backend=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    )
    res = AsyncResult(task_id, app=_celery)
    if res.state == "PENDING" or res.state == "STARTED":
        return SyncStatus(status="running")
    if res.state == "SUCCESS":
        return SyncStatus(status="done", result=SyncResult(**res.result))
    if res.state == "FAILURE":
        return SyncStatus(status="error", error=str(res.result))
    return SyncStatus(status="running")


@router.post("/artists/fetch-artworks", response_model=SyncQueued)
async def fetch_artworks(
    _: User = Depends(require_admin),
):
    """Fire-and-forget: fetch Deezer images for all artists with deezer_id."""
    import os
    from celery import Celery
    _celery = Celery(
        broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        backend=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    )
    result = _celery.send_task("workers.tasks.fetch_artist_artworks")
    return SyncQueued(status="queued", task_id=result.id)


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
