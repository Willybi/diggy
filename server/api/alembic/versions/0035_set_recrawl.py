"""C6.b — set re-crawl state: completion tracking + age-tiered backoff columns."""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade():
    # is_id-based identification ratio (catalog_id is reset by re-imports,
    # so it cannot back a stable completion metric)
    op.add_column("sets", sa.Column("completion_pct", sa.Float, nullable=True))
    op.add_column(
        "sets",
        sa.Column("last_recrawl_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Consecutive re-crawls WITHOUT progression; reset to 0 whenever
    # completion_pct improves, 3 stale runs finalize the set
    op.add_column(
        "sets",
        sa.Column("recrawl_count", sa.Integer, nullable=False, server_default="0"),
    )
    # Application values: 'active' | 'final' (plain String like sets.platform,
    # no PostgreSQL enum)
    op.add_column(
        "sets",
        sa.Column(
            "recrawl_status", sa.String(16), nullable=False, server_default="active"
        ),
    )


def downgrade():
    op.drop_column("sets", "recrawl_status")
    op.drop_column("sets", "recrawl_count")
    op.drop_column("sets", "last_recrawl_at")
    op.drop_column("sets", "completion_pct")
