"""
Radar service: trends listing, bi-score feed, new-count.

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from sqlalchemy import and_, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from utils import space_insensitive_contains


async def list_trends(
    db: AsyncSession,
    user_id: int | None,
    family: str | None,
    limit: int,
):
    from models import CatalogEntry, RadarTrend
    from schemas import TrendItem, TrendList

    from services.catalog_service import catalog_visible

    # Family counts
    count_q = (
        select(RadarTrend.family, func.count())
        .where(RadarTrend.family.isnot(None))
        .group_by(RadarTrend.family)
    )
    count_rows = (await db.execute(count_q)).all()
    family_counts = {r[0]: r[1] for r in count_rows}

    # Top tracks
    q = (
        select(
            RadarTrend.catalog_id,
            RadarTrend.trend_score,
            RadarTrend.rank_global,
            RadarTrend.family,
            RadarTrend.source_count,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.release_date,
        )
        .join(CatalogEntry, CatalogEntry.id == RadarTrend.catalog_id)
        .where(catalog_visible(user_id))
    )
    if family:
        q = q.where(RadarTrend.family == family)
        q = q.order_by(RadarTrend.rank_in_family.asc().nulls_last())
    else:
        q = q.order_by(RadarTrend.rank_global.asc().nulls_last())
    q = q.limit(limit)

    rows = (await db.execute(q)).all()
    items = [
        TrendItem(
            catalog_id=r.catalog_id,
            title=r.title,
            artist=r.artist,
            has_artwork=r.has_artwork,
            has_preview=r.has_preview,
            bpm=r.bpm,
            key=r.key,
            release_date=r.release_date,
            trend_score=r.trend_score,
            rank=idx + 1,
            family=r.family,
            source_count=r.source_count or 0,
        )
        for idx, r in enumerate(rows)
    ]
    return TrendList(items=items, family_counts=family_counts)


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
        # X4.h: in-memory twin of the SQL space-insensitive match (title + artist).
        if not space_insensitive_contains(search, item.title, item.artist):
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
