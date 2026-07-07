"""Tests for /api/search endpoint."""
from models import CatalogEntry, Artist, DJSet, WatchedEntity


class TestSearch:
    async def test_empty_query_returns_empty(self, client):
        r = await client.get("/api/search?q=")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_search_tracks_by_title(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        db.add(CatalogEntry(title="Strobe", artist="Deadmau5", normalized_key="strobe - deadmau5"))
        await db.commit()

        r = await client.get("/api/search?q=cola&scope=track")
        data = r.json()
        assert data["totals"]["track"] == 1
        track_items = [i for i in data["items"] if i["type"] == "track"]
        assert len(track_items) == 1
        assert track_items[0]["title"] == "Cola"

    async def test_search_tracks_by_artist(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        await db.commit()

        r = await client.get("/api/search?q=camelphat&scope=track")
        data = r.json()
        assert data["totals"]["track"] >= 1

    async def test_search_artists(self, client, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        db.add(Artist(name="ANNA", normalized_name="anna"))
        await db.commit()

        r = await client.get("/api/search?q=camel&scope=artist")
        data = r.json()
        assert data["totals"]["artist"] == 1
        assert data["items"][0]["name"] == "CamelPhat"

    async def test_search_sets(self, client, db):
        db.add(DJSet(title="Boiler Room Set", source="trackid"))
        db.add(DJSet(title="Radio Show", source="trackid"))
        await db.commit()

        r = await client.get("/api/search?q=boiler&scope=set")
        data = r.json()
        assert data["totals"]["set"] == 1
        assert data["items"][0]["title"] == "Boiler Room Set"

    async def test_search_sets_excludes_children(self, client, db):
        parent = DJSet(title="Boiler Room London", source="trackid")
        db.add(parent)
        await db.flush()
        child = DJSet(title="Boiler Room London Part 2", source="trackid", parent_set_id=parent.id)
        db.add(child)
        await db.commit()

        r = await client.get("/api/search?q=boiler&scope=set")
        data = r.json()
        titles = [i["title"] for i in data["items"]]
        assert "Boiler Room London" in titles
        assert "Boiler Room London Part 2" not in titles
        assert data["totals"]["set"] == 1

    async def test_search_playlists(self, client, db):
        db.add(WatchedEntity(external_id="123", source="deezer", title="Deep House Selection"))
        db.add(WatchedEntity(external_id="456", source="deezer", title="Techno Picks"))
        await db.commit()

        r = await client.get("/api/search?q=deep&scope=playlist")
        data = r.json()
        assert data["totals"]["playlist"] == 1
        assert data["items"][0]["title"] == "Deep House Selection"

    async def test_search_multiple_scopes(self, client, db):
        """Test searching across multiple entity types (not genre, which needs PG)."""
        db.add(CatalogEntry(title="Deep Track", artist="DJ Deep", normalized_key="deep track - dj deep"))
        db.add(Artist(name="DJ Deep", normalized_name="dj deep"))
        db.add(DJSet(title="Deep Session", source="trackid"))
        await db.commit()

        # Search tracks
        r1 = await client.get("/api/search?q=deep&scope=track")
        assert r1.json()["totals"]["track"] >= 1

        # Search artists
        r2 = await client.get("/api/search?q=deep&scope=artist")
        assert r2.json()["totals"]["artist"] >= 1

        # Search sets
        r3 = await client.get("/api/search?q=deep&scope=set")
        assert r3.json()["totals"]["set"] >= 1

    async def test_search_scope_single_type(self, client, db):
        db.add(CatalogEntry(title="Track", artist="Art", normalized_key="track - art"))
        db.add(Artist(name="Art", normalized_name="art"))
        await db.commit()

        r = await client.get("/api/search?q=art&scope=track")
        data = r.json()
        # Should only return tracks
        types = {i["type"] for i in data["items"]}
        assert types <= {"track"}

    async def test_guest_cap(self, client, db):
        """Guest users should have capped results."""
        for i in range(10):
            db.add(CatalogEntry(
                title=f"House Track {i}", artist="DJ",
                normalized_key=f"house track {i} - dj",
            ))
        await db.commit()

        r = await client.get("/api/search?q=house&scope=track")
        data = r.json()
        # client fixture has no user override, so it's guest
        # GUEST_CAP = 6
        assert len(data["items"]) <= 6

    async def test_search_with_auth_no_cap(self, auth_client, db):
        """Authenticated users should not be capped."""
        for i in range(10):
            db.add(CatalogEntry(
                title=f"House Track {i}", artist="DJ",
                normalized_key=f"house track {i} - dj",
            ))
        await db.commit()

        r = await auth_client.get("/api/search?q=house&scope=track")
        data = r.json()
        assert len(data["items"]) == 10

    async def test_relevance_sorting(self, client, db):
        """Exact matches should rank higher."""
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        db.add(CatalogEntry(title="Cola Remix", artist="CamelPhat", normalized_key="cola remix - camelphat"))
        await db.commit()

        r = await client.get("/api/search?q=cola&scope=track")
        data = r.json()
        assert len(data["items"]) == 2
        # Exact match "Cola" should come first
        assert data["items"][0]["title"] == "Cola"
