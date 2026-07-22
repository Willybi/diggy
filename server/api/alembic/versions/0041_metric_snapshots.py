"""Add metric_snapshots table — hourly time-series of enrichment/crawl backlog
sizes (the throughput/error/duration history already lives in crawl_logs)."""
import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"


def upgrade():
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
    )
    op.create_index(
        "ix_metric_snapshots_captured_at", "metric_snapshots", ["captured_at"]
    )


def downgrade():
    op.drop_index("ix_metric_snapshots_captured_at", table_name="metric_snapshots")
    op.drop_table("metric_snapshots")
