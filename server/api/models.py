from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    group = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False, unique=True)

    tracks = relationship("TrackTag", back_populates="tag")


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True)
    rekordbox_id = Column(Integer, unique=True, index=True)
    title = Column(String(255))
    artist = Column(String(255))
    album = Column(String(255))
    label = Column(String(255))
    bpm = Column(Float)
    key = Column(String(10))
    duration = Column(Integer)   # secondes
    rating = Column(Integer)
    play_count = Column(Integer, default=0)
    file_path = Column(Text)
    date_added = Column(DateTime)

    cues = relationship("Cue", back_populates="track", cascade="all, delete-orphan")
    tags = relationship("TrackTag", back_populates="track", cascade="all, delete-orphan")


class Cue(Base):
    __tablename__ = "cues"

    id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    kind = Column(Integer)        # 0 = memory cue, 1-N = hot cue
    time = Column(Float)          # timestamp en millisecondes
    color = Column(String(10))
    comment = Column(String(255))
    is_loop = Column(Integer, default=0)
    loop_out = Column(Float)

    track = relationship("Track", back_populates="cues")


class TrackTag(Base):
    __tablename__ = "track_tags"

    track_id = Column(Integer, ForeignKey("tracks.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)

    track = relationship("Track", back_populates="tags")
    tag = relationship("Tag", back_populates="tracks")
