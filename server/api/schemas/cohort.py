"""Artist cohort admin schemas (C14.a, L3)."""

from datetime import datetime

from pydantic import BaseModel, Field


class CohortItemOut(BaseModel):
    artist_id: int
    name: str
    deezer_id: str | None = None
    # Effective tier actually used by the watch cadence (forced_tier if set, else
    # computed_tier, else a pin floor). Always non-NULL.
    tier: int
    computed_tier: int | None = None
    forced_tier: int | None = None
    pinned: bool
    excluded: bool
    # Frozen snapshot of the last recompute's raw counts (nb_lib, nb_likes, …).
    signals: dict | None = None
    last_checked_at: datetime | None = None
    last_recomputed_at: datetime | None = None

    model_config = {"from_attributes": True}


class CohortListOut(BaseModel):
    total: int
    items: list[CohortItemOut]


class CohortOverrideIn(BaseModel):
    # PATCH semantics: a field ABSENT from the body is not changed (the router reads
    # the provided keys via model_dump(exclude_unset=True)). forced_tier is bounded
    # to the supported tiers (1/2/3) but an explicit null is a first-class value =
    # UN-force (back to the auto/computed tier) — the ge/le bounds only constrain a
    # provided int, they accept None. The recompute never overwrites these overrides.
    pinned: bool | None = None
    excluded: bool | None = None
    forced_tier: int | None = Field(default=None, ge=1, le=3)
