"""
Personalised "Pour toi" recommendation service (C4).

Crosses the user's taste (likes, library, dislikes) with the C2 similarity
engine, computed on the fly with a fail-open Redis cache.

No LLM: the aggregation is fully deterministic (project invariant — LLMs never
compute similarity/recommendation scores).

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import Integer, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration — retunable weights & caps (cf. SimilarityConfig, C2).
# All defaults live here so the recommendation can be tuned without a refactor.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecommendationConfig:
    # Seed weights
    W_LIKE: float = 1.0        # a liked track is a STRONG positive seed
    W_LIB: float = 0.4         # a library track is a MODERATE positive seed
    W_DISLIKE: float = 0.7     # a disliked track SUBTRACTS from the score
    # Seed caps — bound the cost (the library can hold thousands of tracks).
    # Likes come first, then a slice of the library up to SEED_CAP total.
    # caps volontairement bas — le calcul est on-the-fly derrière un timeout
    # nginx de 60s ; à revoir avec le fix durable (candidate pooling ou
    # précalcul nightly).
    SEED_CAP: int = 12
    DISLIKE_CAP: int = 12
    # Per-seed candidate retrieval: bounded per-seed candidate set (audio KNN ∪
    # co-occurrence, see similarity_service retrieval core), low floor — the
    # aggregation (and the final ranking) is where relevance is decided.
    CAND_PER_SEED: int = 40
    SEED_SCORE_FLOOR: float = 0.02
    # Content (audio embeddings, EffNet) channel: an ADDITIVE, surpondered bonus
    # on top of the metadata score, never a convex blend (décision C9.0-bis : la
    # fusion 50/50 sous-performe l'audio surpondéré). À calibrer par l'éval
    # offline (lot L5).
    CONTENT_BONUS: float = 1.0
    # How many ranked candidates to keep cached (>= the endpoint's max limit,
    # so a single cache entry serves every limit).
    MAX_ITEMS: int = 100
    # Cache. TTL long enough (25h) to bridge two nightly precompute runs
    # (workers.tasks.precompute_recommendations, daily): the cache is written
    # nightly for every active user, so the interactive feed always hits the warm
    # ~1.7s path instead of the ~30s cold compute that timed out under nginx (504,
    # mesuré 2026-08-13). An opinion change still invalidates eagerly.
    CACHE_TTL: int = 90000     # seconds (~25h)


CFG = RecommendationConfig()

_CACHE_PREFIX = "reco"

# Cold-path policy (2026-09-18; compute re-based retrieval-first C9.c/L2): the api
# still NEVER computes inline. Since L2 a cold compute is a BOUNDED retrieval-first
# pass (per-seed KNN ∪ co-occ, a few seconds) — not the old full-pool scan
# (~683k-row visible catalog × multi-seed, ~60-114s measured) that blew the 60s
# nginx proxy timeout into a 504. The dispatch-and-degrade policy is KEPT anyway
# (it stays the right posture — cheap, cache-warming, storm-safe): on a miss the
# api dispatches the per-user worker task
# (workers.tasks.precompute_user_recommendations) and degrades to an empty "Pour
# toi" (Tendance still renders; the feed fills once the worker has cached). The
# dispatch is deduped by a short Redis guard so a rating burst schedules ONE
# recompute, not one per avis — an avis landing while a compute is in flight
# leaves the cache stale for at most guard TTL + one compute, and the nightly
# precompute trues everything up. With ``redis`` None (tests/direct calls) the
# plain inline compute is kept: no cache to warm, and the broker is that same
# Redis anyway.
_DISPATCH_GUARD_PREFIX = "reco:dispatch"
_DISPATCH_GUARD_TTL_S = 180  # ≈ one worker compute; bounds dispatch storms


# ---------------------------------------------------------------------------
# Redis cache (fail-open — availability wins over a warm cache, cf. rate_limit)
# ---------------------------------------------------------------------------

def _cache_key(user_id: int) -> str:
    # Not keyed by ``limit``: we cache the full ranked list (MAX_ITEMS) and slice
    # per request, so one entry serves every limit and invalidation is one key.
    return f"{_CACHE_PREFIX}:{user_id}"


def _dispatch_guard_key(user_id: int) -> str:
    return f"{_DISPATCH_GUARD_PREFIX}:{user_id}"


async def _cache_get(redis, user_id: int):
    from schemas import RecommendationList

    try:
        raw = await redis.get(_cache_key(user_id))
    except Exception as exc:  # fail-open: Redis down/unsupported → recompute
        logger.warning("reco cache read skipped (Redis unavailable): %s", exc)
        return None
    if not raw:
        return None
    try:
        return RecommendationList.model_validate_json(raw)
    except Exception:  # corrupt/legacy payload → recompute
        return None


async def _cache_set(redis, user_id: int, result) -> None:
    try:
        await redis.setex(_cache_key(user_id), CFG.CACHE_TTL, result.model_dump_json())
    except Exception as exc:  # fail-open
        logger.warning("reco cache write skipped (Redis unavailable): %s", exc)


async def invalidate_user(redis, user_id: int) -> None:
    """Best-effort cache drop for a user (e.g. after an opinion change).

    Fail-open: an unavailable Redis just leaves the TTL to expire the entry.
    """
    if redis is None:
        return
    try:
        await redis.delete(_cache_key(user_id))
    except Exception as exc:
        logger.warning("reco cache invalidation skipped (Redis unavailable): %s", exc)


async def schedule_precompute(redis, user_id: int) -> bool:
    """Fire-and-forget worker recompute of one user's reco cache.

    Called on a feed cache miss and right after an opinion change (the api never
    computes inline — see the cold-path policy above). Deduped by a short Redis
    guard so a rating burst dispatches once. Fail-open on both Redis and the
    broker (the same Redis instance): a missed dispatch just leaves the cache
    cold until the nightly precompute. Returns True when a task was dispatched.
    """
    if redis is None:
        return False
    try:
        got = await redis.set(
            _dispatch_guard_key(user_id), "1", nx=True, ex=_DISPATCH_GUARD_TTL_S
        )
    except Exception as exc:  # Redis down → the broker is down too; nothing to do
        logger.warning("reco dispatch guard skipped (Redis unavailable): %s", exc)
        return False
    if not got:
        return False
    try:
        from celery_client import celery

        celery.send_task(
            "workers.tasks.precompute_user_recommendations", args=[user_id]
        )
        return True
    except Exception as exc:
        logger.warning("reco precompute dispatch failed: %s", exc)
        try:  # free the guard so a later request can retry the dispatch
            await redis.delete(_dispatch_guard_key(user_id))
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Taste-source queries
# ---------------------------------------------------------------------------

async def _opinion_ids(db: AsyncSession, user_id: int, opinion: str) -> list[int]:
    """Catalog ids the user has an opinion on (entity_key is stored as a string)."""
    from models import UserOpinion

    rows = (
        await db.execute(
            select(cast(UserOpinion.entity_key, Integer)).where(
                UserOpinion.user_id == user_id,
                UserOpinion.entity_type == "track",
                UserOpinion.opinion == opinion,
            )
        )
    ).all()
    return [r[0] for r in rows if r[0] is not None]


async def _lib_ids(db: AsyncSession, user_id: int) -> list[int]:
    """Catalog ids in the user's imported library, most recently added first."""
    from models import UserTrack

    rows = (
        await db.execute(
            select(UserTrack.catalog_id)
            .where(UserTrack.user_id == user_id)
            .order_by(UserTrack.created_at.desc(), UserTrack.catalog_id.desc())
        )
    ).all()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

async def _compute(db: AsyncSession, user_id: int):
    """Compute the full ranked recommendation list (uncached).

    Retrieval-first (C9.c). Instead of scoring the WHOLE visible catalog
    (~700k rows, ~85s measured) against every seed, each positive seed retrieves
    a BOUNDED candidate set — its top-K pgvector audio neighbours ∪ its
    inverted-index co-occurrence rows (the L1 retrieval core) — and only that
    union is scored by the existing in-memory metadata core. On top of the
    metadata score the audio-content channel adds a surpondered ADDITIVE bonus
    per (seed, neighbour): a candidate reached only through the KNN (no
    metadata/co-occ link) surfaces on its content bonus alone (the C9
    cold-start), and a candidate with no embedding keeps EXACTLY its metadata
    score. On SQLite (tests) ``content_neighbor_ids`` returns ``{}``, so the
    computation reduces to co-occurrence scoring — identical to the pre-C9.c
    behaviour on the co-occ-only test datasets.
    """
    from schemas import RecommendationList

    likes = await _opinion_ids(db, user_id, "liked")
    dislikes = await _opinion_ids(db, user_id, "disliked")
    lib = await _lib_ids(db, user_id)

    # Cold start: nothing to build a taste profile from.
    if not likes and not lib:
        return RecommendationList(items=[])

    from services.similarity_service import (
        _build_result_items,
        _dedup_by_album,
        _score_seed_against_pool,
        content_neighbor_ids,
        cooc_candidate_ids,
        load_candidates_by_ids,
        load_similarity_context,
    )

    # Seed-agnostic maps loaded ONCE (cached in-process, 6h TTL). Carries the
    # inverted co-occurrence indexes the retrieval reads.
    ctx = await load_similarity_context(db)

    # Never recommend what the user already owns or has rated.
    excluded = set(likes) | set(dislikes) | set(lib)
    like_set = set(likes)

    # Positive seeds: likes first (strong), then a library slice (moderate),
    # capped at SEED_CAP total.
    positive_seeds: list[tuple[int, float]] = [
        (cid, CFG.W_LIKE) for cid in likes[: CFG.SEED_CAP]
    ]
    remaining = CFG.SEED_CAP - len(positive_seeds)
    if remaining > 0:
        for cid in lib:
            if cid in like_set:  # a liked library track is already a like-seed
                continue
            positive_seeds.append((cid, CFG.W_LIB))
            remaining -= 1
            if remaining <= 0:
                break

    dislike_seeds = dislikes[: CFG.DISLIKE_CAP]

    # Seed FEATURES in ONE bounded pass (no more full-catalog pool). A seed the
    # viewer cannot see (deleted/foreign-private) is absent from the pool and is
    # skipped below (was ``pool.get(seed_id) is None → continue``).
    seed_ids = {sid for sid, _ in positive_seeds} | set(dislike_seeds)
    seed_pool = await load_candidates_by_ids(db, user_id, ctx, seed_ids)

    visible_positive = [sid for sid, _ in positive_seeds if sid in seed_pool]

    # Per-seed audio neighbours (PostgreSQL only; ``{}`` on SQLite). One call
    # loops the embedded seeds internally. ``{seed_id: [(cid, cosine_dist), ...]}``.
    knn = await content_neighbor_ids(db, visible_positive, user_id)

    # Candidate set = union over positive seeds of (audio KNN ∪ co-occurrence),
    # minus everything the user already owns/rated.
    candidate_ids: set[int] = set()
    for seed_id, _weight in positive_seeds:
        seed = seed_pool.get(seed_id)
        if seed is None:
            continue
        candidate_ids.update(cid for cid, _dist in knn.get(seed_id, ()))
        candidate_ids |= cooc_candidate_ids(ctx, seed.sets, seed.playlists)
    candidate_ids -= excluded

    # Candidate features in ONE bounded pass. Full ORM data is still fetched only
    # for the final ranked winners, via _build_result_items.
    cand_pool = await load_candidates_by_ids(db, user_id, ctx, candidate_ids)

    reco_score: dict[int, float] = {}
    # Similarity (score_pct, components, available) from the FIRST positive seed
    # that surfaced each candidate — mirrors the old ``track_by_id.setdefault``,
    # which kept the first seed's full result dict.
    first_sim: dict[int, tuple[float, dict, list]] = {}

    for seed_id, weight in positive_seeds:
        seed = seed_pool.get(seed_id)
        if seed is None:  # deleted/invisible seed → skip (was LookupError→[])
            continue
        # Off-loop per seed: scoring the candidate pool is pure CPU and would
        # block the event loop past the uvicorn supervisor ping window.
        scored = (
            await asyncio.to_thread(
                _score_seed_against_pool,
                cand_pool,
                seed,
                score_floor=CFG.SEED_SCORE_FLOOR,
                limit=CFG.CAND_PER_SEED,
            )
        )[: CFG.CAND_PER_SEED]
        for cid, score_pct, components, available in scored:
            if cid in excluded:
                continue
            # Weight the ROUNDED per-seed score: the pre-pool path summed
            # ``cand["similarity"]["score"]``, which was already round(_, 4).
            reco_score[cid] = reco_score.get(cid, 0.0) + weight * round(score_pct, 4)
            if cid not in first_sim:
                first_sim[cid] = (score_pct, components, available)

        # Content channel (C9.c): ADDITIVE, surpondered bonus for each audio
        # neighbour of this seed. Never a convex blend — a candidate with no
        # embedding (reached via co-occ) keeps its metadata score untouched, and
        # a KNN-only candidate (no metadata/co-occ link to any seed) still
        # surfaces on this bonus alone (cold-start). ``1 - dist`` ∈ [0, 1] since
        # the EffNet vectors are L2-normalised.
        for cid, dist in knn.get(seed_id, ()):
            if cid in excluded:
                continue
            reco_score[cid] = reco_score.get(cid, 0.0) + (
                weight * CFG.CONTENT_BONUS * (1.0 - dist)
            )
            # A content-only candidate has no metadata result — give it a zeroed
            # metadata block tagged "content" so the winner build finds it.
            first_sim.setdefault(
                cid,
                (
                    max(0.0, 1.0 - dist),
                    {"sets": 0.0, "playlists": 0.0, "style": 0.0, "context": 0.0},
                    ["content"],
                ),
            )

    # Dislikes penalise candidates that a positive seed already surfaced. A
    # candidate reachable only through a dislike would be purely negative and is
    # dropped by the ``> 0`` filter below anyway, so we don't materialise it. The
    # penalty is metadata-only (dislikes are not part of the content retrieval).
    for seed_id in dislike_seeds:
        seed = seed_pool.get(seed_id)
        if seed is None:
            continue
        scored = (
            await asyncio.to_thread(
                _score_seed_against_pool,
                cand_pool,
                seed,
                score_floor=CFG.SEED_SCORE_FLOOR,
                limit=CFG.CAND_PER_SEED,
            )
        )[: CFG.CAND_PER_SEED]
        for cid, score_pct, components, available in scored:
            if cid in excluded or cid not in reco_score:
                continue
            reco_score[cid] -= CFG.W_DISLIKE * round(score_pct, 4)

    # Rank best-first, then apply the L4 album de-dup (≤1 track per album, keeps
    # the best-scored) BEFORE truncating to MAX_ITEMS — so the cached list holds
    # up to MAX_ITEMS distinct-album items, not a post-truncation remainder.
    ranked = _dedup_by_album(
        sorted(
            ((cid, sc) for cid, sc in reco_score.items() if sc > 0.0),
            key=lambda x: x[1],
            reverse=True,
        ),
        cand_pool,
        CFG.MAX_ITEMS,
    )

    # Heavy fetch for the ranked winners only; then stamp reco_score by id (no
    # positional zip — robust to any missing entry). The album_id comes straight
    # from the pool — no extra query.
    winners = [(cid, *first_sim[cid]) for cid, _ in ranked]
    album_by_id = {cid: cand_pool[cid].album_id for cid, _ in ranked}
    items = await _build_result_items(db, winners, user_id, album_by_id=album_by_id)
    for item in items:
        item["reco_score"] = round(reco_score[item["id"]], 4)

    return RecommendationList.model_validate({"items": items})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def get_recommendations(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int = 20,
    redis=None,
):
    """Personalised recommendations for a user.

    Returns a ``RecommendationList`` (empty on cold start AND on a cold cache —
    the api never computes inline, see the cold-path policy above). ``redis`` is
    the optional cache backend; when omitted the list is computed live.
    """
    from schemas import RecommendationList

    full = None
    if redis is not None:
        full = await _cache_get(redis, user_id)
    if full is None:
        if redis is None:
            # Tests/direct calls: no cache to warm, no broker — compute live.
            full = await _compute(db, user_id)
        else:
            # Cold cache: schedule a worker recompute and degrade to an empty
            # "Pour toi" this once (also on an unavailable Redis — an outage
            # must not trigger a ~60s inline compute per request).
            await schedule_precompute(redis, user_id)
            full = RecommendationList(items=[])

    return RecommendationList(items=full.items[:limit])
