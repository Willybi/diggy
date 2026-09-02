"""ix_trackid_index_set_id — index trackid_index.set_id.

Backs the set-search channel join (``sets.id`` ← ``trackid_index.set_id``). The
index was already created BY HAND in prod (to lift a 504 on the reworked set
search), so ``CREATE INDEX IF NOT EXISTS`` makes this upgrade a no-op there; on a
fresh DB it creates it. Mirrors the 0034_uq_artists_deezer_id pattern.
"""

from alembic import op

revision = "0054"
down_revision = "0053"


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trackid_index_set_id "
        "ON trackid_index (set_id)"
    )


def downgrade():
    op.drop_index("ix_trackid_index_set_id", table_name="trackid_index")
