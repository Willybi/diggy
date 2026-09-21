"""Shared retrieval core (C9.c, lot L1) — bounded per-seed candidate retrieval.

``content_neighbor_ids`` uses the PostgreSQL-only pgvector ``<=>`` operator, so
its ranking/visibility tests are PG-only (mirroring test_similarity_content.py).
The dialect guard, ``cooc_candidate_ids`` and ``load_candidates_by_ids`` are
dialect-neutral and run on the default SQLite harness.
"""
import os

import pytest

from models import EMBEDDING_DIM, MODEL_NAME, MODEL_VERSION
from services import similarity_service

_is_pg = os.environ.get("DATABASE_URL", "").startswith("postgresql")


def _vec(*prefix):
    """A 1280-d vector from a short non-zero prefix (rest zero-padded)."""
    return list(prefix) + [0.0] * (EMBEDDING_DIM - len(prefix))


async def _add_track(db, title, *, scope="shared", owner_id=None, emb=None, **kw):
    from models import CatalogEntry, TrackEmbedding

    entry = CatalogEntry(
        title=title,
        artist="A",
        normalized_key=f"{title}|a",
        scope=scope,
        owner_id=owner_id,
        bpm=kw.get("bpm"),
        label=kw.get("label"),
        release_date=kw.get("release_date"),
        genres=kw.get("genres", []),
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


@pytest.mark.skipif(
    not _is_pg,
    reason="content-neighbour KNN uses the PostgreSQL-only pgvector <=> operator",
)
class TestContentNeighborIds:
    async def test_ranks_by_distance_and_excludes_seed(self, db, auth_user):
        seed = await _add_track(db, "seed", emb=_vec(1.0, 0.0))
        near = await _add_track(db, "near", emb=_vec(1.0, 0.05))
        mid = await _add_track(db, "mid", emb=_vec(1.0, 0.6))
        far = await _add_track(db, "far", emb=_vec(0.0, 1.0))
        await db.commit()

        out = await similarity_service.content_neighbor_ids(
            db, [seed.id], auth_user.id
        )
        assert set(out) == {seed.id}
        pairs = out[seed.id]
        # Ranked by ascending cosine distance, seed excluded.
        assert [cid for cid, _ in pairs] == [near.id, mid.id, far.id]
        dists = [d for _, d in pairs]
        assert dists == sorted(dists)

    async def test_excludes_foreign_private_rows(self, db, auth_user, admin_user):
        seed = await _add_track(db, "seed2", emb=_vec(1.0, 0.0))
        vis = await _add_track(db, "vis", emb=_vec(1.0, 0.2))
        # admin_user's private row, even closer — must never leak to auth_user.
        await _add_track(
            db, "secret", scope="private", owner_id=admin_user.id, emb=_vec(1.0, 0.01)
        )
        await db.commit()

        out = await similarity_service.content_neighbor_ids(
            db, [seed.id], auth_user.id
        )
        assert [cid for cid, _ in out[seed.id]] == [vis.id]

    async def test_seed_without_embedding_absent(self, db, auth_user):
        seed = await _add_track(db, "noemb")  # never embedded
        emb_seed = await _add_track(db, "withemb", emb=_vec(1.0, 0.0))
        await _add_track(db, "other", emb=_vec(1.0, 0.1))
        await db.commit()

        out = await similarity_service.content_neighbor_ids(
            db, [seed.id, emb_seed.id], auth_user.id
        )
        # The un-embedded seed is simply absent; the embedded one is present.
        assert set(out) == {emb_seed.id}

    async def test_per_seed_k_respected(self, db, auth_user):
        seed = await _add_track(db, "seedk", emb=_vec(1.0, 0.0))
        for i in range(5):
            await _add_track(db, f"n{i}", emb=_vec(1.0, 0.1 * (i + 1)))
        await db.commit()

        out = await similarity_service.content_neighbor_ids(
            db, [seed.id], auth_user.id, per_seed_k=2
        )
        assert len(out[seed.id]) == 2


@pytest.mark.skipif(
    _is_pg,
    reason="dialect guard asserts the NON-postgresql short-circuit",
)
class TestDialectGuard:
    async def test_returns_empty_without_touching_db(self, db, auth_user):
        # On SQLite the content channel is a no-op: {} and no query error even
        # when the seed ids exist.
        out = await similarity_service.content_neighbor_ids(
            db, [1, 2, 3], auth_user.id
        )
        assert out == {}


class TestCoocCandidateIds:
    def _ctx(self, *, set_inverted=None, playlist_inverted=None):
        return similarity_service.SimilarityContext(
            name_to_node={},
            parent_map={},
            label_counts={},
            playlist_map={},
            set_map={},
            album_map={},
            set_inverted={k: frozenset(v) for k, v in (set_inverted or {}).items()},
            playlist_inverted={
                k: frozenset(v) for k, v in (playlist_inverted or {}).items()
            },
        )

    def test_union_of_set_and_playlist_cooccurrence(self):
        ctx = self._ctx(
            set_inverted={10: {1, 2, 3}, 11: {4}},
            playlist_inverted={20: {3, 5}, 21: {9}},
        )
        # Seed shares set 10 and playlist 20 → union of both, cap not reached.
        got = similarity_service.cooc_candidate_ids(ctx, {10}, {20}, cap=100)
        assert got == {1, 2, 3, 5}

    def test_missing_group_ids_are_ignored(self):
        ctx = self._ctx(set_inverted={10: {1, 2}})
        got = similarity_service.cooc_candidate_ids(ctx, {10, 999}, {888}, cap=100)
        assert got == {1, 2}

    def test_cap_truncates_deterministically(self):
        ctx = self._ctx(set_inverted={10: set(range(100, 200))})
        got = similarity_service.cooc_candidate_ids(ctx, {10}, set(), cap=5)
        # Stable ascending-id truncation → reproducible.
        assert got == {100, 101, 102, 103, 104}
        again = similarity_service.cooc_candidate_ids(ctx, {10}, set(), cap=5)
        assert got == again

    def test_empty_seed_groups(self):
        ctx = self._ctx(set_inverted={10: {1}})
        assert similarity_service.cooc_candidate_ids(ctx, set(), set(), cap=5) == set()


class TestLoadCandidatesByIds:
    async def test_empty_ids_no_query(self, db):
        ctx = await similarity_service.load_similarity_context(db)
        assert await similarity_service.load_candidates_by_ids(db, None, ctx, []) == {}

    async def test_features_and_projection(self, db):
        from datetime import date

        a = await _add_track(
            db, "A", bpm=128.0, label="Lbl", release_date=date(2024, 1, 1)
        )
        b = await _add_track(db, "B", bpm=None)
        await db.commit()

        ctx = await similarity_service.load_similarity_context(db)
        pool = await similarity_service.load_candidates_by_ids(
            db, None, ctx, [a.id, b.id]
        )
        assert set(pool) == {a.id, b.id}
        ca = pool[a.id]
        assert ca.id == a.id
        assert ca.bpm == 128.0
        assert ca.label == "Lbl"
        assert ca.release_date == date(2024, 1, 1)
        assert ca.album_id is None
        assert pool[b.id].bpm is None

    async def test_visibility_enforced(self, db, auth_user, admin_user):
        shared = await _add_track(db, "shared")
        secret = await _add_track(
            db, "secret", scope="private", owner_id=admin_user.id
        )
        await db.commit()

        ctx = await similarity_service.load_similarity_context(db)
        # auth_user requests both ids; the foreign private row is dropped.
        pool = await similarity_service.load_candidates_by_ids(
            db, auth_user.id, ctx, [shared.id, secret.id]
        )
        assert set(pool) == {shared.id}
