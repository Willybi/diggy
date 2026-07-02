"""Track similarity engine — metadata-based scoring (V1, SQL+Python hybrid)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimilarityConfig:
    BPM_MAX_DIFF: float = 15.0
    HALF_DOUBLE_PENALTY: float = 0.9
    BPM_PREFILTER_WINDOW: float = 16.0
    LABEL_MIN_TRACKS: int = 3
    ERA_MAX_DIFF: int = 9
    MIN_FEATURES: int = 2


CFG = SimilarityConfig()

DEFAULT_WEIGHTS = {
    "bpm": 0.30,
    "key": 0.25,
    "genre": 0.30,
    "label": 0.10,
    "era": 0.05,
}

# ---------------------------------------------------------------------------
# Camelot helpers
# ---------------------------------------------------------------------------

_CAMELOT_RE = re.compile(r"^(\d{1,2})([ABab])$")


def parse_camelot(key_str: str | None) -> tuple[int, str] | None:
    if not key_str:
        return None
    m = _CAMELOT_RE.match(key_str.strip())
    if not m:
        return None
    num = int(m.group(1))
    if num < 1 or num > 12:
        return None
    return (num, m.group(2).upper())


def _camelot_distance(n1: int, n2: int) -> int:
    d = abs(n1 - n2)
    return min(d, 12 - d)


# ---------------------------------------------------------------------------
# Similarity functions (pure, return [0, 1])
# ---------------------------------------------------------------------------

def sim_bpm(a: float, b: float) -> float:
    def _score(diff: float) -> float:
        return max(0.0, 1.0 - diff / CFG.BPM_MAX_DIFF)

    direct = _score(abs(a - b))
    half = _score(abs(a - b / 2)) * CFG.HALF_DOUBLE_PENALTY
    double = _score(abs(a - b * 2)) * CFG.HALF_DOUBLE_PENALTY
    return max(direct, half, double)


def sim_key(a: str, b: str) -> float:
    pa = parse_camelot(a)
    pb = parse_camelot(b)
    if pa is None or pb is None:
        return 0.0
    n1, l1 = pa
    n2, l2 = pb
    dist = _camelot_distance(n1, n2)
    same_letter = l1 == l2

    if dist == 0 and same_letter:
        return 1.0
    if dist == 0 and not same_letter:
        return 0.9  # relative major/minor
    if dist == 1 and same_letter:
        return 0.8  # neighbor
    if dist == 2 and same_letter:
        return 0.5  # energy boost
    if dist == 1 and not same_letter:
        return 0.4  # diagonal
    return 0.0


def sim_genre(
    a_nodes: dict[int, float],
    b_nodes: dict[int, float],
) -> float:
    if not a_nodes or not b_nodes:
        return 0.0
    all_keys = a_nodes.keys() | b_nodes.keys()
    numerator = sum(min(a_nodes.get(k, 0.0), b_nodes.get(k, 0.0)) for k in all_keys)
    denominator = sum(max(a_nodes.get(k, 0.0), b_nodes.get(k, 0.0)) for k in all_keys)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def sim_label(a: str, b: str) -> float:
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def sim_era(a: date, b: date) -> float:
    diff = abs(a.year - b.year)
    if diff <= 1:
        return 1.0
    return max(0.0, 1.0 - (diff - 1) / CFG.ERA_MAX_DIFF)


# ---------------------------------------------------------------------------
# Genre resolution helpers
# ---------------------------------------------------------------------------

def _expand_genre_nodes(
    raw_genres: list[str],
    name_to_node: dict[str, int],
    parent_map: dict[int, set[int]],
) -> dict[int, float]:
    """Resolve raw genre strings to weighted node set (direct=1.0, parents=0.5)."""
    nodes: dict[int, float] = {}
    for g in raw_genres:
        nid = name_to_node.get(g)
        if nid is None:
            continue
        nodes[nid] = 1.0
        for pid in parent_map.get(nid, set()):
            if pid not in nodes:
                nodes[pid] = 0.5
    return nodes


async def _load_genre_context(
    db: AsyncSession,
) -> tuple[dict[str, int], dict[int, set[int]]]:
    from models import GenreEdge, GenreMapping

    # raw_name -> node_id
    rows = (await db.execute(select(GenreMapping.raw_name, GenreMapping.node_id))).all()
    name_to_node = {r[0]: r[1] for r in rows if r[1] is not None}

    # node_id -> set of parent node_ids (edge type='parent', from=child, to=parent)
    edge_rows = (
        await db.execute(
            select(GenreEdge.from_node_id, GenreEdge.to_node_id).where(
                GenreEdge.type == "parent"
            )
        )
    ).all()
    parent_map: dict[int, set[int]] = {}
    for child_id, parent_id in edge_rows:
        parent_map.setdefault(child_id, set()).add(parent_id)

    return name_to_node, parent_map


async def _load_label_counts(db: AsyncSession) -> dict[str, int]:
    from models import CatalogEntry

    rows = (
        await db.execute(
            select(
                func.lower(func.trim(CatalogEntry.label)),
                func.count(),
            )
            .where(CatalogEntry.label.isnot(None))
            .group_by(func.lower(func.trim(CatalogEntry.label)))
        )
    ).all()
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def get_similar_tracks(
    db: AsyncSession,
    catalog_id: int,
    user_id: int | None = None,
    *,
    limit: int = 10,
    w_bpm: float = DEFAULT_WEIGHTS["bpm"],
    w_key: float = DEFAULT_WEIGHTS["key"],
    w_genre: float = DEFAULT_WEIGHTS["genre"],
    w_label: float = DEFAULT_WEIGHTS["label"],
    w_era: float = DEFAULT_WEIGHTS["era"],
    min_score: float = 0.4,
    in_lib: bool | None = None,
) -> list[dict]:
    from models import CatalogArtist, CatalogEntry, UserTrack
    from schemas import ArtistRef, GenreRef, SimilarityBlock, SimilarityComponents

    from services.genre_service import genre_pillar

    # 1. Fetch reference track
    ref = (
        await db.execute(select(CatalogEntry).where(CatalogEntry.id == catalog_id))
    ).scalar_one_or_none()
    if ref is None:
        raise LookupError(f"Catalog entry {catalog_id} not found")

    # 2. Load genre + label context
    name_to_node, parent_map = await _load_genre_context(db)
    label_counts = await _load_label_counts(db)

    ref_genres = _expand_genre_nodes(ref.genres or [], name_to_node, parent_map)
    ref_label = (ref.label or "").strip().lower()
    ref_label_valid = ref_label and label_counts.get(ref_label, 0) >= CFG.LABEL_MIN_TRACKS

    # 3. Build candidate query with BPM pre-filter
    q = select(CatalogEntry).where(CatalogEntry.id != catalog_id)

    if ref.bpm is not None:
        bpm = ref.bpm
        w = CFG.BPM_PREFILTER_WINDOW
        q = q.where(
            (CatalogEntry.bpm.is_(None))
            | (CatalogEntry.bpm.between(bpm - w, bpm + w))
            | (CatalogEntry.bpm.between(bpm / 2 - w, bpm / 2 + w))
            | (CatalogEntry.bpm.between(bpm * 2 - w, bpm * 2 + w))
        )

    if in_lib is True and user_id is not None:
        q = q.where(
            CatalogEntry.id.in_(
                select(UserTrack.catalog_id).where(UserTrack.user_id == user_id)
            )
        )

    candidates = (await db.execute(q)).scalars().all()

    # 4. Score each candidate
    weights = {"bpm": w_bpm, "key": w_key, "genre": w_genre, "label": w_label, "era": w_era}
    scored: list[tuple[CatalogEntry, float, dict[str, float], list[str]]] = []

    for cand in candidates:
        components: dict[str, float] = {}
        available: list[str] = []

        # BPM
        if ref.bpm is not None and cand.bpm is not None:
            components["bpm"] = sim_bpm(ref.bpm, cand.bpm)
            available.append("bpm")

        # Key
        if ref.key and cand.key:
            components["key"] = sim_key(ref.key, cand.key)
            available.append("key")

        # Genre
        cand_genres = _expand_genre_nodes(cand.genres or [], name_to_node, parent_map)
        if ref_genres and cand_genres:
            components["genre"] = sim_genre(ref_genres, cand_genres)
            available.append("genre")

        # Label
        cand_label = (cand.label or "").strip().lower()
        cand_label_valid = cand_label and label_counts.get(cand_label, 0) >= CFG.LABEL_MIN_TRACKS
        if ref_label_valid and cand_label_valid:
            components["label"] = sim_label(ref.label, cand.label)
            available.append("label")

        # Era
        if ref.release_date and cand.release_date:
            components["era"] = sim_era(ref.release_date, cand.release_date)
            available.append("era")

        # Aggregate
        if len(available) < CFG.MIN_FEATURES:
            continue

        w_sum = sum(weights[f] for f in available)
        if w_sum == 0:
            continue
        score = sum(weights[f] * components[f] for f in available) / w_sum

        if score >= min_score:
            scored.append((cand, score, components, available))

    # 5. Sort and limit
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:limit]

    if not top:
        return []

    # 6. Load artists for result tracks
    top_ids = [entry.id for entry, *_ in top]
    from models import Artist

    artist_rows = (
        await db.execute(
            select(CatalogArtist.catalog_id, Artist.id, Artist.name, CatalogArtist.role, Artist.has_artwork)
            .join(Artist, CatalogArtist.artist_id == Artist.id)
            .where(CatalogArtist.catalog_id.in_(top_ids))
            .order_by(CatalogArtist.position)
        )
    ).all()
    artists_by_catalog: dict[int, list[ArtistRef]] = {}
    for cat_id, art_id, art_name, role, has_art in artist_rows:
        artists_by_catalog.setdefault(cat_id, []).append(
            ArtistRef(id=art_id, name=art_name, role=role, has_artwork=has_art)
        )

    # 7. Check in_lib status
    in_lib_ids: set[int] = set()
    if user_id is not None:
        lib_rows = (
            await db.execute(
                select(UserTrack.catalog_id).where(
                    UserTrack.user_id == user_id,
                    UserTrack.catalog_id.in_(top_ids),
                )
            )
        ).all()
        in_lib_ids = {r[0] for r in lib_rows}

    # 8. Build response
    results = []
    for entry, score, components, available in top:
        entry_artists = artists_by_catalog.get(entry.id, [])
        genre_refs = []
        for g in entry.genres or []:
            p, d = genre_pillar(g)
            genre_refs.append(GenreRef(name=g, pillar=p, depth=d))

        results.append(
            {
                "id": entry.id,
                "title": entry.title,
                "artist": entry.artist,
                "isrc": entry.isrc,
                "bpm": entry.bpm,
                "key": entry.key,
                "bpm_source": entry.bpm_source,
                "key_source": entry.key_source,
                "label": entry.label,
                "deezer_id": entry.deezer_id,
                "beatport_id": entry.beatport_id,
                "duration_ms": entry.duration_ms,
                "genres": [gr.model_dump() for gr in genre_refs],
                "release_date": entry.release_date,
                "preview_url": entry.preview_url,
                "has_artwork": entry.has_artwork,
                "has_preview": entry.has_preview,
                "created_at": entry.created_at,
                "in_lib": entry.id in in_lib_ids,
                "nb_radar_playlists": 0,
                "nb_radar_sets": 0,
                "avis": None,
                "artist_id": entry_artists[0].id if entry_artists else None,
                "artists": [a.model_dump() for a in entry_artists],
                "similarity": SimilarityBlock(
                    score=round(score, 4),
                    components=SimilarityComponents(**{f: round(components.get(f, 0), 4) for f in available}),
                    available_features=available,
                ).model_dump(),
            }
        )

    return results
