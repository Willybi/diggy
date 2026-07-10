"""Artist connection engine — co-occurrence scoring (C2.d graphe artistes)."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.genre_service import ensure_pillar_cache, genre_pillar
from services.similarity_service import (
    _expand_genre_nodes,
    _load_genre_context,
    sim_genre,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectionConfig:
    CAP_COLLABS: float = 3.0
    CAP_SETS: float = 2.0
    CAP_PLAYLISTS: float = 2.0
    CAP_STYLE: float = 1.0
    SCORE_TOTAL_CAP: float = 8.0
    K_COLLABS: float = 1.5
    K_SETS: float = 2.0
    K_PLAYLISTS: float = 0.5
    SCORE_FLOOR: float = 0.05


CFG = ConnectionConfig()


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def score_segment(n: int, k: float, cap: float) -> float:
    """Asymptotic scoring: cap * (1 - e^(-k*n))."""
    if n <= 0:
        return 0.0
    return cap * (1.0 - math.exp(-k * n))


# ---------------------------------------------------------------------------
# SQL loaders (return {artist_id: count})
# ---------------------------------------------------------------------------


async def _load_collab_counts(
    db: AsyncSession, artist_id: int
) -> dict[int, int]:
    """Artists sharing catalog entries with the reference artist."""
    from models import CatalogArtist

    ca1 = CatalogArtist.__table__.alias("ca1")
    ca2 = CatalogArtist.__table__.alias("ca2")

    stmt = (
        select(ca2.c.artist_id, func.count(func.distinct(ca2.c.catalog_id)))
        .select_from(ca1.join(ca2, ca1.c.catalog_id == ca2.c.catalog_id))
        .where(ca1.c.artist_id == artist_id, ca2.c.artist_id != artist_id)
        .group_by(ca2.c.artist_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r[0]: r[1] for r in rows}


async def _load_set_counts(
    db: AsyncSession, artist_id: int
) -> dict[int, int]:
    """Artists sharing DJ sets with the reference artist."""
    from models import SetArtist

    sa1 = SetArtist.__table__.alias("sa1")
    sa2 = SetArtist.__table__.alias("sa2")

    stmt = (
        select(sa2.c.artist_id, func.count(func.distinct(sa2.c.set_id)))
        .select_from(sa1.join(sa2, sa1.c.set_id == sa2.c.set_id))
        .where(sa1.c.artist_id == artist_id, sa2.c.artist_id != artist_id)
        .group_by(sa2.c.artist_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r[0]: r[1] for r in rows}


async def _load_playlist_counts(
    db: AsyncSession, artist_id: int
) -> dict[int, int]:
    """Artists whose tracks co-occur in watched playlists with reference artist."""
    from models import CatalogArtist, RadarTrack

    ca1 = CatalogArtist.__table__.alias("ca1")
    ca2 = CatalogArtist.__table__.alias("ca2")
    rt1 = RadarTrack.__table__.alias("rt1")
    rt2 = RadarTrack.__table__.alias("rt2")

    stmt = (
        select(
            ca2.c.artist_id,
            func.count(func.distinct(rt1.c.watched_entity_id)),
        )
        .select_from(
            ca1.join(rt1, (rt1.c.catalog_id == ca1.c.catalog_id) & (rt1.c.removed_at.is_(None)))
            .join(rt2, (rt2.c.watched_entity_id == rt1.c.watched_entity_id)
                  & (rt2.c.catalog_id != ca1.c.catalog_id)
                  & (rt2.c.removed_at.is_(None)))
            .join(ca2, ca2.c.catalog_id == rt2.c.catalog_id)
        )
        .where(ca1.c.artist_id == artist_id, ca2.c.artist_id != artist_id)
        .group_by(ca2.c.artist_id)
    )
    rows = (await db.execute(stmt)).all()
    return {r[0]: r[1] for r in rows}


async def _load_artist_genres(
    db: AsyncSession,
    artist_ids: set[int],
    name_to_node: dict[str, int],
    parent_map: dict[int, set[int]],
) -> dict[int, dict[int, float]]:
    """Load aggregated genre nodes for a batch of artists."""
    from models import CatalogArtist, CatalogEntry

    if not artist_ids:
        return {}

    stmt = (
        select(CatalogArtist.artist_id, CatalogEntry.genres)
        .join(CatalogEntry, CatalogArtist.catalog_id == CatalogEntry.id)
        .where(
            CatalogArtist.artist_id.in_(artist_ids),
            CatalogEntry.genres.isnot(None),
        )
    )
    rows = (await db.execute(stmt)).all()

    # Aggregate: collect all raw genres per artist, then expand
    raw_by_artist: dict[int, list[str]] = defaultdict(list)
    for aid, genres in rows:
        if genres:
            raw_by_artist[aid].extend(genres)

    # Deduplicate raw genres, then expand to weighted nodes
    result: dict[int, dict[int, float]] = {}
    for aid, raw_list in raw_by_artist.items():
        unique_genres = list(dict.fromkeys(raw_list))  # preserve order, dedup
        result[aid] = _expand_genre_nodes(unique_genres, name_to_node, parent_map)

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def get_connections(
    db: AsyncSession,
    artist_id: int,
    *,
    limit: int = 20,
) -> list[dict]:
    from models import Artist
    from schemas import GenreRef

    # 0. Verify artist exists
    ref = (
        await db.execute(select(Artist).where(Artist.id == artist_id))
    ).scalar_one_or_none()
    if ref is None:
        raise LookupError(f"Artist {artist_id} not found")

    # 1. Load co-occurrence counts + genre context in parallel
    collab_counts, set_counts, playlist_counts, (name_to_node, parent_map) = (
        await asyncio.gather(
            _load_collab_counts(db, artist_id),
            _load_set_counts(db, artist_id),
            _load_playlist_counts(db, artist_id),
            _load_genre_context(db),
        )
    )

    # 2. Union of candidate artist IDs
    candidate_ids = set(collab_counts) | set(set_counts) | set(playlist_counts)
    if not candidate_ids:
        return []

    # 3. Load genres for ref + candidates (for style scoring)
    all_ids = candidate_ids | {artist_id}
    genre_nodes = await _load_artist_genres(db, all_ids, name_to_node, parent_map)
    ref_genres = genre_nodes.get(artist_id, {})

    # 4. Score each candidate
    scored: list[tuple[int, float, dict, dict]] = []

    for cand_id in candidate_ids:
        n_collabs = collab_counts.get(cand_id, 0)
        n_sets = set_counts.get(cand_id, 0)
        n_playlists = playlist_counts.get(cand_id, 0)

        s_collabs = score_segment(n_collabs, CFG.K_COLLABS, CFG.CAP_COLLABS)
        s_sets = score_segment(n_sets, CFG.K_SETS, CFG.CAP_SETS)
        s_playlists = score_segment(n_playlists, CFG.K_PLAYLISTS, CFG.CAP_PLAYLISTS)

        # Style: genre Jaccard
        cand_genres = genre_nodes.get(cand_id, {})
        gj = sim_genre(ref_genres, cand_genres) if (ref_genres and cand_genres) else 0.0
        s_style = gj * CFG.CAP_STYLE

        total = s_collabs + s_sets + s_playlists + s_style
        score = total / CFG.SCORE_TOTAL_CAP

        if score < CFG.SCORE_FLOOR:
            continue

        components = {
            "collabs": round(s_collabs, 4),
            "sets": round(s_sets, 4),
            "playlists": round(s_playlists, 4),
            "style": round(s_style, 4),
        }
        details = {
            "shared_tracks": n_collabs,
            "shared_sets": n_sets,
            "shared_playlists": n_playlists,
        }
        scored.append((cand_id, round(score, 4), components, details))

    # 5. Sort and limit
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:limit]

    if not top:
        return []

    # 6. Load artist info for results
    top_ids = [cid for cid, *_ in top]
    artist_rows = (
        await db.execute(
            select(Artist.id, Artist.name, Artist.has_artwork)
            .where(Artist.id.in_(top_ids))
        )
    ).all()
    artist_info = {r[0]: (r[1], r[2]) for r in artist_rows}

    # 7. Build response
    await ensure_pillar_cache(db)

    results = []
    for cand_id, score, components, details in top:
        name, has_artwork = artist_info.get(cand_id, ("Unknown", False))

        # Genre refs from aggregated nodes
        cand_raw_genres = []
        cand_nodes = genre_nodes.get(cand_id, {})
        if cand_nodes:
            # Reverse lookup: node_id -> raw genre names (direct only, weight=1.0)
            node_to_names: dict[int, list[str]] = defaultdict(list)
            for raw_name, nid in name_to_node.items():
                node_to_names[nid].append(raw_name)
            for nid, w in sorted(cand_nodes.items(), key=lambda x: -x[1]):
                if w >= 1.0:  # direct genres only
                    for gname in node_to_names.get(nid, []):
                        p, d = genre_pillar(gname)
                        cand_raw_genres.append(
                            GenreRef(name=gname, pillar=p, depth=d).model_dump()
                        )

        results.append({
            "artist_id": cand_id,
            "name": name,
            "has_artwork": has_artwork,
            "genres": cand_raw_genres[:5],  # top 5 genres
            "score": score,
            "components": components,
            **details,
        })

    return results
