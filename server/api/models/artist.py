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
    Text,
    text,
)
from sqlalchemy.orm import relationship


class Artist(Base):
    __tablename__ = "artists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False)
    normalized_name = Column(String(500), unique=True, nullable=False)
    real_name = Column(String(255), nullable=True)
    country = Column(String(2), nullable=True)
    deezer_id = Column(String(64), nullable=True)
    deezer_searched_at = Column(DateTime(timezone=True), nullable=True)
    soundcloud_id = Column(String(64), nullable=True)
    trackid_id = Column(String(64), nullable=True)
    bio = Column(Text, nullable=True)
    has_artwork = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))

    # Partial unique index: one row per real Deezer artist, but the NOT_FOUND
    # sentinel may repeat freely (many artists confirmed absent from Deezer).
    # Prod already carries this index (created by hand outside migrations, AU3);
    # migration 0034 declares it with IF NOT EXISTS. sqlite_where is mandatory so
    # the test harness (create_all on SQLite) reproduces the constraint.
    __table_args__ = (
        Index(
            "uq_artists_deezer_id",
            "deezer_id",
            unique=True,
            postgresql_where=text("deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND'"),
            sqlite_where=text("deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND'"),
        ),
    )

    aliases = relationship(
        "ArtistAlias", back_populates="artist", cascade="all, delete-orphan"
    )
    set_links = relationship("SetArtist", back_populates="artist")
    catalog_links = relationship("CatalogArtist", back_populates="artist")


class ArtistAlias(Base):
    __tablename__ = "artist_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artist_id = Column(
        Integer,
        ForeignKey("artists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias = Column(String(500), nullable=False)
    normalized_alias = Column(String(500), unique=True, nullable=False)

    artist = relationship("Artist", back_populates="aliases")


class ArtistFlag(Base):
    __tablename__ = "artist_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_artist_string = Column(String(500), nullable=False, unique=True)
    reason = Column(
        String(64), nullable=False
    )  # comma_unresolved | ampersand_ambiguous | ampersand_unknown
    tokens = Column(JSON, nullable=False)  # ["Romy", "Fred again.."]
    deezer_ids = Column(JSON, nullable=False)  # {"Romy": null, "Fred again..": "123"}
    status = Column(
        String(32), nullable=False, default="pending", server_default="pending"
    )  # pending | validated | skipped
    resolved_artist_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
