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
    DJSet,
    SetFlag,
    SetFlagStatus,
    User,
)
from schemas import (
    ArtistDeezerIn,
    ArtistFlagOut,
    CrawlLogsResponse,
    DeezerArtistHit,
    DeezerGenreLookupResponse,
    EnrichBeatportResponse,
    FetchPlaylistArtworksResponse,
    FlagManualIn,
    LinkDeezerResponse,
    NoDeezerResponse,
    OkResponse,
    ResetBeatportResponse,
    ResolveIn,
    SetArtistAddResponse,
    SetArtistIn,
    SetFlagAttachResponse,
    SetFlagListResponse,
    SetFlagOut,
    SyncQueued,
    SyncStatus,
    UnclassifiedCountResponse,
)
from services import artist_service, catalog_service, genre_service
from services.image_service import ImageService
from sqlalchemy import func, select
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


@router.patch("/artists/{artist_id}/deezer", response_model=LinkDeezerResponse)
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


@router.patch("/artists/{artist_id}/no-deezer", response_model=NoDeezerResponse)
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


@router.post("/sets/{set_id}/artists", response_model=SetArtistAddResponse)
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


@router.delete("/sets/{set_id}/artists/{artist_id}", response_model=OkResponse)
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


# ---------- Set Flags ----------


@router.get("/set-flags", response_model=SetFlagListResponse)
async def list_set_flags(
    status: Literal["pending", "attached", "rejected"] = "pending",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """List set dedup flags filtered by status."""
    from sqlalchemy.orm import aliased

    SetA = aliased(DJSet)
    SetB = aliased(DJSet)

    total = (
        await db.execute(
            select(func.count()).select_from(SetFlag).where(SetFlag.status == status)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(SetFlag, SetA.title.label("title_a"), SetB.title.label("title_b"))
            .join(SetA, SetFlag.set_id_a == SetA.id)
            .outerjoin(SetB, SetFlag.set_id_b == SetB.id)
            .where(SetFlag.status == status)
            .order_by(SetFlag.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    # Batch-fetch member titles for group flags
    all_member_ids: set[int] = set()
    for flag, _, _ in rows:
        if flag.member_set_ids:
            all_member_ids.update(flag.member_set_ids)
    member_title_map: dict[int, str] = {}
    if all_member_ids:
        title_rows = (
            await db.execute(
                select(DJSet.id, DJSet.title).where(DJSet.id.in_(all_member_ids))
            )
        ).all()
        member_title_map = {r[0]: r[1] for r in title_rows}

    items = [
        SetFlagOut(
            id=flag.id,
            set_id_a=flag.set_id_a,
            set_id_b=flag.set_id_b,
            flag_type=flag.flag_type,
            confidence=flag.confidence,
            signals=flag.signals,
            status=flag.status,
            created_at=flag.created_at,
            title_a=title_a or "",
            title_b=title_b,
            group_key=flag.group_key,
            member_set_ids=flag.member_set_ids,
            member_titles=(
                [member_title_map.get(mid, "") for mid in (flag.member_set_ids or [])]
            ),
        )
        for flag, title_a, title_b in rows
    ]
    return SetFlagListResponse(total=total, items=items)


@router.post("/set-flags/{flag_id}/attach", response_model=SetFlagAttachResponse)
async def attach_set_flag(
    flag_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Attach sets flagged as duplicates or parts under a virtual parent."""
    from services.set_dedup_service import (
        find_or_create_virtual_parent,
        materialize_parent,
    )

    flag = (
        await db.execute(select(SetFlag).where(SetFlag.id == flag_id))
    ).scalar_one_or_none()
    if not flag or flag.status != SetFlagStatus.pending:
        raise HTTPException(404, "Flag not found or already resolved")

    now = datetime.now(timezone.utc)

    if flag.member_set_ids:
        # Group flag: attach all members to a shared virtual parent
        member_ids: list[int] = flag.member_set_ids
        members = (
            await db.execute(select(DJSet).where(DJSet.id.in_(member_ids)))
        ).scalars().all()
        if len(members) < 2:
            raise HTTPException(404, "Not enough member sets found")

        dates = [m.played_date for m in members if m.played_date is not None]
        played_date = min(dates) if dates else None
        base_title = flag.group_key or members[0].title

        parent_id, _ = await find_or_create_virtual_parent(
            db, member_ids[0], member_ids[1], played_date, base_title
        )
        # Attach remaining members (beyond the first pair)
        for mid in member_ids[2:]:
            member = await db.get(DJSet, mid)
            if member and member.parent_set_id is None:
                member.parent_set_id = parent_id
        await db.flush()

        await materialize_parent(db, parent_id)

        audit_details = {
            "member_set_ids": member_ids,
            "parent_id": parent_id,
            "group_key": flag.group_key,
        }
    else:
        # Pairwise flag
        set_a = (
            await db.execute(select(DJSet).where(DJSet.id == flag.set_id_a))
        ).scalar_one_or_none()
        set_b = (
            await db.execute(select(DJSet).where(DJSet.id == flag.set_id_b))
        ).scalar_one_or_none()
        if not set_a or not set_b:
            raise HTTPException(404, "Set not found")

        parent_id, created = await find_or_create_virtual_parent(
            db, flag.set_id_a, flag.set_id_b, None, None
        )
        if created:
            await materialize_parent(db, parent_id)

        audit_details = {
            "set_id_a": flag.set_id_a,
            "set_id_b": flag.set_id_b,
            "parent_id": parent_id,
        }

    flag.status = SetFlagStatus.attached
    flag.resolved_by = admin.id
    flag.resolved_at = now

    await _audit(db, admin, "attach_set_flag", "set_flag", flag_id, audit_details)
    await db.commit()
    return SetFlagAttachResponse(ok=True, parent_id=parent_id)


@router.post("/set-flags/{flag_id}/reject", response_model=OkResponse)
async def reject_set_flag(
    flag_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Reject a set dedup flag."""
    flag = (
        await db.execute(select(SetFlag).where(SetFlag.id == flag_id))
    ).scalar_one_or_none()
    if not flag or flag.status != SetFlagStatus.pending:
        raise HTTPException(404, "Flag not found or already resolved")

    now = datetime.now(timezone.utc)
    flag.status = SetFlagStatus.rejected
    flag.resolved_by = admin.id
    flag.resolved_at = now

    await _audit(
        db,
        admin,
        "reject_set_flag",
        "set_flag",
        flag_id,
        {
            "set_id_a": flag.set_id_a,
            "set_id_b": flag.set_id_b,
            **({"group_key": flag.group_key} if flag.group_key else {}),
        },
    )
    await db.commit()
    return {"ok": True}


@router.post("/sets/{set_id}/detach", response_model=OkResponse)
async def detach_set(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Detach a set from its virtual parent."""
    from sqlalchemy import delete as sa_delete

    dj_set = (
        await db.execute(select(DJSet).where(DJSet.id == set_id))
    ).scalar_one_or_none()
    if not dj_set:
        raise HTTPException(404, "Set not found")
    if dj_set.parent_set_id is None:
        raise HTTPException(400, "Ce set n'est pas attaché à un parent")

    parent_id = dj_set.parent_set_id
    dj_set.parent_set_id = None
    await db.flush()

    siblings = (
        await db.execute(select(DJSet).where(DJSet.parent_set_id == parent_id))
    ).scalars().all()

    if len(siblings) <= 1:
        if len(siblings) == 1:
            siblings[0].parent_set_id = None
        await db.execute(sa_delete(DJSet).where(DJSet.id == parent_id))

    await _audit(
        db, admin, "detach_set", "set", set_id, {"parent_id": parent_id}
    )
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


@router.post("/reset-beatport", response_model=ResetBeatportResponse)
async def reset_beatport(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Reset all Beatport-sourced data."""
    result = await artist_service.reset_beatport(db)
    await _audit(db, admin, "reset_beatport", None, None, result)
    await db.commit()
    return result


@router.post("/enrich-beatport/{catalog_id}", response_model=EnrichBeatportResponse)
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


@router.get("/genres/unclassified-count", response_model=UnclassifiedCountResponse)
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


@router.get("/deezer-genre/{catalog_id}", response_model=DeezerGenreLookupResponse)
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


@router.post("/playlists/fetch-artworks", response_model=FetchPlaylistArtworksResponse)
async def fetch_all_playlist_artworks(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Fetch Deezer artworks for all playlists missing artwork. Synchronous."""
    return await ImageService.fetch_playlist_artworks(db)


# ---------- Crawl Logs ----------


@router.get("/crawl-logs", response_model=CrawlLogsResponse)
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
