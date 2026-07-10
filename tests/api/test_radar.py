"""
Tests des endpoints /api/radar + C0 security & lifecycle.
"""
import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from models import CatalogEntry, RadarTrack, WatchedEntity, UserRadarState
from dependencies import get_current_user, uid


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def watched_playlist_id(client, mocker):
    mocker.patch("services.watchlist_service._fetch_deezer_playlist", return_value={"title": "Selected House", "track_count": 10, "owner": "willi"})
    mocker.patch("services.watchlist_service._trigger_crawl")
    r = await client.post("/api/watchlist/", json={
        "external_id": "1950581322",
        "source": "deezer",
    })
    return r.json()["id"]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _make_radar_track(db, watched_entity_id, external_track_id="123456789",
                            title="Body Funk", artist="Purple Disco Machine", **kwargs):
    cat = CatalogEntry(title=title, artist=artist, normalized_key=f"{title.lower()} - {(artist or '').lower()}")
    db.add(cat)
    await db.flush()
    rt = RadarTrack(
        watched_entity_id=watched_entity_id,
        external_track_id=external_track_id,
        source=kwargs.get("source", "deezer"),
        title=title,
        artist=artist,
        catalog_id=cat.id,
        detected_at=datetime.now(timezone.utc),
        **{k: v for k, v in kwargs.items() if k not in ("source",)},
    )
    db.add(rt)
    await db.commit()
    await db.refresh(rt)
    return rt


# ── C0.2 Security Tests ─────────────────────────────────────────────────────


class TestLegacyEndpointsRemoved:
    async def test_legacy_get_radar_removed(self, client):
        """GET /api/radar/ should no longer exist."""
        r = await client.get("/api/radar/")
        assert r.status_code in (404, 405)

    async def test_legacy_post_radar_removed(self, client):
        """POST /api/radar/ should no longer exist."""
        r = await client.post("/api/radar/", json={})
        assert r.status_code in (404, 405)


class TestDeleteRadarRequiresAdmin:
    async def test_delete_radar_requires_admin(self, client, db, watched_playlist_id):
        """DELETE /api/radar/{id} by non-admin should return 403."""
        rt = await _make_radar_track(db, watched_playlist_id)
        r = await client.delete(f"/api/radar/{rt.id}")
        assert r.status_code == 403

    async def test_delete_radar_admin_succeeds(self, admin_client, db, mocker):
        mocker.patch("services.watchlist_service._fetch_deezer_playlist", return_value={"title": "PL"})
        mocker.patch("services.watchlist_service._trigger_crawl")
        r = await admin_client.post("/api/watchlist/", json={"external_id": "adm1", "source": "deezer"})
        we_id = r.json()["id"]
        rt = await _make_radar_track(db, we_id)
        r = await admin_client.delete(f"/api/radar/{rt.id}")
        assert r.status_code == 204

    async def test_delete_nonexistent_returns_404(self, admin_client):
        r = await admin_client.delete("/api/radar/9999")
        assert r.status_code == 404


class TestUidNoFallback:
    def test_uid_none_when_no_user(self):
        """uid(None) should return None, not a fallback user ID."""
        assert uid(None) is None

    def test_uid_returns_user_id_when_authenticated(self, auth_user):
        assert uid(auth_user) == auth_user.id


class TestCatalogBrowseNoAuthNoUserData:
    async def test_catalog_browse_no_auth_no_user_data(self, client, db):
        """Browse catalog without auth should not leak in_lib data."""
        # Remove auth overrides to simulate unauthenticated access
        from dependencies import get_current_user_optional
        app.dependency_overrides[get_current_user_optional] = lambda: None

        cat = CatalogEntry(title="Test Track", artist="Test Artist", normalized_key="test track - test artist")
        db.add(cat)
        await db.commit()

        r = await client.get("/api/catalog/")
        assert r.status_code == 200
        data = r.json()
        if data.get("items"):
            for item in data["items"]:
                assert item.get("in_lib") is False or item.get("in_lib") is None

        app.dependency_overrides.pop(get_current_user_optional, None)


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


# ── C0.1 Lifecycle Tests ────────────────────────────────────────────────────


class TestRadarTrackModel:
    async def test_radar_track_has_removed_at_column(self, db):
        """RadarTrack model should have removed_at column."""
        we = WatchedEntity(external_id="lc1", source="deezer", title="PL")
        db.add(we)
        await db.commit()
        await db.refresh(we)
        rt = RadarTrack(
            watched_entity_id=we.id, external_track_id="ext1", source="deezer",
            title="Track", detected_at=datetime.now(timezone.utc),
            removed_at=None,
        )
        db.add(rt)
        await db.commit()
        await db.refresh(rt)
        assert rt.removed_at is None

    async def test_radar_track_has_is_initial_detection(self, db):
        """RadarTrack model should have is_initial_detection column."""
        we = WatchedEntity(external_id="lc2", source="deezer", title="PL")
        db.add(we)
        await db.commit()
        await db.refresh(we)
        rt = RadarTrack(
            watched_entity_id=we.id, external_track_id="ext1", source="deezer",
            title="Track", detected_at=datetime.now(timezone.utc),
            is_initial_detection=True,
        )
        db.add(rt)
        await db.commit()
        await db.refresh(rt)
        assert rt.is_initial_detection is True


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="bulk_insert_radar_tracks uses PostgreSQL dialect (pg_insert)",
)
class TestCrawlDiffLifecycle:
    """Tests that run entirely via sync psycopg2 sessions (no async mixing)."""

    def _make_engine(self):
        from sqlalchemy import create_engine
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        return create_engine(url)

    def test_crawl_marks_removed_tracks(self):
        """Tracks absent from crawl should get removed_at set."""
        from dataclasses import dataclass
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from workers.db import bulk_insert_radar_tracks, bulk_get_or_create_catalog

        @dataclass
        class FakeTrack:
            external_id: str
            title: str
            artist: str
            isrc: str | None = None
            duration_ms: int | None = None

        engine = self._make_engine()
        with Session(engine) as s:
            we = WatchedEntity(external_id="diff1", source="deezer", title="PL")
            s.add(we)
            s.flush()

            for ext_id, title in [("t1", "Track 1"), ("t2", "Track 2")]:
                cat = CatalogEntry(title=title, artist="Art", normalized_key=f"{title.lower()} - art")
                s.add(cat)
                s.flush()
                s.add(RadarTrack(
                    watched_entity_id=we.id, external_track_id=ext_id, source="deezer",
                    title=title, artist="Art", catalog_id=cat.id,
                    detected_at=datetime.now(timezone.utc),
                ))
            s.commit()
            we_id = we.id

        with Session(engine) as s:
            source_tracks = [FakeTrack(external_id="t1", title="Track 1", artist="Art")]
            catalog_map = bulk_get_or_create_catalog(s, [{"title": "Track 1", "artist": "Art"}])
            result = bulk_insert_radar_tracks(s, we_id, "deezer", source_tracks, catalog_map)
            s.commit()

        assert result["removed"] == 1

        with Session(engine) as s:
            t2 = s.execute(
                select(RadarTrack).where(
                    RadarTrack.external_track_id == "t2",
                    RadarTrack.watched_entity_id == we_id,
                )
            ).scalar_one()
            assert t2.removed_at is not None

    def test_crawl_reappearing_track_clears_removed_at(self):
        """Tracks that reappear should have removed_at cleared."""
        from dataclasses import dataclass
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from workers.db import bulk_insert_radar_tracks, bulk_get_or_create_catalog

        @dataclass
        class FakeTrack:
            external_id: str
            title: str
            artist: str
            isrc: str | None = None
            duration_ms: int | None = None

        engine = self._make_engine()
        with Session(engine) as s:
            we = WatchedEntity(external_id="diff2", source="deezer", title="PL")
            s.add(we)
            s.flush()
            cat = CatalogEntry(title="Track", artist="Art", normalized_key="track - art reappear")
            s.add(cat)
            s.flush()
            s.add(RadarTrack(
                watched_entity_id=we.id, external_track_id="t1", source="deezer",
                title="Track", artist="Art", catalog_id=cat.id,
                detected_at=datetime.now(timezone.utc),
                removed_at=datetime.now(timezone.utc),
            ))
            s.commit()
            we_id = we.id

        with Session(engine) as s:
            source_tracks = [FakeTrack(external_id="t1", title="Track", artist="Art")]
            catalog_map = bulk_get_or_create_catalog(s, [{"title": "Track", "artist": "Art"}])
            bulk_insert_radar_tracks(s, we_id, "deezer", source_tracks, catalog_map)
            s.commit()

        with Session(engine) as s:
            t1 = s.execute(
                select(RadarTrack).where(
                    RadarTrack.external_track_id == "t1",
                    RadarTrack.watched_entity_id == we_id,
                )
            ).scalar_one()
            assert t1.removed_at is None

    def test_initial_crawl_flag(self):
        """First crawl of a playlist should flag tracks as initial detections."""
        from dataclasses import dataclass
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from workers.db import bulk_insert_radar_tracks, bulk_get_or_create_catalog

        @dataclass
        class FakeTrack:
            external_id: str
            title: str
            artist: str
            isrc: str | None = None
            duration_ms: int | None = None

        engine = self._make_engine()
        with Session(engine) as s:
            we = WatchedEntity(external_id="init1", source="deezer", title="PL")
            s.add(we)
            s.commit()
            we_id = we.id

        with Session(engine) as s:
            source_tracks = [FakeTrack(external_id="t1", title="Init Track", artist="Art")]
            catalog_map = bulk_get_or_create_catalog(s, [{"title": "Init Track", "artist": "Art"}])
            result = bulk_insert_radar_tracks(
                s, we_id, "deezer", source_tracks, catalog_map,
                is_initial_crawl=True,
            )
            s.commit()

        assert result["inserted"] == 1

        with Session(engine) as s:
            t1 = s.execute(
                select(RadarTrack).where(
                    RadarTrack.external_track_id == "t1",
                    RadarTrack.watched_entity_id == we_id,
                )
            ).scalar_one()
            assert t1.is_initial_detection is True


# ── GET /api/radar/full ──────────────────────────────────────────────────────
# NOTE: /radar/full uses CatalogEntry.genres[1] in its sort_map, which triggers
# a NotImplementedError on SQLite (getitem not supported on StringArray/JSON).
# These tests are skipped in SQLite CI — they run in PostgreSQL prod.
