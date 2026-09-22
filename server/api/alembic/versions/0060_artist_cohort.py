"""artist_cohort — derived artist watch cohort for the Deezer release watch (C14.a).

Materialises the cohort of artists worth watching for new Deezer releases. One
row per member artist, recomputed periodically by
``workers.tasks.recompute_artist_cohort`` (auto-promotion / rétrogradation from
signals already in the DB, without ever overwriting an admin override). Carries
the effective ``tier``, the ``computed_tier`` (before override), the admin
overrides (``pinned`` / ``excluded`` / ``forced_tier``), a JSON snapshot of the
last recompute's signals and the cadence timestamps. Only the table + recompute
land in this lot (L1); the release-watch wiring and admin surface are later lots.

Partial index ``(tier, last_checked_at) WHERE excluded IS NOT TRUE`` backs the
per-tier "due" selection (excluded rows are never watched).
"""

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"


def upgrade():
    op.create_table(
        "artist_cohort",
        sa.Column("artist_id", sa.Integer(), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("computed_tier", sa.SmallInteger(), nullable=True),
        sa.Column("forced_tier", sa.SmallInteger(), nullable=True),
        sa.Column(
            "pinned", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "excluded", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_recomputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["artist_id"], ["artists.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("artist_id"),
    )
    op.create_index(
        "ix_artist_cohort_tier_checked",
        "artist_cohort",
        ["tier", "last_checked_at"],
        postgresql_where=sa.text("excluded IS NOT TRUE"),
    )


def downgrade():
    op.drop_index("ix_artist_cohort_tier_checked", table_name="artist_cohort")
    op.drop_table("artist_cohort")
