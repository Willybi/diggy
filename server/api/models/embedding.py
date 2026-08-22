"""Track audio-embedding storage (C9.a).

Versioned per ``(model_name, model_version)`` so several embedding models — or
successive versions of one — can coexist and be re-derived without dropping the
others. The default C9 v1 model (frozen at the C9.0-bis benchmark) is
Discogs-EffNet, 1280-d. These constants are re-used by the backfill lot.
"""
from database import Base
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from .base import EmbeddingVector

# Frozen C9.a identity of the default embedding model (see MEMORY C9.0-bis).
MODEL_NAME = "discogs-effnet"
MODEL_VERSION = "bs64-1"
EMBEDDING_DIM = 1280


class TrackEmbedding(Base):
    __tablename__ = "track_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), nullable=False
    )
    model_name = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False)
    embedding = Column(EmbeddingVector(EMBEDDING_DIM), nullable=False)
    created_at = Column(DateTime(timezone=True))

    __table_args__ = (
        # One embedding per (track, model, version). The leading catalog_id also
        # backs FK-cascade lookups, so no separate index is declared. The HNSW
        # cosine index on `embedding` lives in migration 0049 only — SQLite (the
        # test dialect) cannot build it.
        UniqueConstraint(
            "catalog_id",
            "model_name",
            "model_version",
            name="uq_track_embeddings_catalog_model",
        ),
    )
