"""Artist cohort admin service (C14.a, L3).

Read + override surface over the ``artist_cohort`` table materialised by the
periodic recompute (``workers/cohort.py``). The recompute owns tier COMPUTATION;
this service only lists the cohort and applies admin overrides (pin / exclude /
forced tier), recomputing the EFFECTIVE tier the same way the recompute does
(``forced_tier`` → ``computed_tier`` → a pin floor of T1).

Convention (mirrors set_dedup_service): the service raises LookupError on a
missing entity and NEVER commits — the thin router audits and commits. DB loaders
are awaited SEQUENTIALLY on the one AsyncSession (never asyncio.gather).
"""

from datetime import datetime, timezone
from typing import Literal

from models import Artist, ArtistCohort
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _effective_tier(row: ArtistCohort) -> int:
    """The tier actually used: forced override, else computed, else a pin floor.

    Always returns a non-NULL tier (the column is NOT NULL). An excluded-only row
    with no computed/forced tier keeps its existing tier (never blanked), falling
    back to T1 for a freshly created row. Matches the recompute's own resolution
    (workers/cohort.py).
    """
    if row.forced_tier is not None:
        return row.forced_tier
    if row.computed_tier is not None:
        return row.computed_tier
    if row.pinned:
        return 1
    return row.tier if row.tier is not None else 1


def _item(row: ArtistCohort, name: str, deezer_id: str | None) -> dict:
    return {
        "artist_id": row.artist_id,
        "name": name,
        "deezer_id": deezer_id,
        "tier": row.tier,
        "computed_tier": row.computed_tier,
        "forced_tier": row.forced_tier,
        "pinned": row.pinned,
        "excluded": row.excluded,
        "signals": row.signals,
        "last_checked_at": row.last_checked_at,
        "last_recomputed_at": row.last_recomputed_at,
    }


async def list_cohort(
    db: AsyncSession,
    *,
    tier: int | None = None,
    override: Literal["pinned", "excluded"] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Paginated cohort listing, joined to Artist for name/deezer_id.

    Optional filters: exact ``tier`` and ``override`` ("pinned"/"excluded" →
    that flag is true). Stable ordering: tier asc, then oldest check first
    (``last_checked_at`` asc, NULLs first — never-checked members lead), then
    artist_id — so the page window is deterministic. Returns ``{total, items}``.
    """
    conditions = []
    if tier is not None:
        conditions.append(ArtistCohort.tier == tier)
    if override == "pinned":
        conditions.append(ArtistCohort.pinned.is_(True))
    elif override == "excluded":
        conditions.append(ArtistCohort.excluded.is_(True))

    total = await db.scalar(
        select(func.count()).select_from(ArtistCohort).where(*conditions)
    )

    rows = (
        await db.execute(
            select(ArtistCohort, Artist.name, Artist.deezer_id)
            .join(Artist, Artist.id == ArtistCohort.artist_id)
            .where(*conditions)
            .order_by(
                ArtistCohort.tier.asc(),
                ArtistCohort.last_checked_at.asc().nulls_first(),
                ArtistCohort.artist_id.asc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()

    return {
        "total": total or 0,
        "items": [_item(row, name, deezer_id) for row, name, deezer_id in rows],
    }


async def set_override(
    db: AsyncSession,
    artist_id: int,
    *,
    changes: dict,
) -> dict:
    """Apply admin overrides to an artist's cohort row; recompute effective tier.

    ``changes`` carries ONLY the explicitly-provided fields (the router builds it
    from ``body.model_dump(exclude_unset=True)``) — proper PATCH semantics: a key
    absent from ``changes`` is left untouched. ``pinned``/``excluded`` are applied
    only when present AND non-null (they are boolean toggles). ``forced_tier`` is
    applied whenever its key is present — the value may be an int 1/2/3 (force) or
    None (UN-force → back to the computed/auto tier), since ``_effective_tier``
    already falls back from a None ``forced_tier`` to ``computed_tier`` (then the
    pin floor). The row is CREATED when absent (an artist outside the cohort can be
    pinned/forced into it). Raises LookupError if the artist itself does not exist.
    Flushes but does NOT commit (the router audits + commits). Returns the item dict.
    """
    artist = (
        await db.execute(select(Artist).where(Artist.id == artist_id))
    ).scalar_one_or_none()
    if artist is None:
        raise LookupError(f"Artist {artist_id} not found")

    row = (
        await db.execute(
            select(ArtistCohort).where(ArtistCohort.artist_id == artist_id)
        )
    ).scalar_one_or_none()
    if row is None:
        # No signal-derived membership yet — start a bare row the overrides carry.
        row = ArtistCohort(
            artist_id=artist_id,
            tier=1,
            computed_tier=None,
            forced_tier=None,
            pinned=False,
            excluded=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)

    if changes.get("pinned") is not None:
        row.pinned = changes["pinned"]
    if changes.get("excluded") is not None:
        row.excluded = changes["excluded"]
    # An explicit forced_tier key (even = None) is honoured: None CLEARS the force.
    if "forced_tier" in changes:
        row.forced_tier = changes["forced_tier"]

    row.tier = _effective_tier(row)
    await db.flush()
    return _item(row, artist.name, artist.deezer_id)
