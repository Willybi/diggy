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
        "external_id": "1950581322",
        "source": "deezer",
        "description": None,
    }
    base.update(overrides)
    return base


def _mock_deezer(mocker):
    mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={"title": "Selected House", "track_count": 42, "owner": "willi"})
    mocker.patch("routers.watchlist._trigger_crawl")


# ── GET /api/watchlist/ ───────────────────────────────────────────────────────

class TestListWatched:
    async def test_empty_db_returns_empty_list(self, client):
        r = await client.get("/api/watchlist/")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_entry_after_insert(self, client, mocker):
        _mock_deezer(mocker)
        await client.post("/api/watchlist/", json=playlist_payload())

        r = await client.get("/api/watchlist/")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["external_id"] == "1950581322"


# ── GET /api/watchlist/browse ────────────────────────────────────────────────

class TestBrowsePlaylists:
    async def test_browse_returns_all_with_followed_flag(self, client, mocker):
        _mock_deezer(mocker)
        await client.post("/api/watchlist/", json=playlist_payload())

        r = await client.get("/api/watchlist/browse")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["followed"] is True

    async def test_browse_shows_unfollowed_after_unfollow(self, client, mocker):
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        await client.delete(f"/api/watchlist/{entry_id}")

        r = await client.get("/api/watchlist/browse")
        assert len(r.json()) == 1
        assert r.json()[0]["followed"] is False


# ── POST /api/watchlist/ ──────────────────────────────────────────────────────

class TestAddWatched:
    async def test_creates_entry_with_fetched_title(self, client, mocker):
        _mock_deezer(mocker)

        r = await client.post("/api/watchlist/", json=playlist_payload())
        assert r.status_code == 201
        data = r.json()
        assert data["external_id"] == "1950581322"
        assert data["title"] == "Selected House"
        assert data["track_count"] == 42
        assert data["owner"] == "willi"
        assert data["source"] == "deezer"
        assert data["description"] is None
        assert "id" in data
        assert "created_at" in data

    async def test_title_is_none_when_deezer_unreachable(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={})
        mocker.patch("routers.watchlist._trigger_crawl")

        r = await client.post("/api/watchlist/", json=playlist_payload())
        assert r.status_code == 201
        assert r.json()["title"] is None

    async def test_duplicate_returns_409(self, client, mocker):
        _mock_deezer(mocker)

        await client.post("/api/watchlist/", json=playlist_payload())
        r = await client.post("/api/watchlist/", json=playlist_payload())
        assert r.status_code == 409

    async def test_source_is_required(self, client, mocker):
        _mock_deezer(mocker)

        payload = {"external_id": "1950581322"}
        r = await client.post("/api/watchlist/", json=payload)
        assert r.status_code == 422

    async def test_custom_source(self, client, mocker):
        mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={"title": "Some Playlist"})
        mocker.patch("routers.watchlist._trigger_crawl")

        r = await client.post("/api/watchlist/", json=playlist_payload(source="soundcloud"))
        assert r.status_code == 201
        assert r.json()["source"] == "soundcloud"

    async def test_description_is_persisted(self, client, mocker):
        _mock_deezer(mocker)

        r = await client.post("/api/watchlist/", json=playlist_payload(description="Ma ref house"))
        assert r.status_code == 201
        assert r.json()["description"] == "Ma ref house"


# ── POST /api/watchlist/{id}/follow ──────────────────────────────────────────

class TestFollowPlaylist:
    async def test_follow_unfollowed_playlist(self, client, mocker):
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        await client.delete(f"/api/watchlist/{entry_id}")
        r = await client.post(f"/api/watchlist/{entry_id}/follow")
        assert r.status_code == 200
        assert r.json()["id"] == entry_id

    async def test_follow_already_followed_returns_409(self, client, mocker):
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        r = await client.post(f"/api/watchlist/{entry_id}/follow")
        assert r.status_code == 409

    async def test_follow_nonexistent_returns_404(self, client, mocker):
        mocker.patch("routers.watchlist._trigger_crawl")
        r = await client.post("/api/watchlist/9999/follow")
        assert r.status_code == 404


# ── POST /api/watchlist/{id}/crawl ───────────────────────────────────────────

class TestCrawlPlaylist:
    async def test_crawl_returns_202(self, client, mocker):
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        r = await client.post(f"/api/watchlist/{entry_id}/crawl")
        assert r.status_code == 202
        assert r.json()["status"] == "crawl_queued"

    async def test_crawl_nonexistent_returns_404(self, client, mocker):
        mocker.patch("routers.watchlist._trigger_crawl")
        r = await client.post("/api/watchlist/9999/crawl")
        assert r.status_code == 404


# ── DELETE /api/watchlist/{id} ────────────────────────────────────────────────

class TestDeleteWatched:
    async def test_deletes_entry(self, client, mocker):
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        r = await client.delete(f"/api/watchlist/{entry_id}")
        assert r.status_code == 204

        r = await client.get("/api/watchlist/")
        assert r.json() == []

    async def test_delete_nonexistent_returns_404(self, client):
        r = await client.delete("/api/watchlist/9999")
        assert r.status_code == 404
