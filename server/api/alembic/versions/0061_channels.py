"""channels — watched source channels for DJ-set discovery (C14.b).

Materialises the first-class channels we watch for DJ sets (YouTube for this
slice, 'soundcloud' later). One row per channel: ``platform`` + ``external_id``
(the platform-side channel id, NULL until resolved), display ``name``, an
application-level ``channel_type`` ('artist' | 'label' | 'organizer' | 'radio',
plain String), an optional ``artist_id`` link, the curation flags ``watched`` /
``excluded``, a JSON ``signals`` snapshot and the ``last_checked_at`` cadence
timestamp. Only the table lands in this lot (L1); the RSS watch wiring and admin
surface are later lots.

Unique ``(platform, external_id)`` guarantees one row per platform channel.
Partial index ``(platform, last_checked_at) WHERE watched IS TRUE`` backs the
per-platform "due" selection (only watched channels are ever polled).
"""

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"


def upgrade():
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=True),
        sa.Column("artist_id", sa.Integer(), nullable=True),
        sa.Column(
            "watched", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "excluded", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["artist_id"], ["artists.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform", "external_id", name="uq_channel_platform_external"
        ),
    )
    op.create_index(
        "ix_channels_due",
        "channels",
        ["platform", "last_checked_at"],
        postgresql_where=sa.text("watched IS TRUE"),
    )


def downgrade():
    op.drop_index("ix_channels_due", table_name="channels")
    op.drop_table("channels")
