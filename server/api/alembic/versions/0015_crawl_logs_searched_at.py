"""Add crawl_logs table and searched_at columns to catalog."""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"


def upgrade():
    # CrawlLog table
    op.create_table(
        "crawl_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("task_type", sa.String(64), nullable=False, index=True),
        sa.Column("target_id", sa.Integer, nullable=True),
        sa.Column("target_label", sa.String(500), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("stats", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
    )

    # Searched_at columns on catalog for skip-re-enrichment
    op.add_column("catalog", sa.Column("deezer_searched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("catalog", sa.Column("beatport_searched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("catalog", "beatport_searched_at")
    op.drop_column("catalog", "deezer_searched_at")
    op.drop_table("crawl_logs")
