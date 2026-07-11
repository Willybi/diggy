"""C6.e — adaptive playlist crawl: watched_entities.last_changed_at."""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"


def upgrade():
    # Stamped only when a crawl actually inserts or removes a track; drives the
    # adaptive crawl cadence. NULL is the fallback state (crawl_radar falls back
    # to created_at), so no backfill is needed.
    op.add_column(
        "watched_entities",
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("watched_entities", "last_changed_at")
