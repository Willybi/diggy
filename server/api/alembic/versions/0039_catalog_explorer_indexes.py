"""Explorer query-builder (D6 p.1) — indexes on catalog filter/sort columns."""

from alembic import op

revision = "0039"
down_revision = "0038"


def upgrade():
    # Simple b-tree indexes backing the GET /catalog/ filters (bpm/key/duration/
    # year ranges) and sorts (created_at is the new default sort).
    op.create_index("ix_catalog_bpm", "catalog", ["bpm"])
    op.create_index("ix_catalog_key", "catalog", ["key"])
    op.create_index("ix_catalog_duration_ms", "catalog", ["duration_ms"])
    op.create_index("ix_catalog_release_date", "catalog", ["release_date"])
    op.create_index("ix_catalog_created_at", "catalog", ["created_at"])


def downgrade():
    op.drop_index("ix_catalog_created_at", table_name="catalog")
    op.drop_index("ix_catalog_release_date", table_name="catalog")
    op.drop_index("ix_catalog_duration_ms", table_name="catalog")
    op.drop_index("ix_catalog_key", table_name="catalog")
    op.drop_index("ix_catalog_bpm", table_name="catalog")
