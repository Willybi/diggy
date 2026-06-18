"""Drop lib_tracks table (legacy, replaced by user_tracks)."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("lib_tracks")


def downgrade():
    # Not reversible — lib_tracks data is gone
    pass
