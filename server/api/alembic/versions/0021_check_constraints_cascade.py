"""Add CHECK constraints and fix CASCADE on RadarTrack.watched_entity_id."""
from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade():
    # 1. Fix CASCADE on radar_tracks.watched_entity_id
    op.execute(
        "ALTER TABLE radar_tracks "
        "DROP CONSTRAINT IF EXISTS radar_tracks_watched_entity_id_fkey"
    )
    op.execute(
        "ALTER TABLE radar_tracks "
        "ADD CONSTRAINT radar_tracks_watched_entity_id_fkey "
        "FOREIGN KEY (watched_entity_id) REFERENCES watched_entities(id) ON DELETE CASCADE"
    )

    # 2. CHECK constraints
    op.execute(
        "ALTER TABLE catalog "
        "ADD CONSTRAINT ck_bpm_positive CHECK (bpm > 0 OR bpm IS NULL)"
    )
    op.execute(
        "ALTER TABLE user_tracks "
        "ADD CONSTRAINT ck_rating_range CHECK (rating >= 0 AND rating <= 5 OR rating IS NULL)"
    )
    op.execute(
        "ALTER TABLE set_tracks "
        "ADD CONSTRAINT ck_position_positive CHECK (position >= 1)"
    )
    op.execute(
        "ALTER TABLE user_opinions "
        "ADD CONSTRAINT ck_opinion_valid CHECK (opinion IN ('liked', 'disliked'))"
    )
    op.execute(
        "ALTER TABLE artist_flags "
        "ADD CONSTRAINT ck_flag_status_valid CHECK (status IN ('pending', 'validated', 'skipped'))"
    )


def downgrade():
    # Drop CHECK constraints
    op.execute("ALTER TABLE artist_flags DROP CONSTRAINT IF EXISTS ck_flag_status_valid")
    op.execute("ALTER TABLE user_opinions DROP CONSTRAINT IF EXISTS ck_opinion_valid")
    op.execute("ALTER TABLE set_tracks DROP CONSTRAINT IF EXISTS ck_position_positive")
    op.execute("ALTER TABLE user_tracks DROP CONSTRAINT IF EXISTS ck_rating_range")
    op.execute("ALTER TABLE catalog DROP CONSTRAINT IF EXISTS ck_bpm_positive")

    # Revert FK to original (no CASCADE)
    op.execute(
        "ALTER TABLE radar_tracks "
        "DROP CONSTRAINT IF EXISTS radar_tracks_watched_entity_id_fkey"
    )
    op.execute(
        "ALTER TABLE radar_tracks "
        "ADD CONSTRAINT radar_tracks_watched_entity_id_fkey "
        "FOREIGN KEY (watched_entity_id) REFERENCES watched_entities(id)"
    )
