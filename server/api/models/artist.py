from database import Base
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
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
    # E1-style re-scan accounting for the Deezer link search (mirror of
    # catalog.deezer_search_attempts): a no-match artist is retried after 30
    # then 90 days and abandoned for good after 3 attempts. Backlog loop-safe.
    deezer_search_attempts = Column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
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
        # Backs the link-candidate tier queries (unlinked artists, by searched_at).
        # postgresql_where ONLY — a non-unique perf index, so the test harness may
        # create it as a full index on SQLite (precedent: ix_catalog_deezer_searched_at).
        Index(
            "ix_artists_deezer_searched_at",
            "deezer_searched_at",
            postgresql_where=text("deezer_id IS NULL"),
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


class FollowedArtist(Base):
    __tablename__ = "followed_artists"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    artist_id = Column(
        Integer,
        ForeignKey("artists.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        index=True,
    )
    followed_at = Column(DateTime(timezone=True), server_default=func.now())


class ArtistActivity(Base):
    __tablename__ = "artist_activity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artist_id = Column(
        Integer,
        ForeignKey("artists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Application values: 'release' | 'set' (plain String, no PG enum)
    activity_type = Column(String(16), nullable=False)
    source = Column(String(32), nullable=False)  # 'deezer' | 'trackid'
    # Deezer album id, or Diggy set id as string
    external_id = Column(String(64), nullable=False)
    title = Column(String(500))
    external_url = Column(Text, nullable=True)
    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="SET NULL"), nullable=True
    )
    set_id = Column(Integer, ForeignKey("sets.id", ondelete="SET NULL"), nullable=True)
    detected_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    # Never store external image URLs here (has_artwork/MinIO only)
    payload = Column(JSON, nullable=True)

    # Idempotence guarantee for the activity worker
    __table_args__ = (
        UniqueConstraint(
            "artist_id",
            "activity_type",
            "source",
            "external_id",
            name="uq_artist_activity_ext",
        ),
    )


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
