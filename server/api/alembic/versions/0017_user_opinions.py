"""Add user_opinions table for like/dislike on all entities."""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade():
    op.create_table(
        "user_opinions",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(20), primary_key=True, nullable=False),
        sa.Column("entity_key", sa.String(255), primary_key=True, nullable=False),
        sa.Column("opinion", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("user_opinions")
