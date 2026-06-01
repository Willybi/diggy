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
