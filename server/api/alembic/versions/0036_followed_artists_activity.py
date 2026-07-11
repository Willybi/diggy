"""C6.c — artist follow: followed_artists + artist_activity tables."""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"


def upgrade():
    op.create_table(
        "followed_artists",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "artist_id",
            sa.Integer,
            sa.ForeignKey("artists.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
            index=True,
        ),
        sa.Column("followed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "artist_activity",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "artist_id",
            sa.Integer,
            sa.ForeignKey("artists.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Application values: 'release' | 'set' (plain String, no PG enum)
        sa.Column("activity_type", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        # Deezer album id, or Diggy set id as string
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("external_url", sa.Text, nullable=True),
        sa.Column(
            "catalog_id",
            sa.Integer,
            sa.ForeignKey("catalog.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "set_id",
            sa.Integer,
            sa.ForeignKey("sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
        sa.Column("payload", sa.JSON, nullable=True),
        # Idempotence guarantee for the activity worker
        sa.UniqueConstraint(
            "artist_id",
            "activity_type",
            "source",
            "external_id",
            name="uq_artist_activity_ext",
        ),
    )


def downgrade():
    op.drop_table("artist_activity")
    op.drop_table("followed_artists")
