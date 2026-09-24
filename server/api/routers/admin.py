import logging
from datetime import date, datetime, timezone
from typing import Literal

import httpx
from celery_client import celery
from database import get_db
from dependencies import get_redis, require_admin
from fastapi import APIRouter, Depends, HTTPException, Query
from models import (
    AdminAuditLog,
    Artist,
    ArtistFlag,
    DJSet,
    SetFlag,
    User,
)
from schemas import (
    ArtistCandidateListOut,
    ArtistChannelResolveOut,
    ArtistDeezerIn,
    ArtistFlagListResponse,
    ArtistFlagOut,
    AuditLogResponse,
    BacklogResponse,
    ChannelCandidateListOut,
    ChannelCreateIn,
    ChannelListOut,
    ChannelOut,
    ChannelSearchListOut,
    ChannelUpdateIn,
    CohortItemOut,
    CohortListOut,
    CohortOverrideIn,
    CrawlLogsResponse,
    DeezerArtistHit,
    DeezerGenreLookupResponse,
    EnrichBeatportResponse,
    FetchPlaylistArtworksResponse,
    FlagManualIn,
    LinkDeezerResponse,
    MonitoringResponse,
    MonitoringSeriesResponse,
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
from services import (
    artist_service,
    catalog_service,
    channel_service,
    cohort_service,
    genre_service,
    monitoring_service,
    set_dedup_service,
)
from services.image_service import ImageService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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


@router.get("/tasks/{task_id}", response_model=SyncStatus)
async def sync_status(task_id: str, _: User = Depends(require_admin)):
    """Poller générique de statut d'une tâche Celery (toutes tâches, pas
    seulement artistes)."""
    from celery.result import AsyncResult

    res = AsyncResult(task_id, app=celery)
    if res.state in ("PENDING", "STARTED"):
        return SyncStatus(status="running")
    if res.state == "SUCCESS":
        return SyncStatus(status="done", result=res.result)
    if res.state == "FAILURE":
        return SyncStatus(status="error", error=str(res.result))
    return SyncStatus(status="running")


@router.post("/artists/link-deezer", response_model=SyncQueued)
async def link_artists_deezer(_: User = Depends(require_admin)):
    """Fire-and-forget: link artists with no deezer_id to Deezer (budget-capped,
    loop-safe). Returns task_id for polling via /tasks/{id}."""
    result = celery.send_task("workers.tasks.link_artists_deezer")
    return SyncQueued(status="queued", task_id=result.id)


@router.post("/artists/fetch-artworks", response_model=SyncQueued)
async def fetch_artworks(_: User = Depends(require_admin)):
    """Fire-and-forget: download Deezer images for linked artists missing artwork."""
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
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.deezer.com/search/artist",
                params={"q": q, "limit": 10},
            )
            data = resp.json()
        return [
            DeezerArtistHit(
                deezer_id=str(h["id"]),
                name=h.get("name", ""),
                picture=h.get("picture_medium"),
                nb_fan=h.get("nb_fan"),
            )
            for h in data.get("data", [])
        ]
    except Exception:
        logger.warning("Deezer artist search failed for %r", q, exc_info=True)
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


@router.get("/artists/flags", response_model=ArtistFlagListResponse)
async def list_flags(
    status: Literal["pending", "validated", "skipped"] = "pending",
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    total = await db.scalar(
        select(func.count()).select_from(ArtistFlag).where(ArtistFlag.status == status)
    )
    result = await db.execute(
        select(ArtistFlag)
        .where(ArtistFlag.status == status)
        .order_by(ArtistFlag.created_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    return {"total": total or 0, "items": result.scalars().all()}


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
            select(
                SetFlag,
                SetA.title.label("title_a"),
                SetB.title.label("title_b"),
                SetA.event_date.label("event_date_a"),
                SetB.event_date.label("event_date_b"),
            )
            .join(SetA, SetFlag.set_id_a == SetA.id)
            .outerjoin(SetB, SetFlag.set_id_b == SetB.id)
            .where(SetFlag.status == status)
            .order_by(SetFlag.confidence.desc().nulls_last(), SetFlag.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    # Batch-fetch member titles + event dates for group flags (C13.e)
    all_member_ids: set[int] = set()
    for row in rows:
        if row.SetFlag.member_set_ids:
            all_member_ids.update(row.SetFlag.member_set_ids)
    member_title_map: dict[int, str] = {}
    member_event_date_map: dict[int, date | None] = {}
    if all_member_ids:
        member_rows = (
            await db.execute(
                select(DJSet.id, DJSet.title, DJSet.event_date).where(
                    DJSet.id.in_(all_member_ids)
                )
            )
        ).all()
        member_title_map = {r[0]: r[1] for r in member_rows}
        member_event_date_map = {r[0]: r[2] for r in member_rows}

    items = [
        SetFlagOut(
            id=row.SetFlag.id,
            set_id_a=row.SetFlag.set_id_a,
            set_id_b=row.SetFlag.set_id_b,
            flag_type=row.SetFlag.flag_type,
            confidence=row.SetFlag.confidence,
            signals=row.SetFlag.signals,
            status=row.SetFlag.status,
            created_at=row.SetFlag.created_at,
            title_a=row.title_a or "",
            title_b=row.title_b,
            event_date_a=row.event_date_a,
            event_date_b=row.event_date_b,
            group_key=row.SetFlag.group_key,
            member_set_ids=row.SetFlag.member_set_ids,
            member_titles=(
                [
                    member_title_map.get(mid, "")
                    for mid in (row.SetFlag.member_set_ids or [])
                ]
            ),
            member_event_dates=(
                [
                    member_event_date_map.get(mid)
                    for mid in (row.SetFlag.member_set_ids or [])
                ]
            ),
        )
        for row in rows
    ]
    return SetFlagListResponse(total=total, items=items)


@router.post("/set-flags/{flag_id}/attach", response_model=SetFlagAttachResponse)
async def attach_set_flag(
    flag_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Attach sets flagged as duplicates or parts under a virtual parent."""
    try:
        parent_id, audit_details = await set_dedup_service.attach_flag(
            db, flag_id, admin.id
        )
    except LookupError as e:
        raise HTTPException(404, str(e))

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
    try:
        audit_details = await set_dedup_service.reject_flag(db, flag_id, admin.id)
    except LookupError as e:
        raise HTTPException(404, str(e))

    await _audit(db, admin, "reject_set_flag", "set_flag", flag_id, audit_details)
    await db.commit()
    return {"ok": True}


@router.post("/sets/{set_id}/detach", response_model=OkResponse)
async def detach_set(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Detach a set from its virtual parent."""
    try:
        audit_details = await set_dedup_service.detach_set_from_parent(db, set_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    await _audit(db, admin, "detach_set", "set", set_id, audit_details)
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


# ---------- Monitoring ----------


@router.get("/monitoring", response_model=MonitoringResponse)
async def get_monitoring(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Instant monitoring status: latest run per task + latest backlog snapshot.

    The time-series moved to GET /admin/monitoring/series (L3 split — the status
    is cheap and always fresh, the series are heavy and cacheable). ``integrity``
    is read from the latest snapshot payload (computed hourly by
    snapshot_backlogs since L1, no longer recomputed per display) — None until a
    post-deploy snapshot carries the key. Thin router — work in monitoring_service.
    """
    status = await monitoring_service.get_current_status(db)
    snapshot = status.get("latest_snapshot") or {}
    return {
        "status": status,
        "integrity": (snapshot.get("payload") or {}).get("integrity"),
    }


@router.get("/monitoring/series", response_model=MonitoringSeriesResponse)
async def get_monitoring_series(
    days: int = Query(14, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin=Depends(require_admin),
):
    """Backlog + throughput time-series (Redis-cached, fail-open, TTL 10 min).

    Thin router — the cache + aggregation live in monitoring_service.
    """
    return await monitoring_service.get_monitoring_series(db, redis, days)


# ---------- Backlog dashboard ----------


@router.get("/backlog", response_model=BacklogResponse)
async def get_backlog(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin=Depends(require_admin),
):
    """Aggregated backlog counters for the admin dashboard.

    Thin — the whole aggregation (latest snapshot payload + live COUNTs + the
    fail-open DLQ read) lives in monitoring_service.
    """
    return await monitoring_service.get_backlog_counters(db, redis)


# ---------- Audit log ----------


@router.get("/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    page: int = 1,
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Paginated admin audit-log entries (newest first), author email resolved.

    Thin router — the paginated read lives in monitoring_service.
    """
    return await monitoring_service.get_audit_log(db, page, per_page)


# ---------- Artist cohort (C14.a) ----------


@router.get("/cohort", response_model=CohortListOut)
async def list_cohort(
    tier: int | None = Query(None, ge=1, le=3),
    override: Literal["pinned", "excluded"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Paginated view of the derived artist cohort (filter by tier / override).

    Thin router — the joined listing lives in cohort_service.
    """
    return await cohort_service.list_cohort(
        db, tier=tier, override=override, page=page, page_size=page_size
    )


@router.patch("/cohort/{artist_id}", response_model=CohortItemOut)
async def update_cohort_override(
    artist_id: int,
    body: CohortOverrideIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Pin / exclude / force-tier an artist. The row is created if absent (an
    artist outside the cohort can be pinned in). 404 on an unknown artist.

    PATCH semantics: only the fields explicitly present in the body are applied —
    so ``{"forced_tier": null}`` UN-forces (back to the auto/computed tier) while
    an absent ``forced_tier`` leaves the existing force untouched."""
    changes = body.model_dump(exclude_unset=True)
    try:
        item = await cohort_service.set_override(db, artist_id, changes=changes)
    except LookupError as e:
        raise HTTPException(404, str(e))

    await _audit(db, admin, "cohort_override", "artist", artist_id, changes)
    await db.commit()
    return item


@router.post("/cohort/recompute", response_model=SyncQueued)
async def recompute_cohort(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Fire-and-forget: recompute the derived cohort. Poll via /tasks/{id}."""
    result = celery.send_task("workers.tasks.recompute_artist_cohort")
    await _audit(db, admin, "cohort_recompute", "cohort", None, {"task_id": result.id})
    await db.commit()
    return SyncQueued(status="queued", task_id=result.id)


# ---------- Watched channels (C14.b) ----------


@router.get("/channels", response_model=ChannelListOut)
async def list_channels(
    watched: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Paginated view of the curated YouTube channels (filter by watched).

    Thin router — the listing lives in channel_service.
    """
    return await channel_service.list_channels(
        db, watched=watched, page=page, page_size=page_size
    )


@router.get("/channels/candidates", response_model=ChannelCandidateListOut)
async def list_channel_candidates(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    """Seed of channels known to the base (trackid_index) but not yet curated,
    ranked by discovery value (least-covered first). Each candidate carries its
    cached YouTube pre-selection READ-ONLY from Redis — this endpoint NEVER runs a
    search (quota-safe on render); a resolution goes through /candidates/resolve.
    Thin router."""
    return await channel_service.list_candidates(db, limit=limit, redis=redis)


@router.get("/channels/candidates/resolve", response_model=ChannelSearchListOut)
async def resolve_channel_candidate(
    name: str,
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    """Resolve ONE candidate name to YouTube channel hits (add-by-search pick).

    NB quota: a resolution spends 100 YouTube Data API units — the result is
    cached (TTL CANDIDATE_RESOLVE_TTL_SECONDS), so an already-resolved name costs
    0. Called on an explicit operator click, never on listing render. Thin router."""
    return await channel_service.resolve_candidate(name, redis)


@router.get("/channels/search", response_model=ChannelSearchListOut)
async def search_channels(
    q: str,
    limit: int = Query(6, ge=1, le=10),
    _admin: User = Depends(require_admin),
):
    """Search YouTube for channels matching ``q`` (add-by-search picker). Thin router.

    NB quota: each search spends 100 YouTube Data API units, so the service gates
    the query length (>= 2 chars after stripping) to avoid burning the quota on
    stray keystrokes — a too-short ``q`` returns an empty list without any call.
    """
    return await channel_service.search_youtube(q, limit=limit)


@router.get("/channels/artist-candidates", response_model=ArtistCandidateListOut)
async def list_artist_candidates(
    limit: int = Query(50, ge=1, le=200),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    """Cohort artists proposed as watched-channel candidates (C14.b 🅱).

    LIVE over ``artist_cohort`` × ``artists``, past the « real artist » gate and
    not yet curated into ``channels``, ranked by tier then relevance. Each item
    carries its cached artist→channel pre-selection READ-ONLY from Redis — this
    endpoint NEVER resolves (quota-safe on render); a resolution goes through
    /artist-candidates/resolve. Thin router."""
    return await channel_service.list_artist_candidates(
        db, redis=redis, limit=limit, page=page
    )


@router.get(
    "/channels/artist-candidates/resolve", response_model=ArtistChannelResolveOut
)
async def resolve_artist_candidate(
    name: str,
    redis=Depends(get_redis),
    _admin: User = Depends(require_admin),
):
    """Resolve ONE artist name to its YouTube channel (cascade Wikidata →
    MusicBrainz → verified search), CACHE-FIRST.

    NB quota: only the search tier spends 100 YouTube Data API units, and the
    result (channel found OR nothing) is cached (TTL CANDIDATE_RESOLVE_TTL_SECONDS)
    — an already-resolved name costs 0. Called on an explicit operator click, the
    ONLY path that spends a resolution. An unresolved artist serialises as the
    empty ArtistChannelResolveOut shape. Thin router."""
    result = await channel_service.resolve_artist_candidate(name, redis)
    return result or {}


@router.post("/channels", response_model=ChannelOut)
async def add_channel(
    body: ChannelCreateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Add (or re-watch) a YouTube channel by URL/handle. 400 if unresolvable."""
    try:
        item = await channel_service.add_channel(db, body)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await _audit(db, admin, "channel_add", "channel", item["id"], {"url": body.url})
    await db.commit()

    # Fire-and-forget one-shot historical backfill (C14.b, L7): page the channel's
    # « uploads » playlist to catch its back-catalogue. Dispatched AFTER the commit
    # so the worker can load the row in its own session. Best-effort — a dispatch
    # failure must NOT fail the add (the nightly crawl still covers the channel).
    # No re-dispatch on the PATCH re-watch path (see update_channel_override).
    try:
        celery.send_task(
            "workers.tasks.backfill_youtube_channel", args=[item["id"]]
        )
    except Exception:
        logger.warning(
            "add_channel: backfill dispatch failed for channel %s (best-effort)",
            item["id"],
            exc_info=True,
        )
    return item


@router.patch("/channels/{channel_id}", response_model=ChannelOut)
async def update_channel_override(
    channel_id: int,
    body: ChannelUpdateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Toggle watched/excluded/type/artist on a channel. 404 on unknown id.

    PATCH semantics: only the fields explicitly present in the body are applied.
    Deliberately does NOT dispatch the historical backfill even when this re-sets
    ``watched=True`` — the one-shot backfill belongs to the add path (POST
    /channels); the nightly crawl keeps a re-watched channel current on its own."""
    changes = body.model_dump(exclude_unset=True)
    try:
        item = await channel_service.set_override(db, channel_id, changes=changes)
    except LookupError as e:
        raise HTTPException(404, str(e))

    await _audit(db, admin, "channel_override", "channel", channel_id, changes)
    await db.commit()
    return item
