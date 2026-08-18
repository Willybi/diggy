import enum

from database import Base
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship


class AlbumType(str, enum.Enum):
    album = "album"
    single = "single"
    ep = "ep"
    compile = "compile"


class Album(Base):
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    # Kept for future title-based lookup/dedup; not populated in L1.
    normalized_title = Column(String(500), nullable=True)
    deezer_album_id = Column(String(64), nullable=True)
    record_type = Column(SAEnum(AlbumType, name="album_type"), nullable=True)
    release_date = Column(Date, nullable=True)
    label = Column(String(255), nullable=True)
    artist_id = Column(
        Integer,
        ForeignKey("artists.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    has_artwork = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))

    # Partial unique index: one row per real Deezer album, but a NULL
    # deezer_album_id may repeat freely (albums not yet linked to Deezer).
    # sqlite_where is mandatory so the test harness (create_all on SQLite)
    # reproduces the constraint. Calqué sur uq_artists_deezer_id.
    __table_args__ = (
        Index(
            "uq_albums_deezer_id",
            "deezer_album_id",
            unique=True,
            postgresql_where=text("deezer_album_id IS NOT NULL"),
            sqlite_where=text("deezer_album_id IS NOT NULL"),
        ),
    )

    catalog_links = relationship(
        "CatalogAlbum", back_populates="album", passive_deletes="all"
    )
    artist = relationship("Artist")


class CatalogAlbum(Base):
    __tablename__ = "catalog_albums"

    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True
    )
    album_id = Column(
        Integer,
        ForeignKey("albums.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    catalog = relationship("CatalogEntry", back_populates="album_links")
    album = relationship("Album", back_populates="catalog_links")
