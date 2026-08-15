"""
Tests des endpoints /api/radar + C0 security & lifecycle.
"""
import os
from datetime import date, datetime, timezone

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


# ── GET /api/radar/feed ──────────────────────────────────────────────────────

class TestRadarFeed:
    async def test_feed_requires_auth(self, db):
        """No JWT and no override → 401 (Radar feed is authenticated)."""
        from dependencies import get_current_user
        app.dependency_overrides.pop(get_current_user, None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.get("/api/radar/feed")
        assert r.status_code == 401

    async def test_feed_returns_bi_score_shape(self, client, db, auth_user):
        from models import RadarTrend
        cat = CatalogEntry(title="Trend", artist="Art", normalized_key="trend - art")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(RadarTrend(
            catalog_id=cat.id, trend_score=5.0, family="house",
            rank_in_family=1, rank_global=1, velocity=0.6,
        ))
        await db.commit()

        r = await client.get("/api/radar/feed")
        assert r.status_code == 200
        data = r.json()
        assert set(data) >= {"total", "trend_count", "reco_count", "items"}
        assert data["trend_count"] == 1
        assert data["reco_count"] == 0
        assert data["total"] == 1
        item = data["items"][0]
        assert item["id"] == cat.id
        assert item["trend_score_10"] is not None
        assert item["reco_score_10"] is None
        assert item["velocity"] == 0.6
        # Inherited CatalogEntryOut fields still present
        for field in ("has_artwork", "has_preview", "in_lib", "artists", "genres"):
            assert field in item

    async def test_feed_sort_param_validation(self, client):
        r = await client.get("/api/radar/feed?sort=bogus")
        assert r.status_code == 422


class TestRadarFeedSpaceInsensitive:
    """X4.h: /api/radar/feed filters `search` space-insensitively (in-memory twin
    of the SQL helper), so a letter-spaced Deezer artist is found by its
    collapsed spelling."""

    async def _add_trend(self, db, title, artist, rank):
        from models import RadarTrend
        cat = CatalogEntry(
            title=title, artist=artist,
            normalized_key=f"{title.lower()} - {(artist or '').lower()}",
        )
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(RadarTrend(
            catalog_id=cat.id, trend_score=5.0, family="house",
            rank_in_family=rank, rank_global=rank, velocity=0.5,
        ))
        await db.commit()
        return cat

    async def test_feed_search_matches_spaced_artist(self, client, db, auth_user):
        spaced = await self._add_trend(db, "Some Track", "t e s t p r e s s", 1)
        other = await self._add_trend(db, "Other Track", "Carl Cox", 2)

        r = await client.get("/api/radar/feed", params={"search": "testpress"})
        assert r.status_code == 200
        data = r.json()
        ids = [it["id"] for it in data["items"]]
        assert spaced.id in ids
        assert other.id not in ids  # non-matching item is excluded
        assert data["total"] == 1

    async def test_feed_normal_search_still_works(self, client, db, auth_user):
        spaced = await self._add_trend(db, "Some Track", "t e s t p r e s s", 1)
        carl = await self._add_trend(db, "Other Track", "Carl Cox", 2)

        r = await client.get("/api/radar/feed", params={"search": "carl"})
        assert r.status_code == 200
        data = r.json()
        ids = [it["id"] for it in data["items"]]
        assert carl.id in ids
        assert spaced.id not in ids
        assert data["total"] == 1


# ── GET /api/radar/trends ─────────────────────────────────────────────────────

class TestTrends:
    async def test_trends_returns_release_date(self, client, db, auth_user):
        from models import RadarTrend
        cat = CatalogEntry(
            title="Trend", artist="Art", normalized_key="trend - art",
            release_date=date(2026, 5, 1),
        )
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(RadarTrend(
            catalog_id=cat.id, trend_score=5.0, family="house",
            rank_in_family=1, rank_global=1,
        ))
        await db.commit()

        r = await client.get("/api/radar/trends")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["release_date"] == "2026-05-01"

    async def test_trends_null_release_date(self, client, db, auth_user):
        from models import RadarTrend
        cat = CatalogEntry(title="NoDate", artist="Art", normalized_key="nodate - art")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(RadarTrend(
            catalog_id=cat.id, trend_score=3.0, family="techno",
            rank_in_family=1, rank_global=1,
        ))
        await db.commit()

        r = await client.get("/api/radar/trends")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["release_date"] is None


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

    def test_bulk_get_or_create_trims_title_and_artist(self):
        """The radar/playlist bulk path stores title/artist trimmed (a source
        playlist often pads them with whitespace), mirroring get_or_create_catalog."""
        from sqlalchemy.orm import Session
        from workers.db import bulk_get_or_create_catalog
        from utils import make_normalized_key

        nk = make_normalized_key("  BulkTrimT ", " BulkTrimA ")
        engine = self._make_engine()
        with Session(engine) as s:
            catalog_map = bulk_get_or_create_catalog(
                s, [{"title": "  BulkTrimT ", "artist": " BulkTrimA "}]
            )
            s.commit()
            entry = catalog_map[nk]
            assert entry.title == "BulkTrimT"
            assert entry.artist == "BulkTrimA"

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
