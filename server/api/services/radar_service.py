"""
Radar service: enriched listing, state management, opinion sync.

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import and_, func, literal, literal_column, select
from sqlalchemy import desc as sa_desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased


async def list_full(
    db: AsyncSession,
    user_id: int,
    status: str | None,
    playlist_id: int | None,
    search: str | None,
    detected_after: datetime | None,
    sort: str,
    order: str,
    skip: int,
    limit: int,
):
    from models import (
        Artist,
        CatalogArtist,
        CatalogEntry,
        RadarTrack,
        RadarTrend,
        UserRadarState,
        UserTrack,
        WatchedEntity,
    )
    from schemas import ArtistRef, RadarFullList, RadarFullOut

    _STATUS_ALIAS = {"liked": "added", "disliked": "ignored"}

    urs = aliased(UserRadarState)
    ut = aliased(UserTrack)

    in_lib_sq = (
        select(literal(True))
        .where(ut.user_id == user_id, ut.catalog_id == CatalogEntry.id)
        .correlate(CatalogEntry)
        .exists()
    )

    _lr = RadarTrack.__table__.alias("lr")
    _lw = WatchedEntity.__table__.alias("lw")
    latest_playlist_title = (
        select(_lw.c.title)
        .select_from(_lr.join(_lw, _lr.c.watched_entity_id == _lw.c.id))
        .where(_lr.c.catalog_id == CatalogEntry.id)
        .order_by(sa_desc(_lr.c.detected_at))
        .limit(1)
        .correlate(CatalogEntry)
        .scalar_subquery()
    )
    latest_playlist_id = (
        select(_lr.c.watched_entity_id)
        .select_from(_lr)
        .where(_lr.c.catalog_id == CatalogEntry.id)
        .order_by(sa_desc(_lr.c.detected_at))
        .limit(1)
        .correlate(CatalogEntry)
        .scalar_subquery()
    )

    rt = aliased(RadarTrend)

    base = (
        select(
            CatalogEntry.id.label("catalog_id"),
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.duration_ms,
            CatalogEntry.genres,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            func.max(RadarTrack.detected_at).label("detected_at"),
            latest_playlist_id.label("playlist_id"),
            latest_playlist_title.label("playlist_title"),
            func.coalesce(func.min(urs.status), literal("new")).label("status"),
            in_lib_sq.label("in_lib"),
            rt.trend_score.label("trend_score"),
            rt.rank_global.label("trend_rank"),
            rt.family.label("trend_family"),
            rt.rank_in_family.label("trend_rank_family"),
            rt.velocity.label("velocity"),
            rt.source_count.label("source_count"),
        )
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(urs, and_(urs.user_id == user_id, urs.catalog_id == CatalogEntry.id))
        .outerjoin(rt, rt.catalog_id == CatalogEntry.id)
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by(
            CatalogEntry.id, urs.status, rt.trend_score,
            rt.rank_global, rt.family, rt.rank_in_family, rt.velocity, rt.source_count,
        )
    )

    resolved_status = _STATUS_ALIAS.get(status, status) if status else None
    if resolved_status:
        if resolved_status == "new":
            base = base.having(
                func.coalesce(func.min(urs.status), literal("new")) == "new"
            )
        else:
            base = base.having(func.min(urs.status) == resolved_status)
    if detected_after:
        base = base.where(RadarTrack.detected_at >= detected_after)
    if playlist_id:
        base = base.where(RadarTrack.watched_entity_id == playlist_id)
    if search:
        term = f"%{search}%"
        base = base.where(
            CatalogEntry.title.ilike(term) | CatalogEntry.artist.ilike(term)
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    counts_base = (
        select(
            func.coalesce(urs.status, literal("new")).label("st"),
            func.count(func.distinct(CatalogEntry.id)).label("cnt"),
        )
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(urs, and_(urs.user_id == user_id, urs.catalog_id == CatalogEntry.id))
        .where(RadarTrack.catalog_id.isnot(None))
        .group_by("st")
    )
    counts_result = await db.execute(counts_base)
    counts = {row.st: row.cnt for row in counts_result}

    sort_map = {
        "detected_at": func.max(RadarTrack.detected_at),
        "title": CatalogEntry.title,
        "artist": CatalogEntry.artist,
        "bpm": CatalogEntry.bpm,
        "key": CatalogEntry.key,
        "genre": literal_column("(catalog.genres)[1]"),
        "playlist_title": latest_playlist_title,
        "trend_score": func.coalesce(rt.trend_score, literal(0)),
    }
    sort_col = sort_map.get(sort, func.max(RadarTrack.detected_at))
    if order == "asc":
        base = base.order_by(sort_col.asc())
    else:
        base = base.order_by(sort_col.desc())

    base = base.offset(skip).limit(limit)
    result = await db.execute(base)
    items = [RadarFullOut.model_validate(row._mapping) for row in result]

    page_cat_ids = [item.catalog_id for item in items]
    if page_cat_ids:
        ca_result = await db.execute(
            select(
                CatalogArtist.catalog_id,
                Artist.id,
                Artist.name,
                CatalogArtist.role,
                Artist.has_artwork,
            )
            .join(Artist, Artist.id == CatalogArtist.artist_id)
            .where(CatalogArtist.catalog_id.in_(page_cat_ids))
            .order_by(CatalogArtist.catalog_id, CatalogArtist.position)
        )
        artists_by_catalog: dict[int, list] = defaultdict(list)
        for ca_cid, a_id, a_name, a_role, a_art in ca_result.all():
            artists_by_catalog[ca_cid].append(
                ArtistRef(id=a_id, name=a_name, role=a_role, has_artwork=a_art)
            )
        for item in items:
            item.artists = artists_by_catalog.get(item.catalog_id, [])

    return RadarFullList(total=total, items=items, counts=counts)


async def new_count(db: AsyncSession, user_id: int) -> dict:
    from models import CatalogEntry, RadarTrack, UserRadarState

    urs = aliased(UserRadarState)
    q = (
        select(func.count(func.distinct(RadarTrack.catalog_id)))
        .select_from(RadarTrack)
        .join(CatalogEntry, RadarTrack.catalog_id == CatalogEntry.id)
        .outerjoin(
            urs, and_(urs.user_id == user_id, urs.catalog_id == RadarTrack.catalog_id)
        )
        .where(
            RadarTrack.catalog_id.isnot(None),
            func.coalesce(urs.status, literal("new")) == "new",
        )
    )
    count = (await db.execute(q)).scalar() or 0
    return {"count": count}


async def update_state(
    db: AsyncSession, user_id: int, catalog_id: int, status: str
) -> dict:
    from models import UserRadarState

    from services.opinion_sync import RADAR_TO_OPINION, sync_track_opinion

    _STATUS_ALIAS = {"liked": "added", "disliked": "ignored"}
    resolved = _STATUS_ALIAS.get(status, status)

    result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == user_id,
            UserRadarState.catalog_id == catalog_id,
        )
    )
    state = result.scalar_one_or_none()

    if state:
        state.status = resolved
        state.updated_at = datetime.now(timezone.utc)
    else:
        state = UserRadarState(
            user_id=user_id,
            catalog_id=catalog_id,
            status=resolved,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(state)

    opinion_val = RADAR_TO_OPINION.get(resolved)
    await sync_track_opinion(db, user_id, catalog_id, opinion_val)
    await db.commit()
    return {"catalog_id": catalog_id, "status": status}


async def batch_update_state(
    db: AsyncSession, user_id: int, items: list[dict]
) -> dict:
    from models import UserRadarState

    from services.opinion_sync import RADAR_TO_OPINION, sync_track_opinion

    _STATUS_ALIAS = {"liked": "added", "disliked": "ignored"}
    now = datetime.now(timezone.utc)

    valid_items = [
        (item["catalog_id"], _STATUS_ALIAS.get(item["status"], item["status"]))
        for item in items
    ]
    if not valid_items:
        return {"updated": 0}

    catalog_ids = [cid for cid, _ in valid_items]
    existing_result = await db.execute(
        select(UserRadarState).where(
            UserRadarState.user_id == user_id,
            UserRadarState.catalog_id.in_(catalog_ids),
        )
    )
    existing_map = {s.catalog_id: s for s in existing_result.scalars()}

    for cid, resolved in valid_items:
        if cid in existing_map:
            existing_map[cid].status = resolved
            existing_map[cid].updated_at = now
        else:
            db.add(
                UserRadarState(
                    user_id=user_id,
                    catalog_id=cid,
                    status=resolved,
                    updated_at=now,
                )
            )
        opinion_val = RADAR_TO_OPINION.get(resolved)
        await sync_track_opinion(db, user_id, cid, opinion_val)

    await db.commit()
    return {"updated": len(valid_items)}


async def add_track(db: AsyncSession, user_id: int, body) -> object:
    """Create a radar track entry (or return existing). Returns RadarTrack ORM."""
    from datetime import datetime, timezone

    from models import RadarTrack, WatchedEntity

    from services.catalog_service import get_or_create_catalog

    entity = await db.execute(
        select(WatchedEntity).where(WatchedEntity.id == body.watched_playlist_id)
    )
    if not entity.scalar_one_or_none():
        raise LookupError("watched_entity not found")

    existing = await db.execute(
        select(RadarTrack).where(
            RadarTrack.watched_entity_id == body.watched_playlist_id,
            RadarTrack.external_track_id == body.external_track_id,
        )
    )
    existing_entry = existing.scalar_one_or_none()
    if existing_entry:
        return existing_entry, True  # (track, already_existed)

    catalog_entry = await get_or_create_catalog(
        db, title=body.title, artist=body.artist, isrc=body.isrc
    )
    entry = RadarTrack(
        watched_entity_id=body.watched_playlist_id,
        external_track_id=body.external_track_id,
        source=body.source,
        title=body.title,
        artist=body.artist,
        isrc=body.isrc,
        detected_at=datetime.now(timezone.utc),
        catalog_id=catalog_entry.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry, False  # (track, already_existed)
