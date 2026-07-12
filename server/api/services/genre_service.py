"""
Genre service: pillar cache + all genre business logic.

Owns the genre->pillar mapping cache used by catalog, artists, and genres routers.
Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

ALL_PILLARS = ("house", "techno", "trance", "dnb", "hardcore", "harddance", "autres")

_ROOT_TO_PILLAR = {
    "house music": "house",
    "disco": "house",
    "UK garage": "house",
    "techno": "techno",
    "trance": "trance",
    "drum and bass": "dnb",
    "dubstep": "dnb",
    "breakbeat": "dnb",
    "hardcore": "hardcore",
    "hard dance": "harddance",
}

# Cache: raw_name -> (pillar, depth)
_PILLAR_CACHE: dict[str, tuple[str, int]] = {}
_pillar_cache_attempted = False


def genre_pillar(genre_name: str) -> tuple[str, int]:
    """Return (pillar, depth) for a genre. Fallback: ('autres', 0)."""
    return _PILLAR_CACHE.get(genre_name, ("autres", 0))


def pillar_map() -> dict[str, tuple[str, int]]:
    """Live view of the pillar cache: raw genre name -> (pillar, depth).

    Read-only accessor for consumers that need to iterate the whole mapping;
    mutations belong to this module only.
    """
    return _PILLAR_CACHE


def _pillar_genre_names(pillar: str) -> list[str]:
    """Genre names belonging to a pillar (from cache)."""
    return [name for name, (p, _d) in _PILLAR_CACHE.items() if p == pillar]


async def _load_pillar_cache(db: AsyncSession) -> None:
    global _PILLAR_CACHE
    root_labels = list(_ROOT_TO_PILLAR.keys())
    rows = (
        await db.execute(
            text("""
        WITH RECURSIVE mapped AS (
            SELECT gm.raw_name, gm.node_id, gn.label AS node_label
            FROM genre_mappings gm
            JOIN genre_nodes gn ON gn.id = gm.node_id
        ),
        anc AS (
            SELECT m.raw_name, m.node_id, ge.to_node_id AS ancestor_id, 1 AS depth
            FROM mapped m
            JOIN genre_edges ge ON ge.from_node_id = m.node_id AND ge.type = 'parent'
            UNION ALL
            SELECT a.raw_name, a.node_id, ge.to_node_id, a.depth + 1
            FROM anc a
            JOIN genre_edges ge ON ge.from_node_id = a.ancestor_id AND ge.type = 'parent'
            WHERE a.depth < 10
        ),
        ancestor_match AS (
            SELECT a.raw_name, gn.label AS ancestor_label, MIN(a.depth) AS depth
            FROM anc a
            JOIN genre_nodes gn ON gn.id = a.ancestor_id
            WHERE gn.label = ANY(:root_labels)
            GROUP BY a.raw_name, gn.label
        ),
        best AS (
            SELECT DISTINCT ON (raw_name) raw_name, ancestor_label, depth
            FROM ancestor_match
            ORDER BY raw_name, depth
        )
        SELECT m.raw_name, m.node_label,
               b.ancestor_label, b.depth AS ancestor_depth
        FROM mapped m
        LEFT JOIN best b ON b.raw_name = m.raw_name
    """),
            {"root_labels": root_labels},
        )
    ).fetchall()

    cache: dict[str, tuple[str, int]] = {}
    for r in rows:
        if r.node_label in _ROOT_TO_PILLAR:
            cache[r.raw_name] = (_ROOT_TO_PILLAR[r.node_label], 0)
        elif r.ancestor_label and r.ancestor_label in _ROOT_TO_PILLAR:
            depth = min(r.ancestor_depth, 3)
            cache[r.raw_name] = (_ROOT_TO_PILLAR[r.ancestor_label], depth)
        else:
            cache[r.raw_name] = ("autres", 0)

    _PILLAR_CACHE.update(cache)
    log.info("Pillar cache loaded: %d genres", len(cache))


async def ensure_pillar_cache(db: AsyncSession) -> None:
    global _pillar_cache_attempted
    if _PILLAR_CACHE or _pillar_cache_attempted:
        return
    _pillar_cache_attempted = True
    try:
        await _load_pillar_cache(db)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        log.warning("Pillar cache load failed (SQLite?), using empty cache")


async def resolve_genre(db: AsyncSession, name: str) -> str:
    """Return canonical genre name (exact casing from DB). Raises LookupError if not found."""
    result = await db.execute(
        text("SELECT g FROM catalog, unnest(genres) AS g WHERE LOWER(g) = LOWER(:name) LIMIT 1"),
        {"name": name},
    )
    row = result.fetchone()
    if not row:
        raise LookupError(f"Genre not found: {name}")
    return row.g


async def list_genres(
    db: AsyncSession,
    user_id: int | None,
    family: str | None,
    sort: str,
    q: str | None,
    limit: int,
    offset: int,
) -> dict:
    await ensure_pillar_cache(db)

    family_genres: list[str] | None = None
    if family and family in ALL_PILLARS:
        family_genres = _pillar_genre_names(family)
        if not family_genres:
            return {"items": [], "total": 0, "pillarCounts": {p: 0 for p in ALL_PILLARS}}

    q_pattern = f"%{q.lower()}%" if q else ""

    stats_result = await db.execute(
        text("""
        SELECT
            g AS genre,
            COUNT(*)::int                                                    AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int                             AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi,
            COUNT(DISTINCT ut.catalog_id)::int                               AS in_lib_count
        FROM catalog c
        CROSS JOIN LATERAL unnest(c.genres) AS g
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE (:family_filter = false OR g = ANY(:family_genres))
          AND (:q_filter = false OR LOWER(g) LIKE :q_pattern)
        GROUP BY g
    """),
        {
            "user_id": user_id,
            "family_filter": family_genres is not None,
            "family_genres": family_genres or [],
            "q_filter": bool(q),
            "q_pattern": q_pattern,
        },
    )
    all_genres = stats_result.fetchall()

    if sort == "alpha":
        all_genres = sorted(all_genres, key=lambda r: r.genre.lower())
    else:
        all_genres = sorted(all_genres, key=lambda r: -r.track_count)

    total = len(all_genres)
    page_genres = all_genres[offset : offset + limit]

    genre_names = [r.genre for r in page_genres]

    artworks_map: dict[str, list[str]] = {g: [] for g in genre_names}
    if genre_names:
        from services.catalog_service import catalog_visible_sql

        aw_result = await db.execute(
            text(f"""
            SELECT genre, id FROM (
                SELECT g AS genre, c.id,
                       ROW_NUMBER() OVER (PARTITION BY g ORDER BY c.id DESC) AS rn
                FROM catalog c CROSS JOIN LATERAL unnest(c.genres) AS g
                WHERE g = ANY(:genres) AND c.has_artwork = true
                  AND {catalog_visible_sql(user_id)}
            ) sub WHERE rn <= 4
        """),
            {
                "genres": genre_names,
                **({"viewer_id": user_id} if user_id is not None else {}),
            },
        )
        for row in aw_result.fetchall():
            artworks_map[row.genre].append(f"/storage/catalog-artworks/{row.id}.jpg")

    artists_map: dict[str, list[dict]] = {g: [] for g in genre_names}
    if genre_names:
        ar_result = await db.execute(
            text("""
            SELECT genre, artist_id, artist_name FROM (
                SELECT g AS genre, a.id AS artist_id, a.name AS artist_name,
                       COUNT(*) AS track_cnt,
                       ROW_NUMBER() OVER (
                           PARTITION BY g
                           ORDER BY COUNT(*) DESC, a.id
                       ) AS rn
                FROM catalog c CROSS JOIN LATERAL unnest(c.genres) AS g
                JOIN artists a ON a.normalized_name = LOWER(c.artist)
                    AND a.has_artwork = true
                WHERE g = ANY(:genres) AND c.artist IS NOT NULL
                GROUP BY g, a.id, a.name
            ) ranked WHERE rn <= 3
        """),
            {"genres": genre_names},
        )
        for row in ar_result.fetchall():
            artists_map[row.genre].append(
                {
                    "id": row.artist_id,
                    "name": row.artist_name,
                    "image": f"/storage/artist-artworks/{row.artist_id}.jpg",
                }
            )

    items = []
    for row in page_genres:
        pillar, depth = genre_pillar(row.genre)
        items.append(
            {
                "name": row.genre,
                "pillar": pillar,
                "depth": depth,
                "trackCount": row.track_count,
                "artistCount": row.artist_count,
                "bpmLo": row.bpm_lo,
                "bpmHi": row.bpm_hi,
                "inLibCount": row.in_lib_count,
                "artworks": artworks_map.get(row.genre, []),
                "artists": artists_map.get(row.genre, []),
            }
        )

    fc_result = await db.execute(
        text("""
        SELECT g AS genre, COUNT(*)::int AS cnt
        FROM catalog c CROSS JOIN LATERAL unnest(c.genres) AS g
        WHERE (:q_filter = false OR LOWER(g) LIKE :q_pattern)
        GROUP BY g
    """),
        {"q_filter": bool(q), "q_pattern": q_pattern},
    )
    pillar_counts: dict[str, int] = {p: 0 for p in ALL_PILLARS}
    for fc_row in fc_result.fetchall():
        p, _d = genre_pillar(fc_row.genre)
        pillar_counts[p] += 1

    return {"items": items, "total": total, "pillarCounts": pillar_counts}


async def get_detail(db: AsyncSession, name: str, user_id: int | None) -> dict:
    genre = await resolve_genre(db, name)
    await ensure_pillar_cache(db)

    s = (
        await db.execute(
            text("""
        SELECT
            COUNT(*)::int AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi,
            COUNT(DISTINCT ut.catalog_id)::int AS in_lib_count
        FROM catalog c
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE :genre = ANY(c.genres)
    """),
            {"genre": genre, "user_id": user_id},
        )
    ).fetchone()

    set_count = (
        await db.execute(
            text("""
        SELECT COUNT(DISTINCT st.set_id)::int AS cnt
        FROM set_tracks st
        JOIN catalog c ON c.id = st.catalog_id
        WHERE :genre = ANY(c.genres)
    """),
            {"genre": genre},
        )
    ).scalar()

    playlist_count = (
        await db.execute(
            text("""
        SELECT COUNT(DISTINCT rt.watched_entity_id)::int AS cnt
        FROM radar_tracks rt
        JOIN catalog c ON c.id = rt.catalog_id
        WHERE :genre = ANY(c.genres)
    """),
            {"genre": genre},
        )
    ).scalar()

    from services.catalog_service import catalog_visible_sql

    aw_result = await db.execute(
        text(f"""
        SELECT id FROM (
            SELECT c.id,
                   ROW_NUMBER() OVER (ORDER BY c.id DESC) AS rn
            FROM catalog c
            WHERE :genre = ANY(c.genres) AND c.has_artwork = true
              AND {catalog_visible_sql(user_id)}
        ) sub WHERE rn <= 6
    """),
        {
            "genre": genre,
            **({"viewer_id": user_id} if user_id is not None else {}),
        },
    )
    artworks = [f"/storage/catalog-artworks/{r.id}.jpg" for r in aw_result.fetchall()]

    ar_result = await db.execute(
        text("""
        SELECT artist_id, artist_name FROM (
            SELECT a.id AS artist_id, a.name AS artist_name,
                   COUNT(*) AS track_cnt,
                   ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, a.id) AS rn
            FROM catalog c
            JOIN artists a ON a.normalized_name = LOWER(c.artist) AND a.has_artwork = true
            WHERE :genre = ANY(c.genres) AND c.artist IS NOT NULL
            GROUP BY a.id, a.name
        ) ranked WHERE rn <= 3
    """),
        {"genre": genre},
    )
    artists = [
        {
            "id": r.artist_id,
            "name": r.artist_name,
            "image": f"/storage/artist-artworks/{r.artist_id}.jpg",
        }
        for r in ar_result.fetchall()
    ]

    pillar, depth = genre_pillar(genre)
    return {
        "name": genre,
        "pillar": pillar,
        "depth": depth,
        "trackCount": s.track_count,
        "artistCount": s.artist_count,
        "bpmLo": s.bpm_lo,
        "bpmHi": s.bpm_hi,
        "inLibCount": s.in_lib_count,
        "setCount": set_count,
        "playlistCount": playlist_count,
        "artworks": artworks,
        "artists": artists,
    }


async def list_genre_artists(
    db: AsyncSession, name: str, user_id: int | None, limit: int, offset: int
) -> dict:
    genre = await resolve_genre(db, name)
    result = await db.execute(
        text("""
        SELECT a.id, a.name, a.has_artwork,
               COUNT(*)::int AS track_count,
               COUNT(DISTINCT ut.catalog_id)::int AS in_lib_count,
               COUNT(*) OVER()::int AS total
        FROM catalog c
        JOIN artists a ON a.normalized_name = LOWER(c.artist)
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE :genre = ANY(c.genres) AND c.artist IS NOT NULL AND c.artist != ''
        GROUP BY a.id, a.name, a.has_artwork
        ORDER BY track_count DESC, a.name
        LIMIT :limit OFFSET :offset
    """),
        {"genre": genre, "user_id": user_id, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()
    total = rows[0].total if rows else 0
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "hasArtwork": r.has_artwork,
                "trackCount": r.track_count,
                "inLibCount": r.in_lib_count,
            }
            for r in rows
        ],
        "total": total,
    }


async def list_genre_sets(db: AsyncSession, name: str, limit: int, offset: int) -> dict:
    genre = await resolve_genre(db, name)
    result = await db.execute(
        text("""
        SELECT s.id, s.title, s.played_date, s.has_artwork,
               COUNT(DISTINCT st.id)::int AS genre_track_count,
               total_sub.total_tracks,
               COUNT(*) OVER()::int AS total
        FROM sets s
        JOIN set_tracks st ON st.set_id = s.id
        JOIN catalog c ON c.id = st.catalog_id AND :genre = ANY(c.genres)
        CROSS JOIN LATERAL (
            SELECT COUNT(*)::int AS total_tracks FROM set_tracks WHERE set_id = s.id
        ) total_sub
        WHERE s.parent_set_id IS NULL
        GROUP BY s.id, s.title, s.played_date, s.has_artwork, total_sub.total_tracks
        ORDER BY genre_track_count DESC, s.played_date DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """),
        {"genre": genre, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()
    total = rows[0].total if rows else 0
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "playedDate": r.played_date.isoformat() if r.played_date else None,
                "hasArtwork": r.has_artwork,
                "genreTrackCount": r.genre_track_count,
                "totalTracks": r.total_tracks,
            }
            for r in rows
        ],
        "total": total,
    }


async def list_genre_playlists(db: AsyncSession, name: str, limit: int, offset: int) -> dict:
    genre = await resolve_genre(db, name)
    result = await db.execute(
        text("""
        SELECT we.id, we.title, we.source, we.has_artwork, we.owner,
               COUNT(DISTINCT rt.catalog_id)::int AS genre_track_count,
               COUNT(*) OVER()::int AS total
        FROM watched_entities we
        JOIN radar_tracks rt ON rt.watched_entity_id = we.id
        JOIN catalog c ON c.id = rt.catalog_id AND :genre = ANY(c.genres)
        GROUP BY we.id, we.title, we.source, we.has_artwork, we.owner
        ORDER BY genre_track_count DESC
        LIMIT :limit OFFSET :offset
    """),
        {"genre": genre, "limit": limit, "offset": offset},
    )
    rows = result.fetchall()
    total = rows[0].total if rows else 0
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "source": r.source,
                "hasArtwork": r.has_artwork,
                "owner": r.owner,
                "genreTrackCount": r.genre_track_count,
            }
            for r in rows
        ],
        "total": total,
    }


async def list_genre_tracks(
    db: AsyncSession,
    name: str,
    user_id: int | None,
    sort: str,
    q: str | None,
    in_lib: int | None,
    limit: int,
    offset: int,
) -> dict:
    from services.catalog_service import catalog_visible_sql

    genre = await resolve_genre(db, name)
    order_clauses = {
        "recent": "c.created_at DESC NULLS LAST",
        "bpm": "c.bpm ASC NULLS LAST",
        "alpha": "LOWER(c.title) ASC",
        "key": (
            "CASE WHEN c.key IS NULL OR c.key = '' THEN 1 ELSE 0 END,"
            " CAST(regexp_replace(c.key, '[^0-9]', '', 'g') AS int),"
            " SUBSTRING(c.key FROM '[A-Ba-b]$')"
        ),
    }
    order_sql = order_clauses[sort]
    q_pattern = f"%{q.lower()}%" if q else ""

    result = await db.execute(
        text(f"""
        SELECT c.id, c.title, c.artist, c.bpm, c.key, c.duration_ms,
               c.has_artwork, c.has_preview,
               CASE WHEN ut.catalog_id IS NOT NULL THEN true ELSE false END AS in_lib,
               COUNT(*) OVER()::int AS total
        FROM catalog c
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE :genre = ANY(c.genres)
          AND {catalog_visible_sql(user_id)}
          AND (:q_filter = false OR (LOWER(c.title) LIKE :q_pattern OR LOWER(c.artist) LIKE :q_pattern))
          AND (:lib_filter = false OR
               (:in_lib = 1 AND ut.catalog_id IS NOT NULL) OR
               (:in_lib = 0 AND ut.catalog_id IS NULL))
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """),
        {
            "genre": genre,
            "user_id": user_id,
            "q_filter": bool(q),
            "q_pattern": q_pattern,
            "lib_filter": in_lib is not None,
            "in_lib": in_lib if in_lib is not None else -1,
            "limit": limit,
            "offset": offset,
            **({"viewer_id": user_id} if user_id is not None else {}),
        },
    )
    rows = result.fetchall()
    total = rows[0].total if rows else 0
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "artist": r.artist,
                "bpm": r.bpm,
                "key": r.key,
                "durationMs": r.duration_ms,
                "hasArtwork": r.has_artwork,
                "hasPreview": r.has_preview,
                "inLib": r.in_lib,
            }
            for r in rows
        ],
        "total": total,
    }


async def get_neighbors(db: AsyncSession, name: str, limit: int) -> dict:
    genre = await resolve_genre(db, name)
    await ensure_pillar_cache(db)
    result = await db.execute(
        text("""
        WITH genre_artists AS (
            SELECT DISTINCT LOWER(artist) AS artist_name
            FROM catalog
            WHERE :genre = ANY(genres) AND artist IS NOT NULL AND artist != ''
        )
        SELECT g AS genre,
               COUNT(DISTINCT LOWER(c.artist))::int AS common_artists,
               COUNT(*)::int AS track_count
        FROM catalog c
        CROSS JOIN LATERAL unnest(c.genres) AS g
        JOIN genre_artists ga ON LOWER(c.artist) = ga.artist_name
        WHERE g != :genre
        GROUP BY g
        ORDER BY common_artists DESC
        LIMIT :limit
    """),
        {"genre": genre, "limit": limit},
    )
    items = []
    for r in result.fetchall():
        p, d = genre_pillar(r.genre)
        items.append(
            {
                "name": r.genre,
                "pillar": p,
                "depth": d,
                "commonArtists": r.common_artists,
                "trackCount": r.track_count,
            }
        )
    return {"items": items}


async def random_track(
    db: AsyncSession, genre: str, exclude_id: int | None, user_id: int | None = None
) -> dict:
    from services.catalog_service import catalog_visible_sql

    result = await db.execute(
        text(f"""
        SELECT id, title, artist, bpm, key FROM catalog
        WHERE :genre = ANY(genres)
          AND has_preview = true
          AND {catalog_visible_sql(user_id, alias="catalog")}
          AND (:has_exclude = false OR id != :exclude_id)
        ORDER BY random()
        LIMIT 1
    """),
        {
            "genre": genre,
            "has_exclude": exclude_id is not None,
            "exclude_id": exclude_id or 0,
            **({"viewer_id": user_id} if user_id is not None else {}),
        },
    )
    row = result.fetchone()
    if not row:
        raise LookupError("No previewable track for this genre")
    return {
        "catalog_id": row.id,
        "title": row.title,
        "artist": row.artist,
        "bpm": row.bpm,
        "key": row.key,
    }


async def merge(db: AsyncSession, source: str, target: str) -> dict:
    src = await resolve_genre(db, source)
    tgt = await resolve_genre(db, target)
    if src == tgt:
        raise ValueError("Source and target are the same genre")
    result = await db.execute(
        text("""
        UPDATE catalog
        SET genres = (SELECT ARRAY(SELECT DISTINCT unnest(array_replace(genres, :source, :target))))
        WHERE :source = ANY(genres)
    """),
        {"source": src, "target": tgt},
    )
    await db.commit()
    return {"merged": True, "source": src, "target": tgt, "affected": result.rowcount}


async def rename(db: AsyncSession, old_name: str, new_name: str) -> dict:
    genre = await resolve_genre(db, old_name)
    if not new_name:
        raise ValueError("New name cannot be empty")
    if new_name == genre:
        raise ValueError("New name is the same as current")
    existing = await db.execute(
        text("SELECT 1 FROM catalog WHERE :new_name = ANY(genres) LIMIT 1"),
        {"new_name": new_name},
    )
    if existing.fetchone():
        raise ValueError(f"Genre '{new_name}' already exists — use merge instead")
    result = await db.execute(
        text("""
        UPDATE catalog
        SET genres = array_replace(genres, :old_name, :new_name)
        WHERE :old_name = ANY(genres)
    """),
        {"old_name": genre, "new_name": new_name},
    )
    await db.commit()
    return {"renamed": True, "from": genre, "to": new_name, "affected": result.rowcount}


async def lookup_deezer_genres(db: AsyncSession, catalog_id: int, apply: bool) -> dict:
    """Fetch genre from Deezer for a catalog entry (via track -> album -> genres)."""
    import httpx
    from models import CatalogEntry
    from sqlalchemy import select

    entry = (
        await db.execute(select(CatalogEntry).where(CatalogEntry.id == catalog_id))
    ).scalar_one_or_none()
    if not entry:
        raise LookupError("Track not found")
    if not entry.deezer_id:
        raise ValueError("Pas de deezer_id pour ce track")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://api.deezer.com/track/{entry.deezer_id}")
        track_data = r.json()
        album_id = (track_data.get("album") or {}).get("id")
        if not album_id:
            return {"status": "no_album", "genres": []}
        r2 = await client.get(f"https://api.deezer.com/album/{album_id}")
        album_data = r2.json()
        genres_data = (album_data.get("genres") or {}).get("data") or []
        genre_names = [g["name"] for g in genres_data if g.get("name")]

    result_data = {"status": "ok", "genres": genre_names, "applied": False}
    if apply and genre_names:
        entry.genres = genre_names[:3]
        await db.commit()
        result_data["applied"] = True
        result_data["genres"] = entry.genres
    return result_data
