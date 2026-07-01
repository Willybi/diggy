"""Add radar_trends, user_collections, collection_items tables (Phase 5)."""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade():
    # radar_trends
    op.create_table(
        "radar_trends",
        sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("trend_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("window_days", sa.Integer, server_default="30"),
        sa.Column("detection_count", sa.Integer, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # user_collections
    op.create_table(
        "user_collections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), server_default="playlist"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_collections_user", "user_collections", ["user_id"])

    # collection_items
    op.create_table(
        "collection_items",
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("user_collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, server_default="0"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("collection_id", "catalog_id"),
    )


def downgrade():
    op.drop_table("collection_items")
    op.drop_index("ix_user_collections_user", table_name="user_collections")
    op.drop_table("user_collections")
    op.drop_table("radar_trends")
