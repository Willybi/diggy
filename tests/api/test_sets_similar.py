"""Tests for GET /api/sets/{id}/similar (Lot 0 — C2 engine aggregated at set level)."""
from models import Artist, CatalogEntry, DJSet, SetArtist, SetTrack, User


async def _make_catalog(db, title, *, scope="shared", owner_id=None):
    c = CatalogEntry(
        title=title,
        artist=title,
        normalized_key=f"{title}|{title}".lower(),
        scope=scope,
        owner_id=owner_id,
    )
    db.add(c)
    await db.flush()
    return c


async def _make_set(db, title, catalog_ids, *, parent_set_id=None):
    s = DJSet(source="trackid", title=title, parent_set_id=parent_set_id)
    db.add(s)
    await db.flush()
    for pos, cid in enumerate(catalog_ids, start=1):
        db.add(
            SetTrack(
                set_id=s.id, position=pos, catalog_id=cid,
                is_id=False, raw_title=f"t{cid}",
            )
        )
    await db.flush()
    return s


class TestSimilarSets:
    async def test_404_unknown_set(self, client):
        r = await client.get("/api/sets/999999/similar")
        assert r.status_code == 404

    async def test_empty_when_no_overlap(self, client, db):
        # a set whose only track appears in no other set -> nothing is close
        c1 = await _make_catalog(db, "solo")
        s = await _make_set(db, "Lonely", [c1.id])
        await db.commit()

        r = await client.get(f"/api/sets/{s.id}/similar")
        assert r.status_code == 200
        assert r.json() == []

    async def test_overlap_ranks_and_normalizes(self, client, db):
        c1 = await _make_catalog(db, "c1")
        c2 = await _make_catalog(db, "c2")
        c3 = await _make_catalog(db, "c3")
        s = await _make_set(db, "Seed", [c1.id, c2.id])
        a = await _make_set(db, "A", [c1.id, c2.id, c3.id])  # overlap 2 (c1, c2)
        b = await _make_set(db, "B", [c1.id])                # overlap 1 (c1)
        await db.commit()

        r = await client.get(f"/api/sets/{s.id}/similar")
        assert r.status_code == 200
        items = r.json()
        ids = [it["id"] for it in items]
        assert s.id not in ids          # current set excluded
        assert ids[0] == a.id           # most overlap ranks first
        assert b.id in ids
        scores = [it["score"] for it in items]
        assert scores[0] == 1.0         # max normalized to 1.0
        assert all(0.0 < sc <= 1.0 for sc in scores)
        # winner card mirrors the list-endpoint shape
        top = items[0]
        assert top["title"] == "A"
        assert top["total_tracks"] == 3
        assert top["identified_tracks"] == 3

    async def test_current_set_and_parent_excluded(self, client, db):
        c1 = await _make_catalog(db, "p1")
        parent = await _make_set(db, "Parent", [c1.id])
        child = await _make_set(db, "Child", [c1.id], parent_set_id=parent.id)
        other = await _make_set(db, "Other", [c1.id])
        await db.commit()

        r = await client.get(f"/api/sets/{child.id}/similar")
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()]
        assert parent.id not in ids     # parent root excluded
        assert child.id not in ids      # current set excluded
        assert ids == [other.id]        # only the unrelated root survives

    async def test_limit_caps_results(self, client, db):
        c1 = await _make_catalog(db, "s1")
        s = await _make_set(db, "Seed", [c1.id])
        for i in range(4):
            await _make_set(db, f"Other{i}", [c1.id])
        await db.commit()

        r = await client.get(f"/api/sets/{s.id}/similar?limit=2")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_winner_card_includes_artist_names(self, client, db):
        c1 = await _make_catalog(db, "wc1")
        s = await _make_set(db, "Seed", [c1.id])
        a = await _make_set(db, "A", [c1.id])
        art = Artist(name="ANNA", normalized_name="anna")
        db.add(art)
        await db.flush()
        db.add(SetArtist(set_id=a.id, artist_id=art.id, role="main", position=1))
        await db.commit()

        r = await client.get(f"/api/sets/{s.id}/similar")
        items = r.json()
        assert items[0]["id"] == a.id
        assert items[0]["artists"] == ["ANNA"]

    async def test_auth_user_access(self, auth_client, db):
        c1 = await _make_catalog(db, "au1")
        c2 = await _make_catalog(db, "au2")
        s = await _make_set(db, "Seed", [c1.id, c2.id])
        a = await _make_set(db, "A", [c1.id, c2.id])
        await db.commit()

        r = await auth_client.get(f"/api/sets/{s.id}/similar")
        assert r.status_code == 200
        assert [it["id"] for it in r.json()] == [a.id]

    async def test_private_seed_not_visible_yields_no_overlap(self, auth_client, db, auth_user):
        """A seed track owned privately by another user is outside the viewer's
        pool (C3), so it contributes no similarity signal."""
        other = User(email="o2@test.com", username="o2", google_id="g-o2", is_active=True)
        db.add(other)
        await db.flush()
        priv = await _make_catalog(db, "secret", scope="private", owner_id=other.id)
        s = await _make_set(db, "SeedPriv", [priv.id])
        await _make_set(db, "AlsoPriv", [priv.id])
        await db.commit()

        r = await auth_client.get(f"/api/sets/{s.id}/similar")
        assert r.status_code == 200
        assert r.json() == []  # the only seed is invisible -> no C2 signal
