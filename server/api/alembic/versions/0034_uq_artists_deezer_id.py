"""AU3 follow-up — declare uq_artists_deezer_id (partial unique on artists.deezer_id).

The index already exists in prod (created by hand outside any migration). The
IF NOT EXISTS makes this a no-op there; on a fresh DB it creates it. Additive —
assumes nothing about the current state of the table.
"""

from alembic import op

revision = "0034"
down_revision = "0033"


def upgrade():
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_artists_deezer_id "
        "ON public.artists USING btree (deezer_id) "
        "WHERE ((deezer_id IS NOT NULL) AND ((deezer_id)::text <> 'NOT_FOUND'::text))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_artists_deezer_id")
