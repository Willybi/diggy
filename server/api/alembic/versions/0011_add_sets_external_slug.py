"""Add external_slug column to sets for TrackID re-crawl."""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"

def upgrade():
    op.add_column("sets", sa.Column("external_slug", sa.String(500), nullable=True))

def downgrade():
    op.drop_column("sets", "external_slug")
