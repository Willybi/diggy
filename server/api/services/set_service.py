"""
Set service: enriched set listing (filters, sort, dominance-genre, batch
artists + top_genres).

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from datetime import date

from models import Artist, CatalogEntry, DJSet, SetArtist, SetTrack
from schemas import ArtistRef, SetListItemOut, SetListResponse
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from trackid.reliability import set_reliable
from utils import like_escape

from services.catalog_service import catalog_visible
from services.genre_service import aggregate_top_genres, ensure_pillar_cache

# Style filter = DOMINANCE, not mere presence. A DJ set spans many styles, so
# "contains ≥1 track of style X" matches almost everything (a raw "House" match
# returned mostly hip-hop/dance sets carrying one buried House track — noise). A
# set must carry the style on at least this share of its identified visible
# tracks to count as a "style X" set. Calibrated on prod: at 25 %, 98.4 % of the
# kept sets still show the style in their top-2 deduced genres (the ones on the
# row), so the filter stays consistent with what the card displays.
GENRE_MIN_SHARE_PCT = 25


async def list_sets(
    db: AsyncSession,
    user_id: int | None,
    *,
    q: str | None,
    sort: str,
    ids: list[int] | None,
    exclude_ids: list[int] | None,
    genres: list[str] | None,
    artist_ids: list[int] | None = None,
    duration_min: int | None,
    duration_max: int | None,
    year_min: int | None,
    year_max: int | None,
    tracks_min: int | None,
    tracks_max: int | None,
    limit: int,
    offset: int,
) -> SetListResponse:
    """Enriched, filtered and sorted listing of root sets (parent-less), each
    carrying its total/identified track counts, ordered artists and dominant
    deduced genres. ``ids``/``exclude_ids``/``genres`` arrive already parsed by
    the router (mirrors ``watchlist_service.browse``)."""
    # Warm the pillar cache up front (mirrors get_set_detail): its loader rolls
    # the session back on failure, so it must run BEFORE we hold any ORM row.
    await ensure_pillar_cache(db)

    identified_expr = func.count(
        case(
            (
                and_(SetTrack.is_id.is_(False), SetTrack.catalog_id.isnot(None)),
                SetTrack.id,
            ),
        )
    )
    total_tracks_expr = func.count(SetTrack.id)

    stmt = (
        select(
            DJSet,
            total_tracks_expr.label("total_tracks"),
            identified_expr.label("identified_tracks"),
        )
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        # C8: hide unreliable TrackID sets (adds to the roots-only filter).
        .where(DJSet.parent_set_id.is_(None), set_reliable())
        .group_by(DJSet.id)
        # A set with no identified track is noise in a discovery list: exclude it.
        # The count subquery below is built on this stmt, so total honours it.
        .having(identified_expr > 0)
    )

    if q:
        stmt = stmt.where(DJSet.title.ilike(f"%{like_escape(q)}%", escape="\\"))

    if ids is not None:
        stmt = stmt.where(DJSet.id.in_(ids))
    if exclude_ids is not None:
        stmt = stmt.where(DJSet.id.notin_(exclude_ids))

    # Duration (ms) bounds — a null duration_ms can't satisfy a bound, so it is
    # excluded as soon as either side is set (the frontend presets are ranges).
    if duration_min is not None:
        stmt = stmt.where(DJSet.duration_ms >= duration_min)
    if duration_max is not None:
        stmt = stmt.where(DJSet.duration_ms <= duration_max)

    # Played date by year bounds — expressed as Date comparisons (portable across
    # PG/SQLite); a null played_date can't match, so it drops out when filtered.
    if year_min is not None:
        stmt = stmt.where(DJSet.played_date >= date(year_min, 1, 1))
    if year_max is not None:
        stmt = stmt.where(DJSet.played_date <= date(year_max, 12, 31))

    # Style filter (DOMINANCE — see GENRE_MIN_SHARE_PCT): keep a set only when the
    # requested styles cover ≥ that share of its VISIBLE identified tracks (C3
    # perimeter). The match runs over ALL identified visible tracks of the set
    # (not a pre-filtered subset) so the SUM/COUNT ratio is the real share.
    # `genres.any(g)` compiles per dialect (StringArray.array_any).
    if genres:
        genre_match = or_(*[CatalogEntry.genres.any(g) for g in genres])
        hit_count = func.sum(case((genre_match, 1), else_=0))
        track_count = func.count(SetTrack.id)
        genre_sub = (
            select(SetTrack.set_id)
            .join(CatalogEntry, CatalogEntry.id == SetTrack.catalog_id)
            .where(
                SetTrack.is_id.is_(False),
                SetTrack.catalog_id.isnot(None),
                catalog_visible(user_id),
            )
            .group_by(SetTrack.set_id)
            # Integer form of hit/total >= share (avoids float rounding).
            .having(hit_count * 100 >= track_count * GENRE_MIN_SHARE_PCT)
        )
        stmt = stmt.where(DJSet.id.in_(genre_sub))

    # Artist filter (D8.c): sets crediting one of these DJs via SetArtist — the
    # SAME relation the Artist Detail "Sets" section lists, so the contextual
    # "/sets?artist_id=" landing mirrors it. Roots-only is already enforced by the
    # main query (parent_set_id IS NULL). Applied to stmt so `total` honours it.
    if artist_ids:
        artist_sub = select(SetArtist.set_id).where(
            SetArtist.artist_id.in_(artist_ids)
        )
        stmt = stmt.where(DJSet.id.in_(artist_sub))

    # Track-count bounds — total_tracks is an aggregate, so these are HAVING
    # clauses (AND-ed with the identified>0 gate above).
    if tracks_min is not None:
        stmt = stmt.having(total_tracks_expr >= tracks_min)
    if tracks_max is not None:
        stmt = stmt.having(total_tracks_expr <= tracks_max)

    # Ordering: leading '-' = descending, else ascending. Unknown key -> -date.
    # id.desc() is the final tie-break everywhere: created_at is NOT unique, so a
    # non-unique tie-break let the windowed pagination duplicate/omit a row across
    # pages; id is unique and stable (same lesson as catalog_service/artist_service).
    # "tracks" sorts by the total track COUNT: the import stores only identified
    # tracks, so the identified/total ratio is always ~100% and would sort nothing.
    sort_columns = {
        "title": DJSet.title,
        "date": DJSet.played_date,
        "tracks": total_tracks_expr,
        "duration": DJSet.duration_ms,
    }
    key = sort or "-date"
    descending = key.startswith("-")
    key = key[1:] if descending else key
    if key not in sort_columns:
        key, descending = "date", True
    col = sort_columns[key]
    primary = (col.desc() if descending else col.asc()).nulls_last()
    stmt = stmt.order_by(primary, DJSet.id.desc())

    # Total count
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar()

    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()
    set_ids = [row[0].id for row in rows]

    # Batch-fetch artists as [{id, name}] (ordered by position)
    set_artists_map: dict[int, list[ArtistRef]] = {}
    if set_ids:
        aq = await db.execute(
            select(SetArtist.set_id, Artist.id, Artist.name)
            .join(Artist, Artist.id == SetArtist.artist_id)
            .where(SetArtist.set_id.in_(set_ids))
            .order_by(SetArtist.position)
        )
        for sid, aid, name in aq.all():
            set_artists_map.setdefault(sid, []).append(ArtistRef(id=aid, name=name))

    # Batch-deduce top_genres per set — same rules as get_set_detail, page-wide:
    # only identified tracks (catalog_id set, not an "ID" placeholder), restricted
    # to the viewer's visible perimeter (C3 — a foreign private track never leaks
    # its genres into the aggregate). Sequential awaits on one session — never
    # asyncio.gather on `db` (asyncpg wedges the connection).
    top_genres_map: dict[int, list] = {}
    if set_ids:
        st_rows = await db.execute(
            select(SetTrack.set_id, SetTrack.catalog_id).where(
                SetTrack.set_id.in_(set_ids),
                SetTrack.is_id.is_(False),
                SetTrack.catalog_id.isnot(None),
            )
        )
        catalog_ids_by_set: dict[int, list[int]] = {}
        all_catalog_ids: set[int] = set()
        for sid, cid in st_rows.all():
            catalog_ids_by_set.setdefault(sid, []).append(cid)
            all_catalog_ids.add(cid)

        genres_by_id: dict[int, list[str]] = {}
        if all_catalog_ids:
            gres = await db.execute(
                select(CatalogEntry.id, CatalogEntry.genres).where(
                    CatalogEntry.id.in_(all_catalog_ids), catalog_visible(user_id)
                )
            )
            genres_by_id = {cid: (g or []) for cid, g in gres.all()}

        for sid, cids in catalog_ids_by_set.items():
            top_genres_map[sid] = aggregate_top_genres(
                (genres_by_id[cid] for cid in cids if cid in genres_by_id),
                cap=3,
            )

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
            top_genres=top_genres_map.get(s.id, []),
        )
        for s, total_tracks, identified in rows
    ]
    return SetListResponse(total=total, items=items)
