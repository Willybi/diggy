"""
Tests des endpoints /api/radar.
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


@pytest_asyncio.fixture
async def watched_playlist_id(client, mocker):
    mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={"title": "Selected House", "track_count": 10, "owner": "willi"})
    r = await client.post("/api/watchlist/", json={
        "external_id": "1950581322",
        "source": "deezer",
    })
    return r.json()["id"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def radar_payload(watched_playlist_id: int, **overrides) -> dict:
    base = {
        "watched_playlist_id": watched_playlist_id,
        "external_track_id": "123456789",
        "source": "deezer",
        "title": "Body Funk",
        "artist": "Purple Disco Machine",
        "isrc": "GBUM71029604",
    }
    base.update(overrides)
    return base


# ── GET /api/radar/ ───────────────────────────────────────────────────────────

class TestListRadar:
    async def test_empty_returns_empty_list(self, client):
        r = await client.get("/api/radar/")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_entry_after_insert(self, client, watched_playlist_id):
        await client.post("/api/radar/", json=radar_payload(watched_playlist_id))
        r = await client.get("/api/radar/")
        assert r.status_code == 200
        assert len(r.json()) == 1

    async def test_filter_by_watched_playlist_id(self, client, mocker, watched_playlist_id):
        mocker.patch("routers.watchlist._fetch_deezer_playlist_title", return_value="Techno Picks")
        r2 = await client.post("/api/watchlist/", json={"external_id": "999", "source": "deezer"})
        playlist2_id = r2.json()["id"]

        await client.post("/api/radar/", json=radar_payload(watched_playlist_id, title="Track A"))
        await client.post("/api/radar/", json=radar_payload(playlist2_id, external_track_id="999", title="Track B"))

        r = await client.get(f"/api/radar/?watched_playlist_id={watched_playlist_id}")
        assert len(r.json()) == 1
        assert r.json()[0]["title"] == "Track A"

    async def test_filter_by_source(self, client, watched_playlist_id):
        await client.post("/api/radar/", json=radar_payload(watched_playlist_id, source="deezer", external_track_id="1"))
        await client.post("/api/radar/", json=radar_payload(watched_playlist_id, source="youtube", external_track_id="2"))

        r = await client.get("/api/radar/?source=youtube")
        assert len(r.json()) == 1
        assert r.json()[0]["source"] == "youtube"


# ── POST /api/radar/ ──────────────────────────────────────────────────────────

class TestAddRadar:
    async def test_creates_entry(self, client, watched_playlist_id):
        r = await client.post("/api/radar/", json=radar_payload(watched_playlist_id))
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Body Funk"
        assert data["artist"] == "Purple Disco Machine"
        assert data["isrc"] == "GBUM71029604"
        assert data["source"] == "deezer"
        assert data["watched_playlist_id"] == watched_playlist_id
        assert "detected_at" in data

    async def test_isrc_nullable(self, client, watched_playlist_id):
        r = await client.post("/api/radar/", json=radar_payload(watched_playlist_id, isrc=None))
        assert r.status_code == 201
        assert r.json()["isrc"] is None

    async def test_artist_nullable(self, client, watched_playlist_id):
        r = await client.post("/api/radar/", json=radar_payload(watched_playlist_id, artist=None))
        assert r.status_code == 201
        assert r.json()["artist"] is None

    async def test_invalid_watched_playlist_returns_404(self, client):
        r = await client.post("/api/radar/", json=radar_payload(9999))
        assert r.status_code == 404

    async def test_duplicate_track_returns_existing(self, client, watched_playlist_id):
        r1 = await client.post("/api/radar/", json=radar_payload(watched_playlist_id))
        r2 = await client.post("/api/radar/", json=radar_payload(watched_playlist_id))
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]

        r = await client.get("/api/radar/")
        assert len(r.json()) == 1


# ── DELETE /api/radar/{id} ────────────────────────────────────────────────────

class TestDeleteRadar:
    async def test_deletes_entry(self, client, watched_playlist_id):
        post_r = await client.post("/api/radar/", json=radar_payload(watched_playlist_id))
        entry_id = post_r.json()["id"]

        r = await client.delete(f"/api/radar/{entry_id}")
        assert r.status_code == 204

        r = await client.get("/api/radar/")
        assert r.json() == []

    async def test_delete_nonexistent_returns_404(self, client):
        r = await client.delete("/api/radar/9999")
        assert r.status_code == 404
