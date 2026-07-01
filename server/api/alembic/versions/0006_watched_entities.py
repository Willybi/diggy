"""watched_playlists → watched_entities + user_follows

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # --- Partie A : renommer watched_playlists → watched_entities ---
    if "watched_playlists" in tables and "watched_entities" not in tables:
        op.rename_table("watched_playlists", "watched_entities")

    # Ajouter colonne type si absente
    watched_cols = {c["name"] for c in insp.get_columns("watched_entities") if "watched_entities" in tables or "watched_playlists" not in tables}
    if "type" not in watched_cols:
        op.add_column(
            "watched_entities",
            sa.Column("type", sa.String(20), nullable=False, server_default="playlist"),
        )

    # --- Partie B : renommer watched_playlist_id → watched_entity_id dans radar_tracks ---
    radar_cols = {c["name"] for c in insp.get_columns("radar_tracks")}
    if "watched_playlist_id" in radar_cols and "watched_entity_id" not in radar_cols:
        op.alter_column("radar_tracks", "watched_playlist_id", new_column_name="watched_entity_id")

    # --- Partie C : créer user_follows ---
    if "user_follows" not in tables:
        op.create_table(
            "user_follows",
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("entity_id", sa.Integer, sa.ForeignKey("watched_entities.id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("followed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_user_follows_entity", "user_follows", ["entity_id"])

        # Seed : toutes les entités existantes sont suivies par user 1
        op.execute("""
            INSERT INTO user_follows (user_id, entity_id)
            SELECT 1, id FROM watched_entities
            ON CONFLICT (user_id, entity_id) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("user_follows")

    conn = op.get_bind()
    insp = sa.inspect(conn)
    radar_cols = {c["name"] for c in insp.get_columns("radar_tracks")}
    if "watched_entity_id" in radar_cols:
        op.alter_column("radar_tracks", "watched_entity_id", new_column_name="watched_playlist_id")

    op.drop_column("watched_entities", "type")
    op.rename_table("watched_entities", "watched_playlists")
