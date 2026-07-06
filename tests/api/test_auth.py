"""Tests for /api/auth endpoints (Google OAuth)."""
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from auth import create_token


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


FAKE_GOOGLE_INFO = {
    "google_id": "google-123456",
    "email": "testgoogle@gmail.com",
    "name": "Test User",
    "picture": "https://lh3.googleusercontent.com/photo.jpg",
}


class TestGoogleLogin:
    async def test_returns_url_and_state(self, client):
        r = await client.get("/api/auth/google/login")
        assert r.status_code == 200
        data = r.json()
        assert "url" in data
        assert "accounts.google.com" in data["url"]
        assert "state" in data


class TestGoogleCallback:
    async def _callback(self, client, code="test-code", state="test-state"):
        return await client.get(
            f"/api/auth/google/callback?code={code}&state={state}",
            follow_redirects=False,
        )

    @patch("routers.auth.verify_google_token", new_callable=AsyncMock, return_value=FAKE_GOOGLE_INFO)
    async def test_creates_user_and_returns_html(self, mock_verify, client):
        r = await self._callback(client)
        assert r.status_code == 200
        body = r.text
        assert "diggy_token" in body
        assert "diggy_user" in body
        assert "oauth_state" in body
        assert "no-store" in r.headers.get("cache-control", "")

    @patch("routers.auth.verify_google_token", new_callable=AsyncMock, return_value=FAKE_GOOGLE_INFO)
    async def test_second_login_reuses_user(self, mock_verify, client):
        await self._callback(client)
        r = await self._callback(client)
        assert r.status_code == 200
        # Still works — same user, no duplicate error

    @patch("routers.auth.verify_google_token", new_callable=AsyncMock, return_value=FAKE_GOOGLE_INFO)
    async def test_html_contains_state(self, mock_verify, client):
        r = await self._callback(client, state="mystate123")
        assert r.status_code == 200
        assert "mystate123" in r.text


class TestMe:
    async def test_returns_user_info(self, auth_user, client):
        token = create_token(auth_user.id)
        r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "test@test.com"
        assert data["username"] == "testuser"

    async def test_no_token_returns_401(self, client):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401
