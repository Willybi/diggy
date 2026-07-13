"""
Personalised "Pour toi" recommendation service (C4).

Crosses the user's taste (likes, library, dislikes) with the C2 similarity
engine, computed on the fly with a fail-open Redis cache.

No LLM: the aggregation is fully deterministic (project invariant — LLMs never
compute similarity/recommendation scores).

Services raise LookupError (404) or ValueError (400), never HTTPException.
"""

from __future__ import annotations

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
    SEED_CAP: int = 80
    DISLIKE_CAP: int = 80
    # Per-seed candidate retrieval: broad pool, low floor — the aggregation
    # (and the final ranking) is where relevance is decided.
    CAND_PER_SEED: int = 100
    SEED_SCORE_FLOOR: float = 0.02
    # How many ranked candidates to keep cached (>= the endpoint's max limit,
    # so a single cache entry serves every limit).
    MAX_ITEMS: int = 100
    # Cache
    CACHE_TTL: int = 3600      # seconds


CFG = RecommendationConfig()

_CACHE_PREFIX = "reco"


# ---------------------------------------------------------------------------
# Redis cache (fail-open — availability wins over a warm cache, cf. rate_limit)
# ---------------------------------------------------------------------------

def _cache_key(user_id: int) -> str:
    # Not keyed by ``limit``: we cache the full ranked list (MAX_ITEMS) and slice
    # per request, so one entry serves every limit and invalidation is one key.
    return f"{_CACHE_PREFIX}:{user_id}"


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


async def _similar(db: AsyncSession, ctx, seed_id: int, user_id: int) -> list[dict]:
    """Candidates similar to one seed, scored against a pre-loaded C2 context.

    Consumes the similarity engine's ``similar_from_context`` primitive with the
    context ``ctx`` (the 4 maps) loaded ONCE per compute — no per-seed full-table
    reload. ``catalog_visible`` is applied there (candidate read side), so
    private rows never leak. A seed that became invisible/deleted raises
    LookupError → we skip it rather than failing the whole recommendation.
    """
    from services.similarity_service import similar_from_context

    try:
        return await similar_from_context(
            db,
            ctx,
            seed_id,
            user_id,
            top_n=CFG.CAND_PER_SEED,
            score_floor=CFG.SEED_SCORE_FLOOR,
        )
    except LookupError:
        return []


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

async def _compute(db: AsyncSession, user_id: int):
    """Compute the full ranked recommendation list (uncached)."""
    from schemas import RecommendationList

    likes = await _opinion_ids(db, user_id, "liked")
    dislikes = await _opinion_ids(db, user_id, "disliked")
    lib = await _lib_ids(db, user_id)

    # Cold start: nothing to build a taste profile from.
    if not likes and not lib:
        return RecommendationList(items=[])

    from services.similarity_service import load_similarity_context

    # Load the 4 similarity maps ONCE and reuse across every seed (only past the
    # cold-start guard, so we never pay it for a user with no taste profile).
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

    reco_score: dict[int, float] = {}
    track_by_id: dict[int, dict] = {}

    for seed_id, weight in positive_seeds:
        for cand in await _similar(db, ctx, seed_id, user_id):
            cid = cand["id"]
            if cid in excluded:
                continue
            reco_score[cid] = reco_score.get(cid, 0.0) + weight * cand["similarity"]["score"]
            track_by_id.setdefault(cid, cand)

    # Dislikes penalise candidates that a positive seed already surfaced. A
    # candidate reachable only through a dislike would be purely negative and is
    # dropped by the ``> 0`` filter below anyway, so we don't materialise it.
    for seed_id in dislikes[: CFG.DISLIKE_CAP]:
        for cand in await _similar(db, ctx, seed_id, user_id):
            cid = cand["id"]
            if cid in excluded or cid not in reco_score:
                continue
            reco_score[cid] -= CFG.W_DISLIKE * cand["similarity"]["score"]

    ranked = sorted(
        ((cid, sc) for cid, sc in reco_score.items() if sc > 0.0),
        key=lambda x: x[1],
        reverse=True,
    )[: CFG.MAX_ITEMS]

    items = []
    for cid, sc in ranked:
        item = dict(track_by_id[cid])
        item["reco_score"] = round(sc, 4)
        items.append(item)

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

    Returns a ``RecommendationList`` (empty on cold start). ``redis`` is the
    optional cache backend; when omitted the list is always computed live.
    """
    from schemas import RecommendationList

    full = None
    if redis is not None:
        full = await _cache_get(redis, user_id)
    if full is None:
        full = await _compute(db, user_id)
        if redis is not None:
            await _cache_set(redis, user_id, full)

    return RecommendationList(items=full.items[:limit])
