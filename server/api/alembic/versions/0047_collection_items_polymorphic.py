"""collection_items polymorphic items (C5 v2) — a collection can hold any entity
(track/set/artist/genre/playlist), not just tracks.

Migrates the tracks-only table (composite PK collection_id+catalog_id, native FK
to catalog.id) to a polymorphic shape (surrogate PK id, item_type/item_id/
item_name, no native FK — application-level integrity). Every existing row is a
track, so it is backfilled item_type='track', item_id=catalog_id, item_name NULL.
No row is lost on upgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"


def upgrade():
    # 1. New polymorphic columns (nullable while we backfill).
    op.add_column(
        "collection_items", sa.Column("item_type", sa.String(20), nullable=True)
    )
    op.add_column("collection_items", sa.Column("item_id", sa.Integer(), nullable=True))
    op.add_column(
        "collection_items", sa.Column("item_name", sa.String(255), nullable=True)
    )

    # 2. Backfill: every pre-existing row is a track pointing at catalog_id.
    op.execute(
        "UPDATE collection_items SET item_type = 'track', item_id = catalog_id"
    )
    op.alter_column("collection_items", "item_type", nullable=False)

    # 3. Drop the composite PK + the native catalog FK, then the old column.
    op.drop_constraint(
        "collection_items_pkey", "collection_items", type_="primary"
    )
    op.drop_constraint(
        "collection_items_catalog_id_fkey", "collection_items", type_="foreignkey"
    )
    op.drop_column("collection_items", "catalog_id")

    # 4. Surrogate PK. Adding an IDENTITY column backfills existing rows with
    #    generated values, so the new PK is populated without a manual pass.
    op.add_column(
        "collection_items",
        sa.Column(
            "id", sa.Integer(), sa.Identity(always=False), nullable=False
        ),
    )
    op.create_primary_key("collection_items_pkey", "collection_items", ["id"])

    # 5. Index backing the per-collection listing/dedup lookups (was served by
    #    the old composite PK's leading column).
    op.create_index(
        "ix_collection_items_collection_id", "collection_items", ["collection_id"]
    )


def downgrade():
    op.drop_index("ix_collection_items_collection_id", table_name="collection_items")
    op.drop_constraint(
        "collection_items_pkey", "collection_items", type_="primary"
    )
    op.drop_column("collection_items", "id")

    # The old schema is tracks-only with a NOT NULL catalog_id: non-track items
    # cannot survive a downgrade — drop them before reconstituting the column.
    op.execute("DELETE FROM collection_items WHERE item_type <> 'track'")
    op.add_column(
        "collection_items", sa.Column("catalog_id", sa.Integer(), nullable=True)
    )
    op.execute("UPDATE collection_items SET catalog_id = item_id")
    op.alter_column("collection_items", "catalog_id", nullable=False)
    op.create_foreign_key(
        "collection_items_catalog_id_fkey",
        "collection_items",
        "catalog",
        ["catalog_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key(
        "collection_items_pkey", "collection_items", ["collection_id", "catalog_id"]
    )

    op.drop_column("collection_items", "item_name")
    op.drop_column("collection_items", "item_id")
    op.drop_column("collection_items", "item_type")
