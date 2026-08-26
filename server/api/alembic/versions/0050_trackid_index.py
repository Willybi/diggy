"""trackid_index — raw index of TrackID.net audiostreams (C11).

Creates ``trackid_index``: a raw mirror of the ``/audiostreams`` listing payload
(identity ``trackid_id`` + listing signals + a ``raw_json`` zero-loss safety net)
plus Diggy-side columns (dedup, score, hydration state, set link) filled by later
lots. Lean constraints: UNIQUE on ``trackid_id`` and indexes on
``hydration_state`` and ``added_on``. No PG-only type or index.
"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"


def upgrade():
    op.create_table(
        "trackid_index",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trackid_id", sa.Integer, nullable=False),
        sa.Column("slug", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("channel", sa.String(255), nullable=True),
        sa.Column("styles", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("status", sa.Integer, nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=True),
        sa.Column("track_count", sa.Integer, nullable=True),
        sa.Column("duration", sa.String(64), nullable=True),
        sa.Column("time_hit_rate", sa.Float, nullable=True),
        sa.Column("track_hit_rate", sa.Float, nullable=True),
        sa.Column("processing_priority", sa.Integer, nullable=True),
        sa.Column("artwork_url", sa.Text, nullable=True),
        sa.Column("added_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_by", sa.String(255), nullable=True),
        sa.Column("added_by_id", sa.Integer, nullable=True),
        sa.Column("audio_stream_type", sa.Integer, nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("favourite_count", sa.Integer, nullable=True),
        sa.Column("like_count", sa.Integer, nullable=True),
        sa.Column("average_rating", sa.Float, nullable=True),
        sa.Column("raw_json", sa.JSON, nullable=True),
        sa.Column("window_id", sa.String(64), nullable=True),
        sa.Column("dedup_group_id", sa.Integer, nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("score_components", sa.JSON, nullable=True),
        sa.Column(
            "hydration_state",
            sa.String(32),
            nullable=False,
            server_default="not_hydrated",
        ),
        sa.Column("matched_artist_ids", sa.JSON, nullable=True),
        sa.Column(
            "set_id",
            sa.Integer,
            sa.ForeignKey("sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("trackid_id", name="uq_trackid_index_trackid_id"),
    )
    op.create_index(
        "ix_trackid_index_hydration_state", "trackid_index", ["hydration_state"]
    )
    op.create_index("ix_trackid_index_added_on", "trackid_index", ["added_on"])


def downgrade():
    op.drop_index("ix_trackid_index_added_on", table_name="trackid_index")
    op.drop_index("ix_trackid_index_hydration_state", table_name="trackid_index")
    op.drop_table("trackid_index")
