"""trackid_index — raw index of TrackID.net audiostreams (C11).

We index every TrackID.net set (~381k) into this table WITHOUT hydrating them
(no catalog/tracklist expansion), to build the scoring material for C12. The
row is a RAW MIRROR of the listing payload from ``/audiostreams`` — capturing a
field is cheap, missing one costs a re-crawl of the whole 381k corpus — so the
columns are permissive and SQLite-safe, and ``raw_json`` keeps the full listing
item as a zero-loss safety net. Diggy-side columns (score, dedup, hydration
state, set link) are seeded/filled by later lots (L3 import, C12 scoring).
"""
from database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .base import StringArray


class TrackIdIndex(Base):
    __tablename__ = "trackid_index"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Identity & listing signals (raw payload mirror) ---
    trackid_id = Column(Integer, nullable=False)  # payload `id` = TrackID identity
    slug = Column(String(500), nullable=True)
    title = Column(String(500), nullable=True)
    channel = Column(String(255), nullable=True)
    styles = Column(StringArray, nullable=True)  # payload `styles[]`
    status = Column(Integer, nullable=True)  # payload `status` (int code)
    is_deleted = Column(Boolean, nullable=True)  # payload `isDeleted`, raw mirror
    track_count = Column(Integer, nullable=True)  # payload `trackCount`
    duration = Column(String(64), nullable=True)  # payload `duration`, raw timespan string
    time_hit_rate = Column(Float, nullable=True)  # payload `timeHitRate`
    track_hit_rate = Column(Float, nullable=True)  # payload `trackHitRate`
    processing_priority = Column(Integer, nullable=True)  # payload `processingPriority`
    artwork_url = Column(Text, nullable=True)
    added_on = Column(DateTime(timezone=True), nullable=True)  # payload `addedOn`
    created_on = Column(DateTime(timezone=True), nullable=True)  # payload `createdOn`
    added_by = Column(String(255), nullable=True)  # payload `addedBy`
    added_by_id = Column(Integer, nullable=True)  # payload `addedById`
    audio_stream_type = Column(Integer, nullable=True)  # payload `audioStreamType` (int code)
    external_id = Column(String(255), nullable=True)  # payload `externalId` (YT/SC)
    url = Column(Text, nullable=True)
    favourite_count = Column(Integer, nullable=True)  # payload `favouriteCount`
    like_count = Column(Integer, nullable=True)  # payload `likeCount`
    average_rating = Column(Float, nullable=True)  # payload `averageRating`
    # Safety net: the full raw listing item, guarantees zero field loss.
    raw_json = Column(JSON, nullable=True)

    # --- Diggy-side columns ---
    window_id = Column(String(64), nullable=True)  # static crawl window
    dedup_group_id = Column(Integer, nullable=True)  # dedup cluster (filled at L3)
    score = Column(Float, nullable=True)  # left NULL — filled by C12
    score_components = Column(JSON, nullable=True)  # left NULL — filled by C12
    hydration_state = Column(
        String(32), nullable=False, default="not_hydrated", server_default="not_hydrated"
    )
    matched_artist_ids = Column(JSON, nullable=True)  # left NULL — filled later
    set_id = Column(
        Integer, ForeignKey("sets.id", ondelete="SET NULL"), nullable=True
    )
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("trackid_id", name="uq_trackid_index_trackid_id"),
        Index("ix_trackid_index_hydration_state", "hydration_state"),
        Index("ix_trackid_index_added_on", "added_on"),
    )
