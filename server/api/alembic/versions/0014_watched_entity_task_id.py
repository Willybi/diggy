"""Add current_task_id and crawl_started_at to watched_entities for crawl status tracking."""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"


def upgrade():
    op.add_column("watched_entities", sa.Column("current_task_id", sa.String(255), nullable=True))
    op.add_column("watched_entities", sa.Column("crawl_started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("watched_entities", "crawl_started_at")
    op.drop_column("watched_entities", "current_task_id")
