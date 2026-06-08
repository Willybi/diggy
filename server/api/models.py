from database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint


class LibTrack(Base):
    __tablename__ = "lib_tracks"

    id = Column(Integer, primary_key=True)  # = rekordbox_id
    title = Column(String(255))
    artist = Column(String(255))
    bpm = Column(Float)
    key = Column(String(10))
    duration = Column(Integer)  # ms
    rating = Column(Integer)
    file_path = Column(Text)
    date_added = Column(DateTime)
    tags = Column(Text)  # JSON array ex: ["Tech House", "TO_CUE"]
    has_artwork = Column(Boolean, default=False)


class WatchedPlaylist(Base):
    __tablename__ = "watched_playlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), unique=True, nullable=False)
    source = Column(String(64), nullable=False)
    title = Column(String(255))
    description = Column(Text)
    created_at = Column(DateTime)
    last_crawled_at = Column(DateTime)


class RadarTrack(Base):
    __tablename__ = "radar_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    watched_playlist_id = Column(Integer, ForeignKey("watched_playlists.id"), nullable=False)
    external_track_id = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    artist = Column(String(500))
    isrc = Column(String(20))
    detected_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("watched_playlist_id", "external_track_id", name="uq_radar_playlist_track"),
    )
