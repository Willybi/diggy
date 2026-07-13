"""Backlog loop-safe — artists.deezer_search_attempts (mirror of catalog E1)."""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade():
    # Mirror of catalog.deezer_search_attempts (0033). server_default is
    # mandatory: the ~29 670 existing rows must receive a value for the NOT NULL
    # column. PostgreSQL only (no batch_alter_table, same as 0033).
    op.add_column(
        "artists",
        sa.Column(
            "deezer_search_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # Artists already Deezer-searched before this migration count as one attempt,
    # so they enter the 30-day retry tier instead of being orphaned (an
    # attempts=0 row with a non-NULL searched_at matches no re-scan tier).
    op.execute(
        "UPDATE artists SET deezer_search_attempts = 1 "
        "WHERE deezer_searched_at IS NOT NULL"
    )

    # Partial index backing the link-candidate tier queries. postgresql_where
    # ONLY (real precedent: ix_catalog_deezer_searched_at, 0033) — no sqlite_where.
    op.create_index(
        "ix_artists_deezer_searched_at",
        "artists",
        ["deezer_searched_at"],
        postgresql_where=sa.text("deezer_id IS NULL"),
    )


def downgrade():
    op.drop_index("ix_artists_deezer_searched_at", table_name="artists")
    op.drop_column("artists", "deezer_search_attempts")
