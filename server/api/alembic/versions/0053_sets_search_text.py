"""sets_search_text — search-only folded text column on sets.

Adds ``sets.search_text`` (nullable): the accent/punctuation-insensitive folded
form of a set's searchable text (``utils.search_fold``), backing the reworked
set search. No index here — pg_trgm is deliberately deferred to a later lot. The
column is populated by the importer/backfill, not by this migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"


def upgrade():
    op.add_column("sets", sa.Column("search_text", sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column("sets", "search_text")
