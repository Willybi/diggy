"""Add compound indexes on radar_tracks and user_opinions."""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade():
    op.create_index(
        "ix_radar_tracks_source_detected",
        "radar_tracks",
        ["source", sa.text("detected_at DESC")],
    )
    op.create_index(
        "ix_user_opinions_user_opinion",
        "user_opinions",
        ["user_id", "opinion"],
    )


def downgrade():
    op.drop_index("ix_user_opinions_user_opinion", table_name="user_opinions")
    op.drop_index("ix_radar_tracks_source_detected", table_name="radar_tracks")
