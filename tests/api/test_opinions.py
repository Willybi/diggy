"""
Tests du système d'opinions (likes/dislikes) et de la synchronisation
UserOpinion ↔ UserTrack.avis ↔ UserRadarState ↔ UserFollow/UserSetFollow.
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from main import app
from models import (
    CatalogEntry, UserTrack, UserRadarState, UserOpinion,
    DJSet, UserSetFollow, WatchedEntity, UserFollow,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def catalog_entry(db):
    cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@pytest_asyncio.fixture
async def catalog_with_user_track(db, catalog_entry):
    ut = UserTrack(user_id=1, catalog_id=catalog_entry.id, avis=None, source="test")
    db.add(ut)
    await db.commit()
    return catalog_entry


@pytest_asyncio.fixture
async def dj_set(db):
    s = DJSet(title="Test Set", source="test")
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def watched_playlist(db, mocker):
    mocker.patch("routers.watchlist._fetch_deezer_playlist", return_value={"title": "Test PL"})
    mocker.patch("routers.watchlist._trigger_crawl")
    entity = WatchedEntity(
        external_id="12345", source="deezer", title="Test PL",
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


# ── Helpers ───────────────────────────────────────────────────────────────────

def opinion_payload(entity_type, entity_key, opinion):
    return {"entity_type": entity_type, "entity_key": str(entity_key), "opinion": opinion}


# ── GET /api/opinions/ ───────────────────────────────────────────────────────

class TestGetOpinions:
    async def test_empty_returns_empty_dict(self, client):
        r = await client.get("/api/opinions/")
        assert r.status_code == 200
        assert r.json() == {}

    async def test_returns_opinions_grouped_by_type(self, client, catalog_entry, dj_set):
        await client.patch("/api/opinions/", json=opinion_payload("track", catalog_entry.id, "liked"))
        await client.patch("/api/opinions/", json=opinion_payload("set", dj_set.id, "disliked"))

        r = await client.get("/api/opinions/")
        data = r.json()
        assert data["track"][str(catalog_entry.id)] == "liked"
        assert data["set"][str(dj_set.id)] == "disliked"


# ── PATCH /api/opinions/ — basic CRUD ────────────────────────────────────────

class TestSetOpinion:
    async def test_like_artist(self, client):
        r = await client.patch("/api/opinions/", json=opinion_payload("artist", "42", "liked"))
        assert r.status_code == 200
        assert r.json()["opinion"] == "liked"

        data = (await client.get("/api/opinions/")).json()
        assert data["artist"]["42"] == "liked"

    async def test_dislike_artist(self, client):
        await client.patch("/api/opinions/", json=opinion_payload("artist", "42", "disliked"))
        data = (await client.get("/api/opinions/")).json()
        assert data["artist"]["42"] == "disliked"

    async def test_remove_opinion(self, client):
        await client.patch("/api/opinions/", json=opinion_payload("artist", "42", "liked"))
        await client.patch("/api/opinions/", json=opinion_payload("artist", "42", None))
        data = (await client.get("/api/opinions/")).json()
        assert "artist" not in data or "42" not in data.get("artist", {})

    async def test_toggle_opinion(self, client):
        await client.patch("/api/opinions/", json=opinion_payload("artist", "42", "liked"))
        await client.patch("/api/opinions/", json=opinion_payload("artist", "42", "disliked"))
        data = (await client.get("/api/opinions/")).json()
        assert data["artist"]["42"] == "disliked"

    async def test_invalid_entity_type_returns_422(self, client):
        r = await client.patch("/api/opinions/", json=opinion_payload("invalid", "1", "liked"))
        assert r.status_code == 422

    async def test_invalid_opinion_value_returns_422(self, client):
        r = await client.patch("/api/opinions/", json=opinion_payload("artist", "1", "love"))
        assert r.status_code == 422


# ── Track opinion sync (UserOpinion ↔ UserTrack.avis ↔ UserRadarState) ───────

class TestTrackOpinionSync:
    async def test_like_track_syncs_to_user_tracks_avis(self, client, db, catalog_with_user_track):
        cat = catalog_with_user_track
        await client.patch("/api/opinions/", json=opinion_payload("track", cat.id, "liked"))

        result = await db.execute(
            select(UserTrack).where(UserTrack.user_id == 1, UserTrack.catalog_id == cat.id)
        )
        ut = result.scalar_one()
        assert ut.avis == "liked"

    async def test_like_track_creates_radar_state_added(self, client, db, catalog_entry):
        await client.patch("/api/opinions/", json=opinion_payload("track", catalog_entry.id, "liked"))

        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == 1, UserRadarState.catalog_id == catalog_entry.id,
            )
        )
        urs = result.scalar_one()
        assert urs.status == "added"

    async def test_dislike_track_creates_radar_state_ignored(self, client, db, catalog_entry):
        await client.patch("/api/opinions/", json=opinion_payload("track", catalog_entry.id, "disliked"))

        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == 1, UserRadarState.catalog_id == catalog_entry.id,
            )
        )
        urs = result.scalar_one()
        assert urs.status == "ignored"

    async def test_remove_track_opinion_resets_radar_to_new(self, client, db, catalog_entry):
        await client.patch("/api/opinions/", json=opinion_payload("track", catalog_entry.id, "liked"))
        await client.patch("/api/opinions/", json=opinion_payload("track", catalog_entry.id, None))

        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == 1, UserRadarState.catalog_id == catalog_entry.id,
            )
        )
        urs = result.scalar_one()
        assert urs.status == "new"

    async def test_catalog_avis_syncs_to_opinion(self, client, db, catalog_entry):
        r = await client.patch(
            f"/api/catalog/{catalog_entry.id}/avis", json={"avis": "liked"},
        )
        assert r.status_code == 200

        result = await db.execute(
            select(UserOpinion).where(
                UserOpinion.user_id == 1,
                UserOpinion.entity_type == "track",
                UserOpinion.entity_key == str(catalog_entry.id),
            )
        )
        op = result.scalar_one()
        assert op.opinion == "liked"

    async def test_catalog_avis_creates_radar_state(self, client, db, catalog_entry):
        """Bug 3: /catalog/{id}/avis must create UserRadarState if absent."""
        await client.patch(
            f"/api/catalog/{catalog_entry.id}/avis", json={"avis": "liked"},
        )

        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == 1, UserRadarState.catalog_id == catalog_entry.id,
            )
        )
        urs = result.scalar_one()
        assert urs.status == "added"

    async def test_radar_state_syncs_to_opinion(self, client, db, catalog_entry):
        r = await client.patch(
            f"/api/radar/{catalog_entry.id}/state", json={"status": "added"},
        )
        assert r.status_code == 200

        result = await db.execute(
            select(UserOpinion).where(
                UserOpinion.user_id == 1,
                UserOpinion.entity_type == "track",
                UserOpinion.entity_key == str(catalog_entry.id),
            )
        )
        op = result.scalar_one()
        assert op.opinion == "liked"

    async def test_radar_batch_syncs_to_opinion(self, client, db, catalog_entry):
        """Bug 5: batch_update_radar_state must sync to UserOpinion."""
        r = await client.patch(
            "/api/radar/state/batch",
            json=[{"catalog_id": catalog_entry.id, "status": "added"}],
        )
        assert r.status_code == 200

        result = await db.execute(
            select(UserOpinion).where(
                UserOpinion.user_id == 1,
                UserOpinion.entity_type == "track",
                UserOpinion.entity_key == str(catalog_entry.id),
            )
        )
        op = result.scalar_one()
        assert op.opinion == "liked"


# ── Set opinion sync (UserOpinion ↔ UserSetFollow) ───────────────────────────

class TestSetOpinionSync:
    async def test_like_set_creates_follow(self, client, db, dj_set):
        await client.patch("/api/opinions/", json=opinion_payload("set", dj_set.id, "liked"))

        result = await db.execute(
            select(UserSetFollow).where(
                UserSetFollow.user_id == 1, UserSetFollow.set_id == dj_set.id,
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_unlike_set_deletes_follow(self, client, db, dj_set):
        await client.patch("/api/opinions/", json=opinion_payload("set", dj_set.id, "liked"))
        await client.patch("/api/opinions/", json=opinion_payload("set", dj_set.id, None))

        result = await db.execute(
            select(UserSetFollow).where(
                UserSetFollow.user_id == 1, UserSetFollow.set_id == dj_set.id,
            )
        )
        assert result.scalar_one_or_none() is None


# ── Playlist opinion sync (UserOpinion ↔ UserFollow) ────────────────────────

class TestPlaylistOpinionSync:
    async def test_like_playlist_creates_follow(self, client, db, watched_playlist):
        await client.patch(
            "/api/opinions/",
            json=opinion_payload("playlist", watched_playlist.id, "liked"),
        )

        result = await db.execute(
            select(UserFollow).where(
                UserFollow.user_id == 1, UserFollow.entity_id == watched_playlist.id,
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_unlike_playlist_deletes_follow(self, client, db, watched_playlist):
        await client.patch(
            "/api/opinions/",
            json=opinion_payload("playlist", watched_playlist.id, "liked"),
        )
        await client.patch(
            "/api/opinions/",
            json=opinion_payload("playlist", watched_playlist.id, None),
        )

        result = await db.execute(
            select(UserFollow).where(
                UserFollow.user_id == 1, UserFollow.entity_id == watched_playlist.id,
            )
        )
        assert result.scalar_one_or_none() is None
