"""Content (audio embeddings) channel of the reco (C9.c, lot L2).

Retrieval-first "Pour toi" adds a surpondered ADDITIVE bonus per (seed, audio
neighbour) on top of the metadata score. These behaviours live entirely on the
PostgreSQL pgvector path (``content_neighbor_ids`` returns ``{}`` on SQLite, so
the SQLite golden tests cover the co-occ-only parity separately).

PostgreSQL only: the KNN uses the pgvector ``<=>`` operator the SQLite harness
(``EmbeddingVector`` stored as JSON) cannot run.
"""
import dataclasses
import os

import pytest

from models import (
    EMBEDDING_DIM,
    MODEL_NAME,
    MODEL_VERSION,
    CatalogEntry,
    DJSet,
    SetTrack,
    TrackEmbedding,
    UserOpinion,
)
from services import recommendation_service

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="the reco content channel uses the PostgreSQL-only pgvector <=> operator",
)


def _vec(*prefix):
    """A 1280-d vector from a short non-zero prefix (rest zero-padded)."""
    return list(prefix) + [0.0] * (EMBEDDING_DIM - len(prefix))


async def _mk_track(db, title, nk, *, bpm=128.0, emb=None):
    c = CatalogEntry(
        title=title,
        artist="Artist",
        normalized_key=nk,
        bpm=bpm,
        key="8A",
        scope="shared",
    )
    db.add(c)
    await db.flush()
    if emb is not None:
        db.add(
            TrackEmbedding(
                catalog_id=c.id,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                embedding=emb,
            )
        )
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


async def _like(db, user_id, catalog_id):
    from datetime import datetime, timezone

    db.add(
        UserOpinion(
            user_id=user_id,
            entity_type="track",
            entity_key=str(catalog_id),
            opinion="liked",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


class TestContentChannel:
    async def test_audio_neighbour_without_cooccurrence_surfaces(self, db, auth_user):
        # Cold-start C9: a candidate reachable ONLY through the audio KNN (no
        # shared set/playlist, no genre) still surfaces, on its content bonus.
        seed = await _mk_track(db, "Seed", "a|seed", emb=_vec(1.0, 0.0))
        audio = await _mk_track(db, "Audio", "a|audio", emb=_vec(1.0, 0.05))
        await _like(db, auth_user.id, seed.id)

        result = await recommendation_service._compute(db, auth_user.id)
        ids = {i.id for i in result.items}
        assert audio.id in ids  # surfaced by the content channel alone
        assert seed.id not in ids

        # With CONTENT_BONUS disabled it has no metadata link → it disappears,
        # proving the surfacing came from the content channel.
        cfg0 = dataclasses.replace(recommendation_service.CFG, CONTENT_BONUS=0.0)
        recommendation_service.CFG = cfg0
        try:
            result0 = await recommendation_service._compute(db, auth_user.id)
        finally:
            recommendation_service.CFG = dataclasses.replace(cfg0, CONTENT_BONUS=1.0)
        assert audio.id not in {i.id for i in result0.items}

    async def test_content_bonus_orders_equal_metadata_candidates(self, db, auth_user):
        # Two candidates with IDENTICAL metadata similarity (both share exactly
        # the seed's single set, no genres) are ordered by their audio proximity.
        seed = await _mk_track(db, "Seed", "a|seed", emb=_vec(1.0, 0.0))
        near = await _mk_track(db, "Near", "a|near", emb=_vec(1.0, 0.05))
        far = await _mk_track(db, "Far", "a|far", emb=_vec(1.0, 0.8))
        await _put_in_set(db, [seed.id, near.id, far.id])
        await _like(db, auth_user.id, seed.id)

        result = await recommendation_service._compute(db, auth_user.id)
        scores = {i.id: i.reco_score for i in result.items}
        assert near.id in scores and far.id in scores
        # Same metadata score, so the closer audio neighbour ranks strictly higher.
        assert scores[near.id] > scores[far.id]
        order = [i.id for i in result.items]
        assert order.index(near.id) < order.index(far.id)

    async def test_non_embedded_cooc_candidate_keeps_exact_meta_score(
        self, db, auth_user, monkeypatch
    ):
        # A non-embedded candidate reached via co-occurrence is NEVER in any KNN,
        # so the content channel must leave its score byte-for-byte unchanged —
        # the bonus is additive, not a blend.
        seed = await _mk_track(db, "Seed", "a|seed", emb=_vec(1.0, 0.0))
        audio = await _mk_track(db, "Audio", "a|audio", emb=_vec(1.0, 0.05))
        plain = await _mk_track(db, "Plain", "a|plain", emb=None)  # no embedding
        await _put_in_set(db, [seed.id, audio.id, plain.id])
        await _like(db, auth_user.id, seed.id)

        # Default CONTENT_BONUS (content channel active for `audio`).
        r_default = await recommendation_service._compute(db, auth_user.id)
        s_default = {i.id: i.reco_score for i in r_default.items}

        # CONTENT_BONUS = 0 → the content channel adds nothing.
        monkeypatch.setattr(
            recommendation_service,
            "CFG",
            dataclasses.replace(recommendation_service.CFG, CONTENT_BONUS=0.0),
        )
        r_zero = await recommendation_service._compute(db, auth_user.id)
        s_zero = {i.id: i.reco_score for i in r_zero.items}

        # The non-embedded co-occ candidate is identical in both runs.
        assert s_default[plain.id] == s_zero[plain.id]
        # The embedded co-occ candidate DID gain from the content channel.
        assert s_default[audio.id] > s_zero[audio.id]
