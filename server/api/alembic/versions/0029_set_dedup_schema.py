"""Add set dedup schema: parent/virtual columns, set_flags table, platform backfill."""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"


def upgrade():
    # 1. New columns on sets
    op.add_column(
        "sets",
        sa.Column(
            "parent_set_id",
            sa.Integer,
            sa.ForeignKey("sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sets_parent_set_id", "sets", ["parent_set_id"])
    op.add_column(
        "sets",
        sa.Column(
            "is_virtual",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column("sets", sa.Column("platform", sa.String(32), nullable=True))
    op.add_column(
        "sets", sa.Column("normalized_title", sa.String(500), nullable=True)
    )
    op.add_column("sets", sa.Column("part_number", sa.Integer, nullable=True))

    # 2. Index on set_tracks(trackid_music_track_id)
    op.create_index(
        "ix_set_tracks_trackid_music_track_id",
        "set_tracks",
        ["trackid_music_track_id"],
    )

    # 3. New table set_flags
    set_flag_type = sa.Enum(
        "duplicate_candidate",
        "part_candidate",
        "part_overlap_anomaly",
        name="set_flag_type",
    )
    set_flag_status = sa.Enum(
        "pending",
        "attached",
        "rejected",
        name="set_flag_status",
    )
    op.create_table(
        "set_flags",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "set_id_a",
            sa.Integer,
            sa.ForeignKey("sets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "set_id_b",
            sa.Integer,
            sa.ForeignKey("sets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("flag_type", set_flag_type, nullable=False),
        sa.Column(
            "confidence",
            sa.Float,
            nullable=True,
        ),
        sa.Column("signals", sa.JSON, nullable=True),
        sa.Column(
            "status",
            set_flag_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "resolved_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("set_id_a", "set_id_b", name="uq_set_flag_pair"),
    )

    # 4. Backfill platform from source_url
    op.execute(
        """
        UPDATE sets SET platform =
            CASE
                WHEN source_url ILIKE '%youtube.com%'    THEN 'youtube'
                WHEN source_url ILIKE '%soundcloud.com%' THEN 'soundcloud'
                WHEN source_url ILIKE '%mixcloud.com%'   THEN 'mixcloud'
                WHEN source_url ILIKE '%hearthis.at%'    THEN 'hearthis'
                ELSE NULL
            END
        WHERE source_url IS NOT NULL
        """
    )


def downgrade():
    # Reverse order
    op.drop_index("ix_set_tracks_trackid_music_track_id", table_name="set_tracks")
    op.drop_table("set_flags")
    sa.Enum(name="set_flag_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="set_flag_status").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_sets_parent_set_id", table_name="sets")
    op.drop_column("sets", "part_number")
    op.drop_column("sets", "normalized_title")
    op.drop_column("sets", "platform")
    op.drop_column("sets", "is_virtual")
    op.drop_column("sets", "parent_set_id")
