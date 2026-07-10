"""E1 — re-scan enrichment: attempt counters + partial indexes on searched_at."""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"


def upgrade():
    op.add_column(
        "catalog",
        sa.Column(
            "deezer_search_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "catalog",
        sa.Column(
            "beatport_search_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # Rows already searched before E1 count as one attempt
    op.execute(
        "UPDATE catalog SET deezer_search_attempts = 1 "
        "WHERE deezer_searched_at IS NOT NULL"
    )
    op.execute(
        "UPDATE catalog SET beatport_search_attempts = 1 "
        "WHERE beatport_searched_at IS NOT NULL"
    )

    op.create_index(
        "ix_catalog_deezer_searched_at",
        "catalog",
        ["deezer_searched_at"],
        postgresql_where=sa.text("deezer_id IS NULL"),
    )
    op.create_index(
        "ix_catalog_beatport_searched_at",
        "catalog",
        ["beatport_searched_at"],
        postgresql_where=sa.text("beatport_id IS NULL"),
    )


def downgrade():
    op.drop_index("ix_catalog_beatport_searched_at", table_name="catalog")
    op.drop_index("ix_catalog_deezer_searched_at", table_name="catalog")
    op.drop_column("catalog", "beatport_search_attempts")
    op.drop_column("catalog", "deezer_search_attempts")
