"""C6.1 — set parts detection: part_total on sets, group flag columns on set_flags."""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"


def upgrade():
    # 1. sets.part_total
    op.add_column("sets", sa.Column("part_total", sa.Integer, nullable=True))

    # 2. set_flags: make set_id_b nullable
    op.alter_column("set_flags", "set_id_b", nullable=True)

    # 3. set_flags: group_key + member_set_ids
    op.add_column(
        "set_flags",
        sa.Column("group_key", sa.String(500), nullable=True),
    )
    op.create_index("ix_set_flags_group_key", "set_flags", ["group_key"])
    op.add_column(
        "set_flags",
        sa.Column("member_set_ids", sa.JSON, nullable=True),
    )

    # 4. Partial unique index: one pending/attached flag per group_key
    op.execute(
        "CREATE UNIQUE INDEX uq_set_flag_group_key "
        "ON set_flags(group_key) WHERE group_key IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_set_flag_group_key")
    op.drop_index("ix_set_flags_group_key", table_name="set_flags")
    op.drop_column("set_flags", "member_set_ids")
    op.drop_column("set_flags", "group_key")
    op.alter_column("set_flags", "set_id_b", nullable=False)
    op.drop_column("sets", "part_total")
