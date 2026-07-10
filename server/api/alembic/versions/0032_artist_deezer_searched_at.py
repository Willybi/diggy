"""AU4 — artists.deezer_searched_at: remember Deezer searches to stop infinite re-searches (A3-12)."""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"


def upgrade():
    # Same pattern as catalog.deezer_searched_at: NULL = never searched.
    # The NOT_FOUND sentinel on deezer_id stays a human-only decision.
    op.add_column(
        "artists",
        sa.Column("deezer_searched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("artists", "deezer_searched_at")
