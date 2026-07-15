"""Tests for services/recommendation_service.py (C4 — "Pour toi").

Similarity is driven here by SET co-occurrence: two tracks sharing a DJ set get
a strong, deterministic similarity score regardless of the (empty in tests)
genre graph.
"""

from datetime import datetime, timezone

from models import CatalogEntry, DJSet, SetTrack, UserOpinion, UserTrack
from services import recommendation_service


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

async def _mk_track(db, title, nk):
    c = CatalogEntry(
        title=title,
        artist="Artist",
        normalized_key=nk,
        bpm=128.0,
        key="8A",
        scope="shared",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _put_in_set(db, catalog_ids, title="Set"):
    s = DJSet(source="trackid", title=title)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    for pos, cid in enumerate(catalog_ids):
        db.add(SetTrack(set_id=s.id, catalog_id=cid, position=pos))
    await db.commit()
    return s


async def _opine(db, user_id, catalog_id, opinion="liked"):
    db.add(
        UserOpinion(
            user_id=user_id,
            entity_type="track",
            entity_key=str(catalog_id),
            opinion=opinion,
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def _add_to_lib(db, user_id, catalog_id):
    db.add(UserTrack(user_id=user_id, catalog_id=catalog_id))
    await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetRecommendations:
    async def test_cold_start_returns_empty(self, db, auth_user):
        # No like, no library → empty list, not an error.
        result = await recommendation_service.get_recommendations(db, auth_user.id)
        assert result.items == []

    async def test_like_yields_recos_excluding_seed(self, db, auth_user):
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        c = await _mk_track(db, "C", "a|c")
        await _put_in_set(db, [seed.id, b.id, c.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        result = await recommendation_service.get_recommendations(db, auth_user.id)
        ids = {i.id for i in result.items}
        assert seed.id not in ids  # never recommend the liked seed itself
        assert ids == {b.id, c.id}
        assert all(i.reco_score > 0 for i in result.items)

    async def test_library_counts_as_seed(self, db, auth_user):
        d = await _mk_track(db, "D", "a|d")
        e = await _mk_track(db, "E", "a|e")
        await _put_in_set(db, [d.id, e.id])
        await _add_to_lib(db, auth_user.id, d.id)

        result = await recommendation_service.get_recommendations(db, auth_user.id)
        ids = {i.id for i in result.items}
        assert e.id in ids  # surfaced via the library seed D
        assert d.id not in ids  # owned → excluded from results

    async def test_dislike_penalises_score(self, db, auth_user):
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        c = await _mk_track(db, "C", "a|c")
        await _put_in_set(db, [seed.id, b.id, c.id], title="S1")

        # A disliked track co-occurring only with C.
        dis = await _mk_track(db, "Dis", "a|dis")
        await _put_in_set(db, [dis.id, c.id], title="S2")

        await _opine(db, auth_user.id, seed.id, "liked")
        await _opine(db, auth_user.id, dis.id, "disliked")

        result = await recommendation_service.get_recommendations(db, auth_user.id)
        scores = {i.id: i.reco_score for i in result.items}
        assert b.id in scores and c.id in scores
        assert dis.id not in scores  # disliked → excluded from results
        # C shares the dislike's set → its score is dragged below B's.
        assert scores[c.id] < scores[b.id]

    async def test_in_lib_candidate_excluded_others_survive(self, db, auth_user):
        seed = await _mk_track(db, "Seed", "a|seed")
        in_lib = await _mk_track(db, "InLib", "a|inlib")
        fresh = await _mk_track(db, "Fresh", "a|fresh")
        await _put_in_set(db, [seed.id, in_lib.id, fresh.id])
        await _opine(db, auth_user.id, seed.id, "liked")
        await _add_to_lib(db, auth_user.id, in_lib.id)

        result = await recommendation_service.get_recommendations(db, auth_user.id)
        ids = {i.id for i in result.items}
        assert in_lib.id not in ids  # owned → excluded even though similar
        assert fresh.id in ids

    async def test_respects_limit(self, db, auth_user):
        seed = await _mk_track(db, "Seed", "a|seed")
        cands = [await _mk_track(db, f"C{i}", f"a|c{i}") for i in range(5)]
        await _put_in_set(db, [seed.id] + [c.id for c in cands])
        await _opine(db, auth_user.id, seed.id, "liked")

        result = await recommendation_service.get_recommendations(db, auth_user.id, limit=2)
        assert len(result.items) == 2

    async def test_deleted_liked_seed_skipped_not_404(self, db, auth_user):
        # A like pointing at a now-invisible/deleted catalog row must be skipped,
        # not bubble a LookupError/404 through the whole recommendation.
        await _opine(db, auth_user.id, 999999, "liked")
        result = await recommendation_service.get_recommendations(db, auth_user.id)
        assert result.items == []

    async def test_context_loaded_once_per_compute(self, db, auth_user, monkeypatch):
        # The 4 similarity maps must be loaded ONCE per compute, not per seed
        # (the L1 perf contract). Two like-seeds → a single load_similarity_context.
        from services import similarity_service

        seed1 = await _mk_track(db, "Seed1", "a|s1")
        seed2 = await _mk_track(db, "Seed2", "a|s2")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed1.id, b.id], title="S1")
        await _put_in_set(db, [seed2.id, b.id], title="S2")
        await _opine(db, auth_user.id, seed1.id, "liked")
        await _opine(db, auth_user.id, seed2.id, "liked")

        calls = {"n": 0}
        real = similarity_service.load_similarity_context

        async def _spy(db_arg):
            calls["n"] += 1
            return await real(db_arg)

        monkeypatch.setattr(similarity_service, "load_similarity_context", _spy)

        result = await recommendation_service.get_recommendations(db, auth_user.id)
        assert calls["n"] == 1  # loaded once, not once per seed
        assert b.id in {i.id for i in result.items}  # still recommended across 2 seeds

    async def test_liked_library_track_not_double_counted(self, db, auth_user):
        # A track that is both liked AND in the library is a single like-seed;
        # the library loop skips it, and it stays excluded from the results.
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _opine(db, auth_user.id, seed.id, "liked")
        await _add_to_lib(db, auth_user.id, seed.id)  # same track also in lib

        result = await recommendation_service.get_recommendations(db, auth_user.id)
        ids = {i.id for i in result.items}
        assert seed.id not in ids
        assert b.id in ids


# ---------------------------------------------------------------------------
# Cache behaviour (fail-open) — small inline fakes, independent of conftest.
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


class _BrokenRedis:
    async def get(self, key):
        raise RuntimeError("redis down")

    async def setex(self, key, ttl, value):
        raise RuntimeError("redis down")

    async def delete(self, key):
        raise RuntimeError("redis down")


class TestRecommendationCache:
    async def test_cache_hit_and_invalidation(self, db, auth_user):
        redis = _FakeRedis()
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        r1 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert {i.id for i in r1.items} == {b.id}
        assert redis.store  # something was cached

        # Add a new co-occurring candidate; the cache should still mask it.
        c = await _mk_track(db, "C", "a|c")
        await _put_in_set(db, [seed.id, c.id])
        r2 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert {i.id for i in r2.items} == {b.id}  # served from cache

        # Invalidate the reco cache AND drop the in-process similarity context:
        # C's set co-occurrence is *context* data (cached ~6h in prod, refreshed
        # nightly), so a recompute only surfaces C once the context is rebuilt —
        # invalidating the per-user reco cache alone is not enough anymore.
        await recommendation_service.invalidate_user(redis, auth_user.id)
        from services.similarity_service import reset_similarity_context_cache
        reset_similarity_context_cache()
        r3 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert c.id in {i.id for i in r3.items}

    async def test_cache_fail_open(self, db, auth_user):
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        # Every Redis call raises → the service must still compute live.
        result = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=_BrokenRedis()
        )
        assert {i.id for i in result.items} == {b.id}
