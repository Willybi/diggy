"""Drop user_tracks.rating — the Rekordbox 0-5 star rating is removed from the
project (destructive: existing rating values are dropped)."""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"


def upgrade():
    op.execute("ALTER TABLE user_tracks DROP CONSTRAINT IF EXISTS ck_rating_range")
    op.drop_column("user_tracks", "rating")


def downgrade():
    op.add_column("user_tracks", sa.Column("rating", sa.Integer(), nullable=True))
    op.execute(
        "ALTER TABLE user_tracks "
        "ADD CONSTRAINT ck_rating_range CHECK (rating >= 0 AND rating <= 5 OR rating IS NULL)"
    )
