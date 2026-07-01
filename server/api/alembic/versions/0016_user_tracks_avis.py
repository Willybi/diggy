"""Add avis column to user_tracks."""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade():
    op.add_column("user_tracks", sa.Column("avis", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("user_tracks", "avis")
