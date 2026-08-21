"""Tests for /api/collections endpoints (C5 v2 — polymorphic items)."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from dependencies import get_current_user
from models import Artist, CatalogEntry, CollectionFolder, DJSet, User, WatchedEntity


@pytest_asyncio.fixture
async def client(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def catalog_entry(db):
    entry = CatalogEntry(
        title="Body Funk",
        artist="Purple Disco Machine",
        normalized_key="purple disco machine|body funk",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def catalog_entry_2(db):
    entry = CatalogEntry(
        title="Rasputin",
        artist="Majestic",
        normalized_key="majestic|rasputin",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def dj_set(db):
    s = DJSet(source="trackid", title="Boiler Room Berlin", event="Boiler Room")
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def artist(db):
    a = Artist(name="Four Tet", normalized_name="four tet")
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest_asyncio.fixture
async def playlist(db):
    w = WatchedEntity(external_id="pl-1", source="deezer", title="Deep House", owner="dj")
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return w


@pytest_asyncio.fixture
async def other_user(db):
    u = User(
        email="other@test.com",
        username="otheruser",
        google_id="google-other-user",
        is_active=True,
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


class TestListCollections:
    async def test_empty(self, client):
        r = await client.get("/api/collections/")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_created(self, client):
        await client.post("/api/collections/", json={"name": "Favorites"})
        r = await client.get("/api/collections/")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["name"] == "Favorites"
        assert items[0]["item_count"] == 0

    async def test_item_count_across_types(self, client, catalog_entry, artist):
        cr = await client.post("/api/collections/", json={"name": "Mixed"})
        coll_id = cr.json()["id"]
        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "artist", "item_id": artist.id},
        )
        r = await client.get("/api/collections/")
        assert r.json()[0]["item_count"] == 2


class TestCreateCollection:
    async def test_create_success(self, client):
        r = await client.post("/api/collections/", json={"name": "My Playlist"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Playlist"
        assert data["type"] == "playlist"
        assert data["item_count"] == 0

    async def test_create_with_type(self, client):
        r = await client.post("/api/collections/", json={"name": "House", "type": "category"})
        assert r.status_code == 201
        assert r.json()["type"] == "category"

    async def test_create_empty_name_rejected(self, client):
        r = await client.post("/api/collections/", json={"name": ""})
        assert r.status_code == 422


class TestCollectionDetail:
    async def test_not_found(self, client):
        r = await client.get("/api/collections/9999")
        assert r.status_code == 404

    async def test_detail_with_track(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )

        r = await client.get(f"/api/collections/{coll_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["item_count"] == 1
        item = data["items"][0]
        assert item["item_type"] == "track"
        assert item["title"] == "Body Funk"
        assert item["subtitle"] == "Purple Disco Machine"
        assert item["missing"] is False

    async def test_detail_mixed_types_ordered(
        self, client, catalog_entry, dj_set, artist, playlist
    ):
        cr = await client.post("/api/collections/", json={"name": "Mixed"})
        coll_id = cr.json()["id"]
        for body in (
            {"item_type": "track", "item_id": catalog_entry.id},
            {"item_type": "set", "item_id": dj_set.id},
            {"item_type": "artist", "item_id": artist.id},
            {"item_type": "playlist", "item_id": playlist.id},
            {"item_type": "genre", "item_name": "Techno"},
        ):
            r = await client.post(f"/api/collections/{coll_id}/items", json=body)
            assert r.status_code == 201, r.text

        data = (await client.get(f"/api/collections/{coll_id}")).json()
        items = data["items"]
        assert [i["item_type"] for i in items] == [
            "track",
            "set",
            "artist",
            "playlist",
            "genre",
        ]
        titles = {i["item_type"]: i["title"] for i in items}
        assert titles["set"] == "Boiler Room Berlin"
        assert titles["artist"] == "Four Tet"
        assert titles["playlist"] == "Deep House"
        assert titles["genre"] == "Techno"
        # track-only extras are null on the non-track rows
        assert items[1]["bpm"] is None
        assert items[4]["item_id"] is None  # genre

    async def test_detail_missing_entity(self, client, catalog_entry, db):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]
        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        # Delete the underlying entity — the item stays but resolves as missing.
        await db.delete(catalog_entry)
        await db.commit()

        data = (await client.get(f"/api/collections/{coll_id}")).json()
        assert data["item_count"] == 1
        assert data["items"][0]["missing"] is True


class TestAddItem:
    async def test_add_track(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["item_type"] == "track"
        assert body["item_id"] == catalog_entry.id
        assert body["position"] == 1
        assert body["title"] == "Body Funk"

    async def test_add_artist(self, client, artist):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "artist", "item_id": artist.id},
        )
        assert r.status_code == 201
        assert r.json()["title"] == "Four Tet"

    async def test_add_genre_by_name(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "genre", "item_name": "Techno"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["item_type"] == "genre"
        assert body["item_id"] is None
        assert body["title"] == "Techno"

    async def test_add_duplicate_track_rejected(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        assert r.status_code == 409

    async def test_add_duplicate_genre_rejected(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "genre", "item_name": "Techno"},
        )
        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "genre", "item_name": "Techno"},
        )
        assert r.status_code == 409

    async def test_same_id_different_type_not_a_dup(self, client, catalog_entry, artist):
        # A track id and an artist id can collide numerically without being a dup.
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]
        r1 = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        r2 = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "artist", "item_id": artist.id},
        )
        assert r1.status_code == 201 and r2.status_code == 201

    async def test_add_nonexistent_track(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": 99999},
        )
        assert r.status_code == 404

    async def test_add_nonexistent_set(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "set", "item_id": 99999},
        )
        assert r.status_code == 404

    async def test_add_invalid_type_rejected(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "album", "item_id": 1},
        )
        assert r.status_code == 422

    async def test_add_track_without_id_rejected(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track"},
        )
        assert r.status_code == 422

    async def test_add_genre_without_name_rejected(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "genre"},
        )
        assert r.status_code == 422

    async def test_positions_increment(self, client, catalog_entry, catalog_entry_2):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r1 = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        r2 = await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry_2.id},
        )
        assert r1.json()["position"] == 1
        assert r2.json()["position"] == 2


class TestRemoveItem:
    async def test_remove_track(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "track", "item_id": catalog_entry.id},
        )
        r = await client.delete(
            f"/api/collections/{coll_id}/items/track/{catalog_entry.id}"
        )
        assert r.status_code == 204

        data = (await client.get(f"/api/collections/{coll_id}")).json()
        assert data["item_count"] == 0

    async def test_remove_genre_by_name(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        await client.post(
            f"/api/collections/{coll_id}/items",
            json={"item_type": "genre", "item_name": "Techno"},
        )
        r = await client.delete(
            f"/api/collections/{coll_id}/items/genre/0", params={"item_name": "Techno"}
        )
        assert r.status_code == 204

        data = (await client.get(f"/api/collections/{coll_id}")).json()
        assert data["item_count"] == 0

    async def test_remove_genre_without_name_rejected(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]
        r = await client.delete(f"/api/collections/{coll_id}/items/genre/0")
        assert r.status_code == 400

    async def test_remove_nonexistent(self, client, catalog_entry):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.delete(
            f"/api/collections/{coll_id}/items/track/{catalog_entry.id}"
        )
        assert r.status_code == 404


class TestDeleteCollection:
    async def test_delete(self, client):
        cr = await client.post("/api/collections/", json={"name": "Test"})
        coll_id = cr.json()["id"]

        r = await client.delete(f"/api/collections/{coll_id}")
        assert r.status_code == 204

        r2 = await client.get("/api/collections/")
        assert r2.json() == []

    async def test_delete_nonexistent(self, client):
        r = await client.delete("/api/collections/9999")
        assert r.status_code == 404


class TestFolders:
    async def test_list_empty(self, client):
        r = await client.get("/api/collections/folders")
        assert r.status_code == 200
        assert r.json() == []

    async def test_create_folder(self, client):
        r = await client.post("/api/collections/folders", json={"name": "House"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "House"
        assert data["position"] == 0
        assert data["collection_count"] == 0

    async def test_create_empty_name_rejected(self, client):
        r = await client.post("/api/collections/folders", json={"name": ""})
        assert r.status_code == 422

    async def test_list_returns_created(self, client):
        await client.post("/api/collections/folders", json={"name": "House"})
        r = await client.get("/api/collections/folders")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["name"] == "House"

    async def test_rename_folder(self, client):
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        r = await client.patch(
            f"/api/collections/folders/{fid}", json={"name": "Deep House"}
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Deep House"

    async def test_reposition_folder(self, client):
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        r = await client.patch(
            f"/api/collections/folders/{fid}", json={"position": 5}
        )
        assert r.status_code == 200
        assert r.json()["position"] == 5

    async def test_delete_folder(self, client):
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        r = await client.delete(f"/api/collections/folders/{fid}")
        assert r.status_code == 204
        assert (await client.get("/api/collections/folders")).json() == []

    async def test_update_nonexistent_folder(self, client):
        r = await client.patch(
            "/api/collections/folders/9999", json={"name": "Nope"}
        )
        assert r.status_code == 404

    async def test_delete_nonexistent_folder(self, client):
        r = await client.delete("/api/collections/folders/9999")
        assert r.status_code == 404

    # --- user scoping ---

    async def test_other_users_folder_hidden_from_list(
        self, client, other_user, db
    ):
        folder = CollectionFolder(user_id=other_user.id, name="Their Folder")
        db.add(folder)
        await db.commit()
        r = await client.get("/api/collections/folders")
        assert r.json() == []

    async def test_other_users_folder_patch_404(self, client, other_user, db):
        folder = CollectionFolder(user_id=other_user.id, name="Their Folder")
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        r = await client.patch(
            f"/api/collections/folders/{folder.id}", json={"name": "Hijack"}
        )
        assert r.status_code == 404

    async def test_other_users_folder_delete_404(self, client, other_user, db):
        folder = CollectionFolder(user_id=other_user.id, name="Their Folder")
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        r = await client.delete(f"/api/collections/folders/{folder.id}")
        assert r.status_code == 404

    async def test_assign_to_other_users_folder_404(
        self, client, other_user, db
    ):
        folder = CollectionFolder(user_id=other_user.id, name="Their Folder")
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        cr = await client.post("/api/collections/", json={"name": "Mine"})
        coll_id = cr.json()["id"]
        r = await client.patch(
            f"/api/collections/{coll_id}/folder", json={"folder_id": folder.id}
        )
        assert r.status_code == 404


class TestCollectionFolderAssignment:
    async def test_assign_and_reflect_in_list(self, client):
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        cr = await client.post("/api/collections/", json={"name": "Deep cuts"})
        coll_id = cr.json()["id"]

        r = await client.patch(
            f"/api/collections/{coll_id}/folder", json={"folder_id": fid}
        )
        assert r.status_code == 200
        assert r.json()["folder_id"] == fid

        # folder_id is surfaced on the collection listing
        listed = (await client.get("/api/collections/")).json()
        assert listed[0]["folder_id"] == fid
        # and the folder's collection_count reflects it
        folders = (await client.get("/api/collections/folders")).json()
        assert folders[0]["collection_count"] == 1

    async def test_remove_from_folder(self, client):
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        cr = await client.post("/api/collections/", json={"name": "Deep cuts"})
        coll_id = cr.json()["id"]
        await client.patch(
            f"/api/collections/{coll_id}/folder", json={"folder_id": fid}
        )

        r = await client.patch(
            f"/api/collections/{coll_id}/folder", json={"folder_id": None}
        )
        assert r.status_code == 200
        assert r.json()["folder_id"] is None
        listed = (await client.get("/api/collections/")).json()
        assert listed[0]["folder_id"] is None

    async def test_assign_nonexistent_collection_404(self, client):
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        r = await client.patch(
            "/api/collections/9999/folder", json={"folder_id": fid}
        )
        assert r.status_code == 404

    async def test_delete_folder_orphans_collections(self, client):
        """Deleting a folder leaves its collections alive with folder_id NULL."""
        fr = await client.post("/api/collections/folders", json={"name": "House"})
        fid = fr.json()["id"]
        cr = await client.post("/api/collections/", json={"name": "Deep cuts"})
        coll_id = cr.json()["id"]
        await client.patch(
            f"/api/collections/{coll_id}/folder", json={"folder_id": fid}
        )

        r = await client.delete(f"/api/collections/folders/{fid}")
        assert r.status_code == 204

        # The collection survives, now orphaned (folder_id NULL).
        listed = (await client.get("/api/collections/")).json()
        assert len(listed) == 1
        assert listed[0]["id"] == coll_id
        assert listed[0]["folder_id"] is None
