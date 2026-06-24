"""Replace password auth with Google OAuth: add google_id, avatar_url, drop hashed_password."""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"


def upgrade():
    op.add_column("users", sa.Column("google_id", sa.String(255), unique=True, nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.Text, nullable=True))
    op.drop_column("users", "hashed_password")


def downgrade():
    op.add_column("users", sa.Column("hashed_password", sa.Text, nullable=True))
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "google_id")
