"""Add beatport_id column to catalog."""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"

def upgrade():
    op.add_column("catalog", sa.Column("beatport_id", sa.String(64), nullable=True))

def downgrade():
    op.drop_column("catalog", "beatport_id")
