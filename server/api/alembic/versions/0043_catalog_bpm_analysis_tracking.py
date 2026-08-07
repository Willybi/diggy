"""catalog bpm analysis tracking columns — state markers so the nightly
estimated-BPM-from-Deezer-preview task (E2.c) does not re-analyze forever a
candidate that was already tried but stays bpm NULL (recalé par le gate de
confiance)."""

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"


def upgrade():
    # NULL = never analyzed. Stamped once an analysis produced a verdict
    # (ok OR low_conf), never on a transient network failure.
    op.add_column(
        "catalog",
        sa.Column("bpm_analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Informative counter. server_default is mandatory: existing rows must
    # receive a value for the NOT NULL column (same pattern as 0038).
    op.add_column(
        "catalog",
        sa.Column(
            "bpm_analysis_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade():
    op.drop_column("catalog", "bpm_analysis_attempts")
    op.drop_column("catalog", "bpm_analyzed_at")
