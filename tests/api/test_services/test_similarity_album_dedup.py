"""Album-awareness of the similarity/reco engine (L4).

The engine must never recommend several tracks of the SAME album: at most one
track per album survives the final list (the best-scored), tracks with no album
are never de-duped against one another, and the representative ``album_id`` is
exposed on every result row (reused from the pool — no extra query).
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


async def _mk_album(db, title="Album", deezer_album_id=None):
    from models import Album

    a = Album(title=title, deezer_album_id=deezer_album_id)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def _link_album(db, catalog_id, album_id):
    from models import CatalogAlbum

    db.add(CatalogAlbum(catalog_id=catalog_id, album_id=album_id))
    await db.commit()


async def _seed_genre_graph(db):
    """House parent with a single Tech House child (weight-0.5 to it)."""
    from models import GenreEdge, GenreMapping, GenreNode

    parent = GenreNode(wikidata_id="Q-house", label="House")
    db.add(parent)
    await db.commit()
    await db.refresh(parent)
    tech = GenreNode(wikidata_id="Q-tech", label="Tech House")
    db.add(tech)
    await db.commit()
    await db.refresh(tech)
    db.add_all([
        GenreMapping(raw_name="Tech House", node_id=tech.id),
        GenreMapping(raw_name="House", node_id=parent.id),
        GenreEdge(from_node_id=tech.id, to_node_id=parent.id, type="parent", source="test"),
    ])
    await db.commit()


async def _descending_dataset(db):
    """Ref + 5 candidates that all score, with STRICTLY decreasing scores.

    All Tech House / same valid label / same era, so only BPM proximity varies:
    c1 (128) > c2 (127) > c3 (126) > c4 (125) > c5 (124). All fall inside the BPM
    window so they are all candidates, and the label "Drumcode" occurs 6× (>=
    LABEL_MIN_TRACKS) so context contributes too.
    """
    await _seed_genre_graph(db)
    ref = await _mk(db, title="Ref", nk="a|ref", bpm=128.0, key="8A",
                    label="Drumcode", release_date=date(2025, 1, 1),
                    genres=["Tech House"])
    cands = {}
    for i, bpm in enumerate((128.0, 127.0, 126.0, 125.0, 124.0), start=1):
        cands[f"c{i}"] = await _mk(
            db, title=f"C{i}", nk=f"a|c{i}", bpm=bpm, key="8A",
            label="Drumcode", release_date=date(2025, 1, 1),
            genres=["Tech House"],
        )
    return ref, cands


async def _ids_in_order(db, seed_id, **kwargs):
    res = await similarity_service.get_similar_tracks(
        db, seed_id, limit=50, top_n=50, score_floor=0.0, **kwargs
    )
    return res


class TestSimilarAlbumDedup:
    async def test_same_album_keeps_best_scored_only(self, db):
        # c1 and c2 both score; put them on the SAME album → only c1 (higher
        # score) survives, c2 is dropped. Others (distinct/no album) untouched.
        ref, c = await _descending_dataset(db)
        album = await _mk_album(db, title="Shared", deezer_album_id="d-shared")
        await _link_album(db, c["c1"].id, album.id)
        await _link_album(db, c["c2"].id, album.id)

        res = await _ids_in_order(db, ref.id)
        ids = [r["id"] for r in res]

        assert c["c1"].id in ids
        assert c["c2"].id not in ids  # same album as c1, lower score → dropped
        # every other candidate stays
        for name in ("c3", "c4", "c5"):
            assert c[name].id in ids

    async def test_no_album_never_deduped(self, db):
        # No albums at all → nothing is de-duped, every candidate is returned.
        ref, c = await _descending_dataset(db)
        res = await _ids_in_order(db, ref.id)
        ids = {r["id"] for r in res}
        assert all(c[n].id in ids for n in ("c1", "c2", "c3", "c4", "c5"))
        assert all(r["album_id"] is None for r in res)

    async def test_album_id_exposed_in_output(self, db):
        # album_id is populated from the pool: a linked track carries its album,
        # an unlinked one carries None.
        ref, c = await _descending_dataset(db)
        album = await _mk_album(db, title="A1", deezer_album_id="d-a1")
        await _link_album(db, c["c1"].id, album.id)

        res = await _ids_in_order(db, ref.id)
        by_id = {r["id"]: r for r in res}
        assert by_id[c["c1"].id]["album_id"] == album.id
        assert by_id[c["c3"].id]["album_id"] is None

    async def test_multi_album_uses_min_album_id(self, db):
        # A track on several albums collapses to the SMALLEST album_id
        # (deterministic representative).
        ref, c = await _descending_dataset(db)
        a1 = await _mk_album(db, title="A1", deezer_album_id="d-a1")
        a2 = await _mk_album(db, title="A2", deezer_album_id="d-a2")
        lo, hi = (a1, a2) if a1.id < a2.id else (a2, a1)
        await _link_album(db, c["c1"].id, lo.id)
        await _link_album(db, c["c1"].id, hi.id)

        res = await _ids_in_order(db, ref.id)
        by_id = {r["id"]: r for r in res}
        assert by_id[c["c1"].id]["album_id"] == lo.id

    async def test_overprovision_refills_to_top_n(self, db):
        # With c1 & c2 on the same album and top_n=4, the dedup drops c2 but the
        # over-provisioning pulls c5 into the window → still 4 distinct results.
        ref, c = await _descending_dataset(db)
        album = await _mk_album(db, title="Shared", deezer_album_id="d-shared")
        await _link_album(db, c["c1"].id, album.id)
        await _link_album(db, c["c2"].id, album.id)

        res = await similarity_service.get_similar_tracks(
            db, ref.id, limit=4, top_n=4, score_floor=0.0
        )
        ids = [r["id"] for r in res]
        assert len(ids) == 4
        assert c["c2"].id not in ids  # deduped
        assert c["c1"].id in ids
        # c5 was beyond the naive top-4 window but refilled the dropped slot.
        assert c["c5"].id in ids


class TestRecoAlbumDedup:
    async def _like(self, db, user_id, catalog_id):
        from models import UserOpinion

        db.add(UserOpinion(user_id=user_id, entity_type="track",
                           entity_key=str(catalog_id), opinion="liked",
                           created_at=datetime.now(timezone.utc)))
        await db.commit()

    async def test_reco_dedups_by_album(self, db, auth_user):
        # Liking ref surfaces c1..c5; c1 & c2 share an album → the reco list keeps
        # c1 (higher) and drops c2, while exposing album_id.
        ref, c = await _descending_dataset(db)
        album = await _mk_album(db, title="Shared", deezer_album_id="d-shared")
        await _link_album(db, c["c1"].id, album.id)
        await _link_album(db, c["c2"].id, album.id)
        await self._like(db, auth_user.id, ref.id)

        res = await recommendation_service.get_recommendations(
            db, auth_user.id, limit=50
        )
        ids = [i.id for i in res.items]
        assert c["c1"].id in ids
        assert c["c2"].id not in ids
        for name in ("c3", "c4", "c5"):
            assert c[name].id in ids
        by_id = {i.id: i for i in res.items}
        assert by_id[c["c1"].id].album_id == album.id
        assert by_id[c["c3"].id].album_id is None
