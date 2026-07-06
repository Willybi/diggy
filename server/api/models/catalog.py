from database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .base import StringArray


class CatalogEntry(Base):
    __tablename__ = "catalog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    artist = Column(String(500))
    normalized_key = Column(String(500), unique=True, nullable=False)
    isrc = Column(String(20), unique=True, nullable=True)
    deezer_id = Column(String(64), nullable=True)
    beatport_id = Column(String(64), nullable=True)
    bpm = Column(Float, nullable=True)
    key = Column(String(10), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    genres = Column(StringArray(), server_default="{}", default=list)
    release_date = Column(Date, nullable=True)
    preview_url = Column(Text, nullable=True)
    has_artwork = Column(Boolean, default=False)
    has_preview = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))
    # Phase 2 — multi-user fields
    scope = Column(
        String(10), nullable=False, server_default="shared", default="shared"
    )
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    origin = Column(
        String(50), nullable=False, server_default="deezer", default="deezer"
    )
    status = Column(
        String(20), nullable=False, server_default="official", default="official"
    )
    bpm_source = Column(String(20), nullable=True)
    key_source = Column(String(20), nullable=True)
    label = Column(String(255), nullable=True)
    fingerprint = Column(String, unique=True, nullable=True)
    needs_reconciliation = Column(Boolean, server_default="false", nullable=True)
    deezer_searched_at = Column(DateTime(timezone=True), nullable=True)
    beatport_searched_at = Column(DateTime(timezone=True), nullable=True)

    artist_links = relationship(
        "CatalogArtist",
        back_populates="catalog",
        cascade="all, delete-orphan",
    )


class CatalogArtist(Base):
    __tablename__ = "catalog_artists"

    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id = Column(
        Integer,
        ForeignKey("artists.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    role = Column(String(32), nullable=True)
    position = Column(Integer, nullable=True)

    catalog = relationship("CatalogEntry", back_populates="artist_links")
    artist = relationship("Artist", back_populates="catalog_links")


class UserTrack(Base):
    __tablename__ = "user_tracks"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    catalog_id = Column(
        Integer,
        ForeignKey("catalog.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    rekordbox_id = Column(Integer, nullable=True)
    date_added = Column(DateTime(timezone=True), nullable=True)
    source = Column(
        String(50),
        server_default="rekordbox_import",
        default="rekordbox_import",
        nullable=True,
    )
    file_path = Column(Text, nullable=True)
    rb_bpm = Column(Float, nullable=True)
    rb_key = Column(String(10), nullable=True)
    rb_mytags = Column(JSON, server_default="[]", default=list, nullable=True)
    rating = Column(Integer, nullable=True)
    avis = Column(String(20), nullable=True)
    has_artwork = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))

    catalog = relationship("CatalogEntry")
    user = relationship("User")
