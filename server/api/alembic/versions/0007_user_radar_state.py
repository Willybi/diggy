"""user_radar_state — per-user radar track status

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if "user_radar_state" not in tables:
        op.create_table(
            "user_radar_state",
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="new"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_user_radar_state_status", "user_radar_state", ["user_id", "status"])

        # Seed: all existing radar catalog_ids → status='new' for user 1
        op.execute("""
            INSERT INTO user_radar_state (user_id, catalog_id, status)
            SELECT DISTINCT 1, catalog_id, 'new'
            FROM radar_tracks
            WHERE catalog_id IS NOT NULL
            ON CONFLICT (user_id, catalog_id) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("user_radar_state")
