"""album entity foundation — first-class Album + catalog_albums link (L1).

No behaviour change elsewhere: the tables are created empty and only wired to
the catalog via a CASCADE M2M link; upsert/enrichment happens in L2."""

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"


def upgrade():
    op.create_table(
        "albums",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("normalized_title", sa.String(500), nullable=True),
        sa.Column("deezer_album_id", sa.String(64), nullable=True),
        sa.Column(
            "record_type",
            sa.Enum("album", "single", "ep", "compile", name="album_type"),
            nullable=True,
        ),
        sa.Column("release_date", sa.Date, nullable=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "artist_id",
            sa.Integer,
            sa.ForeignKey("artists.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "has_artwork", sa.Boolean, nullable=True, server_default=sa.text("false")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_albums_artist_id", "albums", ["artist_id"])
    # Partial unique index: one row per real Deezer album, NULL repeats freely.
    op.create_index(
        "uq_albums_deezer_id",
        "albums",
        ["deezer_album_id"],
        unique=True,
        postgresql_where=sa.text("deezer_album_id IS NOT NULL"),
    )

    op.create_table(
        "catalog_albums",
        sa.Column(
            "catalog_id",
            sa.Integer,
            sa.ForeignKey("catalog.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "album_id",
            sa.Integer,
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_catalog_albums_album_id", "catalog_albums", ["album_id"])


def downgrade():
    op.drop_index("ix_catalog_albums_album_id", table_name="catalog_albums")
    op.drop_table("catalog_albums")
    op.drop_index("uq_albums_deezer_id", table_name="albums")
    op.drop_index("ix_albums_artist_id", table_name="albums")
    op.drop_table("albums")
