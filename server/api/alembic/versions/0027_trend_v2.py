"""Enrich radar_trends with family, ranks, velocity, source_count."""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"


def upgrade():
    op.add_column("radar_trends", sa.Column("family", sa.String(50), nullable=True))
    op.add_column("radar_trends", sa.Column("rank_in_family", sa.Integer, nullable=True))
    op.add_column("radar_trends", sa.Column("rank_global", sa.Integer, nullable=True))
    op.add_column("radar_trends", sa.Column("velocity", sa.Float, nullable=True))
    op.add_column("radar_trends", sa.Column("source_count", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("radar_trends", "source_count")
    op.drop_column("radar_trends", "velocity")
    op.drop_column("radar_trends", "rank_global")
    op.drop_column("radar_trends", "rank_in_family")
    op.drop_column("radar_trends", "family")
