from database import Base
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship


# ---------- Association tables (no extra columns) ----------

# ---------- Models ----------


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    google_id = Column(String(255), unique=True, nullable=True)
    avatar_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False, server_default="false")
    settings = Column(JSON, default=dict, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True))


class Artist(Base):
    __tablename__ = "artists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False)
    normalized_name = Column(String(500), unique=True, nullable=False)
    real_name = Column(String(255), nullable=True)
    country = Column(String(2), nullable=True)
    deezer_id = Column(String(64), nullable=True)
    soundcloud_id = Column(String(64), nullable=True)
    trackid_id = Column(String(64), nullable=True)
    bio = Column(Text, nullable=True)
    has_artwork = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))

    aliases = relationship("ArtistAlias", back_populates="artist", cascade="all, delete-orphan")
    set_links = relationship("SetArtist", back_populates="artist")


class ArtistAlias(Base):
    __tablename__ = "artist_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artist_id = Column(Integer, ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String(500), nullable=False)
    normalized_alias = Column(String(500), unique=True, nullable=False)

    artist = relationship("Artist", back_populates="aliases")


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
    genre = Column(String(100), nullable=True)
    release_date = Column(Date, nullable=True)
    preview_url = Column(Text, nullable=True)
    has_artwork = Column(Boolean, default=False)
    has_preview = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))
    # Phase 2 — multi-user fields
    scope = Column(String(10), nullable=False, server_default="shared", default="shared")
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    origin = Column(String(50), nullable=False, server_default="deezer", default="deezer")
    status = Column(String(20), nullable=False, server_default="official", default="official")
    bpm_source = Column(String(20), nullable=True)
    key_source = Column(String(20), nullable=True)
    label = Column(String(255), nullable=True)
    fingerprint = Column(String, unique=True, nullable=True)
    needs_reconciliation = Column(Boolean, server_default="false", nullable=True)
    deezer_searched_at = Column(DateTime(timezone=True), nullable=True)
    beatport_searched_at = Column(DateTime(timezone=True), nullable=True)


class UserTrack(Base):
    __tablename__ = "user_tracks"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    catalog_id = Column(Integer, ForeignKey("catalog.id", ondelete="RESTRICT"), primary_key=True, nullable=False)
    rekordbox_id = Column(Integer, nullable=True)
    date_added = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(50), server_default="rekordbox_import", default="rekordbox_import", nullable=True)
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


class WatchedEntity(Base):
    __tablename__ = "watched_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), unique=True, nullable=False)
    source = Column(String(64), nullable=False)
    type = Column(String(20), nullable=False, server_default="playlist", default="playlist")
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

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    entity_id = Column(Integer, ForeignKey("watched_entities.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    followed_at = Column(DateTime(timezone=True))

    user = relationship("User")
    entity = relationship("WatchedEntity")


class UserSetFollow(Base):
    __tablename__ = "user_set_follows"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    set_id = Column(Integer, ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    followed_at = Column(DateTime(timezone=True))


class UserRadarState(Base):
    __tablename__ = "user_radar_state"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    catalog_id = Column(Integer, ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    status = Column(String(20), nullable=False, server_default="new", default="new")
    updated_at = Column(DateTime(timezone=True))

    user = relationship("User")
    catalog = relationship("CatalogEntry")


class RadarTrack(Base):
    __tablename__ = "radar_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    watched_entity_id = Column(
        Integer, ForeignKey("watched_entities.id"), nullable=False
    )
    external_track_id = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    artist = Column(String(500))
    isrc = Column(String(20))
    detected_at = Column(DateTime(timezone=True))
    catalog_id = Column(Integer, ForeignKey("catalog.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "watched_entity_id", "external_track_id", name="uq_radar_playlist_track"
        ),
    )


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

    __table_args__ = (
        UniqueConstraint("external_id", "source", name="uq_set_external_source"),
    )

    tracks = relationship(
        "SetTrack", back_populates="dj_set",
        cascade="all, delete-orphan", order_by="SetTrack.position",
    )
    artist_links = relationship(
        "SetArtist", back_populates="dj_set",
        cascade="all, delete-orphan",
    )


class SetArtist(Base):
    __tablename__ = "set_artists"

    set_id = Column(Integer, ForeignKey("sets.id", ondelete="CASCADE"), primary_key=True)
    artist_id = Column(Integer, ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True, index=True)
    role = Column(String(32), nullable=True)
    position = Column(Integer, nullable=True)

    dj_set = relationship("DJSet", back_populates="artist_links")
    artist = relationship("Artist", back_populates="set_links")


class SetTrack(Base):
    __tablename__ = "set_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    set_id = Column(Integer, ForeignKey("sets.id", ondelete="CASCADE"), nullable=False, index=True)
    catalog_id = Column(Integer, ForeignKey("catalog.id", ondelete="SET NULL"), nullable=True, index=True)
    position = Column(Integer, nullable=False)
    timecode_ms = Column(Integer, nullable=True)
    raw_title = Column(String(500), nullable=True)
    raw_artist = Column(String(500), nullable=True)
    is_id = Column(Boolean, default=False)
    trackid_music_track_id = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("set_id", "position", name="uq_set_track_position"),
    )

    dj_set = relationship("DJSet", back_populates="tracks")
    catalog = relationship("CatalogEntry")


class ArtistFlag(Base):
    __tablename__ = "artist_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_artist_string = Column(String(500), nullable=False, unique=True)
    reason = Column(String(64), nullable=False)  # comma_unresolved | ampersand_ambiguous | ampersand_unknown
    tokens = Column(JSON, nullable=False)          # ["Romy", "Fred again.."]
    deezer_ids = Column(JSON, nullable=False)      # {"Romy": null, "Fred again..": "123"}
    status = Column(String(32), nullable=False, default="pending", server_default="pending")  # pending | validated | skipped
    resolved_artist_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


class UserOpinion(Base):
    __tablename__ = "user_opinions"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    entity_type = Column(String(20), primary_key=True, nullable=False)  # artist, set, playlist, genre
    entity_key = Column(String(255), primary_key=True, nullable=False)  # id as string, or genre name
    opinion = Column(String(20), nullable=False)  # liked | disliked
    created_at = Column(DateTime(timezone=True))


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(64), nullable=False, index=True)
    target_id = Column(Integer, nullable=True)
    target_label = Column(String(500), nullable=True)
    source = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, server_default="running", default="running")
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    stats = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
