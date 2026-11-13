"""hidden_reason — reversible masking of undesirable catalog rows and artists.

An audit (docs/audits/2026-11/donnees-indesirables.md, section 9) found
undesirable tracks and artists (AI farms, fake artists, functional music). The
decision is to MASK them reversibly, never to delete them. This migration lays
the columns only:

- ``catalog.hidden_reason`` / ``artists.hidden_reason`` (String(50), nullable):
  NULL = visible; otherwise the id of the rule that hid the row (``farm_fort``,
  ``isrc_block``, ...), so a single rule can be reverted on its own.
- ``catalog.hidden_at`` / ``artists.hidden_at`` (timestamptz, nullable): when.

No index: the predicate ``hidden_reason IS NULL`` is not selective (the vast
majority of rows stay visible), it is filtered inline by catalog_visible.
"""

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"


def upgrade():
    op.add_column(
        "catalog", sa.Column("hidden_reason", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "catalog", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "artists", sa.Column("hidden_reason", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "artists", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("artists", "hidden_at")
    op.drop_column("artists", "hidden_reason")
    op.drop_column("catalog", "hidden_at")
    op.drop_column("catalog", "hidden_reason")
