"""Tests for /api/catalog endpoints."""
from datetime import datetime, timezone

from models import CatalogEntry, UserTrack, Artist, RadarTrack, WatchedEntity, SetTrack, DJSet


class TestListCatalog:
    async def test_empty_returns_zero(self, client):
        r = await client.get("/api/catalog/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_returns_entries(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        await db.commit()
        r = await client.get("/api/catalog/")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Cola"

    async def test_search_filter(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        db.add(CatalogEntry(title="Strobe", artist="Deadmau5", normalized_key="strobe - deadmau5"))
        await db.commit()
        r = await client.get("/api/catalog/?search=cola")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Cola"

    async def test_pagination(self, client, db):
        for i in range(5):
            db.add(CatalogEntry(title=f"Track {i}", artist="Art", normalized_key=f"track {i} - art"))
        await db.commit()
        r = await client.get("/api/catalog/?limit=2")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_pagination_skip(self, client, db):
        for i in range(5):
            db.add(CatalogEntry(title=f"Track {i}", artist="Art", normalized_key=f"track {i} - art"))
        await db.commit()
        r = await client.get("/api/catalog/?skip=3&limit=10")
        data = r.json()
        assert len(data["items"]) == 2


class TestCatalogDetail:
    async def test_returns_entry(self, client, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        r = await client.get(f"/api/catalog/{cat.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Cola"
        assert data["artist"] == "CamelPhat"
        assert "radar_appearances" in data
        assert "set_appearances" in data

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/catalog/9999")
        assert r.status_code == 404


class TestCatalogInLib:
    async def test_in_lib_true_filter(self, auth_client, db, auth_user):
        cat1 = CatalogEntry(title="InLib", artist="A", normalized_key="inlib - a")
        cat2 = CatalogEntry(title="NotInLib", artist="B", normalized_key="notinlib - b")
        db.add_all([cat1, cat2])
        await db.commit()
        await db.refresh(cat1)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat1.id, source="test"))
        await db.commit()

        r = await auth_client.get("/api/catalog/?in_lib=true")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "InLib"
        assert data["items"][0]["in_lib"] is True

    async def test_in_lib_false_filter(self, auth_client, db, auth_user):
        cat1 = CatalogEntry(title="InLib", artist="A", normalized_key="inlib - a")
        cat2 = CatalogEntry(title="NotInLib", artist="B", normalized_key="notinlib - b")
        db.add_all([cat1, cat2])
        await db.commit()
        await db.refresh(cat1)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat1.id, source="test"))
        await db.commit()

        r = await auth_client.get("/api/catalog/?in_lib=false")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "NotInLib"


class TestCatalogSort:
    async def test_sort_by_title_asc(self, client, db):
        db.add(CatalogEntry(title="Zebra", artist="A", normalized_key="zebra - a"))
        db.add(CatalogEntry(title="Alpha", artist="B", normalized_key="alpha - b"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=title&order=asc")
        data = r.json()
        assert data["items"][0]["title"] == "Alpha"
        assert data["items"][1]["title"] == "Zebra"

    async def test_sort_by_title_desc(self, client, db):
        db.add(CatalogEntry(title="Zebra", artist="A", normalized_key="zebra - a"))
        db.add(CatalogEntry(title="Alpha", artist="B", normalized_key="alpha - b"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=title&order=desc")
        data = r.json()
        assert data["items"][0]["title"] == "Zebra"

    async def test_sort_by_bpm(self, client, db):
        db.add(CatalogEntry(title="Slow", artist="A", normalized_key="slow - a", bpm=100))
        db.add(CatalogEntry(title="Fast", artist="B", normalized_key="fast - b", bpm=140))
        await db.commit()

        r = await client.get("/api/catalog/?sort=bpm&order=asc")
        data = r.json()
        assert data["items"][0]["bpm"] == 100


class TestCatalogSearchByArtist:
    async def test_search_artist(self, client, db):
        db.add(CatalogEntry(title="Track A", artist="CamelPhat", normalized_key="a - camelphat"))
        db.add(CatalogEntry(title="Track B", artist="Deadmau5", normalized_key="b - deadmau5"))
        await db.commit()

        r = await client.get("/api/catalog/?search=camelphat")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["artist"] == "CamelPhat"


class TestCatalogDetailEnriched:
    async def test_detail_includes_same_artist_tracks(self, client, db):
        cat1 = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        cat2 = CatalogEntry(title="Breathe", artist="CamelPhat", normalized_key="breathe - camelphat")
        db.add_all([cat1, cat2])
        await db.commit()
        await db.refresh(cat1)

        r = await client.get(f"/api/catalog/{cat1.id}")
        data = r.json()
        same = data["same_artist_tracks"]
        assert len(same) == 1
        assert same[0]["title"] == "Breathe"

    async def test_detail_with_radar_appearances(self, client, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        we = WatchedEntity(external_id="123", source="deezer", title="Playlist 1")
        db.add_all([cat, we])
        await db.commit()
        await db.refresh(cat)
        await db.refresh(we)
        db.add(RadarTrack(
            watched_entity_id=we.id, external_track_id="ext1", source="deezer",
            title="Cola", artist="CamelPhat", catalog_id=cat.id,
            detected_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        r = await client.get(f"/api/catalog/{cat.id}")
        data = r.json()
        assert len(data["radar_appearances"]) == 1
        assert data["radar_appearances"][0]["playlist_title"] == "Playlist 1"

    async def test_detail_with_set_appearances(self, client, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        s = DJSet(title="My Set", source="trackid")
        db.add_all([cat, s])
        await db.commit()
        await db.refresh(cat)
        await db.refresh(s)
        db.add(SetTrack(set_id=s.id, catalog_id=cat.id, position=1))
        await db.commit()

        r = await client.get(f"/api/catalog/{cat.id}")
        data = r.json()
        assert len(data["set_appearances"]) == 1
        assert data["set_appearances"][0]["set_title"] == "My Set"

    async def test_list_includes_artist_id(self, client, db):
        """The list endpoint should resolve artist_id via batch lookup."""
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add_all([a, cat])
        await db.commit()
        await db.refresh(a)

        r = await client.get("/api/catalog/")
        data = r.json()
        assert data["items"][0].get("artist_id") == a.id


class TestCatalogAvis:
    async def test_set_avis_liked(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        assert r.status_code == 200
        assert r.json()["avis"] == "liked"

    async def test_set_avis_disliked(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "disliked"})
        assert r.status_code == 200
        assert r.json()["avis"] == "disliked"

    async def test_set_avis_creates_user_track_if_missing(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        assert r.status_code == 200

    async def test_set_avis_nonexistent_catalog_returns_404(self, auth_client):
        r = await auth_client.patch("/api/catalog/9999/avis", json={"avis": "liked"})
        assert r.status_code == 404

    async def test_set_avis_remove(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": None})
        assert r.status_code == 200
        assert r.json()["avis"] is None
