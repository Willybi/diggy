"""AU3 — schema purge: drop watched_playlists, dead catalog columns, add FK indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"


def upgrade():
    # A2-01: orphan table (renamed to watched_entities in 0006, absent from models)
    op.execute("DROP TABLE IF EXISTS watched_playlists")

    # A2-06: dead column; PG drops the dependent unique index automatically
    op.drop_column("catalog", "fingerprint")

    # A2-07: dead column — live previews go through GET /catalog/{id}/preview-url
    op.drop_column("catalog", "preview_url")

    # A2-09: DB-side default; existing NULL rows are kept as-is
    op.alter_column("user_tracks", "created_at", server_default=sa.text("now()"))

    # A2-11: missing FK indexes
    op.create_index("ix_user_tracks_catalog_id", "user_tracks", ["catalog_id"])
    op.create_index("ix_user_follows_entity_id", "user_follows", ["entity_id"])


def downgrade():
    # watched_playlists is not recreated (stale data, irreversible drop)
    op.drop_index("ix_user_follows_entity_id", table_name="user_follows")
    op.drop_index("ix_user_tracks_catalog_id", table_name="user_tracks")
    op.alter_column("user_tracks", "created_at", server_default=None)
    op.add_column("catalog", sa.Column("preview_url", sa.Text, nullable=True))
    op.add_column(
        "catalog", sa.Column("fingerprint", sa.String, nullable=True, unique=True)
    )
