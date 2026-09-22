"""Derived artist-cohort recompute (C14.a).

Materialises the ``artist_cohort`` table from signals already in the DB — library
membership, likes, reliable DJ-set appearances over the last 12 months, catalog
depth and manual follows — using deterministic thresholds only (invariant #5: no
LLM here). The recompute AUTO-PROMOTES an artist that crosses a threshold and
DROPS a pure-signal artist that goes silent, but NEVER overwrites an admin
override (``pinned`` / ``excluded`` / ``forced_tier``).

This module is PURE of the Celery machinery: it takes a plain sync engine/session
so it is unit-testable against SQLite. The Celery wrapper lives in
``workers/tasks/cohort.py``.
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# --- tunable membership thresholds ---
# >= this many reliable DJ sets over the window → T1 on its own.
SETS_12M_T1 = 3
# >= this many sets over the window AND a deep catalog → T1.
SETS_12M_DEEP = 2
# >= this many distinct catalog tracks = a "deep" discography.
CATALOG_DEEP = 10
# >= this many distinct catalog tracks → at least T2.
CATALOG_T2 = 10
# >= this many reliable DJ sets over the window → at least T2.
SETS_12M_T2 = 1

# Recency window for the DJ-set signal (12 months).
SETS_WINDOW_DAYS = 365

# --- per-tier watch cadence (release-watch lot L2) ---
# The nightly Deezer release-watch re-checks a T1 (daily) member once a day and a
# T2 (weekly) member once a week; select_due_cohort_ids draws the members whose
# cadence has elapsed. Tier 3 is deferred (v1) and never drawn.
T1_CADENCE_DAYS = 1
T2_CADENCE_DAYS = 7


def compute_tier(*, nb_lib, nb_likes, nb_sets_12m, nb_catalog, followed):
    """The tier derived from the raw signals, before any admin override.

    Returns 1 (daily), 2 (weekly) or ``None`` (out of cohort). A followed artist
    is always T1 (follows force membership, tier >= 1).
    """
    is_deep = nb_catalog >= CATALOG_DEEP
    if (
        nb_lib > 0
        or followed
        or nb_likes > 0
        or nb_sets_12m >= SETS_12M_T1
        or (nb_sets_12m >= SETS_12M_DEEP and is_deep)
    ):
        return 1
    if nb_catalog >= CATALOG_T2 or nb_sets_12m >= SETS_12M_T2:
        return 2
    return None


def recompute(engine) -> dict:
    """Recompute the whole cohort in one session, commit, and return stats."""
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        stats = recompute_cohort(session)
        session.commit()
    return stats


def recompute_cohort(session, *, now=None) -> dict:
    """Core recompute against a sync session. Flushes but does NOT commit.

    Auto-promotes/demotes on signals, preserves admin overrides, prunes
    pure-signal dropouts. Returns ``{n_t1, n_t2, n_pinned, n_excluded, n_pruned,
    n_total}``.
    """
    from models import (
        ArtistCohort,
        CatalogArtist,
        DJSet,
        FollowedArtist,
        SetArtist,
        UserOpinion,
        UserTrack,
    )
    from sqlalchemy import func, select
    from trackid.reliability import set_reliable

    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=SETS_WINDOW_DAYS)).date()

    # ── Signal 1: catalog depth — distinct catalog tracks per artist. Same
    # pattern as artist_service.list_artists (count distinct catalog_artists).
    nb_catalog = dict(
        session.execute(
            select(
                CatalogArtist.artist_id,
                func.count(func.distinct(CatalogArtist.catalog_id)),
            ).group_by(CatalogArtist.artist_id)
        ).all()
    )

    # ── Signal 2: library membership — distinct catalog tracks of the artist
    # that live in ANY user's user_tracks (all users), joined via catalog_artists.
    nb_lib = dict(
        session.execute(
            select(
                CatalogArtist.artist_id,
                func.count(func.distinct(UserTrack.catalog_id)),
            )
            .join(UserTrack, UserTrack.catalog_id == CatalogArtist.catalog_id)
            .group_by(CatalogArtist.artist_id)
        ).all()
    )

    # ── Signal 3: reliable, root, non-virtual DJ sets over the last 12 months
    # where the artist is a DJ. roots-only + set_reliable() + is_virtual guard so
    # dedup virtual parents and unreliable sets never count (invariant: a set
    # never spans multiple days → event_date preferred over the upload played_date).
    nb_sets_12m = dict(
        session.execute(
            select(
                SetArtist.artist_id,
                func.count(func.distinct(DJSet.id)),
            )
            .join(DJSet, DJSet.id == SetArtist.set_id)
            .where(
                SetArtist.role == "dj",
                DJSet.parent_set_id.is_(None),
                DJSet.is_virtual.is_(False),
                set_reliable(),
                func.coalesce(DJSet.event_date, DJSet.played_date) >= cutoff,
            )
            .group_by(SetArtist.artist_id)
        ).all()
    )

    # ── Signal 4: likes — user_opinions(opinion='liked'). Artist-level opinions
    # (entity_key = str(artist_id)) plus track-level opinions mapped to their
    # artists via catalog_artists. user_opinions is the canonical opinion store
    # (D2); we deliberately do NOT introduce a third like source.
    nb_likes: dict[int, int] = {}
    for entity_key, n in session.execute(
        select(UserOpinion.entity_key, func.count())
        .where(
            UserOpinion.entity_type == "artist",
            UserOpinion.opinion == "liked",
        )
        .group_by(UserOpinion.entity_key)
    ).all():
        try:
            aid = int(entity_key)
        except (TypeError, ValueError):
            continue
        nb_likes[aid] = nb_likes.get(aid, 0) + int(n)

    liked_catalog_ids: set[int] = set()
    for (entity_key,) in session.execute(
        select(UserOpinion.entity_key).where(
            UserOpinion.entity_type == "track",
            UserOpinion.opinion == "liked",
        )
    ).all():
        try:
            liked_catalog_ids.add(int(entity_key))
        except (TypeError, ValueError):
            continue
    if liked_catalog_ids:
        for aid, n in session.execute(
            select(
                CatalogArtist.artist_id,
                func.count(func.distinct(CatalogArtist.catalog_id)),
            )
            .where(CatalogArtist.catalog_id.in_(liked_catalog_ids))
            .group_by(CatalogArtist.artist_id)
        ).all():
            nb_likes[aid] = nb_likes.get(aid, 0) + int(n)

    # ── Signal 5: manual follows (any user) — always cohort members (D4).
    followed = {
        aid
        for (aid,) in session.execute(
            select(FollowedArtist.artist_id).distinct()
        ).all()
    }

    # Candidate universe = artists carrying at least one signal. An artist absent
    # from every dict computes to None (out of cohort) by construction, so there
    # is no need to scan the whole artists table.
    candidate_ids = (
        set(nb_catalog)
        | set(nb_lib)
        | set(nb_sets_12m)
        | set(nb_likes)
        | followed
    )

    def _signals(aid: int) -> dict:
        return {
            "nb_lib": int(nb_lib.get(aid, 0)),
            "nb_likes": int(nb_likes.get(aid, 0)),
            "nb_sets_12m": int(nb_sets_12m.get(aid, 0)),
            "nb_catalog": int(nb_catalog.get(aid, 0)),
            "followed": aid in followed,
        }

    qualifying: dict[int, int] = {}
    for aid in candidate_ids:
        sig = _signals(aid)
        ct = compute_tier(
            nb_lib=sig["nb_lib"],
            nb_likes=sig["nb_likes"],
            nb_sets_12m=sig["nb_sets_12m"],
            nb_catalog=sig["nb_catalog"],
            followed=sig["followed"],
        )
        if ct is not None:
            qualifying[aid] = ct

    existing = {
        row.artist_id: row
        for row in session.execute(select(ArtistCohort)).scalars().all()
    }

    n_pruned = 0

    # Auto-promote/demote every qualifying artist (upsert), preserving overrides.
    for aid, ct in qualifying.items():
        row = existing.get(aid)
        if row is None:
            row = ArtistCohort(
                artist_id=aid,
                pinned=False,
                excluded=False,
                forced_tier=None,
                created_at=now,
            )
            session.add(row)
            existing[aid] = row
        row.computed_tier = ct
        row.signals = _signals(aid)
        row.last_recomputed_at = now
        # Effective tier = admin override if any, else computed. A followed
        # artist computes to T1, so follows already force tier >= 1.
        row.tier = row.forced_tier if row.forced_tier is not None else ct

    # Non-qualifying existing rows: keep if an override memorises them, else drop.
    for aid, row in list(existing.items()):
        if aid in qualifying:
            continue
        row.computed_tier = None
        row.signals = _signals(aid)
        row.last_recomputed_at = now
        has_override = bool(
            row.pinned or row.excluded or row.forced_tier is not None
        )
        if not has_override:
            # Pure-signal dropout — remove from the cohort entirely.
            session.delete(row)
            del existing[aid]
            n_pruned += 1
            continue
        # Kept alive by an override. tier stays non-NULL: forced_tier wins, else a
        # pin floors it at T1, else (excluded only) keep the existing tier for
        # memory of the exclusion — never blank it.
        if row.forced_tier is not None:
            row.tier = row.forced_tier
        elif row.pinned:
            row.tier = 1
        # excluded-only: leave row.tier untouched.

    session.flush()

    n_t1 = n_t2 = n_pinned = n_excluded = 0
    for row in existing.values():
        if row.pinned:
            n_pinned += 1
        if row.excluded:
            n_excluded += 1
            continue
        if row.tier == 1:
            n_t1 += 1
        elif row.tier == 2:
            n_t2 += 1

    stats = {
        "n_t1": n_t1,
        "n_t2": n_t2,
        "n_pinned": n_pinned,
        "n_excluded": n_excluded,
        "n_pruned": n_pruned,
        "n_total": len(existing),
    }
    logger.info("recompute_artist_cohort: %s", stats)
    return stats


def select_due_cohort_ids(session, now, budget):
    """Return up to ``budget`` cohort ``artist_id``s DUE for a Deezer check.

    A non-excluded row is due when its per-tier cadence has elapsed since its
    last check, or it was never checked: T1 (tier 1) every ``T1_CADENCE_DAYS``,
    T2 (tier 2) every ``T2_CADENCE_DAYS`` (tier 3 is deferred — never drawn).
    Ordered T1-due first, then T2-due, tie-broken by the oldest check
    (``last_checked_at`` ASC, NULLs first) so a never-checked member is picked
    before a recently-checked one — the far larger T2 population can therefore
    never starve T1. SYNC (mirrors ``recompute_cohort``), returns the ordered id
    list, driven by the release-watch task (workers/tasks/artists.py).
    """
    from models import ArtistCohort
    from sqlalchemy import and_, or_, select

    t1_cutoff = now - timedelta(days=T1_CADENCE_DAYS)
    t2_cutoff = now - timedelta(days=T2_CADENCE_DAYS)

    due = or_(
        and_(
            ArtistCohort.tier == 1,
            or_(
                ArtistCohort.last_checked_at.is_(None),
                ArtistCohort.last_checked_at < t1_cutoff,
            ),
        ),
        and_(
            ArtistCohort.tier == 2,
            or_(
                ArtistCohort.last_checked_at.is_(None),
                ArtistCohort.last_checked_at < t2_cutoff,
            ),
        ),
    )
    stmt = (
        select(ArtistCohort.artist_id)
        # excluded IS NOT TRUE mirrors the partial index ix_artist_cohort_tier_checked.
        .where(ArtistCohort.excluded.isnot(True), due)
        # tier ASC → T1 before T2 (only tiers 1/2 satisfy `due`); NULLs-first
        # last_checked_at → never-checked members are the highest priority.
        .order_by(
            ArtistCohort.tier.asc(),
            ArtistCohort.last_checked_at.asc().nulls_first(),
        )
        .limit(budget)
    )
    return [row[0] for row in session.execute(stmt).all()]
