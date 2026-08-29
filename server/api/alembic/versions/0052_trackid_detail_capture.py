"""trackid_detail_capture — persist three detail-payload fields (C12).

Before the mass hydration of ~300k TrackID sets, widen the schema so three
fields of the detail payload that were previously discarded are persisted (we
don't pass twice over 300k sets): the track-level ``label`` and ``end_time_ms``
(``set_tracks``), and the set-level ``can_reprocess`` (``sets``). The rest of
the payload (referenceCount/isNew/accountMusicTrack/amendments/…) stays dropped.
"""

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"


def upgrade():
    op.add_column("set_tracks", sa.Column("label", sa.String(255), nullable=True))
    op.add_column("set_tracks", sa.Column("end_time_ms", sa.Integer, nullable=True))
    op.add_column("sets", sa.Column("can_reprocess", sa.Boolean, nullable=True))


def downgrade():
    op.drop_column("sets", "can_reprocess")
    op.drop_column("set_tracks", "end_time_ms")
    op.drop_column("set_tracks", "label")
