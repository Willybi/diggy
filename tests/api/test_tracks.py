"""
Tests des endpoints /api/tracks.

Utilise une DB SQLite en mémoire (aiosqlite) et mocke MinIO
pour rester indépendant de l'infrastructure.
"""
import json
import base64
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from database import Base, get_db
from main import app


# ── DB en mémoire ────────────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session():
    async with TestSession() as session:
        yield session


# ── Helpers ───────────────────────────────────────────────────────────────────

def track_payload(**overrides):
    base = {
        "id": 1,
        "title": "Wannabe",
        "artist": "VOLAC",
        "bpm": 128.0,
        "key": "6A",
        "duration": 165000,
        "rating": 3,
        "file_path": "C:/Music/Wannabe.mp3",
        "date_added": None,
        "tags": ["Tech House", "TO_CUE"],
        "image_base64": None,
    }
    base.update(overrides)
    return base


# ── GET /api/tracks/existing-ids ─────────────────────────────────────────────

class TestGetExistingIds:
    async def test_empty_db_returns_empty_list(self, client):
        r = await client.get("/api/tracks/existing-ids")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_ids_after_insert(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")
        await client.post("/api/tracks/bulk", json=[track_payload()])

        r = await client.get("/api/tracks/existing-ids")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["has_artwork"] is False


# ── POST /api/tracks/bulk ─────────────────────────────────────────────────────

class TestBulkImport:
    async def test_insert_new_track(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        r = await client.post("/api/tracks/bulk", json=[track_payload()])
        assert r.status_code == 200
        result = r.json()
        assert result["inserted"] == 1
        assert result["updated"] == 0
        assert result["artworks_uploaded"] == 0

    async def test_update_existing_track(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        await client.post("/api/tracks/bulk", json=[track_payload()])
        r = await client.post("/api/tracks/bulk", json=[track_payload(title="Wannabe V2")])
        assert r.status_code == 200
        result = r.json()
        assert result["inserted"] == 0
        assert result["updated"] == 1

    async def test_updated_title_is_persisted(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        await client.post("/api/tracks/bulk", json=[track_payload()])
        await client.post("/api/tracks/bulk", json=[track_payload(title="Wannabe V2")])

        r = await client.get("/api/tracks/1")
        assert r.json()["title"] == "Wannabe V2"

    async def test_insert_multiple_tracks(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        tracks = [track_payload(id=i, title=f"Track {i}") for i in range(1, 4)]
        r = await client.post("/api/tracks/bulk", json=tracks)
        assert r.json()["inserted"] == 3

    async def test_artwork_uploaded_when_base64_provided(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mock_upload = mocker.patch("storage.upload_artwork")

        fake_image = base64.b64encode(b"FAKEIMAGE").decode()
        r = await client.post("/api/tracks/bulk", json=[track_payload(image_base64=fake_image)])
        assert r.json()["artworks_uploaded"] == 1
        mock_upload.assert_called_once()

    async def test_artwork_not_uploaded_twice(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mock_upload = mocker.patch("storage.upload_artwork")

        fake_image = base64.b64encode(b"FAKEIMAGE").decode()
        await client.post("/api/tracks/bulk", json=[track_payload(image_base64=fake_image)])
        # Deuxième import avec image : ne doit pas re-uploader
        r = await client.post("/api/tracks/bulk", json=[track_payload(image_base64=fake_image)])
        assert r.json()["artworks_uploaded"] == 0
        assert mock_upload.call_count == 1

    async def test_no_artwork_when_base64_absent(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        r = await client.post("/api/tracks/bulk", json=[track_payload(image_base64=None)])
        assert r.json()["artworks_uploaded"] == 0


# ── GET /api/tracks/ ──────────────────────────────────────────────────────────

class TestListTracks:
    async def _insert(self, client, mocker, tracks=None):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")
        if tracks is None:
            tracks = [track_payload()]
        await client.post("/api/tracks/bulk", json=tracks)

    async def test_returns_all_tracks(self, client, mocker):
        await self._insert(client, mocker)
        r = await client.get("/api/tracks/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    async def test_empty_db(self, client):
        r = await client.get("/api/tracks/")
        assert r.json()["total"] == 0
        assert r.json()["items"] == []

    async def test_filter_by_artist(self, client, mocker):
        tracks = [
            track_payload(id=1, artist="VOLAC"),
            track_payload(id=2, artist="Daft Punk"),
        ]
        await self._insert(client, mocker, tracks)

        r = await client.get("/api/tracks/?artist=volac")
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["artist"] == "VOLAC"

    async def test_filter_by_artist_partial_match(self, client, mocker):
        tracks = [
            track_payload(id=1, artist="VOLAC"),
            track_payload(id=2, artist="Daft Punk"),
        ]
        await self._insert(client, mocker, tracks)

        r = await client.get("/api/tracks/?artist=daft")
        assert r.json()["total"] == 1

    async def test_pagination_limit(self, client, mocker):
        tracks = [track_payload(id=i, title=f"Track {i}") for i in range(1, 6)]
        await self._insert(client, mocker, tracks)

        r = await client.get("/api/tracks/?limit=2")
        assert len(r.json()["items"]) == 2
        assert r.json()["total"] == 5

    async def test_pagination_skip(self, client, mocker):
        tracks = [track_payload(id=i, title=f"Track {i}") for i in range(1, 4)]
        await self._insert(client, mocker, tracks)

        r = await client.get("/api/tracks/?skip=2")
        assert len(r.json()["items"]) == 1

    async def test_tags_returned_as_list(self, client, mocker):
        await self._insert(client, mocker)
        r = await client.get("/api/tracks/")
        assert r.json()["items"][0]["tags"] == ["Tech House", "TO_CUE"]


# ── GET /api/tracks/{id} ──────────────────────────────────────────────────────

class TestGetTrack:
    async def test_returns_track(self, client, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")
        await client.post("/api/tracks/bulk", json=[track_payload()])

        r = await client.get("/api/tracks/1")
        assert r.status_code == 200
        assert r.json()["title"] == "Wannabe"
        assert r.json()["artist"] == "VOLAC"

    async def test_returns_404_when_not_found(self, client):
        r = await client.get("/api/tracks/9999")
        assert r.status_code == 404
