"""sets_signals — TrackID set signals mirrored onto sets (C13.a).

Adds six nullable columns to ``sets`` carrying the TrackID listing/detail signals
that until now lived only in ``trackid_index`` and were therefore unusable with the
set itself: ``channel`` + ``styles`` (surfaced in the UI) and the data-only
``time_hit_rate`` / ``track_hit_rate`` / ``favourite_count`` / ``like_count``.
Written at the import funnel and backfilled from ``trackid_index`` for existing
rows (``scripts/backfill_set_signals.py``); this migration only adds the columns.
``styles`` mirrors ``trackid_index.styles`` — ``ARRAY(Text)`` on PostgreSQL (see 0050).
"""

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"


def upgrade():
    op.add_column("sets", sa.Column("channel", sa.String(length=255), nullable=True))
    op.add_column("sets", sa.Column("styles", sa.ARRAY(sa.Text), nullable=True))
    op.add_column("sets", sa.Column("time_hit_rate", sa.Float, nullable=True))
    op.add_column("sets", sa.Column("track_hit_rate", sa.Float, nullable=True))
    op.add_column("sets", sa.Column("favourite_count", sa.Integer, nullable=True))
    op.add_column("sets", sa.Column("like_count", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("sets", "like_count")
    op.drop_column("sets", "favourite_count")
    op.drop_column("sets", "track_hit_rate")
    op.drop_column("sets", "time_hit_rate")
    op.drop_column("sets", "styles")
    op.drop_column("sets", "channel")
