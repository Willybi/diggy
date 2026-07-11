import enum

from database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import backref, relationship


class DJSet(Base):
    __tablename__ = "sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), nullable=True)
    source = Column(String(64), nullable=False)
    source_url = Column(Text, nullable=True)
    title = Column(String(500), nullable=False)
    event = Column(String(255), nullable=True)
    venue = Column(String(255), nullable=True)
    played_date = Column(Date, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    external_slug = Column(String(500), nullable=True)
    has_artwork = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))
    last_crawled_at = Column(DateTime(timezone=True))
    parent_set_id = Column(
        Integer, ForeignKey("sets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_virtual = Column(Boolean, nullable=False, default=False, server_default="false")
    platform = Column(String(32), nullable=True)
    normalized_title = Column(String(500), nullable=True)
    part_number = Column(Integer, nullable=True)
    part_total = Column(Integer, nullable=True)
    # C6.b re-crawl state — completion_pct is is_id-based (catalog_id is reset
    # by re-imports and cannot back a stable metric)
    completion_pct = Column(Float, nullable=True)
    last_recrawl_at = Column(DateTime(timezone=True), nullable=True)
    # Consecutive re-crawls WITHOUT progression; reset to 0 whenever
    # completion_pct improves, 3 stale runs finalize the set
    recrawl_count = Column(Integer, nullable=False, default=0, server_default="0")
    # 'active' | 'final' — plain String like platform, no PG enum
    recrawl_status = Column(
        String(16), nullable=False, default="active", server_default="active"
    )

    __table_args__ = (
        UniqueConstraint("external_id", "source", name="uq_set_external_source"),
    )

    tracks = relationship(
        "SetTrack",
        back_populates="dj_set",
        cascade="all, delete-orphan",
        order_by="SetTrack.position",
    )
    artist_links = relationship(
        "SetArtist",
        back_populates="dj_set",
        cascade="all, delete-orphan",
    )
    children = relationship(
        "DJSet",
        foreign_keys=[parent_set_id],
        backref=backref("parent", remote_side="DJSet.id"),
    )


class SetArtist(Base):
    __tablename__ = "set_artists"

    set_id = Column(
        Integer, ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id = Column(
        Integer,
        ForeignKey("artists.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    role = Column(String(32), nullable=True)
    position = Column(Integer, nullable=True)

    dj_set = relationship("DJSet", back_populates="artist_links")
    artist = relationship("Artist", back_populates="set_links")


class SetTrack(Base):
    __tablename__ = "set_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    set_id = Column(
        Integer, ForeignKey("sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    catalog_id = Column(
        Integer,
        ForeignKey("catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    position = Column(Integer, nullable=False)
    timecode_ms = Column(Integer, nullable=True)
    raw_title = Column(String(500), nullable=True)
    raw_artist = Column(String(500), nullable=True)
    is_id = Column(Boolean, default=False)
    trackid_music_track_id = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("set_id", "position", name="uq_set_track_position"),
    )

    dj_set = relationship("DJSet", back_populates="tracks")
    catalog = relationship("CatalogEntry")


class UserSetFollow(Base):
    __tablename__ = "user_set_follows"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    set_id = Column(
        Integer,
        ForeignKey("sets.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    followed_at = Column(DateTime(timezone=True))


class SetFlagType(str, enum.Enum):
    duplicate_candidate = "duplicate_candidate"
    part_candidate = "part_candidate"
    part_overlap_anomaly = "part_overlap_anomaly"


class SetFlagStatus(str, enum.Enum):
    pending = "pending"
    attached = "attached"
    rejected = "rejected"


class SetFlag(Base):
    __tablename__ = "set_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    set_id_a = Column(
        Integer, ForeignKey("sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    set_id_b = Column(
        Integer, ForeignKey("sets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    flag_type = Column(SAEnum(SetFlagType, name="set_flag_type"), nullable=False)
    confidence = Column(Float, nullable=True)
    signals = Column(JSON, nullable=True)
    status = Column(
        SAEnum(SetFlagStatus, name="set_flag_status"),
        nullable=False,
        default=SetFlagStatus.pending,
        server_default="pending",
    )
    resolved_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    group_key = Column(String(500), nullable=True, index=True)
    member_set_ids = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("set_id_a", "set_id_b", name="uq_set_flag_pair"),
        # Partial unique index created as-is in 0030, hence the uq_ name
        Index(
            "uq_set_flag_group_key",
            "group_key",
            unique=True,
            postgresql_where=text("group_key IS NOT NULL"),
        ),
    )
