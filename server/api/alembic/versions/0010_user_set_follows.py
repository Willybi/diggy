"""Add user_set_follows table for set follow/bookmark feature."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_set_follows",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("set_id", sa.Integer, sa.ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("followed_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("user_set_follows")
