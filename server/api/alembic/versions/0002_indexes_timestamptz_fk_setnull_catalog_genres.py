"""Add indexes on genre_id, convert timestamps to TIMESTAMPTZ, FK SET NULL, catalog_genres table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # =====================================================================
    # 1. Indexes on genre_id in association tables (idempotent)
    # =====================================================================
    sg_indexes = [idx["name"] for idx in insp.get_indexes("set_genres")]
    if "ix_set_genres_genre_id" not in sg_indexes:
        op.create_index("ix_set_genres_genre_id", "set_genres", ["genre_id"])

    ag_indexes = [idx["name"] for idx in insp.get_indexes("artist_genres")]
    if "ix_artist_genres_genre_id" not in ag_indexes:
        op.create_index("ix_artist_genres_genre_id", "artist_genres", ["genre_id"])

    # =====================================================================
    # 2. Convert all timestamp columns to TIMESTAMPTZ
    # =====================================================================
    # Tables with data — use AT TIME ZONE 'UTC' to preserve values
    op.execute("ALTER TABLE catalog ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE lib_tracks ALTER COLUMN date_added TYPE TIMESTAMPTZ USING date_added AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE radar_tracks ALTER COLUMN detected_at TYPE TIMESTAMPTZ USING detected_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE watched_playlists ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE watched_playlists ALTER COLUMN last_crawled_at TYPE TIMESTAMPTZ USING last_crawled_at AT TIME ZONE 'UTC'")

    # New tables (empty) — simple type change
    op.execute("ALTER TABLE genres ALTER COLUMN created_at TYPE TIMESTAMPTZ")
    op.execute("ALTER TABLE artists ALTER COLUMN created_at TYPE TIMESTAMPTZ")
    op.execute("ALTER TABLE sets ALTER COLUMN created_at TYPE TIMESTAMPTZ")
    op.execute("ALTER TABLE sets ALTER COLUMN last_crawled_at TYPE TIMESTAMPTZ")

    # =====================================================================
    # 3. FK catalog_id -> ON DELETE SET NULL (drop + recreate)
    # =====================================================================
    # lib_tracks
    op.drop_constraint("lib_tracks_catalog_id_fkey", "lib_tracks", type_="foreignkey")
    op.create_foreign_key("lib_tracks_catalog_id_fkey", "lib_tracks", "catalog", ["catalog_id"], ["id"], ondelete="SET NULL")

    # radar_tracks
    op.drop_constraint("radar_tracks_catalog_id_fkey", "radar_tracks", type_="foreignkey")
    op.create_foreign_key("radar_tracks_catalog_id_fkey", "radar_tracks", "catalog", ["catalog_id"], ["id"], ondelete="SET NULL")

    # set_tracks
    op.drop_constraint("set_tracks_catalog_id_fkey", "set_tracks", type_="foreignkey")
    op.create_foreign_key("set_tracks_catalog_id_fkey", "set_tracks", "catalog", ["catalog_id"], ["id"], ondelete="SET NULL")

    # genres.parent_id -> ON DELETE SET NULL
    op.drop_constraint("genres_parent_id_fkey", "genres", type_="foreignkey")
    op.create_foreign_key("genres_parent_id_fkey", "genres", "genres", ["parent_id"], ["id"], ondelete="SET NULL")

    # =====================================================================
    # 4. Create catalog_genres association table (idempotent)
    # =====================================================================
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "catalog_genres" not in inspector.get_table_names():
        op.create_table(
            "catalog_genres",
            sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
        )

    existing_indexes = [idx["name"] for idx in inspector.get_indexes("catalog_genres")]
    if "ix_catalog_genres_genre_id" not in existing_indexes:
        op.create_index("ix_catalog_genres_genre_id", "catalog_genres", ["genre_id"])


def downgrade() -> None:
    # 4. Drop catalog_genres
    op.drop_index("ix_catalog_genres_genre_id", "catalog_genres")
    op.drop_table("catalog_genres")

    # 3. Revert FK to NO ACTION
    op.drop_constraint("genres_parent_id_fkey", "genres", type_="foreignkey")
    op.create_foreign_key("genres_parent_id_fkey", "genres", "genres", ["parent_id"], ["id"])

    op.drop_constraint("set_tracks_catalog_id_fkey", "set_tracks", type_="foreignkey")
    op.create_foreign_key("set_tracks_catalog_id_fkey", "set_tracks", "catalog", ["catalog_id"], ["id"])

    op.drop_constraint("radar_tracks_catalog_id_fkey", "radar_tracks", type_="foreignkey")
    op.create_foreign_key("radar_tracks_catalog_id_fkey", "radar_tracks", "catalog", ["catalog_id"], ["id"])

    op.drop_constraint("lib_tracks_catalog_id_fkey", "lib_tracks", type_="foreignkey")
    op.create_foreign_key("lib_tracks_catalog_id_fkey", "lib_tracks", "catalog", ["catalog_id"], ["id"])

    # 2. Revert TIMESTAMPTZ to TIMESTAMP
    op.execute("ALTER TABLE sets ALTER COLUMN last_crawled_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE sets ALTER COLUMN created_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE artists ALTER COLUMN created_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE genres ALTER COLUMN created_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE watched_playlists ALTER COLUMN last_crawled_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE watched_playlists ALTER COLUMN created_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE radar_tracks ALTER COLUMN detected_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE lib_tracks ALTER COLUMN date_added TYPE TIMESTAMP")
    op.execute("ALTER TABLE catalog ALTER COLUMN created_at TYPE TIMESTAMP")

    # 1. Drop indexes
    op.drop_index("ix_artist_genres_genre_id", "artist_genres")
    op.drop_index("ix_set_genres_genre_id", "set_genres")
