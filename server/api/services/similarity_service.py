"""Track similarity engine — 4-segment scoring (C2.b + C2.c + C2.d)."""

from __future__ import annotations

import asyncio
import math
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
    # BPM
    BPM_MAX_DIFF: float = 15.0
    HALF_DOUBLE_PENALTY: float = 0.9
    BPM_PREFILTER_WINDOW: float = 16.0
    BPM_FACTOR_FLOOR: float = 0.3
    # Era / Label
    ERA_MAX_DIFF: int = 9
    LABEL_MIN_TRACKS: int = 3
    # Segment caps (pts)
    CAP_SETS: float = 3.0
    CAP_PLAYLISTS: float = 2.0
    CAP_STYLE: float = 2.0
    CAP_CONTEXT: float = 1.0
    SCORE_TOTAL_CAP: float = 8.0
    # Asymptotic k (calibrated)
    K_SETS: float = 2.0
    K_PLAYLISTS: float = 0.8
    # Context weights
    W_LABEL: float = 0.6
    W_ERA: float = 0.4
    # Result filter
    TOP_N: int = 20
    SCORE_FLOOR: float = 0.10


CFG = SimilarityConfig()

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
# Similarity functions (pure, return [0, 1]) — kept for tests & backwards compat
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


def sim_cooc(a_items: frozenset[int], b_items: frozenset[int]) -> float:
    """Jaccard sur ensembles d'IDs (playlists ou sets)."""
    if not a_items or not b_items:
        return 0.0
    inter = len(a_items & b_items)
    union = len(a_items | b_items)
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# New scoring functions (C2.d — 4-segment additive)
# ---------------------------------------------------------------------------

def bpm_factor(a: float, b: float) -> float:
    """BPM alignment factor in [BPM_FACTOR_FLOOR, 1.0]."""
    def _raw(x: float, y: float) -> float:
        return max(0.0, 1.0 - abs(x - y) / CFG.BPM_MAX_DIFF)
    raw = max(
        _raw(a, b),
        _raw(a, b / 2.0) * CFG.HALF_DOUBLE_PENALTY,
        _raw(a, b * 2.0) * CFG.HALF_DOUBLE_PENALTY,
    )
    return CFG.BPM_FACTOR_FLOOR + (1.0 - CFG.BPM_FACTOR_FLOOR) * raw


def score_style(genre_jac: float, bpm_fac: float) -> float:
    return genre_jac * bpm_fac * CFG.CAP_STYLE


def score_context(label_sim: float, era_sim_val: float) -> float:
    return CFG.CAP_CONTEXT * (CFG.W_LABEL * label_sim + CFG.W_ERA * era_sim_val)


def score_cooc(n: int, k: float, cap: float) -> float:
    """Asymptotic scoring: cap * (1 - e^(-k*n))."""
    if n <= 0:
        return 0.0
    return cap * (1.0 - math.exp(-k * n))


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


async def _load_playlist_map(db: AsyncSession) -> dict[int, frozenset[int]]:
    """catalog_id -> frozenset[watched_entity_id] pour les tracks actives."""
    from models import RadarTrack

    rows = (
        await db.execute(
            select(RadarTrack.catalog_id, RadarTrack.watched_entity_id).where(
                RadarTrack.catalog_id.isnot(None),
                RadarTrack.removed_at.is_(None),
            )
        )
    ).all()
    result: dict[int, set[int]] = {}
    for catalog_id, entity_id in rows:
        result.setdefault(catalog_id, set()).add(entity_id)
    return {k: frozenset(v) for k, v in result.items()}


async def _load_set_map(db: AsyncSession) -> dict[int, frozenset[int]]:
    """catalog_id -> frozenset[set_id]."""
    from models import SetTrack

    rows = (
        await db.execute(
            select(SetTrack.catalog_id, SetTrack.set_id).where(
                SetTrack.catalog_id.isnot(None),
            )
        )
    ).all()
    result: dict[int, set[int]] = {}
    for catalog_id, set_id in rows:
        result.setdefault(catalog_id, set()).add(set_id)
    return {k: frozenset(v) for k, v in result.items()}


# ---------------------------------------------------------------------------
# Shared context (pre-loaded maps, reusable across seeds)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimilarityContext:
    """Seed-agnostic maps loaded once and reused across many similarity seeds.

    Carries the 4 full-table loads (genre resolution, label counts, playlist and
    set co-occurrence maps) so scoring a batch of seeds pays the loading cost once.
    """
    name_to_node: dict[str, int]
    parent_map: dict[int, set[int]]
    label_counts: dict[str, int]
    playlist_map: dict[int, frozenset[int]]
    set_map: dict[int, frozenset[int]]


async def load_similarity_context(db: AsyncSession) -> SimilarityContext:
    """Load the 4 seed-agnostic maps once (genre, label, playlist, set)."""
    (name_to_node, parent_map), label_counts, playlist_map, set_map = await asyncio.gather(
        _load_genre_context(db),
        _load_label_counts(db),
        _load_playlist_map(db),
        _load_set_map(db),
    )
    return SimilarityContext(
        name_to_node=name_to_node,
        parent_map=parent_map,
        label_counts=label_counts,
        playlist_map=playlist_map,
        set_map=set_map,
    )


# ---------------------------------------------------------------------------
# Scoring core + public entry points
# ---------------------------------------------------------------------------

async def _similar_core(
    db: AsyncSession,
    ctx: SimilarityContext,
    seed_catalog_id: int,
    user_id: int | None,
    *,
    top_n: int,
    score_floor: float,
    in_lib: bool | None,
) -> list[dict]:
    """Score candidates for one seed against ``ctx`` (no ``limit`` applied).

    Shared body behind :func:`similar_from_context` (in_lib=None) and
    :func:`get_similar_tracks`. Applies ``catalog_visible(user_id)`` on every
    catalog read and raises ``LookupError`` if the seed is absent/invisible.
    """
    from models import CatalogArtist, CatalogEntry, UserTrack
    from schemas import ArtistRef, GenreRef, SimilarityBlock, SimilarityComponents

    from services.catalog_service import catalog_visible
    from services.genre_service import genre_pillar

    # 1. Fetch reference track (respecting private-scope visibility)
    ref = (
        await db.execute(
            select(CatalogEntry).where(
                CatalogEntry.id == seed_catalog_id, catalog_visible(user_id)
            )
        )
    ).scalar_one_or_none()
    if ref is None:
        raise LookupError(f"Catalog entry {seed_catalog_id} not found")

    # 2. Read pre-loaded context (genre/label + co-occurrence maps)
    name_to_node = ctx.name_to_node
    parent_map = ctx.parent_map
    label_counts = ctx.label_counts
    playlist_map = ctx.playlist_map
    set_map = ctx.set_map

    ref_genres = _expand_genre_nodes(ref.genres or [], name_to_node, parent_map)
    ref_label = (ref.label or "").strip().lower()
    ref_label_valid = ref_label and label_counts.get(ref_label, 0) >= CFG.LABEL_MIN_TRACKS
    ref_playlists = playlist_map.get(seed_catalog_id, frozenset())
    ref_sets = set_map.get(seed_catalog_id, frozenset())

    # 3. Build candidate set — union(BPM window, co-occurrence)
    q = select(CatalogEntry).where(
        CatalogEntry.id != seed_catalog_id, catalog_visible(user_id)
    )

    bpm_filter_ids: set[int] | None = None
    if ref.bpm is not None:
        bpm = ref.bpm
        w = CFG.BPM_PREFILTER_WINDOW
        bpm_q = q.where(
            (CatalogEntry.bpm.is_(None))
            | (CatalogEntry.bpm.between(bpm - w, bpm + w))
            | (CatalogEntry.bpm.between(bpm / 2 - w, bpm / 2 + w))
            | (CatalogEntry.bpm.between(bpm * 2 - w, bpm * 2 + w))
        )
        bpm_candidates = (await db.execute(bpm_q)).scalars().all()
        bpm_filter_ids = {c.id for c in bpm_candidates}
    else:
        bpm_candidates = (await db.execute(q)).scalars().all()
        bpm_filter_ids = {c.id for c in bpm_candidates}

    # Co-occurrence candidate IDs (share >=1 playlist or set with ref)
    cooc_ids: set[int] = set()
    if ref_playlists:
        for cid, playlists in playlist_map.items():
            if cid != seed_catalog_id and playlists & ref_playlists:
                cooc_ids.add(cid)
    if ref_sets:
        for cid, sets in set_map.items():
            if cid != seed_catalog_id and sets & ref_sets:
                cooc_ids.add(cid)

    # Union: BPM candidates + co-occurrence candidates not already included
    extra_ids = cooc_ids - bpm_filter_ids
    extra_candidates: list[CatalogEntry] = []
    if extra_ids:
        extra_q = select(CatalogEntry).where(
            CatalogEntry.id.in_(extra_ids), catalog_visible(user_id)
        )
        extra_candidates = (await db.execute(extra_q)).scalars().all()

    # Combine, preserving bpm_candidates list (already fetched)
    all_candidates = list(bpm_candidates) + extra_candidates

    if in_lib is True and user_id is not None:
        lib_ids_rows = (
            await db.execute(
                select(UserTrack.catalog_id).where(UserTrack.user_id == user_id)
            )
        ).all()
        lib_ids = {r[0] for r in lib_ids_rows}
        all_candidates = [c for c in all_candidates if c.id in lib_ids]

    # 4. Score each candidate (4-segment additive)
    scored: list[tuple[CatalogEntry, float, dict[str, float], list[str]]] = []

    for cand in all_candidates:
        # Genre
        cand_genres = _expand_genre_nodes(cand.genres or [], name_to_node, parent_map)
        gj = sim_genre(ref_genres, cand_genres) if (ref_genres and cand_genres) else 0.0

        # BPM factor
        if ref.bpm is not None and cand.bpm is not None:
            bf = bpm_factor(ref.bpm, cand.bpm)
        else:
            bf = CFG.BPM_FACTOR_FLOOR

        # Style
        s_style = score_style(gj, bf)

        # Context
        cand_label = (cand.label or "").strip().lower()
        cand_label_valid = cand_label and label_counts.get(cand_label, 0) >= CFG.LABEL_MIN_TRACKS
        lm = sim_label(ref.label, cand.label) if (ref_label_valid and cand_label_valid) else 0.0
        es = sim_era(ref.release_date, cand.release_date) if (ref.release_date and cand.release_date) else 0.0
        s_context = score_context(lm, es)

        # Co-occurrence
        cand_playlists = playlist_map.get(cand.id, frozenset())
        n_pl = len(ref_playlists & cand_playlists)
        s_playlists = score_cooc(n_pl, CFG.K_PLAYLISTS, CFG.CAP_PLAYLISTS)

        cand_sets = set_map.get(cand.id, frozenset())
        n_st = len(ref_sets & cand_sets)
        s_sets = score_cooc(n_st, CFG.K_SETS, CFG.CAP_SETS)

        total_pts = s_sets + s_playlists + s_style + s_context
        score_pct = total_pts / CFG.SCORE_TOTAL_CAP

        if score_pct < score_floor:
            continue

        available = []
        components = {
            "sets": round(s_sets, 4),
            "playlists": round(s_playlists, 4),
            "style": round(s_style, 4),
            "context": round(s_context, 4),
        }
        if n_st > 0:
            available.append("sets")
        if n_pl > 0:
            available.append("playlists")
        if gj > 0:
            available.append("style")
        if lm > 0 or es > 0:
            available.append("context")

        scored.append((cand, score_pct, components, available))

    # 5. Sort, top_n (the caller applies limit)
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_n]

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
                    components=SimilarityComponents(
                        sets=components["sets"],
                        playlists=components["playlists"],
                        style=components["style"],
                        context=components["context"],
                    ),
                    available_features=available,
                ).model_dump(),
            }
        )

    return results


async def similar_from_context(
    db: AsyncSession,
    ctx: SimilarityContext,
    seed_catalog_id: int,
    user_id: int | None = None,
    *,
    top_n: int = CFG.TOP_N,
    score_floor: float = 0.0,
) -> list[dict]:
    """Reusable primitive: score one seed against a pre-loaded context.

    Same candidate generation, scoring and return shape as
    :func:`get_similar_tracks`, but consuming ``ctx`` instead of re-reading the 4
    maps. Raises ``LookupError`` if the seed is absent/invisible.
    """
    return await _similar_core(
        db, ctx, seed_catalog_id, user_id,
        top_n=top_n, score_floor=score_floor, in_lib=None,
    )


async def get_similar_tracks(
    db: AsyncSession,
    catalog_id: int,
    user_id: int | None = None,
    *,
    limit: int = 10,
    top_n: int = CFG.TOP_N,
    score_floor: float = CFG.SCORE_FLOOR,
    in_lib: bool | None = None,
) -> list[dict]:
    """Similar tracks for one seed (public contract unchanged).

    Loads a fresh :class:`SimilarityContext`, scores via the shared core, then
    applies ``limit``.
    """
    ctx = await load_similarity_context(db)
    results = await _similar_core(
        db, ctx, catalog_id, user_id,
        top_n=top_n, score_floor=score_floor, in_lib=in_lib,
    )
    return results[:limit]
