"""Tests for /api/auth endpoints (Google OAuth)."""
from unittest.mock import patch

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from auth import create_token

FAKE_GOOGLE_PAYLOAD = {
    "sub": "google-id-999",
    "email": "user@gmail.com",
    "name": "Test User",
    "picture": "https://lh3.googleusercontent.com/photo.jpg",
}


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestGoogleLogin:
    async def test_creates_user_on_first_login(self, client):
        with patch("routers.auth.verify_google_token", return_value=FAKE_GOOGLE_PAYLOAD):
            r = await client.post("/api/auth/google", json={"credential": "fake-token"})
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["username"] == "Test User"
        assert data["user_id"] > 0
        assert data["avatar_url"] == FAKE_GOOGLE_PAYLOAD["picture"]

    async def test_returns_same_user_on_second_login(self, client):
        with patch("routers.auth.verify_google_token", return_value=FAKE_GOOGLE_PAYLOAD):
            r1 = await client.post("/api/auth/google", json={"credential": "fake-token"})
            r2 = await client.post("/api/auth/google", json={"credential": "fake-token"})
        assert r1.json()["user_id"] == r2.json()["user_id"]

    async def test_invalid_token_returns_401(self, client):
        with patch("routers.auth.verify_google_token", return_value=None):
            r = await client.post("/api/auth/google", json={"credential": "bad-token"})
        assert r.status_code == 401

    async def test_disabled_account_returns_403(self, client, db):
        from models import User
        user = User(
            email="disabled@gmail.com",
            username="disabled",
            google_id="google-disabled",
            is_active=False,
        )
        db.add(user)
        await db.commit()

        payload = {**FAKE_GOOGLE_PAYLOAD, "sub": "google-disabled", "email": "disabled@gmail.com"}
        with patch("routers.auth.verify_google_token", return_value=payload):
            r = await client.post("/api/auth/google", json={"credential": "fake-token"})
        assert r.status_code == 403


class TestMe:
    async def test_returns_user_info(self, client):
        with patch("routers.auth.verify_google_token", return_value=FAKE_GOOGLE_PAYLOAD):
            reg = await client.post("/api/auth/google", json={"credential": "fake-token"})
        token = reg.json()["token"]
        r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "user@gmail.com"
        assert data["username"] == "Test User"

    async def test_no_token_returns_401(self, client):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401
