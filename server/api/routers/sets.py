import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user, get_current_user_optional
from models import (
    DJSet, SetTrack, SetArtist, Artist, CatalogEntry, UserTrack,
    UserSetFollow, User,
)
from schemas import (
    DJSetDetailOut, SetTrackDetailOut, SetArtistDetailOut, GenreOut,
    SetListItemOut,
)

router = APIRouter(prefix="/sets", tags=["sets"])

_DEFAULT_USER_ID = 1


def _uid(user: User | None) -> int:
    return user.id if user else _DEFAULT_USER_ID


# ---------- Schemas ----------

class SetImportIn(BaseModel):
    url: str | None = None
    slug: str | None = None


# ---------- Search TrackID ----------

class TrackIDSearchResult(BaseModel):
    trackid_id: int
    slug: str
    title: str
    channel: str | None = None
    artwork_url: str | None = None
    track_count: int = 0
    duration: str | None = None
    created_on: str | None = None
    already_imported: bool = False


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

@router.get("/", response_model=list[SetListItemOut])
async def list_sets(
    q: str | None = None,
    followed: bool | None = None,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    uid = _uid(user)

    follow_sub = (
        select(UserSetFollow.set_id)
        .where(UserSetFollow.user_id == uid, UserSetFollow.set_id == DJSet.id)
        .correlate(DJSet)
        .exists()
    )

    stmt = (
        select(
            DJSet,
            func.count(SetTrack.id).label("total_tracks"),
            func.count(
                case(
                    (and_(SetTrack.is_id.is_(False), SetTrack.catalog_id.isnot(None)), SetTrack.id),
                )
            ).label("identified_tracks"),
            follow_sub.label("followed"),
        )
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        .group_by(DJSet.id)
        .order_by(DJSet.played_date.desc().nulls_last(), DJSet.created_at.desc())
    )

    if q:
        stmt = stmt.where(DJSet.title.ilike(f"%{q}%"))
    if followed is True:
        stmt = stmt.where(follow_sub)

    rows = (await db.execute(stmt)).all()

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

    return [
        SetListItemOut(
            id=s.id,
            title=s.title,
            source=s.source,
            source_url=s.source_url,
            played_date=s.played_date,
            duration_ms=s.duration_ms,
            has_artwork=s.has_artwork,
            total_tracks=total,
            identified_tracks=identified,
            artists=set_artists_map.get(s.id, []),
            followed=fol,
        )
        for s, total, identified, fol in rows
    ]


# ---------- Import ----------

@router.post("/import")
async def import_set_url(
    body: SetImportIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import a set from a TrackID URL or slug, and auto-follow it."""
    slug = None
    if body.slug:
        slug = body.slug.strip().rstrip('/')
    elif body.url:
        match = re.search(r'trackid\.net/audiostream/(.+?)(?:\?|$)', body.url.strip())
        if match:
            slug = match.group(1).rstrip('/')
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

        # Auto-follow
        ef = await db.execute(
            select(UserSetFollow).where(
                UserSetFollow.user_id == user.id,
                UserSetFollow.set_id == dj_set.id,
            )
        )
        if not ef.scalar_one_or_none():
            db.add(UserSetFollow(
                user_id=user.id,
                set_id=dj_set.id,
                followed_at=datetime.now(timezone.utc),
            ))

        await db.commit()
        await db.refresh(dj_set)

        # Fire track resolution in background
        from celery import Celery
        _celery = Celery(broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"))
        _celery.send_task("workers.tasks.resolve_set_tracks")

        return {"id": dj_set.id, "title": dj_set.title}


# ---------- Follow / Unfollow ----------

@router.post("/{set_id}/follow")
async def follow_set(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(DJSet).where(DJSet.id == set_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Set not found")

    existing = await db.execute(
        select(UserSetFollow).where(
            UserSetFollow.user_id == user.id, UserSetFollow.set_id == set_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already following")

    db.add(UserSetFollow(
        user_id=user.id,
        set_id=set_id,
        followed_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return {"ok": True}


@router.delete("/{set_id}/follow")
async def unfollow_set(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserSetFollow).where(
            UserSetFollow.user_id == user.id, UserSetFollow.set_id == set_id
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        raise HTTPException(status_code=404, detail="Not following")
    await db.delete(follow)
    await db.commit()
    return {"ok": True}


# ---------- Detail ----------

@router.get("/{set_id}", response_model=DJSetDetailOut)
async def get_set_detail(set_id: int, db: AsyncSession = Depends(get_db)):
    # 1. DJSet + genres
    result = await db.execute(
        select(DJSet)
        .options(
            selectinload(DJSet.genres),
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

    # 3. Collect catalog_ids to batch-check lib status
    catalog_ids = [t.catalog_id for t in dj_set.tracks if t.catalog_id]
    lib_set = set()
    if catalog_ids:
        lib_result = await db.execute(
            select(UserTrack.catalog_id).where(UserTrack.catalog_id.in_(catalog_ids))
        )
        lib_set = {r[0] for r in lib_result.all()}

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

        tracklist.append(SetTrackDetailOut(
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
            has_artwork=cat.has_artwork if cat else False,
            in_lib=t.catalog_id in lib_set if t.catalog_id else False,
            has_preview=cat.has_preview if cat else False,
        ))

    return DJSetDetailOut(
        id=dj_set.id,
        external_id=dj_set.external_id,
        source=dj_set.source,
        source_url=dj_set.source_url,
        title=dj_set.title,
        event=dj_set.event,
        venue=dj_set.venue,
        played_date=dj_set.played_date,
        duration_ms=dj_set.duration_ms,
        description=dj_set.description,
        has_artwork=dj_set.has_artwork,
        created_at=dj_set.created_at,
        last_crawled_at=dj_set.last_crawled_at,
        total_tracks=total,
        identified_tracks=identified,
        artists=artists,
        genres=[GenreOut.model_validate(g) for g in dj_set.genres],
        tracklist=tracklist,
    )
