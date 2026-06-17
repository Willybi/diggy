"""Add users table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "users" not in insp.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(255), unique=True, nullable=False),
            sa.Column("username", sa.String(100), unique=True, nullable=False),
            sa.Column("hashed_password", sa.Text, nullable=False),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("settings", JSONB, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("users")
