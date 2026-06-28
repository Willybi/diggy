"""
Tests for the JWT auth middleware.

Re-enables the middleware (disabled globally in conftest) to test
that unauthenticated requests are rejected on protected endpoints
and allowed on public ones.
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import auth_middleware
from auth import create_token
from main import app


@pytest_asyncio.fixture
async def mw_client(auth_user):
    """Client with middleware enabled, keeping only the DB override."""
    from database import get_db
    old = auth_middleware.enabled
    auth_middleware.enabled = True
    saved = dict(app.dependency_overrides)
    # Keep only the DB override — strip auth overrides so middleware is tested
    db_override = saved.get(get_db)
    app.dependency_overrides.clear()
    if db_override:
        app.dependency_overrides[get_db] = db_override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as c:
        yield c, auth_user
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)
    auth_middleware.enabled = old


class TestPublicEndpoints:
    """Public endpoints should be accessible without a token."""

    async def test_health(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/health")
        assert r.status_code == 200

    async def test_auth_login_no_token_needed(self, mw_client):
        client, _ = mw_client
        r = await client.post("/api/auth/login", json={
            "email": "nobody@test.com", "password": "wrong",
        })
        # 401 from login logic, NOT from middleware
        assert r.status_code == 401
        assert "Invalid" in r.json()["detail"] or "credentials" in r.json()["detail"].lower()

    async def test_auth_register_no_token_needed(self, mw_client):
        client, _ = mw_client
        r = await client.post("/api/auth/register", json={
            "email": "mw@test.com", "username": "mwuser", "password": "secret123",
        })
        assert r.status_code == 201

    async def test_catalog_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/catalog/")
        assert r.status_code == 200

    async def test_artists_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/artists/")
        assert r.status_code == 200

    async def test_sets_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/sets/")
        assert r.status_code == 200


class TestProtectedEndpoints:
    """Non-public endpoints should require a valid JWT."""

    async def test_tracks_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/tracks/")
        assert r.status_code == 401
        assert r.json()["detail"] == "Not authenticated"

    async def test_tracks_invalid_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/tracks/", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid or expired token"

    async def test_tracks_valid_token_passes_middleware(self, mw_client):
        client, user = mw_client
        token = create_token(user.id)
        r = await client.get("/api/tracks/", headers={
            "Authorization": f"Bearer {token}",
        })
        # Should pass middleware (200 from route handler)
        assert r.status_code == 200

    async def test_radar_full_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/radar/full")
        assert r.status_code == 401

    async def test_opinions_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/opinions/")
        assert r.status_code == 401

    async def test_catalog_patch_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.patch("/api/catalog/1/avis", json={"avis": "liked"})
        assert r.status_code == 401

    async def test_admin_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.post("/api/admin/artists/sync")
        assert r.status_code == 401


class TestOptionsPreflightAllowed:
    """CORS preflight (OPTIONS) should always pass through."""

    async def test_options_no_token_ok(self, mw_client):
        client, _ = mw_client
        r = await client.options("/api/tracks/")
        # FastAPI returns 405 for OPTIONS on routes without explicit OPTIONS handler,
        # but the middleware should NOT block it with 401
        assert r.status_code != 401
