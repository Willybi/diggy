"""set reliability flag — sets.unreliable marks low-trust TrackID audiostreams
(mostly unidentified tracks, no source_url, placeholder artwork) so they can be
hidden everywhere and excluded from proximity scoring WITHOUT deleting the
underlying tracks (C8)."""

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"


def upgrade():
    # server_default false is mandatory: existing rows must receive a value for
    # the NOT NULL column (same pattern as 0043 bpm_analysis_attempts). The flag
    # is materialized (a plain boolean column), recomputed on every (re-)import.
    op.add_column(
        "sets",
        sa.Column(
            "unreliable",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade():
    op.drop_column("sets", "unreliable")
