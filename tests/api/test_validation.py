"""
Tests for input validation: Literal enums, max_length, bulk limits.
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from dependencies import get_current_user, require_admin


@pytest_asyncio.fixture
async def client(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def admin_client(admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[require_admin] = lambda: admin_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Radar status validation ──────────────────────────────────────────────────

class TestRadarStatusValidation:
    async def test_invalid_status_returns_422(self, client):
        r = await client.patch("/api/radar/1/state", json={"status": "banana"})
        assert r.status_code == 422

    async def test_valid_status_accepted(self, client, db):
        from models import CatalogEntry
        entry = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        r = await client.patch(f"/api/radar/{entry.id}/state", json={"status": "seen"})
        assert r.status_code != 422


class TestRadarBatchValidation:
    async def test_invalid_status_in_batch_returns_422(self, client):
        r = await client.patch(
            "/api/radar/state/batch",
            json=[{"catalog_id": 1, "status": "invalid"}],
        )
        assert r.status_code == 422

    async def test_missing_catalog_id_returns_422(self, client):
        r = await client.patch(
            "/api/radar/state/batch",
            json=[{"status": "seen"}],
        )
        assert r.status_code == 422

    async def test_valid_batch_accepted(self, client, db):
        from models import CatalogEntry
        entry = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        r = await client.patch(
            "/api/radar/state/batch",
            json=[{"catalog_id": entry.id, "status": "seen"}],
        )
        assert r.status_code != 422


# ── Catalog sort/order validation ────────────────────────────────────────────

class TestCatalogSortValidation:
    async def test_invalid_sort_returns_422(self, client):
        r = await client.get("/api/catalog/?sort=invalid_column")
        assert r.status_code == 422

    async def test_valid_sort_accepted(self, client):
        r = await client.get("/api/catalog/?sort=title")
        assert r.status_code == 200

    async def test_invalid_order_returns_422(self, client):
        r = await client.get("/api/catalog/?order=sideways")
        assert r.status_code == 422

    async def test_valid_order_accepted(self, client):
        r = await client.get("/api/catalog/?order=asc")
        assert r.status_code == 200

    async def test_invalid_view_returns_422(self, client):
        r = await client.get("/api/catalog/?view=invalid")
        assert r.status_code == 422

    async def test_invalid_avis_returns_422(self, client):
        r = await client.get("/api/catalog/?avis=maybe")
        assert r.status_code == 422


# ── Catalog avis update validation ───────────────────────────────────────────

class TestCatalogAvisUpdateValidation:
    async def test_invalid_avis_value_returns_422(self, client, db):
        from models import CatalogEntry
        entry = CatalogEntry(title="Test", artist="Test", normalized_key="test|test")
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        r = await client.patch(
            f"/api/catalog/{entry.id}/avis",
            json={"avis": "banana"},
        )
        assert r.status_code == 422


# ── Max length validation ────────────────────────────────────────────────────

class TestMaxLengthValidation:
    async def test_catalog_search_too_long_returns_422(self, client):
        r = await client.get(f"/api/catalog/?search={'x' * 201}")
        assert r.status_code == 422

    async def test_catalog_search_at_limit_accepted(self, client):
        r = await client.get(f"/api/catalog/?search={'x' * 200}")
        assert r.status_code == 200

    async def test_radar_search_too_long_returns_422(self, client):
        r = await client.get(f"/api/radar/full?search={'x' * 201}")
        assert r.status_code == 422


# ── Radar sort validation ────────────────────────────────────────────────────

class TestRadarSortValidation:
    async def test_invalid_sort_returns_422(self, client):
        r = await client.get("/api/radar/full?sort=invalid")
        assert r.status_code == 422

    async def test_valid_sort_not_rejected_as_invalid(self, client):
        # radar sort_map uses genres[1] which crashes on SQLite,
        # but we verify the Literal validation itself passes (no 422)
        # The endpoint may return 500 due to SQLite limitations
        try:
            r = await client.get("/api/radar/full?sort=detected_at")
            assert r.status_code != 422
        except NotImplementedError:
            pass  # SQLite doesn't support ARRAY indexing

    async def test_invalid_order_returns_422(self, client):
        r = await client.get("/api/radar/full?order=sideways")
        assert r.status_code == 422


# ── Admin flag status validation ─────────────────────────────────────────────

class TestAdminFlagValidation:
    async def test_invalid_flag_status_returns_422(self, admin_client):
        r = await admin_client.get("/api/admin/artists/flags?status=invalid")
        assert r.status_code == 422

    async def test_valid_flag_status_accepted(self, admin_client):
        r = await admin_client.get("/api/admin/artists/flags?status=pending")
        assert r.status_code == 200

    async def test_invalid_resolve_action_returns_422(self, admin_client, db):
        from models import ArtistFlag
        flag = ArtistFlag(
            raw_artist_string="Test", reason="test",
            tokens=["test"], deezer_ids={}, status="pending",
        )
        db.add(flag)
        await db.commit()
        await db.refresh(flag)

        r = await admin_client.post(
            f"/api/admin/artists/flags/{flag.id}/resolve",
            json={"action": "invalid"},
        )
        assert r.status_code == 422
