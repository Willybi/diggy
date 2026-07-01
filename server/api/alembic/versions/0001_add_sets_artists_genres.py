"""Add sets, artists, genres tables + watched_playlists columns

Revision ID: 0001
Revises: None
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    # --- New tables (idempotent: skip if create_all already ran) ---

    if "genres" not in existing:
        op.create_table(
            "genres",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(100), unique=True, nullable=False),
            sa.Column("parent_id", sa.Integer, sa.ForeignKey("genres.id"), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=True),
        )

    if "artists" not in existing:
        op.create_table(
            "artists",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(500), nullable=False),
            sa.Column("normalized_name", sa.String(500), unique=True, nullable=False),
            sa.Column("real_name", sa.String(255), nullable=True),
            sa.Column("country", sa.String(2), nullable=True),
            sa.Column("deezer_id", sa.String(64), nullable=True),
            sa.Column("soundcloud_id", sa.String(64), nullable=True),
            sa.Column("trackid_id", sa.String(64), nullable=True),
            sa.Column("bio", sa.Text, nullable=True),
            sa.Column("has_artwork", sa.Boolean, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime, nullable=True),
        )

    if "artist_aliases" not in existing:
        op.create_table(
            "artist_aliases",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("artist_id", sa.Integer, sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("alias", sa.String(500), nullable=False),
            sa.Column("normalized_alias", sa.String(500), unique=True, nullable=False),
        )

    if "sets" not in existing:
        op.create_table(
            "sets",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("external_id", sa.String(64), nullable=True),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("source_url", sa.Text, nullable=True),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("event", sa.String(255), nullable=True),
            sa.Column("venue", sa.String(255), nullable=True),
            sa.Column("played_date", sa.Date, nullable=True),
            sa.Column("duration_ms", sa.Integer, nullable=True),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("has_artwork", sa.Boolean, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("last_crawled_at", sa.DateTime, nullable=True),
            sa.UniqueConstraint("external_id", "source", name="uq_set_external_source"),
        )

    if "set_artists" not in existing:
        op.create_table(
            "set_artists",
            sa.Column("set_id", sa.Integer, sa.ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("artist_id", sa.Integer, sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True, index=True),
            sa.Column("role", sa.String(32), nullable=True),
            sa.Column("position", sa.Integer, nullable=True),
        )

    if "set_tracks" not in existing:
        op.create_table(
            "set_tracks",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("set_id", sa.Integer, sa.ForeignKey("sets.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id"), nullable=True, index=True),
            sa.Column("position", sa.Integer, nullable=False),
            sa.Column("timecode_ms", sa.Integer, nullable=True),
            sa.Column("raw_title", sa.String(500), nullable=True),
            sa.Column("raw_artist", sa.String(500), nullable=True),
            sa.Column("is_id", sa.Boolean, server_default=sa.text("false")),
            sa.UniqueConstraint("set_id", "position", name="uq_set_track_position"),
        )

    if "set_genres" not in existing:
        op.create_table(
            "set_genres",
            sa.Column("set_id", sa.Integer, sa.ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
        )

    if "artist_genres" not in existing:
        op.create_table(
            "artist_genres",
            sa.Column("artist_id", sa.Integer, sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
        )

    # --- ALTER watched_playlists: add 3 columns ---

    wp_cols = [c["name"] for c in inspector.get_columns("watched_playlists")]

    if "has_artwork" not in wp_cols:
        op.add_column("watched_playlists", sa.Column("has_artwork", sa.Boolean, server_default=sa.text("false")))

    if "track_count" not in wp_cols:
        op.add_column("watched_playlists", sa.Column("track_count", sa.Integer, nullable=True))

    if "owner" not in wp_cols:
        op.add_column("watched_playlists", sa.Column("owner", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("watched_playlists", "owner")
    op.drop_column("watched_playlists", "track_count")
    op.drop_column("watched_playlists", "has_artwork")
    op.drop_table("artist_genres")
    op.drop_table("set_genres")
    op.drop_table("set_tracks")
    op.drop_table("set_artists")
    op.drop_table("sets")
    op.drop_table("artist_aliases")
    op.drop_table("artists")
    op.drop_table("genres")
