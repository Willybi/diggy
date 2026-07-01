"""Tests for server/api/auth.py — JWT utilities and Google token verification."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")

from auth import create_token, decode_token


class TestCreateToken:
    def test_returns_jwt_string(self):
        token = create_token(42)
        assert isinstance(token, str)
        assert len(token) > 20
        assert token.count(".") == 2  # JWT has 3 parts

    def test_different_users_different_tokens(self):
        t1 = create_token(1)
        t2 = create_token(2)
        assert t1 != t2


class TestDecodeToken:
    def test_roundtrip(self):
        token = create_token(42)
        uid = decode_token(token)
        assert uid == 42

    def test_invalid_token_returns_none(self):
        assert decode_token("invalid.token.here") is None

    def test_empty_string_returns_none(self):
        assert decode_token("") is None

    def test_tampered_token_returns_none(self):
        token = create_token(42)
        parts = token.split(".")
        parts[2] = "AAAA_TAMPERED_SIGNATURE_AAAA"
        assert decode_token(".".join(parts)) is None


class TestVerifyGoogleToken:
    @pytest.mark.asyncio
    async def test_exchanges_code_and_returns_user_info(self):
        # Mock httpx POST response
        mock_response = MagicMock()
        mock_response.json.return_value = {"id_token": "fake-id-token"}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        # Mock google.oauth2.id_token module (not installed locally)
        mock_verify_oauth2 = MagicMock(return_value={
            "sub": "google-789",
            "email": "user@gmail.com",
            "name": "Test User",
            "picture": "https://photo.url/pic.jpg",
        })
        mock_id_token_mod = MagicMock()
        mock_id_token_mod.verify_oauth2_token = mock_verify_oauth2

        mock_requests_mod = MagicMock()
        mock_oauth2 = MagicMock()
        mock_oauth2.id_token = mock_id_token_mod

        mock_auth_transport = MagicMock()
        mock_auth_transport.requests = mock_requests_mod

        mock_google_auth = MagicMock()
        mock_google_auth.transport = mock_auth_transport

        mock_google = MagicMock()
        mock_google.auth = mock_google_auth
        mock_google.oauth2 = mock_oauth2

        modules = {
            "google": mock_google,
            "google.auth": mock_google_auth,
            "google.auth.transport": mock_auth_transport,
            "google.auth.transport.requests": mock_requests_mod,
            "google.oauth2": mock_oauth2,
            "google.oauth2.id_token": mock_id_token_mod,
        }

        with patch("auth.httpx.AsyncClient", return_value=mock_client), \
             patch.dict(sys.modules, modules):
            from auth import verify_google_token

            result = await verify_google_token("auth-code-123")
            assert result["google_id"] == "google-789"
            assert result["email"] == "user@gmail.com"
            assert result["name"] == "Test User"
            assert result["picture"] == "https://photo.url/pic.jpg"
