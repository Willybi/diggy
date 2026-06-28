"""Tests for /api/sets endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from models import DJSet, SetTrack, SetArtist, Artist, UserSetFollow


class TestListSets:
    async def test_empty_returns_zero(self, client):
        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_returns_sets(self, client, db):
        db.add(DJSet(source="trackid", title="Boiler Room London"))
        await db.commit()
        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Boiler Room London"

    async def test_filter_by_title(self, client, db):
        db.add(DJSet(source="trackid", title="Boiler Room London"))
        db.add(DJSet(source="trackid", title="Cercle Paris"))
        await db.commit()
        r = await client.get("/api/sets/?q=boiler")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Boiler Room London"

    async def test_includes_track_counts(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Track 1"))
        db.add(SetTrack(set_id=s.id, position=2, raw_title="ID", is_id=True))
        await db.commit()
        r = await client.get("/api/sets/")
        data = r.json()
        assert data["items"][0]["total_tracks"] == 2

    async def test_includes_artists(self, client, db):
        a = Artist(name="ANNA", normalized_name="anna")
        db.add(a)
        s = DJSet(source="trackid", title="ANNA at Boiler Room")
        db.add(s)
        await db.flush()
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="main", position=1))
        await db.commit()
        r = await client.get("/api/sets/")
        data = r.json()
        assert data["items"][0]["artists"] == ["ANNA"]

    async def test_pagination(self, client, db):
        for i in range(5):
            db.add(DJSet(source="trackid", title=f"Set {i}"))
        await db.commit()
        r = await client.get("/api/sets/?limit=2")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_pagination_offset(self, client, db):
        for i in range(5):
            db.add(DJSet(source="trackid", title=f"Set {i}"))
        await db.commit()
        r = await client.get("/api/sets/?offset=3&limit=10")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5


class TestSetDetail:
    async def test_returns_set(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.commit()
        await db.refresh(s)
        r = await client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        assert r.json()["title"] == "Test Set"

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/sets/9999")
        assert r.status_code == 404

    async def test_includes_tracklist(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        await db.commit()
        await db.refresh(s)
        r = await client.get(f"/api/sets/{s.id}")
        data = r.json()
        assert len(data["tracklist"]) == 1
        assert data["tracklist"][0]["raw_title"] == "Cola"


class TestImportSet:
    async def test_invalid_input_returns_422(self, auth_client):
        r = await auth_client.post("/api/sets/import", json={})
        assert r.status_code == 422

    async def test_import_with_slug(self, auth_client, db, mocker):
        fake_detail = {
            "id": 12345,
            "title": "Test Set from TrackID",
            "slug": "test-set",
            "duration": "01:30:00.0000000",
            "tracks": [],
        }
        mock_client_instance = AsyncMock()
        mock_client_instance.get_set_detail = AsyncMock(return_value=fake_detail)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("trackid.client.TrackIDClient", return_value=mock_ctx)

        # Pre-create the set in the DB so refresh works
        dj_set = DJSet(source="trackid", title="Test Set from TrackID", external_id="12345")
        db.add(dj_set)
        await db.commit()
        await db.refresh(dj_set)

        mock_import = AsyncMock(return_value=(dj_set, []))
        mocker.patch("trackid.importer.import_audiostream", mock_import)

        r = await auth_client.post("/api/sets/import", json={"slug": "test-set"})
        assert r.status_code == 200
        assert r.json()["title"] == "Test Set from TrackID"


class TestSearchSets:
    async def test_search(self, client, mocker):
        mock_client_instance = AsyncMock()
        mock_client_instance.search_sets = AsyncMock(return_value=(
            [{"id": 1, "slug": "test", "title": "Test Set", "channel": None,
              "artworkUrl": None, "trackCount": 10, "duration": "01:00:00",
              "createdOn": "2024-01-01"}],
            1,
        ))

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("trackid.client.TrackIDClient", return_value=mock_ctx)

        r = await client.get("/api/sets/search?q=test")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Set"
        assert data[0]["already_imported"] is False
