import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user_optional, require_admin, uid as _uid
from models import User

router = APIRouter(tags=["genres"])

# ── Genre -> family mapping (mirror of frontend diggy-style-map.js) ──────

_ALL_FAMILIES = ('house', 'techno', 'trance', 'other', 'misc')

_SLUG_FAMILY: dict[str, str] = {}
_NAME_FAMILY: dict[str, str] = {}   # original name -> family (for reverse lookup)


def _slug(name: str) -> str:
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', name.lower()))


def _register(family: str, names: list[str]):
    for n in names:
        _SLUG_FAMILY[_slug(n)] = family
        _NAME_FAMILY[n] = family


_register('house', [
    'House', 'Deep House', 'Tech House', 'Afro House', 'Bass House',
    'Progressive House', 'Jackin House', 'Funky House', 'Soulful House',
    'Organic House', 'Organic House / Downtempo', 'Afro / Organic House',
    'Nu Disco / Disco', 'Nu-Disco', 'Nu Disco', 'Indie Dance',
    'Melodic House', 'French Touch', 'UK House', 'UK Garage', 'UK Garage / Bassline',
    'Downtempo', 'Minimal / Deep Tech',
])
_register('techno', [
    'Techno (Peak Time / Driving)', 'Techno (Peak Time)', 'Techno (Raw / Deep / Hypnotic)',
    'Hard Techno', 'Melodic House & Techno', 'Melodic Techno', 'Minimal Techno',
    'Electro (Classic / Detroit / Modern)', 'Electro Brut', 'Electro brut',
    'Classic/Min. Techno', 'Hard/Dark Techno', 'Trance Techno',
])
_register('trance', [
    'Trance (Main Floor)', 'Trance (Raw / Deep / Hypnotic)',
    'Psy-Trance', 'Psytrance',
    'Hard Dance / Hardcore / Neo Rave', 'Hard Dance',
])
_register('other', [
    'Drum & Bass', 'Breaks / Breakbeat / UK Bass', 'Electronica',
    'Rock', 'Hip-Hop', 'R&B', 'Pop', 'Funk / Soul', 'Funk-Soul',
    'Bass', 'Country', 'Latin', 'Latin Electronic',
    '140 / Deep Dubstep / Grime', 'Dubstep', 'Trap / Future Bass',
    'Bass / Club', 'Ambient / Experimental', 'African', 'Caribbean',
])
_register('misc', [
    'DJ Tools / Acapellas', 'DJ Tools / Acape', 'DJ Edits',
    'Mainstage', 'Dance / Pop', 'Misc. Tracks',
])


def genre_family(genre_name: str) -> str:
    return _SLUG_FAMILY.get(_slug(genre_name), 'misc')


def _family_genre_names(family: str) -> list[str]:
    """Original genre names belonging to a family."""
    return [name for name, fam in _NAME_FAMILY.items() if fam == family]


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/random-track")
async def random_genre_track(
    genre: str = Query(...),
    exclude: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return a random previewable catalog entry for the given genre."""
    result = await db.execute(text("""
        SELECT id FROM catalog
        WHERE genre = :genre
          AND has_preview = true
          AND (:has_exclude = false OR id != :exclude_id)
        ORDER BY random()
        LIMIT 1
    """), {"genre": genre, "has_exclude": exclude is not None, "exclude_id": exclude or 0})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "No previewable track for this genre")
    return {"catalog_id": row.id}


@router.get("")
async def list_genres(
    sort: str = Query("tracks", pattern="^(tracks|alpha)$"),
    family: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Aggregated genre cards with stats, artworks, and artist photos."""
    user_id = _uid(user)

    # Family filter — "other" includes misc (front merges both into "Autre" chip)
    family_genres: list[str] | None = None
    if family and family in _ALL_FAMILIES:
        family_genres = _family_genre_names(family)
        if family == 'other':
            family_genres = family_genres + _family_genre_names('misc')
        if not family_genres:
            return {"items": [], "total": 0, "familyCounts": {f: 0 for f in _ALL_FAMILIES}}

    q_pattern = f"%{q.lower()}%" if q else ""

    # ── Stats per genre ──
    stats_result = await db.execute(text("""
        SELECT
            c.genre,
            COUNT(*)::int                                                    AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int                             AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi,
            COUNT(DISTINCT ut.catalog_id)::int                               AS in_lib_count
        FROM catalog c
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE c.genre IS NOT NULL AND c.genre != ''
          AND (:family_filter = false OR c.genre = ANY(:family_genres))
          AND (:q_filter = false OR LOWER(c.genre) LIKE :q_pattern)
        GROUP BY c.genre
    """), {
        "user_id": user_id,
        "family_filter": family_genres is not None,
        "family_genres": family_genres or [],
        "q_filter": bool(q),
        "q_pattern": q_pattern,
    })
    all_genres = stats_result.fetchall()

    # Sort
    if sort == "alpha":
        all_genres = sorted(all_genres, key=lambda r: r.genre.lower())
    else:
        all_genres = sorted(all_genres, key=lambda r: -r.track_count)

    total = len(all_genres)
    page_genres = all_genres[offset:offset + limit]

    # ── Artworks + artists per genre (batched) ──
    genre_names = [r.genre for r in page_genres]

    # Top 4 artworks per genre
    artworks_map: dict[str, list[str]] = {g: [] for g in genre_names}
    if genre_names:
        aw_result = await db.execute(text("""
            SELECT genre, id FROM (
                SELECT c.genre, c.id,
                       ROW_NUMBER() OVER (PARTITION BY c.genre ORDER BY c.id DESC) AS rn
                FROM catalog c
                WHERE c.genre = ANY(:genres) AND c.has_artwork = true
            ) sub WHERE rn <= 4
        """), {"genres": genre_names})
        for row in aw_result.fetchall():
            artworks_map[row.genre].append(f"/storage/catalog-artworks/{row.id}.jpg")

    # Top 3 artists with photos per genre
    artists_map: dict[str, list[dict]] = {g: [] for g in genre_names}
    if genre_names:
        ar_result = await db.execute(text("""
            SELECT genre, artist_id, artist_name FROM (
                SELECT c.genre, a.id AS artist_id, a.name AS artist_name,
                       COUNT(*) AS track_cnt,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.genre
                           ORDER BY COUNT(*) DESC, a.id
                       ) AS rn
                FROM catalog c
                JOIN artists a ON a.normalized_name = LOWER(c.artist)
                    AND a.has_artwork = true
                WHERE c.genre = ANY(:genres) AND c.artist IS NOT NULL
                GROUP BY c.genre, a.id, a.name
            ) ranked WHERE rn <= 3
        """), {"genres": genre_names})
        for row in ar_result.fetchall():
            artists_map[row.genre].append({
                "id": row.artist_id,
                "name": row.artist_name,
                "image": f"/storage/artist-artworks/{row.artist_id}.jpg",
            })

    # ── Build items ──
    items = []
    for row in page_genres:
        items.append({
            "name": row.genre,
            "family": genre_family(row.genre),
            "trackCount": row.track_count,
            "artistCount": row.artist_count,
            "bpmLo": row.bpm_lo,
            "bpmHi": row.bpm_hi,
            "inLibCount": row.in_lib_count,
            "artworks": artworks_map.get(row.genre, []),
            "artists": artists_map.get(row.genre, []),
        })

    # ── Family counts (independent of family filter, respects search) ──
    fc_result = await db.execute(text("""
        SELECT c.genre, COUNT(*)::int AS cnt
        FROM catalog c
        WHERE c.genre IS NOT NULL AND c.genre != ''
          AND (:q_filter = false OR LOWER(c.genre) LIKE :q_pattern)
        GROUP BY c.genre
    """), {"q_filter": bool(q), "q_pattern": q_pattern})

    family_counts: dict[str, int] = {f: 0 for f in _ALL_FAMILIES}
    for fc_row in fc_result.fetchall():
        family_counts[genre_family(fc_row.genre)] += 1

    return {
        "items": items,
        "total": total,
        "familyCounts": family_counts,
    }


# ── Schemas ───────────────────────────────────────────────────────────────

class GenreRenameIn(BaseModel):
    new_name: str

class GenreMergeIn(BaseModel):
    source: str
    target: str


# ── Helpers ───────────────────────────────────────────────────────────────

async def _resolve_genre(db: AsyncSession, name: str) -> str:
    """Return the canonical genre name (exact casing from DB). Raise 404 if not found."""
    result = await db.execute(text("""
        SELECT genre FROM catalog
        WHERE LOWER(genre) = LOWER(:name)
        LIMIT 1
    """), {"name": name})
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Genre not found")
    return row.genre


# ── Admin (must be declared BEFORE /{name} routes) ───────────────────────

@router.post("/merge")
async def merge_genres(
    body: GenreMergeIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Merge source genre into target: reassign all tracks."""
    source = await _resolve_genre(db, body.source)
    target = await _resolve_genre(db, body.target)
    if source == target:
        raise HTTPException(400, "Source and target are the same genre")
    result = await db.execute(text("""
        UPDATE catalog SET genre = :target WHERE genre = :source
    """), {"source": source, "target": target})
    await db.commit()
    return {"merged": True, "source": source, "target": target, "affected": result.rowcount}


# ── Genre detail endpoints ────────────────────────────────────────────────

@router.get("/detail/{name:path}")
async def get_genre_detail(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Aggregated stats for a single genre (hero + StatStrip)."""
    genre = await _resolve_genre(db, name)
    user_id = _uid(user)

    # Stats
    stats = await db.execute(text("""
        SELECT
            COUNT(*)::int                                                        AS track_count,
            COUNT(DISTINCT LOWER(c.artist))::int                                 AS artist_count,
            COALESCE(ROUND(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_lo,
            COALESCE(ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY c.bpm))::int, 0) AS bpm_hi,
            COUNT(DISTINCT ut.catalog_id)::int                                   AS in_lib_count
        FROM catalog c
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE c.genre = :genre
    """), {"genre": genre, "user_id": user_id})
    s = stats.fetchone()

    # Set count
    set_result = await db.execute(text("""
        SELECT COUNT(DISTINCT st.set_id)::int AS cnt
        FROM set_tracks st
        JOIN catalog c ON c.id = st.catalog_id
        WHERE c.genre = :genre
    """), {"genre": genre})
    set_count = set_result.scalar()

    # Playlist count
    pl_result = await db.execute(text("""
        SELECT COUNT(DISTINCT rt.watched_entity_id)::int AS cnt
        FROM radar_tracks rt
        JOIN catalog c ON c.id = rt.catalog_id
        WHERE c.genre = :genre
    """), {"genre": genre})
    playlist_count = pl_result.scalar()

    # Top 6 artworks
    aw_result = await db.execute(text("""
        SELECT id FROM (
            SELECT c.id,
                   ROW_NUMBER() OVER (ORDER BY c.id DESC) AS rn
            FROM catalog c
            WHERE c.genre = :genre AND c.has_artwork = true
        ) sub WHERE rn <= 6
    """), {"genre": genre})
    artworks = [f"/storage/catalog-artworks/{r.id}.jpg" for r in aw_result.fetchall()]

    # Top 3 artists with photos
    ar_result = await db.execute(text("""
        SELECT artist_id, artist_name FROM (
            SELECT a.id AS artist_id, a.name AS artist_name,
                   COUNT(*) AS track_cnt,
                   ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, a.id) AS rn
            FROM catalog c
            JOIN artists a ON a.normalized_name = LOWER(c.artist) AND a.has_artwork = true
            WHERE c.genre = :genre AND c.artist IS NOT NULL
            GROUP BY a.id, a.name
        ) ranked WHERE rn <= 3
    """), {"genre": genre})
    artists = [
        {"id": r.artist_id, "name": r.artist_name, "image": f"/storage/artist-artworks/{r.artist_id}.jpg"}
        for r in ar_result.fetchall()
    ]

    return {
        "name": genre,
        "family": genre_family(genre),
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


@router.get("/artists/{name:path}")
async def get_genre_artists(
    name: str,
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Artists in this genre, sorted by track count."""
    genre = await _resolve_genre(db, name)
    user_id = _uid(user)

    result = await db.execute(text("""
        SELECT a.id, a.name, a.has_artwork,
               COUNT(*)::int AS track_count,
               COUNT(DISTINCT ut.catalog_id)::int AS in_lib_count,
               COUNT(*) OVER()::int AS total
        FROM catalog c
        JOIN artists a ON a.normalized_name = LOWER(c.artist)
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE c.genre = :genre AND c.artist IS NOT NULL AND c.artist != ''
        GROUP BY a.id, a.name, a.has_artwork
        ORDER BY track_count DESC, a.name
        LIMIT :limit OFFSET :offset
    """), {"genre": genre, "user_id": user_id, "limit": limit, "offset": offset})
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


@router.get("/sets/{name:path}")
async def get_genre_sets(
    name: str,
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Sets containing tracks of this genre."""
    genre = await _resolve_genre(db, name)

    result = await db.execute(text("""
        SELECT s.id, s.title, s.played_date, s.has_artwork,
               COUNT(DISTINCT st.id)::int AS genre_track_count,
               total_sub.total_tracks,
               COUNT(*) OVER()::int AS total
        FROM sets s
        JOIN set_tracks st ON st.set_id = s.id
        JOIN catalog c ON c.id = st.catalog_id AND c.genre = :genre
        CROSS JOIN LATERAL (
            SELECT COUNT(*)::int AS total_tracks FROM set_tracks WHERE set_id = s.id
        ) total_sub
        GROUP BY s.id, s.title, s.played_date, s.has_artwork, total_sub.total_tracks
        ORDER BY genre_track_count DESC, s.played_date DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), {"genre": genre, "limit": limit, "offset": offset})
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


@router.get("/playlists/{name:path}")
async def get_genre_playlists(
    name: str,
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Watched playlists containing tracks of this genre."""
    genre = await _resolve_genre(db, name)

    result = await db.execute(text("""
        SELECT we.id, we.title, we.source, we.has_artwork, we.owner,
               COUNT(DISTINCT rt.catalog_id)::int AS genre_track_count,
               COUNT(*) OVER()::int AS total
        FROM watched_entities we
        JOIN radar_tracks rt ON rt.watched_entity_id = we.id
        JOIN catalog c ON c.id = rt.catalog_id AND c.genre = :genre
        GROUP BY we.id, we.title, we.source, we.has_artwork, we.owner
        ORDER BY genre_track_count DESC
        LIMIT :limit OFFSET :offset
    """), {"genre": genre, "limit": limit, "offset": offset})
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


@router.get("/tracks/{name:path}")
async def get_genre_tracks(
    name: str,
    sort: str = Query("recent", pattern="^(recent|bpm|key|alpha)$"),
    q: str | None = Query(None),
    in_lib: int | None = Query(None, alias="inLib"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Paginated tracklist for a genre with sort, search, and in-lib filter."""
    genre = await _resolve_genre(db, name)
    user_id = _uid(user)

    order_clauses = {
        "recent": "c.created_at DESC NULLS LAST",
        "bpm": "c.bpm ASC NULLS LAST",
        "alpha": "LOWER(c.title) ASC",
        "key": """CASE WHEN c.key IS NULL OR c.key = '' THEN 1 ELSE 0 END,
                  CAST(regexp_replace(c.key, '[^0-9]', '', 'g') AS int),
                  SUBSTRING(c.key FROM '[A-Ba-b]$')""",
    }
    order_sql = order_clauses[sort]

    q_pattern = f"%{q.lower()}%" if q else ""

    result = await db.execute(text(f"""
        SELECT c.id, c.title, c.artist, c.bpm, c.key, c.duration_ms,
               c.has_artwork, c.has_preview,
               CASE WHEN ut.catalog_id IS NOT NULL THEN true ELSE false END AS in_lib,
               COUNT(*) OVER()::int AS total
        FROM catalog c
        LEFT JOIN user_tracks ut ON ut.catalog_id = c.id AND ut.user_id = :user_id
        WHERE c.genre = :genre
          AND (:q_filter = false OR (LOWER(c.title) LIKE :q_pattern OR LOWER(c.artist) LIKE :q_pattern))
          AND (:lib_filter = false OR
               (:in_lib = 1 AND ut.catalog_id IS NOT NULL) OR
               (:in_lib = 0 AND ut.catalog_id IS NULL))
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """), {
        "genre": genre,
        "user_id": user_id,
        "q_filter": bool(q),
        "q_pattern": q_pattern,
        "lib_filter": in_lib is not None,
        "in_lib": in_lib if in_lib is not None else -1,
        "limit": limit,
        "offset": offset,
    })
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


@router.get("/neighbors/{name:path}")
async def get_genre_neighbors(
    name: str,
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Neighboring genres by common artists."""
    genre = await _resolve_genre(db, name)

    result = await db.execute(text("""
        WITH genre_artists AS (
            SELECT DISTINCT LOWER(artist) AS artist_name
            FROM catalog
            WHERE genre = :genre AND artist IS NOT NULL AND artist != ''
        )
        SELECT c.genre,
               COUNT(DISTINCT LOWER(c.artist))::int AS common_artists,
               COUNT(*)::int AS track_count
        FROM catalog c
        JOIN genre_artists ga ON LOWER(c.artist) = ga.artist_name
        WHERE c.genre IS NOT NULL AND c.genre != '' AND c.genre != :genre
        GROUP BY c.genre
        ORDER BY common_artists DESC
        LIMIT :limit
    """), {"genre": genre, "limit": limit})

    return {
        "items": [
            {
                "name": r.genre,
                "family": genre_family(r.genre),
                "commonArtists": r.common_artists,
                "trackCount": r.track_count,
            }
            for r in result.fetchall()
        ],
    }


@router.patch("/rename/{name:path}")
async def rename_genre(
    name: str,
    body: GenreRenameIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Rename a genre across all catalog entries. Admin only."""
    genre = await _resolve_genre(db, name)
    new_name = body.new_name.strip()
    if not new_name:
        raise HTTPException(400, "New name cannot be empty")
    if new_name == genre:
        raise HTTPException(400, "New name is the same as current")

    # Check if target already exists
    existing = await db.execute(text("""
        SELECT 1 FROM catalog WHERE genre = :new_name LIMIT 1
    """), {"new_name": new_name})
    if existing.fetchone():
        raise HTTPException(409, f"Genre '{new_name}' already exists — use merge instead")

    result = await db.execute(text("""
        UPDATE catalog SET genre = :new_name WHERE genre = :old_name
    """), {"old_name": genre, "new_name": new_name})
    await db.commit()
    return {"renamed": True, "from": genre, "to": new_name, "affected": result.rowcount}
