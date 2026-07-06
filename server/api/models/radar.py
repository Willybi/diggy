from database import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship


class WatchedEntity(Base):
    __tablename__ = "watched_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), unique=True, nullable=False)
    source = Column(String(64), nullable=False)
    type = Column(
        String(20), nullable=False, server_default="playlist", default="playlist"
    )
    title = Column(String(255))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True))
    last_crawled_at = Column(DateTime(timezone=True))
    has_artwork = Column(Boolean, default=False)
    track_count = Column(Integer, nullable=True)
    owner = Column(String(255), nullable=True)
    current_task_id = Column(String(255), nullable=True)
    crawl_started_at = Column(DateTime(timezone=True), nullable=True)


class UserFollow(Base):
    __tablename__ = "user_follows"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    entity_id = Column(
        Integer,
        ForeignKey("watched_entities.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    followed_at = Column(DateTime(timezone=True))

    user = relationship("User")
    entity = relationship("WatchedEntity")


class UserRadarState(Base):
    __tablename__ = "user_radar_state"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    catalog_id = Column(
        Integer,
        ForeignKey("catalog.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    status = Column(String(20), nullable=False, server_default="new", default="new")
    updated_at = Column(DateTime(timezone=True))

    user = relationship("User")
    catalog = relationship("CatalogEntry")


class RadarTrack(Base):
    __tablename__ = "radar_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    watched_entity_id = Column(
        Integer, ForeignKey("watched_entities.id", ondelete="CASCADE"), nullable=False
    )
    external_track_id = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    artist = Column(String(500))
    isrc = Column(String(20))
    detected_at = Column(DateTime(timezone=True))
    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="SET NULL"), nullable=True
    )
    removed_at = Column(DateTime(timezone=True), nullable=True)
    is_initial_detection = Column(Boolean, default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint(
            "watched_entity_id", "external_track_id", name="uq_radar_playlist_track"
        ),
    )


class RadarTrend(Base):
    __tablename__ = "radar_trends"

    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True
    )
    trend_score = Column(Float, nullable=False, server_default="0", default=0)
    window_days = Column(Integer, server_default="30", default=30)
    detection_count = Column(Integer, server_default="0", default=0)
    family = Column(String(50), nullable=True)
    rank_in_family = Column(Integer, nullable=True)
    rank_global = Column(Integer, nullable=True)
    velocity = Column(Float, nullable=True)
    source_count = Column(Integer, nullable=True)
    computed_at = Column(DateTime(timezone=True))

    catalog = relationship("CatalogEntry")
