"""
Tests des endpoints /api/watchlist.

Utilise une DB SQLite en mémoire (aiosqlite) et mocke l'appel Deezer
pour rester indépendant de l'infrastructure.
"""
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio
from httpx import AsyncClient, ASGITransport

from main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────

def playlist_payload(**overrides):
    base = {
        "deezer_playlist_id": "1950581322",
        "source": "deezer",
        "description": None,
    }
    base.update(overrides)
    return base


# ── GET /api/watchlist/ ───────────────────────────────────────────────────────

class TestListWatched:
    async def test_empty_db_returns_empty_list(self, client):
        r = await client.get("/api/watchlist/")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_entry_after_insert(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Selected House")
        await client.post("/api/watchlist/", json=playlist_payload())

        r = await client.get("/api/watchlist/")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["deezer_playlist_id"] == "1950581322"


# ── POST /api/watchlist/ ──────────────────────────────────────────────────────

class TestAddWatched:
    async def test_creates_entry_with_fetched_title(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Selected House")

        r = await client.post("/api/watchlist/", json=playlist_payload())
        assert r.status_code == 201
        data = r.json()
        assert data["deezer_playlist_id"] == "1950581322"
        assert data["title"] == "Selected House"
        assert data["source"] == "deezer"
        assert data["description"] is None
        assert "id" in data
        assert "created_at" in data

    async def test_title_is_none_when_deezer_unreachable(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value=None)

        r = await client.post("/api/watchlist/", json=playlist_payload())
        assert r.status_code == 201
        assert r.json()["title"] is None

    async def test_duplicate_returns_409(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Selected House")

        await client.post("/api/watchlist/", json=playlist_payload())
        r = await client.post("/api/watchlist/", json=playlist_payload())
        assert r.status_code == 409

    async def test_source_is_required(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Selected House")

        payload = {"deezer_playlist_id": "1950581322"}
        r = await client.post("/api/watchlist/", json=payload)
        assert r.status_code == 422

    async def test_custom_source(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Some Playlist")

        r = await client.post("/api/watchlist/", json=playlist_payload(source="soundcloud"))
        assert r.status_code == 201
        assert r.json()["source"] == "soundcloud"

    async def test_description_is_persisted(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Selected House")

        r = await client.post("/api/watchlist/", json=playlist_payload(description="Ma ref house"))
        assert r.status_code == 201
        assert r.json()["description"] == "Ma ref house"


# ── DELETE /api/watchlist/{id} ────────────────────────────────────────────────

class TestDeleteWatched:
    async def test_deletes_entry(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Selected House")
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        r = await client.delete(f"/api/watchlist/{entry_id}")
        assert r.status_code == 204

        r = await client.get("/api/watchlist/")
        assert r.json() == []

    async def test_delete_nonexistent_returns_404(self, client):
        r = await client.delete("/api/watchlist/9999")
        assert r.status_code == 404
