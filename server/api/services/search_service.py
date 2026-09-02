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


# Cap on the number of candidate roots pulled from the DB for the in-memory
# weighted ranking. A set can match on several fields (title, artist, channel,
# date) with different per-field weights, so the final order can only be computed
# in Python — but ranking every match would be unbounded. 1000 is comfortably
# above any realistic search window; if the matching-root union exceeds it, only
# the newest 1000 valid roots are ranked (played_date desc, id desc) — the
# returned `total` stays EXACT via the separate uncapped count query.
_SET_CANDIDATE_CAP = 1000


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

    SET-BASED implementation (perf hotfix): instead of scanning every root with a
    per-row OR of correlated ``EXISTS`` subqueries, each signal is collected once
    as an index-friendly SET of matching ROOT ids (a child match bubbles to its
    parent via ``COALESCE(parent_set_id, id)``). The Python union is then fed to
    a single roots-only + reliable filter (exact ``total``) and a capped detail
    fetch. Every collector is ONE scan/indexed join — no correlated subquery —
    and the DB awaits are sequential (never gathered on a shared session).
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

    # Root-id for a matched set: itself when it is a root, else its parent.
    root_of = func.coalesce(DJSet.parent_set_id, DJSet.id)

    # (1) TITLE — a matching root OR a matching child (bubbled to its parent).
    #     One seq scan on `sets`, no correlated child EXISTS.
    title_rows = (
        await db.execute(
            select(DJSet.id, DJSet.parent_set_id).where(_title_pred(DJSet.search_text))
        )
    ).all()
    title_ids = {r.parent_set_id if r.parent_set_id is not None else r.id for r in title_rows}

    # (2) ARTIST — linked artist name (rare), bubbled to the root.
    artist_rows = (
        await db.execute(
            select(root_of)
            .join(SetArtist, SetArtist.set_id == DJSet.id)
            .join(Artist, Artist.id == SetArtist.artist_id)
            .where(func.lower(Artist.name).like(raw_plain, escape="\\"))
        )
    ).all()
    artist_ids = {r[0] for r in artist_rows}

    # (3) CHANNEL — via `trackid_index` of the set (or a child), bubbled to root.
    #     The join keys on trackid_index.set_id (index ix_trackid_index_set_id);
    #     no OR inside the join condition, no correlated EXISTS.
    channel_rows = (
        await db.execute(
            select(root_of)
            .join(TrackIdIndex, TrackIdIndex.set_id == DJSet.id)
            .where(_channel_pred(TrackIdIndex.channel))
        )
    ).all()
    channel_ids = {r[0] for r in channel_rows}

    # (4) DATE — a root's own played_date typed as text (roots only, as before).
    date_rows = (
        await db.execute(
            select(DJSet.id).where(
                DJSet.parent_set_id.is_(None),
                DJSet.played_date.cast(String).like(raw_plain, escape="\\"),
            )
        )
    ).all()
    date_ids = {r.id for r in date_rows}

    weight3 = title_ids | artist_ids
    weight2 = channel_ids
    weight1 = date_ids
    union = weight3 | weight2 | weight1
    if not union:
        return [], 0

    union_list = list(union)

    # Exact, uncapped total: roots-only + reliable applied to the full union.
    count_q = select(func.count()).select_from(
        select(DJSet.id)
        .where(DJSet.id.in_(union_list), DJSet.parent_set_id.is_(None), set_reliable())
        .subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    # Capped detail fetch of the valid roots, with their track counts. The LEFT
    # JOIN + GROUP BY yields 0 for a track-less root (matches the old scalar sq).
    detail_q = (
        select(
            DJSet.id,
            DJSet.title,
            DJSet.played_date,
            DJSet.has_artwork,
            func.count(SetTrack.id).label("track_count"),
        )
        .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
        .where(DJSet.id.in_(union_list), DJSet.parent_set_id.is_(None), set_reliable())
        .group_by(DJSet.id, DJSet.title, DJSet.played_date, DJSet.has_artwork)
        .order_by(DJSet.played_date.desc().nulls_last(), DJSet.id.desc())
        .limit(_SET_CANDIDATE_CAP)
    )
    rows = (await db.execute(detail_q)).all()

    def _weight(sid: int) -> int:
        if sid in weight3:
            return 3
        if sid in weight2:
            return 2
        return 1

    ranked = sorted(
        rows,
        key=lambda r: (
            -_weight(r.id),
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
