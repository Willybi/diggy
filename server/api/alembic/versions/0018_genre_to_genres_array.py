"""Convert catalog.genre (String) to catalog.genres (TEXT[] array)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0018"
down_revision = "0017"


def upgrade():
    op.add_column("catalog", sa.Column("genres", ARRAY(sa.Text), server_default="{}"))
    op.execute("UPDATE catalog SET genres = ARRAY[genre] WHERE genre IS NOT NULL AND genre != ''")
    op.drop_index("ix_catalog_genre", "catalog")
    op.drop_column("catalog", "genre")
    op.create_index("ix_catalog_genres", "catalog", ["genres"], postgresql_using="gin")


def downgrade():
    op.drop_index("ix_catalog_genres", "catalog")
    op.add_column("catalog", sa.Column("genre", sa.String(100), nullable=True))
    op.execute("UPDATE catalog SET genre = genres[1]")
    op.drop_column("catalog", "genres")
    op.create_index("ix_catalog_genre", "catalog", ["genre"])
