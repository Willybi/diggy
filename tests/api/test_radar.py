"""
Tests des endpoints /api/radar.
"""
from datetime import datetime, timezone

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from models import CatalogEntry, RadarTrack, WatchedEntity, UserRadarState
from dependencies import get_current_user


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def watched_playlist_id(client, mocker):
    mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={"title": "Selected House", "track_count": 10, "owner": "willi"})
    mocker.patch("routers.watchlist._trigger_crawl")
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
        mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={"title": "Techno Picks"})
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


# ── GET /api/radar/new-count ─────────────────────────────────────────────────

class TestNewCount:
    async def test_returns_zero_when_empty(self, client):
        r = await client.get("/api/radar/new-count")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    async def test_counts_new_radar_tracks(self, client, db, auth_user):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art")
        we = WatchedEntity(external_id="we1", source="deezer", title="PL")
        db.add_all([cat, we])
        await db.commit()
        await db.refresh(cat)
        await db.refresh(we)
        db.add(RadarTrack(
            watched_entity_id=we.id, external_track_id="ext1", source="deezer",
            title="Track", catalog_id=cat.id, detected_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        r = await client.get("/api/radar/new-count")
        assert r.json()["count"] == 1

    async def test_excludes_seen_tracks(self, client, db, auth_user):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art")
        we = WatchedEntity(external_id="we1", source="deezer", title="PL")
        db.add_all([cat, we])
        await db.commit()
        await db.refresh(cat)
        await db.refresh(we)
        db.add(RadarTrack(
            watched_entity_id=we.id, external_track_id="ext1", source="deezer",
            title="Track", catalog_id=cat.id, detected_at=datetime.now(timezone.utc),
        ))
        db.add(UserRadarState(
            user_id=auth_user.id, catalog_id=cat.id, status="seen",
            updated_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        r = await client.get("/api/radar/new-count")
        assert r.json()["count"] == 0


# ── PATCH /api/radar/{catalog_id}/state ──────────────────────────────────────

class TestUpdateRadarState:
    async def test_create_state(self, client, db, auth_user):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await client.patch(f"/api/radar/{cat.id}/state", json={"status": "seen"})
        assert r.status_code == 200
        assert r.json()["status"] == "seen"

    async def test_update_existing_state(self, client, db, auth_user):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        await client.patch(f"/api/radar/{cat.id}/state", json={"status": "seen"})
        r = await client.patch(f"/api/radar/{cat.id}/state", json={"status": "added"})
        assert r.status_code == 200
        assert r.json()["status"] == "added"

    async def test_liked_alias_resolves_to_added(self, client, db, auth_user):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        await client.patch(f"/api/radar/{cat.id}/state", json={"status": "liked"})

        from sqlalchemy import select
        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == auth_user.id,
                UserRadarState.catalog_id == cat.id,
            )
        )
        state = result.scalar_one()
        assert state.status == "added"

    async def test_disliked_alias_resolves_to_ignored(self, client, db, auth_user):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        await client.patch(f"/api/radar/{cat.id}/state", json={"status": "disliked"})

        from sqlalchemy import select
        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == auth_user.id,
                UserRadarState.catalog_id == cat.id,
            )
        )
        state = result.scalar_one()
        assert state.status == "ignored"


# ── PATCH /api/radar/state/batch ─────────────────────────────────────────────

class TestBatchUpdateState:
    async def test_batch_update(self, client, db, auth_user):
        cat1 = CatalogEntry(title="T1", artist="A", normalized_key="t1 - a")
        cat2 = CatalogEntry(title="T2", artist="B", normalized_key="t2 - b")
        db.add_all([cat1, cat2])
        await db.commit()
        await db.refresh(cat1)
        await db.refresh(cat2)

        r = await client.patch("/api/radar/state/batch", json=[
            {"catalog_id": cat1.id, "status": "seen"},
            {"catalog_id": cat2.id, "status": "added"},
        ])
        assert r.status_code == 200
        assert r.json()["updated"] == 2

    async def test_batch_empty_list(self, client):
        r = await client.patch("/api/radar/state/batch", json=[])
        assert r.status_code == 200
        assert r.json()["updated"] == 0

    async def test_batch_updates_existing_states(self, client, db, auth_user):
        cat = CatalogEntry(title="T1", artist="A", normalized_key="t1 - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        # Create initial state
        await client.patch(f"/api/radar/{cat.id}/state", json={"status": "seen"})

        # Batch update it
        r = await client.patch("/api/radar/state/batch", json=[
            {"catalog_id": cat.id, "status": "added"},
        ])
        assert r.json()["updated"] == 1

        from sqlalchemy import select
        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == auth_user.id,
                UserRadarState.catalog_id == cat.id,
            )
        )
        state = result.scalar_one()
        assert state.status == "added"


# ── GET /api/radar/full ──────────────────────────────────────────────────────
# NOTE: /radar/full uses CatalogEntry.genres[1] in its sort_map, which triggers
# a NotImplementedError on SQLite (getitem not supported on StringArray/JSON).
# These tests are skipped in SQLite CI — they run in PostgreSQL prod.
