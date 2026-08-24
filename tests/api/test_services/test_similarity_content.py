"""Content-based neighbours — "Sonne comme" (C9.b), pgvector cosine KNN.

PostgreSQL only: the KNN uses the pgvector ``<=>`` operator, which the SQLite
test harness (``EmbeddingVector`` stored as JSON, no vector ops) cannot run.
"""
import os

import pytest

from models import EMBEDDING_DIM, MODEL_NAME, MODEL_VERSION

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="content-neighbour KNN uses the PostgreSQL-only pgvector <=> operator",
)


def _vec(*prefix):
    """A 1280-d vector from a short non-zero prefix (rest zero-padded)."""
    return list(prefix) + [0.0] * (EMBEDDING_DIM - len(prefix))


async def _add_track(db, title, *, scope="shared", owner_id=None, emb=None):
    from models import CatalogEntry, TrackEmbedding

    entry = CatalogEntry(
        title=title,
        artist="A",
        normalized_key=f"{title}|a",
        scope=scope,
        owner_id=owner_id,
    )
    db.add(entry)
    await db.flush()
    if emb is not None:
        db.add(
            TrackEmbedding(
                catalog_id=entry.id,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                embedding=emb,
            )
        )
    await db.flush()
    return entry


class TestContentNeighbors:
    async def test_ranks_by_cosine_and_excludes_seed(self, db, auth_user):
        from services import similarity_service

        seed = await _add_track(db, "seed", emb=_vec(1.0, 0.0))
        near = await _add_track(db, "near", emb=_vec(1.0, 0.05))  # ~0 distance
        mid = await _add_track(db, "mid", emb=_vec(1.0, 0.6))
        far = await _add_track(db, "far", emb=_vec(0.0, 1.0))  # orthogonal, dist 1
        await db.commit()

        res = await similarity_service.get_content_neighbors(
            db, seed.id, auth_user.id, limit=10
        )
        # Seed excluded; neighbours ranked by cosine distance ascending.
        assert [r["id"] for r in res] == [near.id, mid.id, far.id]
        # Content-score block: labelled "content", decreasing with distance.
        assert res[0]["similarity"]["available_features"] == ["content"]
        assert res[0]["similarity"]["score"] > res[-1]["similarity"]["score"]

    async def test_excludes_foreign_private_rows(self, db, auth_user, admin_user):
        from services import similarity_service

        seed = await _add_track(db, "seed2", emb=_vec(1.0, 0.0))
        await _add_track(db, "vis", emb=_vec(1.0, 0.2))
        # admin_user's private row, even CLOSER than the visible one — must never
        # leak to auth_user (catalog_visible scoping).
        await _add_track(
            db, "secret", scope="private", owner_id=admin_user.id, emb=_vec(1.0, 0.01)
        )
        await db.commit()

        res = await similarity_service.get_content_neighbors(
            db, seed.id, auth_user.id, limit=10
        )
        titles = {r["title"] for r in res}
        assert "vis" in titles
        assert "secret" not in titles

    async def test_empty_when_seed_has_no_embedding(self, db, auth_user):
        from services import similarity_service

        # Seed exists but was never embedded — frequent while the backfill runs;
        # the shelf just stays hidden.
        seed = await _add_track(db, "noemb")
        await _add_track(db, "other", emb=_vec(1.0, 0.0))
        await db.commit()

        res = await similarity_service.get_content_neighbors(
            db, seed.id, auth_user.id, limit=10
        )
        assert res == []
