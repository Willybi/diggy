"""Add missing indexes on frequently filtered columns."""
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade():
    op.create_index("ix_radar_tracks_watched_entity", "radar_tracks", ["watched_entity_id"])
    op.create_index("ix_radar_tracks_catalog", "radar_tracks", ["catalog_id"])
    op.execute(
        "CREATE INDEX ix_catalog_deezer_id ON catalog(deezer_id) WHERE deezer_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_catalog_beatport_id ON catalog(beatport_id) WHERE beatport_id IS NOT NULL"
    )
    op.create_index("ix_watched_entities_source", "watched_entities", ["source"])
    op.execute(
        "CREATE INDEX ix_catalog_genres ON catalog USING GIN(genres)"
    )


def downgrade():
    op.drop_index("ix_catalog_genres", table_name="catalog")
    op.drop_index("ix_watched_entities_source", table_name="watched_entities")
    op.drop_index("ix_catalog_beatport_id", table_name="catalog")
    op.drop_index("ix_catalog_deezer_id", table_name="catalog")
    op.drop_index("ix_radar_tracks_catalog", table_name="radar_tracks")
    op.drop_index("ix_radar_tracks_watched_entity", table_name="radar_tracks")
