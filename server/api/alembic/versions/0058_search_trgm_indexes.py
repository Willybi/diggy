"""search_trgm_indexes — pg_trgm GIN indexes for /api/search (deferred since 0053).

The search scopes run ``ILIKE '%…%'`` (and its space-compacted twin
``replace(col, ' ', '') ILIKE``) over the big tables — catalog title/artist,
artists.name, sets.search_text, trackid_index.channel — which are unindexable
seq scans without pg_trgm (measured 6.5–9s per scope=all search in prod).

Every searched column gets TWO trigram indexes: one on the raw column and one on
the exact compacted EXPRESSION the query uses. Both arms of the OR emitted by
``space_insensitive_ilike`` (and the sets/channel predicates) must be indexable
for Postgres to BitmapOr them — indexing only the plain column would leave the
whole OR on a seq scan.

The expressions must match the SQL the app emits VERBATIM (an expression index
only serves an identical expression): ``replace(col, ' ', '')`` for the helper
columns, ``lower(channel)`` / ``replace(lower(channel), ' ', '')`` for the
trackid_index channel predicate (which folds case on the fly).

PG-only (SQLite backs the test suite via create_all and never sees this); the
index names are excluded from autogenerate in ``alembic/env.py``
(_AUTOGEN_SKIP_INDEXES). Builds are non-concurrent — a few seconds per index at
deploy time on ~300k-row tables, done before the container switch.
"""

from alembic import op

revision = "0058"
down_revision = "0057"

# (name, table, indexed expression) — expression strings are PG SQL, verbatim.
_TRGM_INDEXES = [
    ("ix_catalog_title_trgm", "catalog", "title gin_trgm_ops"),
    ("ix_catalog_title_compact_trgm", "catalog", "(replace(title, ' ', '')) gin_trgm_ops"),
    ("ix_catalog_artist_trgm", "catalog", "artist gin_trgm_ops"),
    ("ix_catalog_artist_compact_trgm", "catalog", "(replace(artist, ' ', '')) gin_trgm_ops"),
    ("ix_artists_name_trgm", "artists", "name gin_trgm_ops"),
    ("ix_artists_name_compact_trgm", "artists", "(replace(name, ' ', '')) gin_trgm_ops"),
    ("ix_sets_search_text_trgm", "sets", "search_text gin_trgm_ops"),
    (
        "ix_sets_search_text_compact_trgm",
        "sets",
        "(replace(search_text, ' ', '')) gin_trgm_ops",
    ),
    ("ix_trackid_index_channel_lower_trgm", "trackid_index", "(lower(channel)) gin_trgm_ops"),
    (
        "ix_trackid_index_channel_compact_trgm",
        "trackid_index",
        "(replace(lower(channel), ' ', '')) gin_trgm_ops",
    ),
]


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, expr in _TRGM_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({expr})")


def downgrade():
    for name, _table, _expr in _TRGM_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    # The pg_trgm extension is deliberately left installed (harmless, and other
    # objects may come to depend on it).
