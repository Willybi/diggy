"""Tests for /api/catalog endpoints."""
from models import CatalogEntry


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
        assert "genres" in data
        assert "radar_appearances" in data
        assert "set_appearances" in data

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/catalog/9999")
        assert r.status_code == 404
