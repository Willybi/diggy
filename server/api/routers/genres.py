import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user_optional, uid as _uid
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
