"""Tests for /api/collections endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from dependencies import get_current_user
from models import CatalogEntry


@pytest_asyncio.fixture
async def client(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def catalog_entry(db):
    entry = CatalogEntry(
        title="Body Funk",
        artist="Purple Disco Machine",
        normalized_key="purple disco machine|body funk",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def catalog_entry_2(db):
    entry = CatalogEntry(
        title="Rasputin",
        artist="Majestic",
        normalized_key="majestic|rasputin",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


class TestListCollections:
    async def test_empty(self, client):
        r = await client.get("/api/collections/")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_created(self, client):
        await client.post("/api/collections/", json={"name": "Favorites"})
        r = await client.get("/api/collections/")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["name"] == "Favorites"
        assert items[0]["item_count"] == 0


class TestCreateCollection:
    async def test_create_success(self, client):
        r = await client.post("/api/collections/", json={"name": "My Playlist"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Playlist"
        assert data["type"] == "playlist"
        assert data["item_count"] == 0

    async def test_create_with_type(self, client):
        r = await client.post("/api/collections/", json={"name": "House", "type": "category"})
        assert r.status_code == 201
        assert r.json()["type"] == "category"

    async def test_create_empty_name_rejected(self, client):
        r = await client.post("/api/collections/", json={"name": ""})
        assert r.status_code == 422


class TestCollectionDetail:
    async def test_not_found(self, client):
        r = await client.get("/api/collections/9999")
        assert r.status_code == 404

    async def test_detail_with_items(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry.id})

        r = await client.get(f"/api/collections/{coll_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["item_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Body Funk"


class TestAddItem:
    async def test_add_track(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry.id})
        assert r.status_code == 201
        assert r.json()["catalog_id"] == catalog_entry.id
        assert r.json()["position"] == 1

    async def test_add_duplicate_rejected(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry.id})
        r = await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry.id})
        assert r.status_code == 409

    async def test_add_nonexistent_catalog(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": 99999})
        assert r.status_code == 404

    async def test_positions_increment(self, client, catalog_entry, catalog_entry_2):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r1 = await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry.id})
        r2 = await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry_2.id})
        assert r1.json()["position"] == 1
        assert r2.json()["position"] == 2


class TestRemoveItem:
    async def test_remove_track(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(f"/api/collections/{coll_id}/items", json={"catalog_id": catalog_entry.id})
        r = await client.delete(f"/api/collections/{coll_id}/items/{catalog_entry.id}")
        assert r.status_code == 204

    async def test_remove_nonexistent(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.delete(f"/api/collections/{coll_id}/items/{catalog_entry.id}")
        assert r.status_code == 404


class TestDeleteCollection:
    async def test_delete(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.delete(f"/api/collections/{coll_id}")
        assert r.status_code == 204

        r2 = await client.get("/api/collections/")
        assert r2.json() == []

    async def test_delete_nonexistent(self, client):
        r = await client.delete("/api/collections/9999")
        assert r.status_code == 404
