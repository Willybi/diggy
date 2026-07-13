"""Tests for /api/admin endpoints."""
from models import Artist, ArtistAlias, ArtistFlag, DJSet, SetArtist


class TestAdminRequired:
    async def test_sync_requires_admin(self, client):
        r = await client.post("/api/admin/artists/sync")
        assert r.status_code == 401

    async def test_sync_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post("/api/admin/artists/sync")
        assert r.status_code == 403


class TestSyncArtists:
    async def test_fires_task(self, admin_client):
        r = await admin_client.post("/api/admin/artists/sync")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "queued"
        assert "task_id" in data


class TestFetchArtworks:
    async def test_fires_task(self, admin_client):
        r = await admin_client.post("/api/admin/artists/fetch-artworks")
        assert r.status_code == 200
        assert r.json()["status"] == "queued"


class TestLinkArtistsDeezerTask:
    async def test_fires_task(self, admin_client):
        r = await admin_client.post("/api/admin/artists/link-deezer")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "queued"
        assert "task_id" in data

    async def test_requires_admin(self, client):
        r = await client.post("/api/admin/artists/link-deezer")
        assert r.status_code == 401


class TestLinkDeezer:
    async def test_link_artist(self, admin_client, db, mocker):
        a = Artist(name="Test Artist", normalized_name="test artist")
        db.add(a)
        await db.commit()
        await db.refresh(a)

        mocker.patch("requests.get", return_value=type("R", (), {
            "json": lambda self: {"name": "Official Name", "picture_xl": None}
        })())
        mocker.patch("services.image_service.ImageService.upload_from_url", return_value=False)

        r = await admin_client.patch(f"/api/admin/artists/{a.id}/deezer", json={"deezer_id": "12345"})
        assert r.status_code == 200
        data = r.json()
        assert data["deezer_id"] == "12345"
        assert data["name"] == "Official Name"
        assert data["merged"] is False

    async def test_unlink_artist(self, admin_client, db):
        a = Artist(name="Test", normalized_name="test", deezer_id="123")
        db.add(a)
        await db.commit()
        await db.refresh(a)

        r = await admin_client.patch(f"/api/admin/artists/{a.id}/deezer", json={"deezer_id": ""})
        assert r.status_code == 200
        assert r.json()["deezer_id"] is None

    async def test_404_for_unknown_artist(self, admin_client):
        r = await admin_client.patch("/api/admin/artists/9999/deezer", json={"deezer_id": "123"})
        assert r.status_code == 404


class TestMarkNoDeezer:
    async def test_sets_not_found_sentinel(self, admin_client, db):
        a = Artist(name="Unknown", normalized_name="unknown")
        db.add(a)
        await db.commit()
        await db.refresh(a)

        r = await admin_client.patch(f"/api/admin/artists/{a.id}/no-deezer")
        assert r.status_code == 200
        assert r.json()["name"] == "Unknown"


class TestFlags:
    async def test_create_manual_flag(self, admin_client, db):
        r = await admin_client.post("/api/admin/artists/flags/manual", json={
            "raw_artist_string": "A / B",
            "tokens": ["A", "B"],
            "reason": "manual",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["raw_artist_string"] == "A / B"
        assert data["status"] == "pending"

    async def test_list_pending_flags(self, admin_client, db):
        db.add(ArtistFlag(
            raw_artist_string="X / Y",
            reason="feat",
            tokens=["X", "Y"],
            deezer_ids={},
            status="pending",
        ))
        await db.commit()

        r = await admin_client.get("/api/admin/artists/flags?status=pending")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1

    async def test_resolve_flag_skip(self, admin_client, db):
        flag = ArtistFlag(
            raw_artist_string="X / Y",
            reason="feat",
            tokens=["X", "Y"],
            deezer_ids={},
            status="pending",
        )
        db.add(flag)
        await db.commit()
        await db.refresh(flag)

        r = await admin_client.post(f"/api/admin/artists/flags/{flag.id}/resolve", json={"action": "skip"})
        assert r.status_code == 200
        assert r.json()["status"] == "skipped"

    async def test_resolve_flag_split(self, admin_client, db):
        flag = ArtistFlag(
            raw_artist_string="X feat Y",
            reason="feat",
            tokens=["X", "Y"],
            deezer_ids={},
            status="pending",
        )
        db.add(flag)
        await db.commit()
        await db.refresh(flag)

        r = await admin_client.post(f"/api/admin/artists/flags/{flag.id}/resolve", json={"action": "split"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "validated"
        assert len(data["resolved_artist_ids"]) == 2


class TestSetArtists:
    async def test_add_set_artist(self, admin_client, db):
        a = Artist(name="ANNA", normalized_name="anna")
        s = DJSet(source="trackid", title="Test Set")
        db.add_all([a, s])
        await db.commit()
        await db.refresh(a)
        await db.refresh(s)

        r = await admin_client.post(f"/api/admin/sets/{s.id}/artists", json={
            "artist_id": a.id, "role": "dj",
        })
        assert r.status_code == 200
        assert r.json()["artist_id"] == a.id

    async def test_add_set_artist_duplicate_409(self, admin_client, db):
        a = Artist(name="ANNA", normalized_name="anna")
        s = DJSet(source="trackid", title="Test Set")
        db.add_all([a, s])
        await db.flush()
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="dj", position=0))
        await db.commit()
        await db.refresh(a)
        await db.refresh(s)

        r = await admin_client.post(f"/api/admin/sets/{s.id}/artists", json={
            "artist_id": a.id, "role": "dj",
        })
        assert r.status_code == 409

    async def test_remove_set_artist(self, admin_client, db):
        a = Artist(name="ANNA", normalized_name="anna")
        s = DJSet(source="trackid", title="Test Set")
        db.add_all([a, s])
        await db.flush()
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="dj", position=0))
        await db.commit()
        await db.refresh(a)
        await db.refresh(s)

        r = await admin_client.delete(f"/api/admin/sets/{s.id}/artists/{a.id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_remove_nonexistent_returns_404(self, admin_client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.commit()
        await db.refresh(s)

        r = await admin_client.delete(f"/api/admin/sets/{s.id}/artists/9999")
        assert r.status_code == 404


class TestLinkSetArtistsTask:
    async def test_fires_task(self, admin_client):
        r = await admin_client.post("/api/admin/sets/link-artists")
        assert r.status_code == 200
        assert r.json()["status"] == "queued"


