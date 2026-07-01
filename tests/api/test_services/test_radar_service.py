"""Tests for services/radar_service.py."""
import pytest

from services import radar_service


class TestNewCount:
    async def test_returns_zero_with_no_tracks(self, db, auth_user):
        result = await radar_service.new_count(db, auth_user.id)
        assert result == {"count": 0}

    async def test_returns_count_for_tracks_without_state(self, db, auth_user):
        from models import CatalogEntry, RadarTrack, WatchedEntity
        entity = WatchedEntity(
            source="deezer", external_id="pl_001", title="Test Playlist"
        )
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        cat = CatalogEntry(title="T1", artist="A1", normalized_key="a1|t1")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        rt = RadarTrack(
            watched_entity_id=entity.id, external_track_id="t1",
            source="deezer", title="T1", artist="A1", catalog_id=cat.id
        )
        db.add(rt)
        await db.commit()

        result = await radar_service.new_count(db, auth_user.id)
        assert result["count"] == 1


class TestBatchUpdateState:
    async def test_returns_zero_for_empty_items(self, db, auth_user):
        result = await radar_service.batch_update_state(db, auth_user.id, [])
        assert result == {"updated": 0}

    async def test_creates_state_for_valid_catalog(self, db, auth_user):
        from models import CatalogEntry
        c = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        result = await radar_service.batch_update_state(
            db, auth_user.id, [{"catalog_id": c.id, "status": "new"}]
        )
        assert result == {"updated": 1}

    async def test_batch_status_alias(self, db, auth_user):
        from models import CatalogEntry, UserRadarState
        from sqlalchemy import select
        c = CatalogEntry(title="T2", artist="A2", normalized_key="a2|t2")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        await radar_service.batch_update_state(
            db, auth_user.id, [{"catalog_id": c.id, "status": "liked"}]
        )
        # "liked" is aliased to "added"
        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == auth_user.id,
                UserRadarState.catalog_id == c.id,
            )
        )
        state = result.scalar_one_or_none()
        assert state is not None
        assert state.status == "added"


class TestAddTrack:
    async def test_raises_lookup_error_for_missing_watched_entity(self, db, auth_user):
        class FakeBody:
            watched_playlist_id = 9999999
            external_track_id = "ext1"
            source = "deezer"
            title = "T"
            artist = "A"
            isrc = None

        with pytest.raises(LookupError, match="watched_entity not found"):
            await radar_service.add_track(db, auth_user.id, FakeBody())

    async def test_creates_track_for_valid_entity(self, db, auth_user):
        from models import WatchedEntity

        entity = WatchedEntity(source="deezer", external_id="pl_002", title="Playlist")
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        class FakeBody:
            watched_playlist_id = entity.id
            external_track_id = "ext_new"
            source = "deezer"
            title = "New Track"
            artist = "Artist"
            isrc = None

        track, existed = await radar_service.add_track(db, auth_user.id, FakeBody())
        assert not existed
        assert track.title == "New Track"
        assert track.watched_entity_id == entity.id

    async def test_returns_existing_track_on_duplicate(self, db, auth_user):
        from models import WatchedEntity

        entity = WatchedEntity(source="deezer", external_id="pl_003", title="Playlist 2")
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        class FakeBody:
            watched_playlist_id = entity.id
            external_track_id = "ext_dup"
            source = "deezer"
            title = "Dup Track"
            artist = "Artist"
            isrc = None

        _, existed1 = await radar_service.add_track(db, auth_user.id, FakeBody())
        _, existed2 = await radar_service.add_track(db, auth_user.id, FakeBody())
        assert not existed1
        assert existed2
