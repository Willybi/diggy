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

    from services.catalog_service import catalog_visible

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
        .where(RadarTrack.catalog_id.isnot(None), catalog_visible(user_id))
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
        .where(RadarTrack.catalog_id.isnot(None), catalog_visible(user_id))
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


# Bi-score feed bounds. The trend surface is intentionally small (nightly
# radar_trends): the top of every family plus the global head cover the family
# NULL rows. The union is merged/filtered/sorted in memory (a few hundred rows).
TREND_PER_FAMILY = 60
TREND_GLOBAL_K = 200


def _feed_passes_filters(
    item,
    *,
    search,
    genre,
    bpm_min,
    bpm_max,
    key,
    artist_id,
    duration_min,
    duration_max,
    has_preview,
    avis,
    year_min,
    year_max,
    label,
    in_lib,
) -> bool:
    """In-memory filter over a union row, mirroring ``list_catalog`` semantics.

    A NULL value never satisfies a bound (same as the SQL ``>=``/``<=`` there).
    """
    if search:
        term = search.lower()
        if term not in (item.title or "").lower() and term not in (
            item.artist or ""
        ).lower():
            return False
    if genre:
        wanted = {g.lower() for g in genre}
        if not any((g.name or "").lower() in wanted for g in item.genres):
            return False
    if bpm_min is not None and (item.bpm is None or item.bpm < bpm_min):
        return False
    if bpm_max is not None and (item.bpm is None or item.bpm > bpm_max):
        return False
    if key and item.key not in key:
        return False
    if artist_id:
        wanted_ids = set(artist_id)
        if not any(a.id in wanted_ids for a in item.artists):
            return False
    if duration_min is not None and (
        item.duration_ms is None or item.duration_ms < duration_min
    ):
        return False
    if duration_max is not None and (
        item.duration_ms is None or item.duration_ms > duration_max
    ):
        return False
    if has_preview is True and not item.has_preview:
        return False
    if avis == "none":
        if item.avis is not None:
            return False
    elif avis and item.avis != avis:
        return False
    if year_min is not None and (
        item.release_date is None or item.release_date.year < year_min
    ):
        return False
    if year_max is not None and (
        item.release_date is None or item.release_date.year > year_max
    ):
        return False
    if label and label.lower() not in (item.label or "").lower():
        return False
    if in_lib is True and not item.in_lib:
        return False
    if in_lib is False and item.in_lib:
        return False
    return True


async def list_bi_score(
    db: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    genre: list[str] | None = None,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    key: list[str] | None = None,
    artist_id: list[int] | None = None,
    duration_min: int | None = None,
    duration_max: int | None = None,
    has_preview: bool | None = None,
    avis: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    label: str | None = None,
    in_lib: bool | None = None,
    sort: str = "tendance",
    order: str = "desc",
    skip: int = 0,
    limit: int = 50,
    redis=None,
):
    """Bi-score radar feed: merge "Tendance" (radar_trends) and "Pour toi" (C4
    reco) by ``catalog_id`` into one paginated, filterable, sortable list.

    The union is bounded (top of each trend family + global head, plus the ≤100
    personal recos), merged and ranked in memory. DB reads run sequentially on
    the one session — never gather several ``db.execute`` on the same session.
    """
    from models import CatalogEntry, RadarTrend
    from schemas import RadarFeedItem, RadarFeedList
    from sqlalchemy import and_, or_

    from services import catalog_service, recommendation_service

    # 1. "Pour toi" — sequential first (uses this same session). Empty at cold
    #    start; capped at 100 by the reco service.
    reco = await recommendation_service.get_recommendations(
        db, user_id, limit=recommendation_service.CFG.MAX_ITEMS, redis=redis
    )
    reco_items = {it.id: it for it in reco.items}
    reco_by_id = {it.id: it.reco_score for it in reco.items}
    max_reco = max(reco_by_id.values()) if reco_by_id else 0.0

    # 2. "Tendance" — bounded, visibility-scoped id set from radar_trends.
    trend_q = (
        select(RadarTrend.catalog_id, RadarTrend.velocity)
        .join(CatalogEntry, CatalogEntry.id == RadarTrend.catalog_id)
        .where(
            catalog_service.catalog_visible(user_id),
            or_(
                RadarTrend.rank_in_family <= TREND_PER_FAMILY,
                and_(
                    RadarTrend.family.is_(None),
                    RadarTrend.rank_global <= TREND_GLOBAL_K,
                ),
            ),
        )
    )
    trend_rows = (await db.execute(trend_q)).all()
    trend_ids = [r[0] for r in trend_rows]
    velocity_by_id = {r[0]: r[1] for r in trend_rows}

    # 3. Canonical CatalogEntryOut for the trend ids (max-normalised trend_score_10
    #    + trend_rank come straight from the shared builder).
    trend_items: dict[int, object] = {}
    if trend_ids:
        trend_list = await catalog_service.list_catalog(
            db, user_id, skip=0, limit=len(trend_ids), catalog_ids=trend_ids
        )
        trend_items = {it.id: it for it in trend_list.items}

    # 4. Union: trend row is canonical; a reco-only id keeps its reco item. A
    #    reco-only row is by construction NOT in the bounded trend surface, so its
    #    trend_score_10 is forced None (it must not count toward trend_count).
    union_ids = list(trend_items.keys()) + [
        cid for cid in reco_items if cid not in trend_items
    ]
    items: list = []
    for cid in union_ids:
        base = trend_items.get(cid) or reco_items[cid]
        data = base.model_dump()
        if cid not in trend_items:
            data["trend_score_10"] = None
        if cid in reco_by_id and max_reco > 0:
            data["reco_score_10"] = round(reco_by_id[cid] / max_reco * 10, 1)
        else:
            data["reco_score_10"] = None
        data["velocity"] = velocity_by_id.get(cid)
        items.append(RadarFeedItem(**data))

    # 5. Head counters over the UNFILTERED union.
    trend_count = sum(1 for it in items if it.trend_score_10 is not None)
    reco_count = sum(1 for it in items if it.reco_score_10 is not None)

    # 6. Filter (live) → total.
    filtered = [
        it
        for it in items
        if _feed_passes_filters(
            it,
            search=search, genre=genre, bpm_min=bpm_min, bpm_max=bpm_max,
            key=key, artist_id=artist_id,
            duration_min=duration_min, duration_max=duration_max,
            has_preview=has_preview, avis=avis,
            year_min=year_min, year_max=year_max, label=label, in_lib=in_lib,
        )
    ]
    total = len(filtered)

    # 7. Sort: deterministic (stable ascending-id tiebreak), NULLs always last.
    sort_key = {
        "tendance": lambda it: it.trend_score_10,
        "pour_toi": lambda it: it.reco_score_10,
        "bpm": lambda it: it.bpm,
        "recent": lambda it: it.created_at,
    }.get(sort, lambda it: it.trend_score_10)
    reverse = order != "asc"

    filtered.sort(key=lambda it: it.id)  # stable secondary
    with_val = [it for it in filtered if sort_key(it) is not None]
    without_val = [it for it in filtered if sort_key(it) is None]
    with_val.sort(key=sort_key, reverse=reverse)
    ordered = with_val + without_val

    # 8. Paginate.
    page = ordered[skip : skip + limit]
    return RadarFeedList(
        total=total,
        trend_count=trend_count,
        reco_count=reco_count,
        items=page,
    )


async def new_count(db: AsyncSession, user_id: int) -> dict:
    from models import CatalogEntry, RadarTrack, UserRadarState

    from services.catalog_service import catalog_visible

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
            catalog_visible(user_id),
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
