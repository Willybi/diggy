import re
from datetime import datetime, timezone

from celery_client import celery
from database import get_db
from dependencies import get_current_user, get_current_user_optional
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException, Query
from models import (
    Artist,
    CatalogArtist,
    DJSet,
    SetArtist,
    SetTrack,
    User,
    UserOpinion,
    UserSetFollow,
    UserTrack,
)
from schemas import (
    ArtistRef,
    DJSetDetailOut,
    SetArtistDetailOut,
    SetImportIn,
    SetImportResponse,
    SetListItemOut,
    SetListResponse,
    SetTrackDetailOut,
    TrackIDSearchResult,
)
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/sets", tags=["sets"])


# ---------- Search TrackID ----------


@router.get("/search", response_model=list[TrackIDSearchResult])
async def search_trackid_sets(
    q: str,
    page: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Search sets on TrackID.net and indicate which are already imported."""
    from trackid.client import TrackIDClient

    async with TrackIDClient() as client:
        audiostreams, _ = await client.search_sets(keywords=q, current_page=page)

    # Check which are already imported
    ext_ids = [str(a["id"]) for a in audiostreams]
    imported = set()
    if ext_ids:
        result = await db.execute(
            select(DJSet.external_id).where(
                DJSet.external_id.in_(ext_ids), DJSet.source == "trackid"
            )
        )
        imported = {r[0] for r in result.all()}

    return [
        TrackIDSearchResult(
            trackid_id=a["id"],
            slug=a.get("slug", ""),
            title=a.get("title", ""),
            channel=a.get("channel"),
            artwork_url=a.get("artworkUrl"),
            track_count=a.get("trackCount", 0),
            duration=a.get("duration"),
            created_on=a.get("createdOn"),
            already_imported=str(a["id"]) in imported,
        )
        for a in audiostreams
    ]


# ---------- List ----------


@router.get("/", response_model=SetListResponse)
async def list_sets(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            DJSet,
            func.count(SetTrack.id).label("total_tracks"),
            func.count(
                case(
                    (
                        and_(
                            SetTrack.is_id.is_(False), SetTrack.catalog_id.isnot(None)
                        ),
                        SetTrack.id,
                    ),
                )
            ).label("identified_tracks"),
        )
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        .where(DJSet.parent_set_id.is_(None))
        .group_by(DJSet.id)
        .order_by(DJSet.played_date.desc().nulls_last(), DJSet.created_at.desc())
    )

    if q:
        stmt = stmt.where(DJSet.title.ilike(f"%{q}%"))

    # Total count
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar()

    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()

    # Batch-fetch artists
    set_ids = [row[0].id for row in rows]
    set_artists_map: dict[int, list[str]] = {}
    if set_ids:
        aq = await db.execute(
            select(SetArtist.set_id, Artist.name)
            .join(Artist, Artist.id == SetArtist.artist_id)
            .where(SetArtist.set_id.in_(set_ids))
            .order_by(SetArtist.position)
        )
        for sid, name in aq.all():
            set_artists_map.setdefault(sid, []).append(name)

    items = [
        SetListItemOut(
            id=s.id,
            title=s.title,
            source=s.source,
            source_url=s.source_url,
            played_date=s.played_date,
            duration_ms=s.duration_ms,
            has_artwork=s.has_artwork,
            total_tracks=total_tracks,
            identified_tracks=identified,
            artists=set_artists_map.get(s.id, []),
        )
        for s, total_tracks, identified in rows
    ]
    return SetListResponse(total=total, items=items)


# ---------- Import ----------


@router.post("/import", response_model=SetImportResponse)
async def import_set_url(
    body: SetImportIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a set from a TrackID URL or slug, and auto-follow it."""
    slug = None
    if body.slug:
        slug = body.slug.strip().rstrip("/")
    elif body.url:
        match = re.search(r"trackid\.net/audiostream/(.+?)(?:\?|$)", body.url.strip())
        if match:
            slug = match.group(1).rstrip("/")
    if not slug:
        raise HTTPException(status_code=422, detail="URL TrackID ou slug requis")

    from trackid.client import TrackIDClient
    from trackid.importer import import_audiostream

    async with TrackIDClient() as client:
        detail = await client.get_set_detail(slug)
        if not detail:
            raise HTTPException(status_code=404, detail="Set introuvable sur TrackID")

        ext_id = str(detail.get("id") or slug.split("/")[-1])

        # Check if already imported
        existing = await db.execute(
            select(DJSet).where(DJSet.external_id == ext_id, DJSet.source == "trackid")
        )
        dj_set = existing.scalar_one_or_none()

        if not dj_set:
            audiostream = {"id": ext_id, "slug": slug}
            dj_set, _ = await import_audiostream(
                db, client, audiostream, prefetched_detail=detail
            )

        if not dj_set:
            raise HTTPException(status_code=500, detail="Import échoué")

        # Auto-like (which also auto-follows via _sync_set_follow)
        eo = await db.execute(
            select(UserOpinion).where(
                UserOpinion.user_id == user.id,
                UserOpinion.entity_type == "set",
                UserOpinion.entity_key == str(dj_set.id),
            )
        )
        if not eo.scalar_one_or_none():
            db.add(
                UserOpinion(
                    user_id=user.id,
                    entity_type="set",
                    entity_key=str(dj_set.id),
                    opinion="liked",
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                UserSetFollow(
                    user_id=user.id,
                    set_id=dj_set.id,
                    followed_at=datetime.now(timezone.utc),
                )
            )

        await db.commit()
        await db.refresh(dj_set)

        # Fire track resolution in background
        celery.send_task("workers.tasks.resolve_set_tracks")

        return {"id": dj_set.id, "title": dj_set.title}


# ---------- Detail ----------


@router.get("/{set_id}", response_model=DJSetDetailOut)
async def get_set_detail(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)

    # 1. DJSet
    result = await db.execute(
        select(DJSet)
        .options(
            selectinload(DJSet.artist_links).selectinload(SetArtist.artist),
            selectinload(DJSet.tracks).selectinload(SetTrack.catalog),
        )
        .where(DJSet.id == set_id)
    )
    dj_set = result.scalar_one_or_none()
    if not dj_set:
        raise HTTPException(status_code=404, detail="Set not found")

    # 2. Artists
    artists = [
        SetArtistDetailOut(
            artist_id=sa.artist_id,
            artist_name=sa.artist.name if sa.artist else "",
            has_artwork=sa.artist.has_artwork if sa.artist else False,
            role=sa.role,
            position=sa.position,
        )
        for sa in sorted(dj_set.artist_links, key=lambda x: x.position or 99)
    ]

    # 3. Collect catalog_ids to batch-check lib status + artists.
    # in_lib is scoped to the current user; guests (uid None) never own tracks.
    catalog_ids = [t.catalog_id for t in dj_set.tracks if t.catalog_id]
    lib_set = set()
    if uid is not None and catalog_ids:
        lib_result = await db.execute(
            select(UserTrack.catalog_id).where(
                UserTrack.user_id == uid,
                UserTrack.catalog_id.in_(catalog_ids),
            )
        )
        lib_set = {r[0] for r in lib_result.all()}

    # Batch-fetch linked artists for tracklist
    from collections import defaultdict

    track_artists_map: dict[int, list[ArtistRef]] = defaultdict(list)
    if catalog_ids:
        ca_result = await db.execute(
            select(
                CatalogArtist.catalog_id,
                Artist.id,
                Artist.name,
                CatalogArtist.role,
                Artist.has_artwork,
            )
            .join(Artist, Artist.id == CatalogArtist.artist_id)
            .where(CatalogArtist.catalog_id.in_(catalog_ids))
            .order_by(CatalogArtist.catalog_id, CatalogArtist.position)
        )
        for ca_cid, a_id, a_name, a_role, a_art in ca_result.all():
            track_artists_map[ca_cid].append(
                ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
            )

    # 4. Tracklist
    tracklist = []
    total = 0
    identified = 0
    for t in dj_set.tracks:
        total += 1
        cat = t.catalog
        is_identified = cat is not None and not t.is_id
        if is_identified:
            identified += 1

        tracklist.append(
            SetTrackDetailOut(
                id=t.id,
                set_id=t.set_id,
                catalog_id=t.catalog_id,
                position=t.position,
                timecode_ms=t.timecode_ms,
                raw_title=t.raw_title,
                raw_artist=t.raw_artist,
                is_id=t.is_id,
                catalog_title=cat.title if cat else None,
                catalog_artist=cat.artist if cat else None,
                catalog_artists=track_artists_map.get(t.catalog_id, [])
                if t.catalog_id
                else [],
                has_artwork=cat.has_artwork if cat else False,
                in_lib=t.catalog_id in lib_set if t.catalog_id else False,
                has_preview=cat.has_preview if cat else False,
            )
        )

    return DJSetDetailOut(
        id=dj_set.id,
        external_id=dj_set.external_id,
        source=dj_set.source,
        source_url=dj_set.source_url,
        title=dj_set.title,
        played_date=dj_set.played_date,
        duration_ms=dj_set.duration_ms,
        has_artwork=dj_set.has_artwork,
        created_at=dj_set.created_at,
        last_crawled_at=dj_set.last_crawled_at,
        total_tracks=total,
        identified_tracks=identified,
        artists=artists,
        tracklist=tracklist,
    )
