"""
Tests for multi-user import flow (Phase 7).

Covers:
- Private catalog entries get owner_id set
- Multi-user isolation (user2 can't see user1's tracks)
- Shared catalog entries are reused across users
- Scope promotion (private → shared on Deezer enrichment)
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from main import app
from dependencies import get_current_user
from models import User, CatalogEntry, UserTrack


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def user2(db):
    user = User(
        email="user2@test.com",
        username="user2",
        google_id="google-test-user2",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def client1(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


def _swap_user(user):
    """Swap the current user for subsequent requests."""
    app.dependency_overrides[get_current_user] = lambda: user


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
        "tags": [],
        "image_base64": None,
    }
    base.update(overrides)
    return base


# ── Tests: owner_id on private catalog entries ───────────────────────────────


class TestPrivateCatalogOwnership:
    async def test_private_entry_gets_owner_id(self, client1, auth_user, db, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        r = await client1.post("/api/tracks/bulk", json=[track_payload()])
        assert r.status_code == 200
        assert r.json()["inserted"] == 1

        result = await db.execute(
            select(CatalogEntry).where(CatalogEntry.scope == "private")
        )
        entry = result.scalar_one()
        assert entry.owner_id == auth_user.id
        assert entry.origin == "rekordbox"

    async def test_shared_entry_reused_no_owner(self, client1, db, mocker):
        """When a catalog entry already exists (shared), it should be reused without setting owner_id."""
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        # Pre-create a shared catalog entry
        from utils import make_normalized_key
        norm_key = make_normalized_key("Wannabe", "VOLAC")
        shared = CatalogEntry(
            title="Wannabe",
            artist="VOLAC",
            normalized_key=norm_key,
            scope="shared",
            origin="deezer",
        )
        db.add(shared)
        await db.commit()
        await db.refresh(shared)

        r = await client1.post("/api/tracks/bulk", json=[track_payload()])
        assert r.status_code == 200
        assert r.json()["inserted"] == 1

        # Verify the shared entry was reused, not a new private one created
        result = await db.execute(select(CatalogEntry))
        entries = result.scalars().all()
        assert len(entries) == 1
        assert entries[0].scope == "shared"
        assert entries[0].owner_id is None


# ── Tests: multi-user isolation ──────────────────────────────────────────────


class TestMultiUserIsolation:
    async def test_users_see_only_their_tracks(self, client1, auth_user, user2, db, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        # User 1 imports track 1
        _swap_user(auth_user)
        r1 = await client1.post("/api/tracks/bulk", json=[track_payload(id=1, title="Track A")])
        assert r1.json()["inserted"] == 1

        # User 2 imports track 2
        _swap_user(user2)
        r2 = await client1.post("/api/tracks/bulk", json=[track_payload(id=2, title="Track B")])
        assert r2.json()["inserted"] == 1

        # User 1 sees only their track
        _swap_user(auth_user)
        r = await client1.get("/api/tracks/")
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["title"] == "Track A"

        # User 2 sees only their track
        _swap_user(user2)
        r = await client1.get("/api/tracks/")
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["title"] == "Track B"

    async def test_existing_ids_scoped_to_user(self, client1, auth_user, user2, mocker):
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        _swap_user(auth_user)
        await client1.post("/api/tracks/bulk", json=[track_payload(id=10)])

        # User 1 sees the ID
        r1 = await client1.get("/api/tracks/existing-ids")
        assert len(r1.json()) == 1

        # User 2 does not
        _swap_user(user2)
        r2 = await client1.get("/api/tracks/existing-ids")
        assert len(r2.json()) == 0

    async def test_two_users_same_track_share_catalog(self, client1, auth_user, user2, db, mocker):
        """Two users importing the same track should share the same catalog entry."""
        mocker.patch("storage.ensure_bucket")
        mocker.patch("storage.upload_artwork")

        _swap_user(auth_user)
        payload = track_payload(id=1, title="Shared Track", artist="ArtistX")
        await client1.post("/api/tracks/bulk", json=[payload])

        # User 2 imports same track (different rekordbox_id, same title/artist)
        _swap_user(user2)
        payload2 = track_payload(id=99, title="Shared Track", artist="ArtistX")
        await client1.post("/api/tracks/bulk", json=[payload2])

        # Both should point to the same catalog entry
        result = await db.execute(select(UserTrack))
        user_tracks = result.scalars().all()
        assert len(user_tracks) == 2
        # Both user_tracks should reference the same catalog_id
        catalog_ids = {ut.catalog_id for ut in user_tracks}
        assert len(catalog_ids) == 1


# ── Tests: scope promotion ───────────────────────────────────────────────────


class TestScopePromotion:
    def test_enrich_promotes_private_to_shared(self):
        """When enrich_entry sets deezer_id on a private entry, it should promote to shared."""
        from deezer_enrich import enrich_entry

        class FakeEntry:
            def __init__(self):
                self.id = 1
                self.deezer_id = None
                self.isrc = None
                self.duration_ms = None
                self.has_preview = False
                self.has_artwork = False
                self.scope = "private"
                self.owner_id = 42

        entry = FakeEntry()
        hit = {"id": 12345, "duration": 180, "preview": "http://preview.mp3"}

        changed = enrich_entry(entry, hit, s3=None)
        assert changed is True
        assert entry.deezer_id == "12345"
        assert entry.scope == "shared"
        assert entry.owner_id is None

    def test_enrich_shared_stays_shared(self):
        """Enriching a shared entry should not change its scope."""
        from deezer_enrich import enrich_entry

        class FakeEntry:
            def __init__(self):
                self.id = 1
                self.deezer_id = None
                self.isrc = None
                self.duration_ms = None
                self.has_preview = False
                self.has_artwork = False
                self.scope = "shared"
                self.owner_id = None

        entry = FakeEntry()
        hit = {"id": 99999, "duration": 200, "preview": ""}

        enrich_entry(entry, hit, s3=None)
        assert entry.scope == "shared"
        assert entry.owner_id is None

    def test_no_promotion_without_deezer_match(self):
        """If enrich_entry makes no changes (already enriched), no promotion."""
        from deezer_enrich import enrich_entry

        class FakeEntry:
            def __init__(self):
                self.id = 1
                self.deezer_id = "12345"
                self.isrc = "USRC12345"
                self.duration_ms = 180000
                self.has_preview = True
                self.has_artwork = True
                self.scope = "private"
                self.owner_id = 42

        entry = FakeEntry()
        hit = {"id": 12345, "duration": 180, "preview": "http://preview.mp3"}

        changed = enrich_entry(entry, hit, s3=None)
        assert changed is False
        # Scope stays private because nothing changed
        assert entry.scope == "private"
