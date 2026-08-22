"""track_embeddings — versioned audio-embedding storage (C9.a).

Enables the pgvector extension and creates ``track_embeddings``: a surrogate PK,
a CASCADE FK to ``catalog``, ``(model_name, model_version)`` versioning, a
``Vector(1280)`` embedding, a UNIQUE on ``(catalog_id, model_name,
model_version)`` and an HNSW cosine index on the vector for ANN search.

The HNSW index is created via raw SQL (not declared on the model, which must
stay SQLite-buildable for the test harness) — ``alembic/env.py`` excludes it
from autogenerate so the diff stays empty. The extension is created but NEVER
dropped on downgrade (other objects may depend on it).
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0049"
down_revision = "0048"

EMBEDDING_DIM = 1280


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "track_embeddings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "catalog_id",
            sa.Integer,
            sa.ForeignKey("catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "catalog_id",
            "model_name",
            "model_version",
            name="uq_track_embeddings_catalog_model",
        ),
    )
    op.execute(
        "CREATE INDEX ix_track_embeddings_hnsw ON track_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade():
    op.drop_index("ix_track_embeddings_hnsw", table_name="track_embeddings")
    op.drop_table("track_embeddings")
    # The `vector` extension is intentionally left in place on downgrade.
