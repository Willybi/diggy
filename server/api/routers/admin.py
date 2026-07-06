from datetime import datetime, timezone
from typing import Literal

from celery_client import celery
from database import get_db
from dependencies import require_admin
from fastapi import APIRouter, Depends, HTTPException, Query
from models import (
    AdminAuditLog,
    Artist,
    ArtistFlag,
    User,
)
from pydantic import BaseModel
from services import artist_service, catalog_service, genre_service
from services.image_service import ImageService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["admin"])


async def _audit(
    db: AsyncSession,
    user: User,
    action: str,
    target_type: str = None,
    target_id: int = None,
    details: dict = None,
):
    db.add(
        AdminAuditLog(
            user_id=user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
    )


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


class SyncStatus(BaseModel):
    status: str  # pending | running | done | error
    result: dict | None = None
    error: str | None = None


class ResolveIn(BaseModel):
    action: Literal["split", "keep", "skip"]


class ArtistDeezerIn(BaseModel):
    deezer_id: str


class FlagManualIn(BaseModel):
    raw_artist_string: str
    tokens: list[str]
    reason: str = "manual"


class SetArtistIn(BaseModel):
    artist_id: int
    role: str = "dj"


class DeezerArtistHit(BaseModel):
    deezer_id: str
    name: str
    picture: str | None = None
    nb_fan: int | None = None


# ---------- Artist sync ----------


@router.post("/artists/sync", response_model=SyncQueued)
async def sync_artists(_: User = Depends(require_admin)):
    """Fire-and-forget artist sync. Returns task_id for polling."""
    result = celery.send_task("workers.tasks.sync_artists")
    return SyncQueued(status="queued", task_id=result.id)


@router.get("/artists/sync/status/{task_id}", response_model=SyncStatus)
async def sync_status(task_id: str, _: User = Depends(require_admin)):
    """Poll Celery task result."""
    from celery.result import AsyncResult

    res = AsyncResult(task_id, app=celery)
    if res.state in ("PENDING", "STARTED"):
        return SyncStatus(status="running")
    if res.state == "SUCCESS":
        return SyncStatus(status="done", result=res.result)
    if res.state == "FAILURE":
        return SyncStatus(status="error", error=str(res.result))
    return SyncStatus(status="running")


@router.post("/artists/fetch-artworks", response_model=SyncQueued)
async def fetch_artworks(_: User = Depends(require_admin)):
    """Fire-and-forget: fetch Deezer images for all artists with deezer_id."""
    result = celery.send_task("workers.tasks.fetch_artist_artworks")
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/artists/backfill-multi-artists", response_model=SyncQueued)
async def backfill_multi_artists(_: User = Depends(require_admin)):
    """Re-fetch Deezer data for tracks with 1 artist to discover missing contributors."""
    result = celery.send_task("workers.tasks.backfill_multi_artists")
    return SyncQueued(status="queued", task_id=result.id)


@router.get("/artists/search-deezer", response_model=list[DeezerArtistHit])
async def search_deezer_artist(
    q: str = Query(..., max_length=100),
    _: User = Depends(require_admin),
):
    """Search Deezer for an artist by name."""
    import requests as req

    try:
        resp = req.get(
            "https://api.deezer.com/search/artist",
            params={"q": q, "limit": 10},
            timeout=5,
        )
        return [
            DeezerArtistHit(
                deezer_id=str(h["id"]),
                name=h.get("name", ""),
                picture=h.get("picture_medium"),
                nb_fan=h.get("nb_fan"),
            )
            for h in resp.json().get("data", [])
        ]
    except Exception:
        return []


@router.patch("/artists/{artist_id}/deezer")
async def link_artist_deezer(
    artist_id: int,
    body: ArtistDeezerIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Manually link a deezer_id to an artist (fetch name + artwork, merge if duplicate)."""
    try:
        result = await artist_service.link_to_deezer(db, artist_id, body.deezer_id)
    except LookupError as e:
        raise HTTPException(404, str(e))

    await _audit(
        db, admin, "merge_artist" if result.get("merged") else "link_deezer",
        "artist", result["id"],
        {
            "deezer_id": body.deezer_id,
            "merged_id": result.get("merged_id"),
            "merged_name": result.get("merged_name"),
            "old_name": result.get("name"),
        },
    )
    await db.commit()
    return result


@router.patch("/artists/{artist_id}/no-deezer")
async def mark_no_deezer(
    artist_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Mark an artist as not on Deezer (sentinel deezer_id = 'NOT_FOUND')."""
    result = await db.execute(select(Artist).where(Artist.id == artist_id))
    artist = result.scalar_one_or_none()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    artist.deezer_id = "NOT_FOUND"
    await db.commit()
    return {"id": artist.id, "name": artist.name}


# ---------- Flags ----------


@router.post("/artists/flags/manual", response_model=ArtistFlagOut)
async def create_manual_flag(
    body: FlagManualIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Manually create a flag for an artist string."""
    existing = await db.execute(
        select(ArtistFlag).where(ArtistFlag.raw_artist_string == body.raw_artist_string)
    )
    flag = existing.scalar_one_or_none()
    if flag:
        flag.tokens = body.tokens
        flag.reason = body.reason
        flag.status = "pending"
        flag.updated_at = datetime.now(timezone.utc)
    else:
        flag = ArtistFlag(
            raw_artist_string=body.raw_artist_string,
            reason=body.reason,
            tokens=body.tokens,
            deezer_ids={},
            status="pending",
        )
        db.add(flag)
    await db.commit()
    await db.refresh(flag)
    return flag


@router.get("/artists/flags", response_model=list[ArtistFlagOut])
async def list_flags(
    status: Literal["pending", "validated", "skipped"] = "pending",
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
    try:
        return await artist_service.resolve_flag(db, flag_id, body.action)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


# ---------- Set Artists ----------


@router.post("/sets/link-artists", response_model=SyncQueued)
async def link_set_artists_task(_: User = Depends(require_admin)):
    """Fire-and-forget: parse set titles and link artists."""
    result = celery.send_task("workers.tasks.link_set_artists")
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/sets/enrich-tracks", response_model=SyncQueued)
async def enrich_set_tracks_task(_: User = Depends(require_admin)):
    """Fire-and-forget: enrich set tracks missing Deezer/Beatport data."""
    result = celery.send_task("workers.tasks.enrich_set_tracks")
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/sets/{set_id}/artists")
async def add_set_artist(
    set_id: int,
    body: SetArtistIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Manually link an artist to a set."""
    from models import DJSet, SetArtist

    existing = await db.execute(
        select(SetArtist).where(
            SetArtist.set_id == set_id, SetArtist.artist_id == body.artist_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already linked")
    s = await db.execute(select(DJSet).where(DJSet.id == set_id))
    if not s.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Set not found")
    a = await db.execute(select(Artist).where(Artist.id == body.artist_id))
    if not a.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Artist not found")
    db.add(SetArtist(set_id=set_id, artist_id=body.artist_id, role=body.role, position=0))
    await db.commit()
    return {"set_id": set_id, "artist_id": body.artist_id, "role": body.role}


@router.delete("/sets/{set_id}/artists/{artist_id}")
async def remove_set_artist(
    set_id: int,
    artist_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Remove an artist from a set."""
    from models import SetArtist
    from sqlalchemy import delete as sa_delete

    result = await db.execute(
        sa_delete(SetArtist).where(
            SetArtist.set_id == set_id, SetArtist.artist_id == artist_id
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    await _audit(db, admin, "remove_set_artist", "set", set_id, {"artist_id": artist_id})
    await db.commit()
    return {"ok": True}


# ---------- Beatport ----------


@router.post("/enrich-beatport", response_model=SyncQueued)
async def trigger_enrich_beatport(
    batch_size: int = 0,
    _: User = Depends(require_admin),
):
    """Fire-and-forget: enrich catalog entries via Beatport."""
    result = celery.send_task(
        "workers.tasks.enrich_catalog_beatport", args=[batch_size]
    )
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/reset-beatport")
async def reset_beatport(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Reset all Beatport-sourced data."""
    result = await artist_service.reset_beatport(db)
    await _audit(db, admin, "reset_beatport", None, None, result)
    await db.commit()
    return result


@router.post("/enrich-beatport/{catalog_id}")
async def enrich_single_beatport(
    catalog_id: int,
    force_genre: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Enrich a single catalog entry via Beatport (sync, ~3s)."""
    try:
        return await artist_service.enrich_single_beatport(db, catalog_id, force_genre)
    except LookupError as e:
        raise HTTPException(404, str(e))


# ---------- Genres ----------


@router.get("/genres/unclassified-count")
async def genres_unclassified_count(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Count catalog entries with no genre assigned."""
    from models import CatalogEntry
    from sqlalchemy import func

    result = await db.execute(
        select(func.count(CatalogEntry.id)).where(
            func.coalesce(func.array_length(CatalogEntry.genres, 1), 0) == 0
        )
    )
    return {"count": result.scalar_one()}


@router.post("/genres/auto-classify", response_model=SyncQueued)
async def genres_auto_classify(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Launch Beatport enrichment targeting only tracks without a genre."""
    result = celery.send_task(
        "workers.tasks.enrich_catalog_beatport", kwargs={"genre_only": True}
    )
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/genres/reclassify", response_model=SyncQueued)
async def genres_reclassify(
    eta: str | None = None,
    _: User = Depends(require_admin),
):
    """Reclassify ALL genres (Beatport first, Deezer fallback)."""
    kwargs = {}
    if eta:
        from datetime import datetime as dt

        try:
            scheduled_at = dt.fromisoformat(eta.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Format eta invalide (ISO 8601 attendu)")
        kwargs["eta"] = scheduled_at
    result = celery.send_task("workers.tasks.reclassify_all_genres", **kwargs)
    return SyncQueued(status="queued", task_id=result.id)


@router.get("/deezer-genre/{catalog_id}")
async def deezer_genre_lookup(
    catalog_id: int,
    apply: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Fetch genre from Deezer for a catalog entry."""
    try:
        return await genre_service.lookup_deezer_genres(db, catalog_id, apply)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- Playlist Artworks ----------


@router.post("/playlists/fetch-artworks")
async def fetch_all_playlist_artworks(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Fetch Deezer artworks for all playlists missing artwork. Synchronous."""
    return await ImageService.fetch_playlist_artworks(db)


# ---------- Crawl Logs ----------


@router.get("/crawl-logs")
async def get_crawl_logs(
    page: int = 1,
    per_page: int = 20,
    task_type: str | None = Query(None, max_length=100),
    status: str | None = Query(None, max_length=50),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """List crawl logs with pagination and filters."""
    return await catalog_service.get_crawl_logs(db, page, per_page, task_type, status)
