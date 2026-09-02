"""
Search service: cross-type search (tracks, artists, sets, playlists, genres)
with relevance ranking, guest cap and pagination.

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from __future__ import annotations

from models import (
    Album,
    Artist,
    CatalogArtist,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetTrack,
    TrackIdIndex,
    UserTrack,
    WatchedEntity,
)
from schemas import SearchItem, SearchResponse, SearchTotals
from sqlalchemy import String, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from trackid.reliability import set_reliable
from utils import like_escape, search_fold, space_insensitive_ilike

from services.catalog_service import catalog_visible
from services.genre_service import ensure_pillar_cache, genre_pillar

GUEST_CAP = 6


# ── Relevance scoring ────────────────────────────────────────────


def _relevance(value: str, q: str) -> int:
    v = value.lower()
    if v == q:
        return 3
    if v.startswith(q):
        return 2
    return 1


# ── Per-type search helpers ──────────────────────────────────────


async def _search_tracks(
    db: AsyncSession,
    q: str,
    user_id: int | None,
    is_guest: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    ut_sub = select(UserTrack.catalog_id).where(UserTrack.user_id == user_id).subquery()

    base = (
        select(
            CatalogEntry.id,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.duration_ms,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
            ut_sub.c.catalog_id.label("ut_cid"),
        )
        .outerjoin(ut_sub, CatalogEntry.id == ut_sub.c.catalog_id)
        # X4.h: space-insensitive on title + artist (shared helper).
        .where(space_insensitive_ilike(q, CatalogEntry.title, CatalogEntry.artist))
        .where(catalog_visible(user_id))
        .order_by(CatalogEntry.title, CatalogEntry.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="track",
                id=r.id,
                title=r.title,
                artist=r.artist,
                bpm=r.bpm,
                key=r.key,
                duration_ms=r.duration_ms,
                has_artwork=r.has_artwork,
                has_preview=r.has_preview,
                in_lib=False if is_guest else (r.ut_cid is not None),
            )
        )
    return items, total


async def _search_artists(
    db: AsyncSession,
    q: str,
    user_id: int | None,
    is_guest: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    # X4.f/X4.h: additive "compact" clause matches an artist whose spaced-out
    # Deezer name ("t e s t p r e s s") is searched by its collapsed spelling
    # ("testpress"). Never regresses the plain ILIKE (only the artist branch).
    base = (
        select(Artist.id, Artist.name, Artist.has_artwork)
        .where(space_insensitive_ilike(q, Artist.name))
        .order_by(Artist.name, Artist.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()
    if not rows:
        return [], total

    artist_ids = [r.id for r in rows]

    # batch track counts via catalog_artists
    tc_q = (
        select(
            CatalogArtist.artist_id,
            func.count().label("cnt"),
        )
        .where(CatalogArtist.artist_id.in_(artist_ids))
        .group_by(CatalogArtist.artist_id)
    )
    tc_rows = (await db.execute(tc_q)).all()
    tc_map = {r.artist_id: r.cnt for r in tc_rows}

    # batch in_lib counts via catalog_artists
    lib_map: dict[int, int] = {}
    if not is_guest:
        lib_q = (
            select(
                CatalogArtist.artist_id,
                func.count().label("cnt"),
            )
            .join(
                UserTrack,
                (UserTrack.catalog_id == CatalogArtist.catalog_id)
                & (UserTrack.user_id == user_id),
            )
            .where(CatalogArtist.artist_id.in_(artist_ids))
            .group_by(CatalogArtist.artist_id)
        )
        lib_rows = (await db.execute(lib_q)).all()
        lib_map = {r.artist_id: r.cnt for r in lib_rows}

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="artist",
                id=r.id,
                name=r.name,
                has_artwork=r.has_artwork,
                track_count=tc_map.get(r.id, 0),
                in_lib_count=0 if is_guest else lib_map.get(r.id, 0),
            )
        )
    return items, total


# Cap on the number of candidate roots pulled from the DB before the in-memory
# weighted ranking. A set can match on several fields (title, artist, channel,
# date) with different per-field weights, so the final order can only be computed
# in Python — but selecting every match would be unbounded. 500 is comfortably
# above any realistic single-query match count; if a query somehow exceeds it,
# the lowest-priority (oldest) candidates beyond the cap are dropped from ranking
# only — the returned `total` stays exact via the separate uncapped count query.
_SET_CANDIDATE_CAP = 500


async def _search_sets(
    db: AsyncSession,
    q: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    """Weighted, fold-insensitive set search (roots only, reliable only).

    A ROOT set matches when the folded query hits any of, in priority order:
      - its TITLE or one of its CHILDREN's titles (weight 3) — matched against
        the pre-folded ``search_text`` column, plain and space-compacted, so an
        accent/punctuation-insensitive hit works and a rich child title lifts its
        abbreviated virtual root;
      - a linked ARTIST name (weight 3, rare — ~60 sets carry ``set_artists``);
      - the CHANNEL of its (or a child's) ``trackid_index`` listing (weight 2) —
        a deduplicated root is virtual and has no ``trackid_index`` of its own,
        the row hangs off the CHILD, so both are covered;
      - its played DATE typed as text (weight 1) — an entered year/date.

    Only roots (``parent_set_id IS NULL``) that are reliable (C8) are returned,
    each exactly once. Ranking (weight desc, relevance desc, track_count desc,
    id desc) is done in Python over a capped candidate set; offset/limit are
    applied AFTER the sort.
    """
    fq = search_fold(q)
    if not fq:
        return [], 0

    fq_compact = fq.replace(" ", "")
    title_plain = f"%{like_escape(fq)}%"
    title_compact = f"%{like_escape(fq_compact)}%"
    # Artist/channel/date match the raw (already lowercased) query — no SQL
    # accent folding on these secondary signals (assumed acceptable).
    raw_plain = f"%{like_escape(q)}%"
    raw_compact = f"%{like_escape(q.replace(' ', ''))}%"

    def _title_pred(col):
        # ``search_text`` is stored pre-folded (lowercased, accents stripped) so
        # a plain LIKE is correct and NULL simply never matches. The compact
        # clause catches letter-spaced titles ("t e s t p r e s s" vs "testpress").
        return or_(
            col.like(title_plain, escape="\\"),
            func.replace(col, " ", "").like(title_compact, escape="\\"),
        )

    def _channel_pred(col):
        # Fold on the fly = lower + space-compaction only (no SQL de-accenting).
        lc = func.lower(col)
        return or_(
            lc.like(raw_plain, escape="\\"),
            func.replace(lc, " ", "").like(raw_compact, escape="\\"),
        )

    child = aliased(DJSet)
    child_title_exists = (
        select(child.id)
        .where(child.parent_set_id == DJSet.id, _title_pred(child.search_text))
        .exists()
    )

    artist_exists = (
        select(SetArtist.set_id)
        .where(
            SetArtist.set_id == DJSet.id,
            SetArtist.artist_id == Artist.id,
            func.lower(Artist.name).like(raw_plain, escape="\\"),
        )
        .exists()
    )

    tid_set = aliased(DJSet)
    channel_exists = (
        select(TrackIdIndex.id)
        .join(tid_set, TrackIdIndex.set_id == tid_set.id)
        .where(
            or_(tid_set.id == DJSet.id, tid_set.parent_set_id == DJSet.id),
            _channel_pred(TrackIdIndex.channel),
        )
        .exists()
    )

    date_hit = DJSet.played_date.cast(String).like(raw_plain, escape="\\")

    title_hit = or_(_title_pred(DJSet.search_text), child_title_exists)
    match = or_(title_hit, artist_exists, channel_exists, date_hit)

    where_clauses = (DJSet.parent_set_id.is_(None), set_reliable(), match)

    # Correlated scalar count avoids a GROUP BY next to the boolean-hit columns.
    track_count_sq = (
        select(func.count(SetTrack.id))
        .where(SetTrack.set_id == DJSet.id)
        .correlate(DJSet)
        .scalar_subquery()
    )

    base = (
        select(
            DJSet.id,
            DJSet.title,
            DJSet.played_date,
            DJSet.has_artwork,
            track_count_sq.label("track_count"),
            title_hit.label("title_hit"),
            artist_exists.label("artist_hit"),
            channel_exists.label("channel_hit"),
        )
        .where(*where_clauses)
        .order_by(DJSet.played_date.desc().nulls_last(), DJSet.id.desc())
        .limit(_SET_CANDIDATE_CAP)
    )

    # Exact, uncapped total consistent with the same WHERE.
    count_q = select(func.count()).select_from(
        select(DJSet.id).where(*where_clauses).subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    rows = (await db.execute(base)).all()

    def _weight(r) -> int:
        if r.title_hit or r.artist_hit:
            return 3
        if r.channel_hit:
            return 2
        return 1

    ranked = sorted(
        rows,
        key=lambda r: (
            -_weight(r),
            -_relevance(search_fold(r.title or ""), fq),
            -(r.track_count or 0),
            -r.id,
        ),
    )
    window = ranked[offset : offset + limit]

    items: list[SearchItem] = []
    for r in window:
        items.append(
            SearchItem(
                type="set",
                id=r.id,
                title=r.title,
                played_date=r.played_date.isoformat() if r.played_date else None,
                track_count=r.track_count,
                has_artwork=r.has_artwork,
            )
        )
    return items, total


async def _search_playlists(
    db: AsyncSession,
    q: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    # X4.h: space-insensitive on the playlist title (shared helper). The single
    # `base` query backs both the items and the count subquery, so `total` is
    # always consistent with the returned window.
    base = (
        select(
            WatchedEntity.id,
            WatchedEntity.title,
            WatchedEntity.source,
            WatchedEntity.track_count,
            WatchedEntity.has_artwork,
        )
        .where(space_insensitive_ilike(q, WatchedEntity.title))
        .order_by(WatchedEntity.title, WatchedEntity.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="playlist",
                id=r.id,
                title=r.title,
                source=r.source,
                track_count=r.track_count,
                has_artwork=r.has_artwork,
            )
        )
    return items, total


async def _search_albums(
    db: AsyncSession,
    q: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    # Space-insensitive match on the album title AND its (nullable) normalized
    # title, mirroring the sets/playlists scopes. The single `base` query backs
    # both the items and the count subquery so `total` stays consistent.
    title_match = space_insensitive_ilike(q, Album.title, Album.normalized_title)

    base = (
        select(
            Album.id,
            Album.title,
            Album.record_type,
            Album.release_date,
            Album.has_artwork,
            Artist.name.label("artist_name"),
        )
        .outerjoin(Artist, Artist.id == Album.artist_id)
        .where(title_match)
        .order_by(Album.title, Album.id)
    )

    total_r = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_r.scalar() or 0

    rows = (await db.execute(base.offset(offset).limit(limit))).all()

    items: list[SearchItem] = []
    for r in rows:
        items.append(
            SearchItem(
                type="album",
                id=r.id,
                title=r.title,
                artist=r.artist_name,
                record_type=r.record_type.value if r.record_type else None,
                year=r.release_date.year if r.release_date else None,
                has_artwork=r.has_artwork,
            )
        )
    return items, total


async def _search_genres(
    db: AsyncSession,
    q: str,
    user_id: int | None,
    is_guest: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchItem], int]:
    pattern = f"%{like_escape(q)}%"

    result = await db.execute(
        text("""
        SELECT
            g AS name,
            COUNT(*)::int AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi
        FROM catalog c, unnest(c.genres) AS g
        WHERE LOWER(g) LIKE LOWER(:pattern) ESCAPE '\\'
        GROUP BY g
        ORDER BY COUNT(*) DESC, g
        LIMIT :lim OFFSET :off
    """),
        {"pattern": pattern, "lim": limit, "off": offset},
    )
    rows = result.all()

    # total distinct genres matching
    total_r = await db.execute(
        text("""
        SELECT COUNT(DISTINCT g)::int
        FROM catalog c, unnest(c.genres) AS g
        WHERE LOWER(g) LIKE LOWER(:pattern) ESCAPE '\\'
    """),
        {"pattern": pattern},
    )
    total = total_r.scalar() or 0

    items: list[SearchItem] = []
    for r in rows:
        p, d = genre_pillar(r.name)
        items.append(
            SearchItem(
                type="genre",
                name=r.name,
                pillar=p,
                depth=d,
                track_count=r.track_count,
                artist_count=r.artist_count,
                bpm_lo=r.bpm_lo,
                bpm_hi=r.bpm_hi,
            )
        )
    return items, total


# ── Orchestration ─────────────────────────────────────────────────


async def search(
    db: AsyncSession,
    q: str,
    scope: str,
    limit: int,
    offset: int,
    user_id: int | None,
    is_guest: bool,
) -> SearchResponse:
    """Cross-type search: per-scope queries, relevance ranking, guest cap."""
    await ensure_pillar_cache(db)
    q_lower = q.strip().lower()

    if not q_lower:
        return SearchResponse(items=[], total=0, totals=SearchTotals())

    # For a single scope, offset+limit are pushed straight into the DB query
    # (true pagination). For scope="all", results from every type are merged and
    # re-ranked in Python, which forbids a meaningful global DB offset — so offset
    # is ignored there (see pagination block below) and only limit is applied.
    per_type_limit = limit if scope != "all" else 30
    per_type_offset = offset if scope != "all" else 0

    all_items: list[SearchItem] = []
    totals = SearchTotals()

    if scope in ("all", "track"):
        items, t = await _search_tracks(
            db, q_lower, user_id, is_guest, per_type_limit, per_type_offset
        )
        all_items.extend(items)
        totals.track = t

    if scope in ("all", "artist"):
        items, t = await _search_artists(
            db, q_lower, user_id, is_guest, per_type_limit, per_type_offset
        )
        all_items.extend(items)
        totals.artist = t

    if scope in ("all", "set"):
        items, t = await _search_sets(db, q_lower, per_type_limit, per_type_offset)
        all_items.extend(items)
        totals.set = t

    if scope in ("all", "playlist"):
        items, t = await _search_playlists(db, q_lower, per_type_limit, per_type_offset)
        all_items.extend(items)
        totals.playlist = t

    if scope in ("all", "album"):
        items, t = await _search_albums(db, q_lower, per_type_limit, per_type_offset)
        all_items.extend(items)
        totals.album = t

    if scope in ("all", "genre"):
        items, t = await _search_genres(
            db, q_lower, user_id, is_guest, per_type_limit, per_type_offset
        )
        all_items.extend(items)
        totals.genre = t

    # Sort by relevance: exact > prefix > substring, tie-break by popularity
    def sort_key(item: SearchItem) -> tuple[int, int]:
        label = (item.name or item.title or "").lower()
        rel = _relevance(label, q_lower)
        pop = item.track_count or 0
        return (-rel, -pop)

    # This global re-sort serves the cross-type interleaving of scope="all" and
    # the relevance-first ranking of the other single-type scopes. It is skipped
    # for scope="set": there `_search_sets` already returns its window in the
    # authoritative WEIGHTED order (title/artist > channel > date), which this
    # title-relevance-only sort would otherwise flatten (a channel match with a
    # high track_count could overtake a substring title match — both _relevance=1).
    if scope != "set":
        all_items.sort(key=sort_key)

    total = (
        totals.track
        + totals.artist
        + totals.set
        + totals.playlist
        + totals.genre
        + totals.album
    )

    # Guest cap
    if is_guest:
        capped = all_items[:GUEST_CAP]
        return SearchResponse(items=capped, total=total, totals=totals)

    # Paginate. For a single scope the DB already applied offset+limit, so return
    # the merged window as-is. For scope="all" offset is ignored (merge-in-Python
    # can't honor a global offset); only the limit bounds the merged result.
    page = all_items if scope != "all" else all_items[:limit]
    return SearchResponse(items=page, total=total, totals=totals)
