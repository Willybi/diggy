"""sets_metadata — derived event_date + canonical channel on sets (C13.e).

Adds two nullable columns to ``sets``: ``event_date`` (the event date parsed out
of the set title when unambiguous — preferred over ``played_date``, which mirrors
TrackID's often-upload ``createdOn``) and ``channel_canonical`` (the ``channel``
normalised through a curated gazetteer, cleaned raw passthrough otherwise). Both
are written at the import funnel and backfilled from the title/channel for
existing rows (``scripts/backfill_set_metadata.py``); this migration only adds the
columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"


def upgrade():
    op.add_column("sets", sa.Column("event_date", sa.Date, nullable=True))
    op.add_column(
        "sets", sa.Column("channel_canonical", sa.String(length=255), nullable=True)
    )


def downgrade():
    op.drop_column("sets", "channel_canonical")
    op.drop_column("sets", "event_date")
