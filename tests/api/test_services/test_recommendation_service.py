"""Tests for services/recommendation_service.py (C4 — "Pour toi").

Similarity is driven here by SET co-occurrence: two tracks sharing a DJ set get
a strong, deterministic similarity score regardless of the (empty in tests)
genre graph.
"""

import dataclasses
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

    async def test_empty_content_channel_leaves_results_unchanged(
        self, db, auth_user, monkeypatch
    ):
        # No embeddings anywhere → the audio content channel is empty (on SQLite
        # content_neighbor_ids returns {} by construction; here also on PG since
        # no track is embedded), so CONTENT_BONUS must not change a single score:
        # the retrieval-first compute reduces to pure co-occurrence scoring.
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        c = await _mk_track(db, "C", "a|c")
        await _put_in_set(db, [seed.id, b.id, c.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        r1 = await recommendation_service._compute(db, auth_user.id)
        s1 = {i.id: i.reco_score for i in r1.items}

        monkeypatch.setattr(
            recommendation_service,
            "CFG",
            dataclasses.replace(recommendation_service.CFG, CONTENT_BONUS=0.0),
        )
        r0 = await recommendation_service._compute(db, auth_user.id)
        s0 = {i.id: i.reco_score for i in r0.items}

        assert s1 == s0  # content channel empty → byte-identical scores
        assert set(s1) == {b.id, c.id}


# ---------------------------------------------------------------------------
# Cache behaviour (fail-open) — small inline fakes, independent of conftest.
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, ex=None):
        # Emulate SET NX: refuse if the key already holds a value.
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


class _BrokenRedis:
    async def get(self, key):
        raise RuntimeError("redis down")

    async def set(self, key, value, nx=False, ex=None):
        raise RuntimeError("redis down")

    async def setex(self, key, ttl, value):
        raise RuntimeError("redis down")

    async def delete(self, key):
        raise RuntimeError("redis down")


def _spy_dispatch(monkeypatch):
    """Capture schedule_precompute's send_task calls (celery is conftest-mocked)."""
    import celery_client

    sent = []

    def _send(name, args=None, **kwargs):
        sent.append((name, tuple(args or ())))

    monkeypatch.setattr(celery_client.celery, "send_task", _send)
    return sent


class TestRecommendationCache:
    async def test_warm_cache_served_and_masks_new_data(
        self, db, auth_user, monkeypatch
    ):
        redis = _FakeRedis()
        sent = _spy_dispatch(monkeypatch)
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        # Warm the cache exactly the way the worker task does.
        full = await recommendation_service._compute(db, auth_user.id)
        await recommendation_service._cache_set(redis, auth_user.id, full)

        r1 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert {i.id for i in r1.items} == {b.id}
        assert sent == []  # warm hit → no dispatch

        # A new co-occurring candidate stays masked by the cache until invalidation.
        c = await _mk_track(db, "C", "a|c")
        await _put_in_set(db, [seed.id, c.id])
        r2 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert {i.id for i in r2.items} == {b.id}  # served from cache

        # Invalidation → cold miss: empty list this once + ONE worker dispatch
        # (the api never recomputes inline).
        await recommendation_service.invalidate_user(redis, auth_user.id)
        r3 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert r3.items == []
        assert sent == [
            ("workers.tasks.precompute_user_recommendations", (auth_user.id,))
        ]

    async def test_broken_redis_degrades_to_empty(self, db, auth_user):
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        # Redis down → no cache AND no broker (same instance): degrade to an
        # empty list; never raise, never fall back to the ~60s inline compute.
        result = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=_BrokenRedis()
        )
        assert result.items == []


class TestSchedulePrecompute:
    """Cold path = dispatch-and-degrade: the api never computes inline."""

    async def test_cold_miss_dispatches_once_and_returns_empty(
        self, db, auth_user, monkeypatch
    ):
        redis = _FakeRedis()
        sent = _spy_dispatch(monkeypatch)
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _opine(db, auth_user.id, seed.id, "liked")

        async def _boom(*a, **k):
            raise AssertionError("the api must never compute inline on a cold cache")

        monkeypatch.setattr(recommendation_service, "_compute", _boom)

        r1 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert r1.items == []
        assert sent == [
            ("workers.tasks.precompute_user_recommendations", (auth_user.id,))
        ]
        assert recommendation_service._dispatch_guard_key(auth_user.id) in redis.store

        # Second miss while the guard holds → deduped, no second dispatch.
        r2 = await recommendation_service.get_recommendations(
            db, auth_user.id, redis=redis
        )
        assert r2.items == []
        assert len(sent) == 1

    async def test_dispatch_failure_frees_guard(self, db, auth_user, monkeypatch):
        import celery_client

        redis = _FakeRedis()

        def _send(*a, **k):
            raise RuntimeError("broker down")

        monkeypatch.setattr(celery_client.celery, "send_task", _send)

        ok = await recommendation_service.schedule_precompute(redis, auth_user.id)
        assert ok is False
        # Guard freed so a later request can retry the dispatch.
        assert (
            recommendation_service._dispatch_guard_key(auth_user.id)
            not in redis.store
        )

    async def test_avis_route_invalidates_then_redispatches(
        self, db, auth_user, monkeypatch
    ):
        # The b-lot contract: an opinion change drops the cache AND schedules the
        # async re-warm (catalog_service avis path — same wiring as the opinions
        # router).
        from services import catalog_service

        redis = _FakeRedis()
        sent = _spy_dispatch(monkeypatch)
        track = await _mk_track(db, "T", "a|t")
        redis.store[recommendation_service._cache_key(auth_user.id)] = "stale"

        await catalog_service.update_avis(db, track.id, auth_user.id, "liked", redis=redis)

        assert recommendation_service._cache_key(auth_user.id) not in redis.store
        assert sent == [
            ("workers.tasks.precompute_user_recommendations", (auth_user.id,))
        ]
