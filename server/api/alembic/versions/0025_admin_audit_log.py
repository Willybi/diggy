"""Add admin_audit_log table for tracking destructive admin actions."""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade():
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.Integer, nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_audit_log_user_id", "admin_audit_log", ["user_id"])
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])


def downgrade():
    op.drop_table("admin_audit_log")
