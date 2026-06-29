"""Tests for server/api/auth.py — JWT and password hashing utilities."""
import os
import time

os.environ.setdefault("JWT_SECRET", "test-secret")

from auth import hash_password, verify_password, create_token, decode_token


class TestHashPassword:
    def test_returns_bcrypt_hash(self):
        h = hash_password("password123")
        assert h.startswith("$2b$")
        assert len(h) > 50

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # salt should differ


class TestVerifyPassword:
    def test_correct_password(self):
        h = hash_password("mypass")
        assert verify_password("mypass", h) is True

    def test_wrong_password(self):
        h = hash_password("mypass")
        assert verify_password("wrong", h) is False


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
        # Flip a character in the signature
        parts = token.split(".")
        sig = parts[2]
        tampered = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        parts[2] = tampered
        assert decode_token(".".join(parts)) is None
