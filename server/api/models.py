from database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text


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
    deezer_playlist_id = Column(String(64), unique=True, nullable=False)
    source = Column(String(64), nullable=False)
    title = Column(String(255))
    description = Column(Text)
    created_at = Column(DateTime)
