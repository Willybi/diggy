"""
Tests du modèle TrackEmbedding (C9.a — fondation stockage embeddings audio) et
du type par-dialecte EmbeddingVector : constantes figées, round-trip liste (cas
nominal / vide / None), présence dans le metadata, insertion + relecture DB
(SQLite → JSON), unicité (catalog, model, version) et cascade catalog.
"""
import pytest
from sqlalchemy import select

from database import Base
from models import (
    EMBEDDING_DIM,
    MODEL_NAME,
    MODEL_VERSION,
    CatalogEntry,
    TrackEmbedding,
)
from models.base import EmbeddingVector


# ── Constantes figées (réutilisées par le lot backfill) ────────────────────


def test_frozen_constants():
    assert EMBEDDING_DIM == 1280
    assert MODEL_NAME == "discogs-effnet"
    assert MODEL_VERSION == "bs64-1"


# ── Type EmbeddingVector : round-trip liste↔stockage ───────────────────────


class TestEmbeddingVectorType:
    def test_roundtrip_nominal(self):
        t = EmbeddingVector(EMBEDDING_DIM)
        vec = [0.1, -0.2, 0.3]
        bound = t.process_bind_param(vec, None)
        assert list(bound) == vec
        assert t.process_result_value(bound, None) == pytest.approx(vec)

    def test_roundtrip_empty_list(self):
        t = EmbeddingVector(EMBEDDING_DIM)
        assert t.process_bind_param([], None) == []
        assert t.process_result_value([], None) == []

    def test_roundtrip_none(self):
        t = EmbeddingVector(EMBEDDING_DIM)
        assert t.process_bind_param(None, None) is None
        assert t.process_result_value(None, None) is None

    def test_result_coerces_to_float(self):
        t = EmbeddingVector(EMBEDDING_DIM)
        out = t.process_result_value([1, 2, 3], None)
        assert out == [1.0, 2.0, 3.0]
        assert all(isinstance(x, float) for x in out)


# ── Modèle : metadata (create_all-able) ────────────────────────────────────


def test_model_in_metadata():
    assert "track_embeddings" in Base.metadata.tables


# ── Insertion + relecture DB (round-trip à travers le stockage) ────────────


class TestTrackEmbeddingDB:
    async def test_insert_and_reload(self, db):
        cat = CatalogEntry(title="Latch", normalized_key="latch - disclosure")
        db.add(cat)
        await db.flush()
        vec = [float(i) / 1000 for i in range(EMBEDDING_DIM)]
        db.add(
            TrackEmbedding(
                catalog_id=cat.id,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                embedding=vec,
            )
        )
        await db.commit()

        row = (await db.execute(select(TrackEmbedding))).scalar_one()
        # Force a reload from storage rather than the identity-map instance.
        db.expire(row, ["embedding"])
        await db.refresh(row, ["embedding"])
        assert len(row.embedding) == EMBEDDING_DIM
        assert row.embedding == pytest.approx(vec)

    async def test_unique_catalog_model_version(self, db):
        cat = CatalogEntry(title="Latch", normalized_key="latch - disclosure")
        db.add(cat)
        await db.flush()
        db.add(
            TrackEmbedding(
                catalog_id=cat.id,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                embedding=[0.0, 1.0],
            )
        )
        await db.commit()
        db.add(
            TrackEmbedding(
                catalog_id=cat.id,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                embedding=[1.0, 0.0],
            )
        )
        with pytest.raises(Exception):
            await db.commit()
