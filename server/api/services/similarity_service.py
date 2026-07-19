"""Track similarity engine — 4-segment scoring (C2.b + C2.c + C2.d)."""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import NamedTuple

from sqlalchemy import and_, case, func, select
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
    """catalog_id -> frozenset[set_id], ROOT sets only.

    Only root sets (``parent_set_id IS NULL``) enter the co-occurrence map. A
    virtual parent carries the merged tracklist of its children, so counting the
    parent AND its children would count the SAME logical set 2-3× and inflate the
    co-occurrence weight — same "roots only" rule as trend scoring.
    """
    from models import DJSet, SetTrack

    rows = (
        await db.execute(
            select(SetTrack.catalog_id, SetTrack.set_id)
            .join(DJSet, DJSet.id == SetTrack.set_id)
            .where(
                SetTrack.catalog_id.isnot(None),
                DJSet.parent_set_id.is_(None),
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


# In-process cache for the seed-agnostic context. The 4 maps are user- AND
# seed-independent (they change only when the nightly jobs mutate catalog / sets
# / playlists / genres), yet load_similarity_context was rebuilt on EVERY request
# — 4 sequential full-table scans, the dominant cost of the reco cold path and
# the C2 "similar tracks" endpoint once the catalog passed ~60k rows. Cache the
# built context with a TTL so both consumers reuse it. Reset between tests via
# reset_similarity_context_cache() (autouse fixture in tests/api/conftest.py).
_CONTEXT_TTL_S: float = float(os.getenv("SIMILARITY_CONTEXT_TTL_S", "21600"))  # 6h
_context_cache: SimilarityContext | None = None
_context_built_at: float = 0.0


def reset_similarity_context_cache() -> None:
    """Drop the cached context (test isolation + forced refresh)."""
    global _context_cache, _context_built_at
    _context_cache = None
    _context_built_at = 0.0


async def load_similarity_context(
    db: AsyncSession, *, use_cache: bool = True
) -> SimilarityContext:
    """Load the 4 seed-agnostic maps (genre, label, playlist, set), cached in-process.

    The context is user- and seed-independent, so it is built once and reused for
    ``SIMILARITY_CONTEXT_TTL_S`` seconds (default 6h). Pass ``use_cache=False`` to
    force a fresh build (e.g. right after mutating the underlying data).

    Sequential awaits on the same session: an ``AsyncSession`` cannot be accessed
    concurrently. ``asyncio.gather`` here left an asyncpg connection wedged under
    PostgreSQL (the "non-checked-in connection ... will be terminated" hang);
    SQLite masks it. Order-independent — each loader hits disjoint tables.
    """
    global _context_cache, _context_built_at
    if (
        use_cache
        and _context_cache is not None
        and (time.monotonic() - _context_built_at) < _CONTEXT_TTL_S
    ):
        return _context_cache

    name_to_node, parent_map = await _load_genre_context(db)
    label_counts = await _load_label_counts(db)
    playlist_map = await _load_playlist_map(db)
    set_map = await _load_set_map(db)
    ctx = SimilarityContext(
        name_to_node=name_to_node,
        parent_map=parent_map,
        label_counts=label_counts,
        playlist_map=playlist_map,
        set_map=set_map,
    )
    if use_cache:
        _context_cache = ctx
        _context_built_at = time.monotonic()
    return ctx


# ---------------------------------------------------------------------------
# Candidate pool (built once per compute, scored in memory across many seeds)
# ---------------------------------------------------------------------------

class PooledCandidate(NamedTuple):
    """One catalog row reduced to the fields scoring needs, with the
    seed-INDEPENDENT terms precomputed once.

    ``expanded_genres`` (the genre-node resolution) and ``label_valid`` (the
    label-count threshold) used to be recomputed for EVERY candidate on EVERY
    seed inside the scoring loop, even though they do not depend on the seed.
    Precomputing them once per pool turns per-seed scoring into pure in-memory
    arithmetic: no per-seed DB fetch, no per-candidate genre re-expansion — the
    two costs that made the reco cold path re-read ~55k rows and re-expand
    genres once per seed.
    """
    id: int
    bpm: float | None
    label: str | None
    label_valid: bool
    release_date: date | None
    expanded_genres: dict[int, float]
    playlists: frozenset[int]
    sets: frozenset[int]


async def load_candidate_pool(
    db: AsyncSession, user_id: int | None, ctx: SimilarityContext
) -> dict[int, PooledCandidate]:
    """Build the id-keyed candidate pool for one viewer, ONCE per compute.

    ONE projected query (id, bpm, label, release_date, genres) under
    ``catalog_visible(user_id)`` — NOT full ORM entities — enriched with the
    context's seed-agnostic maps. The pool IS the viewer's visible catalog, so a
    seed lookup and every candidate-membership test is O(1) against it.

    User-scoped (visibility is per-user), so it is built per compute and NEVER
    globally cached — unlike :class:`SimilarityContext`. Insertion order follows
    the DB's natural (unordered) scan, the same row order the pre-pool per-seed
    queries returned, so score-tie ordering is preserved.
    """
    from models import CatalogEntry

    from services.catalog_service import catalog_visible

    rows = (
        await db.execute(
            select(
                CatalogEntry.id,
                CatalogEntry.bpm,
                CatalogEntry.label,
                CatalogEntry.release_date,
                CatalogEntry.genres,
            ).where(catalog_visible(user_id))
        )
    ).all()

    pool: dict[int, PooledCandidate] = {}
    for cid, bpm, label, release_date, genres in rows:
        label_lower = (label or "").strip().lower()
        label_valid = bool(label_lower) and (
            ctx.label_counts.get(label_lower, 0) >= CFG.LABEL_MIN_TRACKS
        )
        pool[cid] = PooledCandidate(
            id=cid,
            bpm=bpm,
            label=label,
            label_valid=label_valid,
            release_date=release_date,
            expanded_genres=_expand_genre_nodes(
                genres or [], ctx.name_to_node, ctx.parent_map
            ),
            playlists=ctx.playlist_map.get(cid, frozenset()),
            sets=ctx.set_map.get(cid, frozenset()),
        )
    return pool


# ---------------------------------------------------------------------------
# Scoring core + public entry points
# ---------------------------------------------------------------------------

def _score_seed_against_pool(
    pool: dict[int, PooledCandidate],
    seed: PooledCandidate,
    *,
    score_floor: float,
    restrict_ids: set[int] | None = None,
) -> list[tuple[int, float, dict[str, float], list[str]]]:
    """Score every candidate in ``pool`` against one ``seed``, purely in memory.

    Replicates the EXACT 4-segment math and candidate SET of the pre-pool
    ``_similar_core`` loop:

    * membership = union(BPM-window-or-null rows, co-occurrence rows) — the same
      union the two SQL queries produced (BPM window incl. ``bpm IS NULL``, plus
      rows sharing >=1 playlist or set with the seed);
    * candidate ORDER = BPM members first (pool order) then co-occurrence-only
      members (pool order), reproducing ``bpm_candidates + extra_candidates`` so
      the stable score-descending sort breaks exact ties identically;
    * ``restrict_ids`` (when not None) reproduces the ``in_lib`` pre-filter:
      only library rows are scored.

    Returns ``(cand_id, score_pct, components, available)`` sorted by RAW
    ``score_pct`` descending, floor-filtered, NOT truncated (the caller applies
    ``top_n``). ``score_pct`` stays raw (rounding only at output), so the sort
    order matches the pre-pool behavior exactly.
    """
    seed_id = seed.id
    seed_bpm = seed.bpm
    seed_genres = seed.expanded_genres
    seed_label = seed.label
    seed_label_valid = seed.label_valid
    seed_release = seed.release_date
    seed_playlists = seed.playlists
    seed_sets = seed.sets
    w = CFG.BPM_PREFILTER_WINDOW

    # Reproduce ``bpm_candidates + extra_candidates`` ordering: BPM-window (or
    # null-bpm) members first, then co-occurrence-only members, both in pool
    # (natural DB scan) order.
    bpm_members: list[PooledCandidate] = []
    cooc_only: list[PooledCandidate] = []
    for cand in pool.values():
        if cand.id == seed_id:
            continue
        if restrict_ids is not None and cand.id not in restrict_ids:
            continue
        if seed_bpm is None or cand.bpm is None:
            bpm_members.append(cand)
            continue
        cb = cand.bpm
        if (
            (seed_bpm - w) <= cb <= (seed_bpm + w)
            or (seed_bpm / 2 - w) <= cb <= (seed_bpm / 2 + w)
            or (seed_bpm * 2 - w) <= cb <= (seed_bpm * 2 + w)
        ):
            bpm_members.append(cand)
        elif (seed_playlists and (cand.playlists & seed_playlists)) or (
            seed_sets and (cand.sets & seed_sets)
        ):
            cooc_only.append(cand)

    scored: list[tuple[int, float, dict[str, float], list[str]]] = []
    for cand in (*bpm_members, *cooc_only):
        # Genre (candidate genres pre-expanded once in the pool)
        gj = (
            sim_genre(seed_genres, cand.expanded_genres)
            if (seed_genres and cand.expanded_genres)
            else 0.0
        )

        # BPM factor
        if seed_bpm is not None and cand.bpm is not None:
            bf = bpm_factor(seed_bpm, cand.bpm)
        else:
            bf = CFG.BPM_FACTOR_FLOOR

        # Style
        s_style = score_style(gj, bf)

        # Context (label validity pre-checked once in the pool)
        lm = (
            sim_label(seed_label, cand.label)
            if (seed_label_valid and cand.label_valid)
            else 0.0
        )
        es = (
            sim_era(seed_release, cand.release_date)
            if (seed_release and cand.release_date)
            else 0.0
        )
        s_context = score_context(lm, es)

        # Co-occurrence
        n_pl = len(seed_playlists & cand.playlists)
        s_playlists = score_cooc(n_pl, CFG.K_PLAYLISTS, CFG.CAP_PLAYLISTS)

        n_st = len(seed_sets & cand.sets)
        s_sets = score_cooc(n_st, CFG.K_SETS, CFG.CAP_SETS)

        total_pts = s_sets + s_playlists + s_style + s_context
        score_pct = total_pts / CFG.SCORE_TOTAL_CAP

        if score_pct < score_floor:
            continue

        available: list[str] = []
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

        scored.append((cand.id, score_pct, components, available))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def _build_result_items(
    db: AsyncSession,
    winners: list[tuple[int, float, dict[str, float], list[str]]],
    user_id: int | None,
) -> list[dict]:
    """Fetch full ORM data for the WINNERS only and build the response dicts.

    ``winners`` is the final ordered list of ``(cand_id, score_pct, components,
    available)``. Full ``CatalogEntry`` rows, artists and ``in_lib`` flags are
    fetched here — for the handful of ranked winners, never for the whole
    candidate pool. Produces the SAME response dict, field for field, as the
    pre-pool core built. Shared by the single-seed and reco paths.
    """
    from models import Artist, CatalogArtist, CatalogEntry, UserTrack
    from schemas import ArtistRef, GenreRef, SimilarityBlock, SimilarityComponents

    from services.genre_service import genre_pillar

    if not winners:
        return []

    winner_ids = [w[0] for w in winners]

    entry_rows = (
        (await db.execute(select(CatalogEntry).where(CatalogEntry.id.in_(winner_ids))))
        .scalars()
        .all()
    )
    entries_by_id = {e.id: e for e in entry_rows}

    artist_rows = (
        await db.execute(
            select(
                CatalogArtist.catalog_id,
                Artist.id,
                Artist.name,
                CatalogArtist.role,
                Artist.has_artwork,
            )
            .join(Artist, CatalogArtist.artist_id == Artist.id)
            .where(CatalogArtist.catalog_id.in_(winner_ids))
            .order_by(CatalogArtist.position)
        )
    ).all()
    artists_by_catalog: dict[int, list[ArtistRef]] = {}
    for cat_id, art_id, art_name, role, has_art in artist_rows:
        artists_by_catalog.setdefault(cat_id, []).append(
            ArtistRef(id=art_id, name=art_name, role=role, has_artwork=has_art)
        )

    in_lib_ids: set[int] = set()
    if user_id is not None:
        lib_rows = (
            await db.execute(
                select(UserTrack.catalog_id).where(
                    UserTrack.user_id == user_id,
                    UserTrack.catalog_id.in_(winner_ids),
                )
            )
        ).all()
        in_lib_ids = {r[0] for r in lib_rows}

    results: list[dict] = []
    for cand_id, score, components, available in winners:
        entry = entries_by_id.get(cand_id)
        if entry is None:
            continue
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

    Builds the candidate pool ONCE (one projected, visibility-scoped query),
    looks the seed up in it, scores in memory, then fetches full ORM data for
    the ``top_n`` winners only. Shared body behind :func:`similar_from_context`
    (in_lib=None) and :func:`get_similar_tracks`. Applies
    ``catalog_visible(user_id)`` (via the pool) and raises ``LookupError`` if the
    seed is absent/invisible.
    """
    from models import UserTrack

    # 1. Build the visible candidate pool and locate the seed within it. The
    #    pool is catalog_visible-scoped, so a missing seed == invisible/deleted.
    pool = await load_candidate_pool(db, user_id, ctx)
    seed = pool.get(seed_catalog_id)
    if seed is None:
        raise LookupError(f"Catalog entry {seed_catalog_id} not found")

    # 2. in_lib pre-filter: restrict candidates to the user's library (the same
    #    filter the pre-pool path applied to the union before scoring).
    restrict_ids: set[int] | None = None
    if in_lib is True and user_id is not None:
        lib_ids_rows = (
            await db.execute(
                select(UserTrack.catalog_id).where(UserTrack.user_id == user_id)
            )
        ).all()
        restrict_ids = {r[0] for r in lib_ids_rows}

    # 3. Score every candidate in memory, sort, keep top_n.
    scored = _score_seed_against_pool(
        pool, seed, score_floor=score_floor, restrict_ids=restrict_ids
    )
    top = scored[:top_n]

    # 4. Heavy fetch (artists, in_lib, full fields) for the winners only.
    return await _build_result_items(db, top, user_id)


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


# ---------------------------------------------------------------------------
# Set-level similarity (C2 engine aggregated over a set's tracklist)
# ---------------------------------------------------------------------------

# A set is scored from at most this many of its identified tracks (bounds the
# per-request cost: each seed is scored against the whole visible pool).
SIMILAR_SETS_SEED_CAP = 24
# Per-seed proximity: keep the top-N most similar tracks; each contributes to the
# sets that contain it.
SIMILAR_SETS_CAND_TRUNC = 40
# Weight of proximity (fuzzy per-track similarity) relative to exact tracklist
# overlap (which contributes +1.0 per shared set per seed, the dominant signal).
SIMILAR_SETS_PROXIMITY_W = 0.5


async def similar_sets(
    db: AsyncSession,
    set_id: int,
    user_id: int | None = None,
    *,
    limit: int = 8,
) -> list[dict]:
    """Sets closest to ``set_id``, aggregating the C2 track engine at set level.

    A set is represented by its identified tracklist; the closest sets are those
    whose tracklists overlap or whose tracks are individually similar. Algorithm:

    1. Load the set (id + ``parent_set_id``); raise ``LookupError`` if absent.
    2. Seeds = the ``catalog_id`` of its identified tracks (``catalog_id`` set,
       ``is_id`` false), ordered by position.
    3. Load the shared context once and the viewer-scoped candidate pool once.
       Restrict the seeds to the pool (= C3 visibility) and cap at
       ``SIMILAR_SETS_SEED_CAP``.
    4. Accumulate a per-set score:
         * OVERLAP (dominant): each root set in ``ctx.set_map[seed]`` gets +1.0;
         * PROXIMITY: score the seed against the pool, keep the top
           ``SIMILAR_SETS_CAND_TRUNC`` candidates, and give every set containing a
           candidate ``+candidate_score * SIMILAR_SETS_PROXIMITY_W``.
    5. Exclude the current set and its ``parent_set_id`` (children are absent from
       ``set_map`` by construction — roots only — so the parent root is the only
       way this set's own tracks re-enter the map).
    6. Normalise (max -> 1.0), sort by ``(-score, set_id)`` for determinism, keep
       the top ``limit``.
    7. Fetch the winner cards (title/source/counts + artist names ordered by
       position), same shape as the set list endpoint.

    Reuses the existing loaders/scoring untouched; awaits are sequential (an
    ``AsyncSession`` is not safe for concurrent ``execute``).
    """
    from models import Artist, DJSet, SetArtist, SetTrack

    # 1. Load the set (id + parent).
    set_row = (
        await db.execute(
            select(DJSet.id, DJSet.parent_set_id).where(DJSet.id == set_id)
        )
    ).first()
    if set_row is None:
        raise LookupError(f"Set {set_id} not found")
    parent_set_id = set_row[1]

    # 2. Seeds = identified tracks' catalog ids (position-ordered, deterministic).
    seed_rows = (
        await db.execute(
            select(SetTrack.catalog_id)
            .where(
                SetTrack.set_id == set_id,
                SetTrack.catalog_id.isnot(None),
                SetTrack.is_id.is_(False),
            )
            .order_by(SetTrack.position)
        )
    ).all()

    # 3. Shared context + viewer-scoped pool; restrict seeds to the visible pool.
    ctx = await load_similarity_context(db)
    pool = await load_candidate_pool(db, user_id, ctx)

    seeds: list[int] = []
    seen: set[int] = set()
    for (cid,) in seed_rows:
        if cid in pool and cid not in seen:
            seen.add(cid)
            seeds.append(cid)
            if len(seeds) >= SIMILAR_SETS_SEED_CAP:
                break

    excluded = {set_id}
    if parent_set_id is not None:
        excluded.add(parent_set_id)

    # 4. Accumulate per-set scores from overlap (dominant) + proximity.
    set_scores: dict[int, float] = {}
    for cid in seeds:
        for sid in ctx.set_map.get(cid, ()):  # exact tracklist overlap
            set_scores[sid] = set_scores.get(sid, 0.0) + 1.0
        scored = _score_seed_against_pool(pool, pool[cid], score_floor=0.0)[
            :SIMILAR_SETS_CAND_TRUNC
        ]
        for cand_id, score_pct, _components, _available in scored:
            weight = score_pct * SIMILAR_SETS_PROXIMITY_W
            if weight <= 0.0:
                continue
            for sid in ctx.set_map.get(cand_id, ()):
                set_scores[sid] = set_scores.get(sid, 0.0) + weight

    # 5. Drop the current set and its parent root.
    for sid in excluded:
        set_scores.pop(sid, None)

    # Guard against zero-only accumulations so every returned score is in (0, 1].
    set_scores = {sid: sc for sid, sc in set_scores.items() if sc > 0.0}
    if not set_scores:
        return []

    # 6. Normalise to (0, 1] and rank.
    max_score = max(set_scores.values())
    winners = sorted(
        ((sid, sc / max_score) for sid, sc in set_scores.items()),
        key=lambda x: (-x[1], x[0]),
    )[:limit]
    winner_ids = [sid for sid, _ in winners]

    # 7. Fetch the winner cards (mirror the list endpoint's shape).
    set_rows = (
        await db.execute(
            select(
                DJSet,
                func.count(SetTrack.id).label("total_tracks"),
                func.count(
                    case(
                        (
                            and_(
                                SetTrack.is_id.is_(False),
                                SetTrack.catalog_id.isnot(None),
                            ),
                            SetTrack.id,
                        ),
                    )
                ).label("identified_tracks"),
            )
            .outerjoin(SetTrack, SetTrack.set_id == DJSet.id)
            .where(DJSet.id.in_(winner_ids))
            .group_by(DJSet.id)
        )
    ).all()
    cards_by_id = {s.id: (s, total, ident) for s, total, ident in set_rows}

    artists_by_set: dict[int, list[str]] = {}
    aq = (
        await db.execute(
            select(SetArtist.set_id, Artist.name)
            .join(Artist, Artist.id == SetArtist.artist_id)
            .where(SetArtist.set_id.in_(winner_ids))
            .order_by(SetArtist.position)
        )
    ).all()
    for sid, name in aq:
        artists_by_set.setdefault(sid, []).append(name)

    results: list[dict] = []
    for sid, score in winners:
        card = cards_by_id.get(sid)
        if card is None:
            continue
        s, total, ident = card
        results.append(
            {
                "id": s.id,
                "title": s.title,
                "source": s.source,
                "played_date": s.played_date,
                "duration_ms": s.duration_ms,
                "has_artwork": s.has_artwork,
                "total_tracks": total,
                "identified_tracks": ident,
                "artists": artists_by_set.get(s.id, []),
                "score": round(score, 4),
            }
        )
    return results
