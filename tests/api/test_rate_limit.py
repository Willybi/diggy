"""Tests for server/api/rate_limit.py — Redis-based rate limiting middleware."""
from unittest.mock import MagicMock, patch
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
import rate_limit
from rate_limit import _get_real_ip, RATE_LIMITS, RateLimitMiddleware


class TestGetRealIp:
    def test_uses_x_real_ip(self):
        request = MagicMock()
        request.headers = {"X-Real-IP": "1.2.3.4"}
        assert _get_real_ip(request) == "1.2.3.4"

    def test_x_real_ip_wins_over_x_forwarded_for(self):
        request = MagicMock()
        request.headers = {"X-Real-IP": "1.2.3.4", "X-Forwarded-For": "6.6.6.6"}
        assert _get_real_ip(request) == "1.2.3.4"

    def test_x_forwarded_for_alone_is_ignored(self):
        """XFF is client-controlled: it must never be used for identity."""
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "6.6.6.6, 5.6.7.8"}
        request.client.host = "192.168.1.1"
        assert _get_real_ip(request) == "192.168.1.1"

    def test_falls_back_to_client_host(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.1"
        assert _get_real_ip(request) == "192.168.1.1"

    def test_strips_whitespace(self):
        request = MagicMock()
        request.headers = {"X-Real-IP": "  1.2.3.4 "}
        assert _get_real_ip(request) == "1.2.3.4"


class TestRateLimitConfig:
    def test_google_callback_rate_limit_defined(self):
        assert "/api/auth/google/callback" in RATE_LIMITS
        max_req, window = RATE_LIMITS["/api/auth/google/callback"]
        assert max_req == 5
        assert window == 60

    def test_all_limits_are_valid_tuples(self):
        for path, config in RATE_LIMITS.items():
            assert isinstance(config, tuple) and len(config) == 2
            max_req, window = config
            assert max_req > 0 and window > 0


class TestRateLimitMiddleware:
    def test_non_rate_limited_route_passes_through(self):
        """Request to a path not in RATE_LIMITS should pass through."""
        middleware = RateLimitMiddleware(app=MagicMock())

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/health"

        next_called = False
        async def mock_next(req):
            nonlocal next_called
            next_called = True
            return MagicMock()

        asyncio.run(middleware.dispatch(request, mock_next))
        assert next_called

    @patch("rate_limit._get_redis")
    def test_get_to_callback_checks_redis(self, mock_redis_fn):
        """GET to /api/auth/google/callback should be rate-limited."""
        middleware = RateLimitMiddleware(app=MagicMock())

        mock_r = MagicMock()
        mock_r.incr.return_value = 1
        mock_r.ttl.return_value = 60
        mock_redis_fn.return_value = mock_r

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/auth/google/callback"
        request.headers = {}
        request.client.host = "127.0.0.1"

        async def mock_next(req):
            return MagicMock()

        asyncio.run(middleware.dispatch(request, mock_next))
        mock_r.incr.assert_called_once()

    @patch("rate_limit._get_redis")
    def test_returns_429_when_limit_exceeded(self, mock_redis_fn):
        """Should return 429 when request count exceeds limit."""
        middleware = RateLimitMiddleware(app=MagicMock())

        mock_r = MagicMock()
        mock_r.incr.return_value = 10  # Exceeds limit of 5
        mock_r.ttl.return_value = 45
        mock_redis_fn.return_value = mock_r

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/auth/google/callback"
        request.headers = {}
        request.client.host = "127.0.0.1"

        async def mock_next(req):
            return MagicMock()

        response = asyncio.run(middleware.dispatch(request, mock_next))
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @patch("rate_limit._get_redis")
    def test_x_real_ip_used_as_key(self, mock_redis_fn):
        """The Redis key must be built from X-Real-IP when present."""
        middleware = RateLimitMiddleware(app=MagicMock())

        mock_r = MagicMock()
        mock_r.incr.return_value = 1
        mock_r.ttl.return_value = 60
        mock_redis_fn.return_value = mock_r

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/auth/google/callback"
        request.headers = {"X-Real-IP": "203.0.113.7"}
        request.client.host = "172.18.0.1"

        async def mock_next(req):
            return MagicMock()

        asyncio.run(middleware.dispatch(request, mock_next))
        key = mock_r.incr.call_args[0][0]
        assert key == "ratelimit:/api/auth/google/callback:203.0.113.7"

    @patch("rate_limit._get_redis")
    def test_spoofed_x_forwarded_for_shares_same_counter(self, mock_redis_fn):
        """Rotating X-Forwarded-For must NOT rotate the rate-limit key."""
        middleware = RateLimitMiddleware(app=MagicMock())

        mock_r = MagicMock()
        mock_r.incr.return_value = 1
        mock_r.ttl.return_value = 60
        mock_redis_fn.return_value = mock_r

        async def mock_next(req):
            return MagicMock()

        keys = []
        for spoofed in ("6.6.6.6", "7.7.7.7"):
            request = MagicMock()
            request.method = "GET"
            request.url.path = "/api/auth/google/callback"
            request.headers = {"X-Forwarded-For": spoofed}
            request.client.host = "172.18.0.1"
            asyncio.run(middleware.dispatch(request, mock_next))
            keys.append(mock_r.incr.call_args[0][0])

        assert keys[0] == keys[1] == "ratelimit:/api/auth/google/callback:172.18.0.1"

    @patch("rate_limit._get_redis")
    def test_redis_failure_passes_through_and_logs_warning(self, mock_redis_fn, caplog):
        """If Redis is unavailable, request passes through and a warning is logged."""
        middleware = RateLimitMiddleware(app=MagicMock())

        mock_redis_fn.side_effect = Exception("Redis down")

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/auth/google/callback"
        request.headers = {}
        request.client.host = "127.0.0.1"

        next_called = False
        async def mock_next(req):
            nonlocal next_called
            next_called = True
            return MagicMock()

        with caplog.at_level(logging.WARNING, logger="rate_limit"):
            asyncio.run(middleware.dispatch(request, mock_next))

        assert next_called
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Redis down" in r.getMessage() for r in warnings)


class TestRateLimitIntegration:
    """Integration test: hit the real ASGI app with a mock Redis."""

    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        counters = {}

        class FakeRedis:
            def incr(self, key):
                counters[key] = counters.get(key, 0) + 1
                return counters[key]

            def expire(self, key, ttl):
                pass

            def ttl(self, key):
                return 60

        with patch.object(rate_limit, "_redis", FakeRedis()):
            yield counters

    @pytest.mark.asyncio
    async def test_callback_429_after_limit(self, client):
        """Hit /api/auth/google/callback beyond 5 → 429 + Retry-After."""
        limit = RATE_LIMITS["/api/auth/google/callback"][0]
        for i in range(limit):
            resp = await client.get(
                "/api/auth/google/callback",
                params={"code": "x", "state": "x"},
            )
            assert resp.status_code != 429, f"Got 429 on request {i+1}"

        resp = await client.get(
            "/api/auth/google/callback",
            params={"code": "x", "state": "x"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    @pytest.mark.asyncio
    async def test_unlimited_route_never_429(self, client):
        """A route not in RATE_LIMITS should never get 429."""
        for _ in range(20):
            resp = await client.get("/api/health")
            assert resp.status_code != 429
