from database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)


class Channel(Base):
    """Watched source channel (C14.b).

    A first-class channel we watch for DJ sets — YouTube for this slice
    ('soundcloud' later). ``external_id`` is the platform-side channel id
    (a YouTube « UC… » id), NULL until resolved. ``channel_type`` is an
    application-level label ('artist' | 'label' | 'organizer' | 'radio'), a
    plain String (no PG enum). ``artist_id`` links to the artist when the
    channel is one (a venue/organiser channel has none). ``watched`` /
    ``excluded`` are the curation flags, ``signals`` snapshots curation/coverage,
    and ``last_checked_at`` (stamped by the later watch lot) drives the cadence.
    """

    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 'youtube' for this slice, 'soundcloud' later (plain String, no PG enum)
    platform = Column(String(20), nullable=False)
    # Platform-side channel id (YouTube « UC… »), NULL until resolved
    external_id = Column(String(64), nullable=True)
    name = Column(String(255), nullable=False)
    # Application values: 'artist' | 'label' | 'organizer' | 'radio'
    channel_type = Column(String(20), nullable=True)
    artist_id = Column(
        Integer, ForeignKey("artists.id", ondelete="SET NULL"), nullable=True
    )
    watched = Column(Boolean, nullable=False, default=False, server_default="false")
    excluded = Column(Boolean, nullable=False, default=False, server_default="false")
    # Snapshot of curation/coverage signals
    signals = Column(JSON, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "platform", "external_id", name="uq_channel_platform_external"
        ),
        # Backs the per-platform "due" selection (platform + last_checked_at
        # ordering) of the watch lot; only watched channels are ever polled, so
        # drop the rest from the index. sqlite_where is mandatory so the test
        # harness (create_all on SQLite) reproduces the partial condition.
        Index(
            "ix_channels_due",
            "platform",
            "last_checked_at",
            postgresql_where=text("watched IS TRUE"),
            sqlite_where=text("watched IS TRUE"),
        ),
    )
