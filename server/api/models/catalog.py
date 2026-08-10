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
    SmallInteger,
    String,
    Text,
    func,
    text,
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
    bpm_source = Column(String(20), nullable=True)
    key_source = Column(String(20), nullable=True)
    # E2.c — BPM analysis tracking (estimated BPM from Deezer previews). Stamped
    # once an analysis produced a VERDICT (ok OR low_conf), never on a transient
    # network failure, so a candidate is not re-analyzed forever.
    bpm_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    bpm_analysis_attempts = Column(
        Integer, nullable=False, server_default="0", default=0
    )
    label = Column(String(255), nullable=True)
    deezer_searched_at = Column(DateTime(timezone=True), nullable=True)
    beatport_searched_at = Column(DateTime(timezone=True), nullable=True)
    deezer_search_attempts = Column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
    beatport_search_attempts = Column(
        SmallInteger, nullable=False, server_default="0", default=0
    )

    __table_args__ = (
        Index(
            "ix_catalog_deezer_id",
            "deezer_id",
            postgresql_where=text("deezer_id IS NOT NULL"),
        ),
        Index(
            "ix_catalog_beatport_id",
            "beatport_id",
            postgresql_where=text("beatport_id IS NOT NULL"),
        ),
        Index("ix_catalog_genres", "genres", postgresql_using="gin"),
        Index("ix_catalog_scope", "scope"),
        Index(
            "ix_catalog_owner",
            "owner_id",
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
        Index(
            "ix_catalog_deezer_searched_at",
            "deezer_searched_at",
            postgresql_where=text("deezer_id IS NULL"),
        ),
        Index(
            "ix_catalog_beatport_searched_at",
            "beatport_searched_at",
            postgresql_where=text("beatport_id IS NULL"),
        ),
        # Explorer query-builder (D6 p.1): filter/sort columns of GET /catalog/
        Index("ix_catalog_bpm", "bpm"),
        Index("ix_catalog_key", "key"),
        Index("ix_catalog_duration_ms", "duration_ms"),
        Index("ix_catalog_release_date", "release_date"),
        # Explorer sort default: created_at DESC then id DESC (stable window
        # tie-break). Prod (PG) adds NULLS LAST via migration 0044 to match the
        # ORDER BY exactly; it is omitted here because SQLite's CREATE INDEX
        # rejects NULLS LAST (it only allows it in ORDER BY) and the test suite
        # builds this schema via create_all on SQLite — where DESC already
        # orders NULLs last anyway, so the two are equivalent on that dialect.
        Index(
            "ix_catalog_created_at_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        # AV3 — partial index mirroring bpm_analysis_candidate_filter() (E2.c backlog)
        Index(
            "ix_catalog_bpm_analysis_backlog",
            "id",
            postgresql_where=text(
                "has_preview AND bpm IS NULL AND bpm_analyzed_at IS NULL "
                "AND deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND'"
            ),
        ),
    )

    artist_links = relationship(
        "CatalogArtist",
        back_populates="catalog",
        cascade="all, delete-orphan",
    )


def bpm_analysis_candidate_filter():
    """Source unique du prédicat backlog analyse BPM (E2.c), partagé par la tâche
    nocturne et l'admin. Une entrée est candidate à l'estimation de BPM depuis sa
    preview Deezer si : elle a une preview, n'a pas encore de BPM, possède un
    deezer_id réel (pas le sentinelle NOT_FOUND) et n'a jamais été analysée.
    Conditions ET-combinables via .where(*bpm_analysis_candidate_filter())."""
    return [
        CatalogEntry.has_preview.is_(True),
        CatalogEntry.bpm.is_(None),
        CatalogEntry.deezer_id.isnot(None),
        CatalogEntry.deezer_id != "NOT_FOUND",
        CatalogEntry.bpm_analyzed_at.is_(None),
    ]


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
        index=True,
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
    avis = Column(String(20), nullable=True)
    has_artwork = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    catalog = relationship("CatalogEntry")
    user = relationship("User")
