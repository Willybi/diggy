"""collection_folders (C5 v2 L2) — a private folder level above collections
(folder > collection > items, one flat level, no nesting).

Creates ``collection_folders`` (per-user) and adds ``user_collections.folder_id``
(nullable, FK ON DELETE SET NULL — a collection survives its folder's deletion as
an orphan).
"""

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"


def upgrade():
    op.create_table(
        "collection_folders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_folders_user_id", "collection_folders", ["user_id"]
    )

    op.add_column(
        "user_collections", sa.Column("folder_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "user_collections_folder_id_fkey",
        "user_collections",
        "collection_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "user_collections_folder_id_fkey", "user_collections", type_="foreignkey"
    )
    op.drop_column("user_collections", "folder_id")
    op.drop_index(
        "ix_collection_folders_user_id", table_name="collection_folders"
    )
    op.drop_table("collection_folders")
