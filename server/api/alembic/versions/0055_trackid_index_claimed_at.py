"""trackid_index.claimed_at — local-hydration lease timestamp.

Replaces the earlier static-shard split between the VPS drain and the local
clean-hydration tool with a DYNAMIC reservation. The local tool
(``worker/trackid_hydrate``) atomically CLAIMS a batch of sets in ``--apply``
(``hydration_state='claimed'``, ``claimed_at=now()``, ``FOR UPDATE SKIP LOCKED``);
the drain selects only ``not_hydrated`` so it ignores a claimed set until the run
finalises it (``hydrated``) or the drain's reaper leases it back after
``TRACKID_CLAIM_LEASE_SECONDS`` — ``claimed_at`` backs that lease and auto-heals a
hard crash of the local tool.
"""

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"


def upgrade():
    op.add_column(
        "trackid_index",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("trackid_index", "claimed_at")
