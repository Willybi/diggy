"""enrich_priority — catalog enrichment-priority scalar (C12).

Adds ``catalog.enrich_priority`` (SmallInteger, nullable): a priority scalar so
the enrichment/backfill drains process the most relevant rows first. LARGER
value = enriched first; NULL = not stamped. Plus a partial index on the stamped
rows only, mirroring ``ix_catalog_deezer_searched_at``. No logic reads the
column yet (the gate/stamping lands in later C12 lots).
"""

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"


def upgrade():
    op.add_column(
        "catalog",
        sa.Column("enrich_priority", sa.SmallInteger, nullable=True),
    )
    op.create_index(
        "ix_catalog_enrich_priority",
        "catalog",
        ["enrich_priority"],
        postgresql_where=sa.text("enrich_priority IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_catalog_enrich_priority", table_name="catalog")
    op.drop_column("catalog", "enrich_priority")
