"""Catalog scope + user_tracks + migration lib_tracks

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    catalog_cols = {c["name"] for c in insp.get_columns("catalog")}

    # --- Partie A : enrichir catalog ---

    if "scope" not in catalog_cols:
        op.add_column("catalog", sa.Column("scope", sa.String(10), nullable=False, server_default="shared"))
    if "owner_id" not in catalog_cols:
        op.add_column("catalog", sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    if "origin" not in catalog_cols:
        op.add_column("catalog", sa.Column("origin", sa.String(50), nullable=False, server_default="deezer"))
    if "status" not in catalog_cols:
        op.add_column("catalog", sa.Column("status", sa.String(20), nullable=False, server_default="official"))
    if "bpm_source" not in catalog_cols:
        op.add_column("catalog", sa.Column("bpm_source", sa.String(20), nullable=True))
    if "key_source" not in catalog_cols:
        op.add_column("catalog", sa.Column("key_source", sa.String(20), nullable=True))
    if "label" not in catalog_cols:
        op.add_column("catalog", sa.Column("label", sa.String(255), nullable=True))
    if "fingerprint" not in catalog_cols:
        op.add_column("catalog", sa.Column("fingerprint", sa.String, nullable=True, unique=True))
    if "needs_reconciliation" not in catalog_cols:
        op.add_column("catalog", sa.Column("needs_reconciliation", sa.Boolean, server_default="false", nullable=True))

    existing_indexes = {idx["name"] for idx in insp.get_indexes("catalog")}
    if "ix_catalog_scope" not in existing_indexes:
        op.create_index("ix_catalog_scope", "catalog", ["scope"])
    if "ix_catalog_owner" not in existing_indexes:
        # Index partiel PostgreSQL uniquement (SQLite ignores unsupported clauses)
        try:
            op.create_index("ix_catalog_owner", "catalog", ["owner_id"], postgresql_where=sa.text("owner_id IS NOT NULL"))
        except Exception:
            op.create_index("ix_catalog_owner", "catalog", ["owner_id"])

    # --- Partie B : créer user_tracks ---

    tables = insp.get_table_names()
    if "user_tracks" not in tables:
        op.create_table(
            "user_tracks",
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False),
            sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="RESTRICT"), primary_key=True, nullable=False),
            sa.Column("rekordbox_id", sa.Integer, nullable=True),
            sa.Column("date_added", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source", sa.String(50), server_default="rekordbox_import", nullable=True),
            sa.Column("file_path", sa.Text, nullable=True),
            sa.Column("rb_bpm", sa.Float, nullable=True),
            sa.Column("rb_key", sa.String(10), nullable=True),
            sa.Column("rb_mytags", sa.JSON, server_default="[]", nullable=True),
            sa.Column("rating", sa.Integer, nullable=True),
            sa.Column("has_artwork", sa.Boolean, server_default="false", nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_user_tracks_catalog", "user_tracks", ["catalog_id"])
        op.create_index("ix_user_tracks_user_added", "user_tracks", ["user_id", "date_added"])

    # --- Partie C : migration des données lib_tracks → user_tracks ---

    # Uniquement si lib_tracks existe et user_tracks est vide
    if "lib_tracks" in tables:
        op.execute("""
            INSERT INTO user_tracks (
                user_id, catalog_id, rekordbox_id, date_added, source,
                file_path, rb_bpm, rb_key, rb_mytags, rating, has_artwork
            )
            SELECT
                1,
                catalog_id,
                id,
                date_added,
                'rekordbox_import',
                file_path,
                bpm,
                key,
                CASE
                    WHEN tags IS NULL OR tags = '' THEN '[]'::json
                    ELSE tags::json
                END,
                rating,
                has_artwork
            FROM lib_tracks
            WHERE catalog_id IS NOT NULL
            ON CONFLICT (user_id, catalog_id) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("user_tracks")

    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in insp.get_indexes("catalog")}
    if "ix_catalog_owner" in existing_indexes:
        op.drop_index("ix_catalog_owner", table_name="catalog")
    if "ix_catalog_scope" in existing_indexes:
        op.drop_index("ix_catalog_scope", table_name="catalog")

    for col in ["scope", "owner_id", "origin", "status", "bpm_source", "key_source", "label", "fingerprint", "needs_reconciliation"]:
        op.drop_column("catalog", col)
