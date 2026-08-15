"""
Tests des endpoints /api/watchlist.

Utilise une DB SQLite en mémoire (aiosqlite) et mocke l'appel Deezer
pour rester indépendant de l'infrastructure.
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from dependencies import get_current_user


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(auth_user):
    from dependencies import get_current_user_optional
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_current_user_optional] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


@pytest_asyncio.fixture
async def anon_client():
    """Client with NO auth override, so the real get_current_user dependency runs
    (existence + is_active checks). auth_middleware is disabled in tests, so this
    is how a missing/invalid/inactive token reaches the dependency."""
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
    mocker.patch("services.watchlist_service._fetch_deezer_playlist", return_value={"title": "Selected House", "track_count": 42, "owner": "willi"})
    mocker.patch("services.watchlist_service._trigger_crawl")


# ── GET /api/watchlist/browse ────────────────────────────────────────────────

class TestBrowsePlaylists:
    async def test_browse_returns_all_with_followed_flag(self, client, mocker):
        _mock_deezer(mocker)
        await client.post("/api/watchlist/", json=playlist_payload())

        r = await client.get("/api/watchlist/browse")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["followed"] is True

    async def test_browse_shows_unfollowed_after_unfollow(self, client, mocker):
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        await client.delete(f"/api/watchlist/{entry_id}")

        r = await client.get("/api/watchlist/browse")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["followed"] is False

    async def test_browse_exposes_new_fields(self, client, mocker):
        """Browse rows carry top_genres (default []) and last_changed_at (None)."""
        _mock_deezer(mocker)
        await client.post("/api/watchlist/", json=playlist_payload())

        r = await client.get("/api/watchlist/browse")
        item = r.json()["items"][0]
        assert "top_genres" in item
        assert item["top_genres"] == []
        assert "last_changed_at" in item
        assert item["last_changed_at"] is None

    async def test_browse_sort_by_title(self, client, db):
        from models import WatchedEntity

        db.add_all(
            [
                WatchedEntity(external_id="p-b", source="deezer", title="Bravo"),
                WatchedEntity(external_id="p-a", source="deezer", title="Alpha"),
                WatchedEntity(external_id="p-c", source="deezer", title="Charlie"),
            ]
        )
        await db.commit()

        asc = await client.get("/api/watchlist/browse?sort=title")
        assert [it["title"] for it in asc.json()["items"]] == [
            "Alpha",
            "Bravo",
            "Charlie",
        ]

        desc = await client.get("/api/watchlist/browse?sort=-title")
        assert [it["title"] for it in desc.json()["items"]] == [
            "Charlie",
            "Bravo",
            "Alpha",
        ]

    async def test_browse_sort_by_tracks(self, client, db):
        from models import WatchedEntity

        db.add_all(
            [
                WatchedEntity(external_id="t1", source="deezer", title="One", track_count=10),
                WatchedEntity(external_id="t2", source="deezer", title="Two", track_count=50),
                WatchedEntity(external_id="t3", source="deezer", title="Three", track_count=30),
            ]
        )
        await db.commit()

        asc = await client.get("/api/watchlist/browse?sort=tracks")
        assert [it["track_count"] for it in asc.json()["items"]] == [10, 30, 50]

        desc = await client.get("/api/watchlist/browse?sort=-tracks")
        assert [it["track_count"] for it in desc.json()["items"]] == [50, 30, 10]

    async def test_browse_filter_ids(self, client, db):
        from models import WatchedEntity

        entities = [
            WatchedEntity(external_id=f"id-{i}", source="deezer", title=f"P{i}")
            for i in range(3)
        ]
        db.add_all(entities)
        await db.commit()
        keep = entities[0].id

        r = await client.get(f"/api/watchlist/browse?ids={keep}")
        data = r.json()
        assert data["total"] == 1
        assert [it["id"] for it in data["items"]] == [keep]

    async def test_browse_exclude_ids(self, client, db):
        from models import WatchedEntity

        entities = [
            WatchedEntity(external_id=f"ex-{i}", source="deezer", title=f"P{i}")
            for i in range(3)
        ]
        db.add_all(entities)
        await db.commit()
        drop = entities[0].id

        r = await client.get(f"/api/watchlist/browse?exclude_ids={drop}")
        data = r.json()
        returned = [it["id"] for it in data["items"]]
        assert drop not in returned
        assert data["total"] == 2

    async def test_browse_top_genres_content(self, client, db):
        """top_genres is deduced from the playlist's visible radar tracks."""
        from models import CatalogEntry, RadarTrack, WatchedEntity

        entity = WatchedEntity(external_id="g-1", source="deezer", title="Genred")
        db.add(entity)
        await db.commit()

        c1 = CatalogEntry(
            title="Track A", normalized_key="a|track a", genres=["House", "Tech House"]
        )
        c2 = CatalogEntry(title="Track B", normalized_key="b|track b", genres=["House"])
        db.add_all([c1, c2])
        await db.commit()

        db.add_all(
            [
                RadarTrack(
                    watched_entity_id=entity.id,
                    external_track_id="x1",
                    source="deezer",
                    title="Track A",
                    catalog_id=c1.id,
                ),
                RadarTrack(
                    watched_entity_id=entity.id,
                    external_track_id="x2",
                    source="deezer",
                    title="Track B",
                    catalog_id=c2.id,
                ),
            ]
        )
        await db.commit()

        r = await client.get(f"/api/watchlist/browse?ids={entity.id}")
        item = r.json()["items"][0]
        genres = {g["name"]: g["pct"] for g in item["top_genres"]}
        # Both tracks carry "House" (2/2 => 100%); only one carries "Tech House".
        assert genres.get("House") == 100
        assert "Tech House" in genres
        assert item["top_genres"][0]["name"] == "House"


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
        mocker.patch("services.watchlist_service._fetch_deezer_playlist", return_value={})
        mocker.patch("services.watchlist_service._trigger_crawl")

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
        mocker.patch("services.watchlist_service._fetch_deezer_playlist", return_value={"title": "Some Playlist"})
        mocker.patch("services.watchlist_service._trigger_crawl")

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
        mocker.patch("services.watchlist_service._trigger_crawl")
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
        mocker.patch("services.watchlist_service._trigger_crawl")
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

        # The playlist still exists system-wide but is no longer followed.
        r = await client.get("/api/watchlist/browse")
        assert all(not it["followed"] for it in r.json()["items"])

    async def test_delete_nonexistent_returns_404(self, client):
        r = await client.delete("/api/watchlist/9999")
        assert r.status_code == 404

    async def test_delete_also_removes_opinion(self, client, mocker):
        """Bug 2: DELETE /watchlist/{id} must also remove UserOpinion."""
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        # Like the playlist via opinions endpoint
        await client.patch("/api/opinions/", json={
            "entity_type": "playlist",
            "entity_key": str(entry_id),
            "opinion": "liked",
        })

        # Unfollow via DELETE
        r = await client.delete(f"/api/watchlist/{entry_id}")
        assert r.status_code == 204

        # Opinion should be gone
        opinions = (await client.get("/api/opinions/")).json()
        assert "playlist" not in opinions or str(entry_id) not in opinions.get("playlist", {})


# ── GET /api/watchlist/{id}/crawl-status ─────────────────────────────────────

class TestCrawlStatusAuth:
    """A6-09: crawl_status must require an authenticated, existing, active user
    (it has a write side effect: it nulls current_task_id)."""

    async def test_no_bearer_returns_401(self, anon_client):
        r = await anon_client.get("/api/watchlist/1/crawl-status")
        assert r.status_code == 401

    async def test_invalid_bearer_returns_401(self, anon_client):
        r = await anon_client.get(
            "/api/watchlist/1/crawl-status",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401

    async def test_authenticated_non_admin_returns_200(self, client, mocker):
        """A valid non-admin user (the `client` fixture's auth_user) gets 200.
        A freshly followed playlist has no current_task_id -> status None."""
        _mock_deezer(mocker)
        post_r = await client.post("/api/watchlist/", json=playlist_payload())
        entry_id = post_r.json()["id"]

        r = await client.get(f"/api/watchlist/{entry_id}/crawl-status")
        assert r.status_code == 200
        assert r.json()["status"] is None

    async def test_inactive_user_returns_401(self, anon_client, db):
        """A deactivated user still holding a valid JWT is rejected by
        get_current_user (is_active check), unlike the old middleware-only path."""
        from auth import create_token
        from models import User, WatchedEntity

        user = User(
            email="inactive@test.com",
            username="inactive",
            google_id="google-inactive",
            is_active=False,
            is_admin=False,
        )
        entity = WatchedEntity(external_id="cs-inactive", source="deezer", title="P")
        db.add_all([user, entity])
        await db.commit()

        token = create_token(user.id)
        r = await anon_client.get(
            f"/api/watchlist/{entity.id}/crawl-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401
