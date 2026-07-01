"""admin role + artist_flags table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # --- is_admin on users ---
    user_cols = [c["name"] for c in insp.get_columns("users")]
    if "is_admin" not in user_cols:
        op.add_column(
            "users",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        )

    # --- artist_flags table ---
    existing_tables = insp.get_table_names()
    if "artist_flags" not in existing_tables:
        op.create_table(
            "artist_flags",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("raw_artist_string", sa.String(500), nullable=False, unique=True),
            sa.Column("reason", sa.String(64), nullable=False),
            sa.Column("tokens", sa.JSON(), nullable=False),
            sa.Column("deezer_ids", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("resolved_artist_ids", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("artist_flags")
    op.drop_column("users", "is_admin")
