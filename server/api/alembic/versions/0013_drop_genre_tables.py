"""Drop genre tables (genres, catalog_genres, artist_genres, set_genres) and add index on catalog.genre."""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade():
    op.drop_table("catalog_genres")
    op.drop_table("artist_genres")
    op.drop_table("set_genres")
    op.drop_table("genres")
    op.create_index("ix_catalog_genre", "catalog", ["genre"])


def downgrade():
    op.drop_index("ix_catalog_genre", "catalog")
    op.create_table(
        "genres",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "catalog_genres",
        sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "artist_genres",
        sa.Column("artist_id", sa.Integer, sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "set_genres",
        sa.Column("set_id", sa.Integer, sa.ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    )
