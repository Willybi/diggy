"""Tests for /api/auth endpoints (Google OAuth)."""
import base64
import json
from urllib.parse import parse_qs, urlparse
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
    async def test_returns_url(self, client):
        r = await client.get("/api/auth/google/login")
        assert r.status_code == 200
        data = r.json()
        assert "url" in data
        assert "accounts.google.com" in data["url"]
        # state is in the URL, not returned separately
        qs = parse_qs(urlparse(data["url"]).query)
        assert "state" in qs


class TestGoogleCallback:
    async def _get_state(self, client):
        """Start a login flow and extract the state from the returned URL."""
        r = await client.get("/api/auth/google/login")
        url = r.json()["url"]
        return parse_qs(urlparse(url).query)["state"][0]

    async def _callback(self, client, code="test-code", state=None):
        if state is None:
            state = await self._get_state(client)
        return await client.get(
            f"/api/auth/google/callback?code={code}&state={state}",
            follow_redirects=False,
        )

    @patch("routers.auth.verify_google_token", new_callable=AsyncMock, return_value=FAKE_GOOGLE_INFO)
    async def test_creates_user_and_sets_cookie(self, mock_verify, client):
        r = await self._callback(client)
        assert r.status_code == 302
        assert r.headers["location"] == "/login/callback"
        assert "auth_callback" in r.headers.get("set-cookie", "")

    @patch("routers.auth.verify_google_token", new_callable=AsyncMock, return_value=FAKE_GOOGLE_INFO)
    async def test_second_login_reuses_user(self, mock_verify, client):
        await self._callback(client)
        r = await self._callback(client)
        assert r.status_code == 302

    @patch("routers.auth.verify_google_token", new_callable=AsyncMock, return_value=FAKE_GOOGLE_INFO)
    async def test_cookie_contains_token_and_user(self, mock_verify, client):
        r = await self._callback(client)
        assert r.status_code == 302
        cookie = r.headers["set-cookie"]
        value = cookie.split("auth_callback=")[1].split(";")[0]
        value += "=" * ((4 - len(value) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value))
        assert "token" in payload
        assert "user" in payload

    async def test_invalid_state_rejected(self, client):
        """Callback with unknown state is rejected (no Redis entry)."""
        r = await self._callback(client, state="bogus-state-value")
        assert r.status_code == 302
        assert "error=" in r.headers["location"]


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
