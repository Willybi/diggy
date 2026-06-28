"""Tests for /api/auth endpoints."""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from auth import create_token


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestRegister:
    async def test_creates_user(self, client):
        r = await client.post("/api/auth/register", json={
            "email": "new@test.com",
            "username": "newuser",
            "password": "secret123",
        })
        assert r.status_code == 201
        data = r.json()
        assert "token" in data
        assert data["username"] == "newuser"
        assert data["user_id"] > 0

    async def test_duplicate_email_returns_409(self, client):
        body = {"email": "dup@test.com", "username": "user1", "password": "password123"}
        await client.post("/api/auth/register", json=body)
        r = await client.post("/api/auth/register", json={
            "email": "dup@test.com", "username": "user2", "password": "password123",
        })
        assert r.status_code == 409

    async def test_duplicate_username_returns_409(self, client):
        body = {"email": "a@test.com", "username": "sameuser", "password": "password123"}
        await client.post("/api/auth/register", json=body)
        r = await client.post("/api/auth/register", json={
            "email": "b@test.com", "username": "sameuser", "password": "password123",
        })
        assert r.status_code == 409


class TestLogin:
    async def test_login_success(self, client):
        await client.post("/api/auth/register", json={
            "email": "login@test.com", "username": "loginuser", "password": "mypassword",
        })
        r = await client.post("/api/auth/login", json={
            "email": "login@test.com", "password": "mypassword",
        })
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["username"] == "loginuser"

    async def test_bad_password_returns_401(self, client):
        await client.post("/api/auth/register", json={
            "email": "bp@test.com", "username": "bpuser", "password": "correctpass",
        })
        r = await client.post("/api/auth/login", json={
            "email": "bp@test.com", "password": "wrongpass",
        })
        assert r.status_code == 401

    async def test_unknown_email_returns_401(self, client):
        r = await client.post("/api/auth/login", json={
            "email": "nope@test.com", "password": "password123",
        })
        assert r.status_code == 401


class TestMe:
    async def test_returns_user_info(self, client):
        reg = await client.post("/api/auth/register", json={
            "email": "me@test.com", "username": "meuser", "password": "password123",
        })
        token = reg.json()["token"]
        r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "me@test.com"
        assert data["username"] == "meuser"

    async def test_no_token_returns_401(self, client):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401
