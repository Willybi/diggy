from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from celery_client import celery
from dependencies import require_admin
from models import Artist, ArtistAlias, ArtistFlag, CatalogEntry, CrawlLog, SetArtist, User, WatchedEntity
from utils import normalize

router = APIRouter(prefix="/admin", tags=["admin"])


async def _ensure_alias(db: AsyncSession, artist_id: int, alias_name: str):
    """Create an ArtistAlias if it doesn't exist yet (by normalized_alias)."""
    norm = normalize(alias_name)
    if not norm:
        return
    existing = await db.execute(
        select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
    )
    if existing.scalar_one_or_none():
        return
    db.add(ArtistAlias(artist_id=artist_id, alias=alias_name, normalized_alias=norm))


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
    action: str  # "split" | "keep" | "skip"


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


# ---------- Endpoints ----------

def _send_sync_task() -> str:
    result = celery.send_task("workers.tasks.sync_artists")
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
    from celery.result import AsyncResult
    res = AsyncResult(task_id, app=celery)
    if res.state == "PENDING" or res.state == "STARTED":
        return SyncStatus(status="running")
    if res.state == "SUCCESS":
        return SyncStatus(status="done", result=res.result)
    if res.state == "FAILURE":
        return SyncStatus(status="error", error=str(res.result))
    return SyncStatus(status="running")


@router.post("/artists/fetch-artworks", response_model=SyncQueued)
async def fetch_artworks(
    _: User = Depends(require_admin),
):
    """Fire-and-forget: fetch Deezer images for all artists with deezer_id."""
    result = celery.send_task("workers.tasks.fetch_artist_artworks")
    return SyncQueued(status="queued", task_id=result.id)


@router.get("/artists/search-deezer", response_model=list[DeezerArtistHit])
async def search_deezer_artist(
    q: str,
    _: User = Depends(require_admin),
):
    """Search Deezer for an artist by name."""
    import requests as req
    try:
        resp = req.get("https://api.deezer.com/search/artist", params={"q": q, "limit": 10}, timeout=5)
        hits = []
        for h in resp.json().get("data", []):
            hits.append(DeezerArtistHit(
                deezer_id=str(h["id"]),
                name=h.get("name", ""),
                picture=h.get("picture_medium"),
                nb_fan=h.get("nb_fan"),
            ))
        return hits
    except Exception:
        return []


@router.patch("/artists/{artist_id}/deezer")
async def link_artist_deezer(
    artist_id: int,
    body: ArtistDeezerIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Manually link a deezer_id to an artist.

    - Fetches official name + artwork from Deezer
    - Updates artist name to Deezer official name
    - If another artist already has this deezer_id, merges into it (reassigns
      set_artists to the canonical artist, deletes the duplicate)
    """
    import requests as req
    from sqlalchemy import update as sa_update
    from deezer_enrich import _get_s3, upload_image_to_bucket

    result = await db.execute(select(Artist).where(Artist.id == artist_id))
    artist = result.scalar_one_or_none()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    # Unlink
    if not body.deezer_id:
        artist.deezer_id = None
        await db.commit()
        await db.refresh(artist)
        return {"id": artist.id, "name": artist.name, "deezer_id": None, "has_artwork": artist.has_artwork, "merged": False}

    # Fetch Deezer data first
    deezer_name = None
    pic_url = None
    try:
        resp = req.get(f"https://api.deezer.com/artist/{body.deezer_id}", timeout=5)
        data = resp.json()
        deezer_name = data.get("name")
        pic_url = data.get("picture_xl") or data.get("picture_big") or data.get("picture")
    except Exception:
        pass

    # Check if another artist already owns this deezer_id → merge
    existing_result = await db.execute(
        select(Artist).where(Artist.deezer_id == body.deezer_id, Artist.id != artist_id)
    )
    canonical = existing_result.scalar_one_or_none()

    if canonical:
        from sqlalchemy import delete as sa_delete
        # Save the duplicate's name as alias on canonical before deleting
        old_name = artist.name
        if normalize(old_name) != normalize(canonical.name):
            await _ensure_alias(db, canonical.id, old_name)
        # Find set_ids already linked to canonical → those would conflict on reassign
        conflict_sets = await db.execute(
            select(SetArtist.set_id).where(SetArtist.artist_id == canonical.id)
        )
        conflict_set_ids = {r[0] for r in conflict_sets.all()}
        # Drop duplicate's set_artists that would conflict
        if conflict_set_ids:
            await db.execute(
                sa_delete(SetArtist).where(
                    SetArtist.artist_id == artist_id,
                    SetArtist.set_id.in_(conflict_set_ids),
                )
            )
        # Reassign the rest to canonical
        await db.execute(
            sa_update(SetArtist)
            .where(SetArtist.artist_id == artist_id)
            .values(artist_id=canonical.id)
            .execution_options(synchronize_session=False)
        )
        # Delete the duplicate (CASCADE handles aliases, genres)
        await db.delete(artist)
        await db.flush()
        # Ensure canonical has artwork
        if pic_url and not canonical.has_artwork:
            s3 = _get_s3()
            if upload_image_to_bucket(s3, pic_url, f"{canonical.id}.jpg", "artist-artworks"):
                canonical.has_artwork = True
        await db.commit()
        await db.refresh(canonical)
        return {"id": canonical.id, "name": canonical.name, "deezer_id": canonical.deezer_id, "has_artwork": canonical.has_artwork, "merged": True}

    # No duplicate — just update this artist
    old_name = artist.name
    artist.deezer_id = body.deezer_id
    if deezer_name and normalize(deezer_name) != normalize(old_name):
        # Save old name as alias before renaming
        await _ensure_alias(db, artist.id, old_name)
        artist.name = deezer_name

    if pic_url:
        try:
            s3 = _get_s3()
            if upload_image_to_bucket(s3, pic_url, f"{artist.id}.jpg", "artist-artworks"):
                artist.has_artwork = True
        except Exception:
            pass

    await db.commit()
    await db.refresh(artist)
    return {"id": artist.id, "name": artist.name, "deezer_id": artist.deezer_id, "has_artwork": artist.has_artwork, "merged": False}


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


@router.post("/artists/flags/manual", response_model=ArtistFlagOut)
async def create_manual_flag(
    body: FlagManualIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Manually create a flag for an artist string (e.g. '/' separator)."""
    # Check if flag already exists
    existing = await db.execute(
        select(ArtistFlag).where(ArtistFlag.raw_artist_string == body.raw_artist_string)
    )
    flag = existing.scalar_one_or_none()
    if flag:
        # Re-open if previously skipped
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


# ---------- Set Artists ----------

@router.post("/sets/link-artists", response_model=SyncQueued)
async def link_set_artists_task(
    _: User = Depends(require_admin),
):
    """Fire-and-forget: parse set titles and link artists."""
    result = celery.send_task("workers.tasks.link_set_artists")
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/sets/enrich-tracks", response_model=SyncQueued)
async def enrich_set_tracks_task(
    _: User = Depends(require_admin),
):
    """Fire-and-forget: enrich set tracks missing Deezer/Beatport data."""
    result = celery.send_task("workers.tasks.enrich_set_tracks")
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/enrich-beatport", response_model=SyncQueued)
async def trigger_enrich_beatport(
    batch_size: int = 0,
    _: User = Depends(require_admin),
):
    """Fire-and-forget: enrich catalog entries via Beatport (BPM, key, label).
    batch_size: max entries to process (0 = all).
    """
    result = celery.send_task("workers.tasks.enrich_catalog_beatport", args=[batch_size])
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/reset-beatport")
async def reset_beatport(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Reset all Beatport-sourced data so a fresh crawl can re-enrich everything."""
    from models import CatalogEntry

    # Clear beatport_id and searched_at on all entries
    r1 = await db.execute(
        update(CatalogEntry).values(beatport_id=None, beatport_searched_at=None)
    )
    # Revert BPM sourced from Beatport
    r2 = await db.execute(
        update(CatalogEntry)
        .where(CatalogEntry.bpm_source == "beatport")
        .values(bpm=None, bpm_source=None)
    )
    # Revert key sourced from Beatport
    r3 = await db.execute(
        update(CatalogEntry)
        .where(CatalogEntry.key_source == "beatport")
        .values(key=None, key_source=None)
    )
    await db.commit()
    return {
        "status": "reset",
        "cleared": r1.rowcount,
        "bpm_reverted": r2.rowcount,
        "key_reverted": r3.rowcount,
    }


@router.post("/enrich-beatport/{catalog_id}")
async def enrich_single_beatport(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Enrich a single catalog entry via Beatport (sync, ~3s)."""
    from models import CatalogEntry
    from beatport.client import BeatportClient
    from beatport.enrich import enrich_from_beatport

    entry = (await db.execute(
        select(CatalogEntry).where(CatalogEntry.id == catalog_id)
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Track not found")

    client = BeatportClient()
    bp_track = None

    if entry.isrc:
        bp_track = client.search_track_by_isrc(entry.isrc)
    if not bp_track and entry.title:
        bp_track = client.search_track_validated(entry.title, entry.artist)

    if not bp_track:
        return {"status": "not_found", "catalog_id": catalog_id}

    changed = enrich_from_beatport(entry, bp_track)
    if changed:
        await db.commit()

    return {
        "status": "enriched" if changed else "unchanged",
        "catalog_id": catalog_id,
        "bpm": entry.bpm,
        "key": entry.key,
        "label": entry.label,
        "beatport_id": entry.beatport_id,
    }


@router.post("/sets/{set_id}/artists")
async def add_set_artist(
    set_id: int,
    body: SetArtistIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Manually link an artist to a set."""
    from models import DJSet
    existing = await db.execute(
        select(SetArtist).where(SetArtist.set_id == set_id, SetArtist.artist_id == body.artist_id)
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
    _: User = Depends(require_admin),
):
    """Remove an artist from a set."""
    from sqlalchemy import delete as sa_delete
    result = await db.execute(
        sa_delete(SetArtist).where(SetArtist.set_id == set_id, SetArtist.artist_id == artist_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.commit()
    return {"ok": True}


# ---------- Genres ----------

@router.get("/genres/unclassified-count")
async def genres_unclassified_count(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Count catalog entries with no genre assigned."""
    result = await db.execute(
        select(func.count(CatalogEntry.id))
        .where((CatalogEntry.genre.is_(None)) | (CatalogEntry.genre == ""))
    )
    return {"count": result.scalar_one()}


@router.post("/genres/auto-classify", response_model=SyncQueued)
async def genres_auto_classify(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Launch Beatport enrichment targeting only tracks without a genre."""
    count_result = await db.execute(
        select(func.count(CatalogEntry.id))
        .where((CatalogEntry.genre.is_(None)) | (CatalogEntry.genre == ""))
    )
    target_count = count_result.scalar_one()
    result = celery.send_task("workers.tasks.enrich_catalog_beatport", kwargs={"genre_only": True})
    return SyncQueued(status="queued", task_id=result.id)


# ---------- Playlist Artworks ----------

@router.post("/playlists/fetch-artworks")
async def fetch_all_playlist_artworks(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Fetch Deezer artworks for all playlists missing artwork. Synchronous."""
    import requests as req
    from deezer_enrich import _get_s3, upload_image_to_bucket, _ensure_bucket

    result = await db.execute(
        select(WatchedEntity).where(
            WatchedEntity.has_artwork.is_(False),
            WatchedEntity.source == "deezer",
        )
    )
    playlists = result.scalars().all()

    if not playlists:
        return {"fetched": 0, "failed": 0, "total": 0}

    s3 = _get_s3()
    _ensure_bucket(s3, "playlist-artworks")

    fetched = 0
    failed = 0
    for pl in playlists:
        try:
            resp = req.get(f"https://api.deezer.com/playlist/{pl.external_id}", timeout=5)
            data = resp.json()
            pic_url = data.get("picture_xl") or data.get("picture_big") or data.get("picture_medium")
            if pic_url and upload_image_to_bucket(s3, pic_url, f"{pl.id}.jpg", "playlist-artworks"):
                pl.has_artwork = True
                fetched += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    await db.commit()
    return {"fetched": fetched, "failed": failed, "total": len(playlists)}


# ---------- Crawl Logs ----------


@router.get("/crawl-logs")
async def get_crawl_logs(
    page: int = 1,
    per_page: int = 20,
    task_type: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """List crawl logs with pagination and filters."""
    query = select(CrawlLog).order_by(CrawlLog.started_at.desc())

    if task_type:
        query = query.where(CrawlLog.task_type == task_type)
    if status:
        query = query.where(CrawlLog.status == status)

    # Count total
    count_query = select(func.count(CrawlLog.id))
    if task_type:
        count_query = count_query.where(CrawlLog.task_type == task_type)
    if status:
        count_query = count_query.where(CrawlLog.status == status)
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    logs = (await db.execute(query)).scalars().all()

    return {
        "items": [
            {
                "id": log.id,
                "task_type": log.task_type,
                "target_id": log.target_id,
                "target_label": log.target_label,
                "source": log.source,
                "status": log.status,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "finished_at": log.finished_at.isoformat() if log.finished_at else None,
                "duration_ms": log.duration_ms,
                "stats": log.stats,
                "error_message": log.error_message,
                "celery_task_id": log.celery_task_id,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
