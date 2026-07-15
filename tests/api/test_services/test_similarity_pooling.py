"""Equivalence anchors for the candidate-pool refactor of the similarity engine.

The pooling optimisation (build the visible catalog ONCE, precompute the
seed-independent candidate terms, score every seed in memory) must be a PURE
optimisation: same ids, same scores, same components as the pre-pool per-seed
path. The concrete expected values below were captured from the pre-refactor
implementation on the same dataset, so they anchor byte-for-byte equivalence.
"""

from datetime import date, datetime, timezone

from services import recommendation_service, similarity_service


async def _mk(db, **data):
    from models import CatalogEntry

    e = CatalogEntry(
        title=data["title"],
        artist=data.get("artist", "Artist"),
        normalized_key=data["nk"],
        bpm=data.get("bpm"),
        key=data.get("key"),
        label=data.get("label"),
        release_date=data.get("release_date"),
        genres=data.get("genres", []),
        scope="shared",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _seed_genre_graph(db):
    """House parent with Tech House / Deep House children (both weight-0.5 to it)."""
    from models import GenreEdge, GenreMapping, GenreNode

    parent = GenreNode(wikidata_id="Q-house", label="House")
    db.add(parent)
    await db.commit()
    await db.refresh(parent)
    tech = GenreNode(wikidata_id="Q-tech", label="Tech House")
    deep = GenreNode(wikidata_id="Q-deep", label="Deep House")
    db.add_all([tech, deep])
    await db.commit()
    await db.refresh(tech)
    await db.refresh(deep)
    db.add_all([
        GenreMapping(raw_name="Tech House", node_id=tech.id),
        GenreMapping(raw_name="Deep House", node_id=deep.id),
        GenreMapping(raw_name="House", node_id=parent.id),
        GenreEdge(from_node_id=tech.id, to_node_id=parent.id, type="parent", source="test"),
        GenreEdge(from_node_id=deep.id, to_node_id=parent.id, type="parent", source="test"),
    ])
    await db.commit()


async def _rich_dataset(db):
    """Ref + candidates exercising every scoring segment plus both co-occurrences.

    * close  — near BPM + same genre + same valid label + same era (style+context)
    * deep   — near BPM + sibling genre (parent overlap) + same label + era
    * half   — half-time BPM + sibling genre + different label + far era
    * nobpm  — bpm IS NULL (must still be a candidate) + far era
    * far    — out of every BPM window, no co-occurrence → NOT a candidate
    * coocpl — far BPM but shares a radar playlist with ref (co-occurrence-only)
    * coocset— far BPM but shares a DJ set with ref (co-occurrence-only)

    "Drumcode" is on ref/close/deep (>= LABEL_MIN_TRACKS) so it counts as a valid
    label; "Toolroom" is on half/nobpm/coocpl (also valid but never matches ref).
    """
    from models import DJSet, RadarTrack, SetTrack, WatchedEntity

    await _seed_genre_graph(db)
    ref = await _mk(db, title="Ref", nk="a|ref", bpm=128.0, key="8A",
                    label="Drumcode", release_date=date(2025, 1, 1),
                    genres=["Tech House"])
    close = await _mk(db, title="Close", nk="a|close", bpm=129.0, key="8A",
                      label="Drumcode", release_date=date(2025, 3, 1),
                      genres=["Tech House"])
    deep = await _mk(db, title="Deep", nk="a|deep", bpm=126.0, key="9A",
                     label="Drumcode", release_date=date(2024, 1, 1),
                     genres=["Deep House"])
    half = await _mk(db, title="Half", nk="a|half", bpm=64.0, key="8A",
                     label="Toolroom", release_date=date(2020, 1, 1),
                     genres=["Deep House"])
    nobpm = await _mk(db, title="NoBpm", nk="a|nobpm", bpm=None, key=None,
                      label="Toolroom", release_date=date(2018, 1, 1),
                      genres=[])
    far = await _mk(db, title="Far", nk="a|far", bpm=180.0, key="3B",
                    label=None, release_date=date(2010, 1, 1), genres=[])
    coocpl = await _mk(db, title="CoocPl", nk="a|coocpl", bpm=200.0, key="3B",
                       label="Toolroom", release_date=date(2015, 1, 1), genres=[])
    coocset = await _mk(db, title="CoocSet", nk="a|coocset", bpm=205.0, key="5A",
                        label=None, release_date=date(2012, 1, 1), genres=[])

    entity = WatchedEntity(external_id="pl1", source="deezer", type="playlist", title="P")
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    db.add(RadarTrack(watched_entity_id=entity.id, external_track_id="r-ref",
                      source="deezer", title="Ref", catalog_id=ref.id))
    db.add(RadarTrack(watched_entity_id=entity.id, external_track_id="r-pl",
                      source="deezer", title="CoocPl", catalog_id=coocpl.id))

    s = DJSet(source="trackid", title="S", external_id="set1")
    db.add(s)
    await db.commit()
    await db.refresh(s)
    db.add(SetTrack(set_id=s.id, catalog_id=ref.id, position=1))
    db.add(SetTrack(set_id=s.id, catalog_id=coocset.id, position=2))
    await db.commit()

    return {
        "ref": ref, "close": close, "deep": deep, "half": half,
        "nobpm": nobpm, "far": far, "coocpl": coocpl, "coocset": coocset,
    }


# Ordered (name, score, components, available) captured from the pre-pool engine.
_EXPECTED_SIMILAR = [
    ("close", 0.3633, {"sets": 0.0, "playlists": 0.0, "style": 1.9067, "context": 1.0},
     ["style", "context"]),
    ("coocset", 0.3242, {"sets": 2.594, "playlists": 0.0, "style": 0.0, "context": 0.0},
     ["sets"]),
    ("deep", 0.1703, {"sets": 0.0, "playlists": 0.0, "style": 0.3627, "context": 1.0},
     ["style", "context"]),
    ("coocpl", 0.1377, {"sets": 0.0, "playlists": 1.1013, "style": 0.0, "context": 0.0},
     ["playlists"]),
    ("half", 0.0743, {"sets": 0.0, "playlists": 0.0, "style": 0.372, "context": 0.2222},
     ["style", "context"]),
    ("nobpm", 0.0167, {"sets": 0.0, "playlists": 0.0, "style": 0.0, "context": 0.1333},
     ["context"]),
]


class TestPoolEquivalence:
    async def test_scoring_matches_pre_pool_reference(self, db):
        # (a) The pooled path reproduces the exact ordered ids, scores,
        # components and available_features of the pre-refactor engine.
        ds = await _rich_dataset(db)
        res = await similarity_service.get_similar_tracks(
            db, ds["ref"].id, limit=50, top_n=50, score_floor=0.0,
        )

        got = [
            (r["id"], r["similarity"]["score"], r["similarity"]["components"],
             r["similarity"]["available_features"])
            for r in res
        ]
        expected = [
            (ds[name].id, score, comps, avail)
            for name, score, comps, avail in _EXPECTED_SIMILAR
        ]
        assert got == expected
        # "far" (out of every BPM window, no co-occurrence) is NOT a candidate:
        # anchors the union(BPM-window-or-null, co-occurrence) candidate set.
        assert ds["far"].id not in {r["id"] for r in res}

    async def test_null_bpm_candidate_included(self, db):
        # (c) A candidate with bpm IS NULL stays in the candidate union and is
        # scored (context-only here), never dropped by the BPM window.
        ds = await _rich_dataset(db)
        res = await similarity_service.get_similar_tracks(
            db, ds["ref"].id, limit=50, top_n=50, score_floor=0.0,
        )
        row = next(r for r in res if r["id"] == ds["nobpm"].id)
        assert row["similarity"]["score"] == 0.0167
        assert row["bpm"] is None

    async def test_low_level_pool_matches_get_similar_tracks(self, db):
        # load_candidate_pool + _score_seed_against_pool + _build_result_items
        # reproduces get_similar_tracks exactly (the pooled primitives are the
        # single source of truth).
        ds = await _rich_dataset(db)
        expected = await similarity_service.get_similar_tracks(
            db, ds["ref"].id, limit=50, top_n=50, score_floor=0.0,
        )

        ctx = await similarity_service.load_similarity_context(db)
        pool = await similarity_service.load_candidate_pool(db, None, ctx)
        seed = pool[ds["ref"].id]
        scored = similarity_service._score_seed_against_pool(pool, seed, score_floor=0.0)
        items = await similarity_service._build_result_items(db, scored[:50], None)
        assert items == expected


class TestRecoPoolEquivalence:
    async def _opine(self, db, user_id, catalog_id, opinion):
        from models import UserOpinion

        db.add(UserOpinion(user_id=user_id, entity_type="track",
                           entity_key=str(catalog_id), opinion=opinion,
                           created_at=datetime.now(timezone.utc)))
        await db.commit()

    async def test_reco_matches_pre_pool_reference(self, db, auth_user):
        # (b) The reco built off the shared pool (once) yields the same ordered
        # items and reco_scores as the pre-pool per-seed path: a like seed, a
        # library (moderate) seed and a dislike seed all cross the same pool.
        from models import UserTrack

        ds = await _rich_dataset(db)
        await self._opine(db, auth_user.id, ds["ref"].id, "liked")
        await self._opine(db, auth_user.id, ds["half"].id, "disliked")
        db.add(UserTrack(user_id=auth_user.id, catalog_id=ds["deep"].id))
        await db.commit()

        res = await recommendation_service.get_recommendations(db, auth_user.id, limit=50)
        got = [(i.id, i.reco_score) for i in res.items]
        expected = [
            (ds["close"].id, 0.3793),
            (ds["coocset"].id, 0.3242),
            (ds["coocpl"].id, 0.1377),
        ]
        assert got == expected
        # A co-occurring liked seed surfaces the co-occurring candidate.
        assert ds["coocset"].id in {i.id for i in res.items}
        # Owned (deep, lib) and rated (half, dislike) tracks are excluded.
        assert ds["deep"].id not in {i.id for i in res.items}
        assert ds["half"].id not in {i.id for i in res.items}
