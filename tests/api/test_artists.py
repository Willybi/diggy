"""Tests for /api/artists endpoints."""
from models import Artist, ArtistAlias, CatalogEntry


class TestListArtists:
    async def test_empty_returns_empty_list(self, client):
        r = await client.get("/api/artists/")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_artists(self, client, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        await db.commit()
        r = await client.get("/api/artists/")
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "CamelPhat"

    async def test_search_filter(self, client, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        db.add(Artist(name="ANNA", normalized_name="anna"))
        await db.commit()
        r = await client.get("/api/artists/?q=camel")
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "CamelPhat"

    async def test_no_deezer_filter(self, client, db):
        db.add(Artist(name="Known", normalized_name="known", deezer_id="123"))
        db.add(Artist(name="Unknown", normalized_name="unknown"))
        await db.commit()
        r = await client.get("/api/artists/?no_deezer=true")
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "Unknown"


class TestArtistDetail:
    async def test_returns_artist(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(a)
        await db.commit()
        await db.refresh(a)
        r = await client.get(f"/api/artists/{a.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "CamelPhat"
        assert "aliases" in data
        assert "genres" in data
        assert "catalog_tracks" in data
        assert "sets" in data
        assert "stats" in data

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/artists/9999")
        assert r.status_code == 404

    async def test_includes_catalog_tracks(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(a)
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add(cat)
        await db.commit()
        await db.refresh(a)
        r = await client.get(f"/api/artists/{a.id}")
        data = r.json()
        assert len(data["catalog_tracks"]) == 1
        assert data["catalog_tracks"][0]["title"] == "Cola"
