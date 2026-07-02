"""Add removed_at and is_initial_detection columns to radar_tracks."""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"


def upgrade():
    op.add_column(
        "radar_tracks",
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "radar_tracks",
        sa.Column(
            "is_initial_detection",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("radar_tracks", "is_initial_detection")
    op.drop_column("radar_tracks", "removed_at")
