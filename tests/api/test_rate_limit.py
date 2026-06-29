"""Tests for server/api/rate_limit.py — Redis-based rate limiting middleware."""
from unittest.mock import MagicMock, patch
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("JWT_SECRET", "test-secret")

from rate_limit import _get_real_ip, RATE_LIMITS, RateLimitMiddleware


class TestGetRealIp:
    def test_uses_x_forwarded_for(self):
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        assert _get_real_ip(request) == "1.2.3.4"

    def test_uses_x_forwarded_for_single(self):
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        assert _get_real_ip(request) == "10.0.0.1"

    def test_falls_back_to_client_host(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.1"
        assert _get_real_ip(request) == "192.168.1.1"

    def test_strips_whitespace(self):
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "  1.2.3.4 , 5.6.7.8"}
        assert _get_real_ip(request) == "1.2.3.4"


class TestRateLimits:
    def test_login_rate_limit_defined(self):
        assert "/api/auth/login" in RATE_LIMITS
        max_req, window = RATE_LIMITS["/api/auth/login"]
        assert max_req == 5
        assert window == 60

    def test_register_rate_limit_defined(self):
        assert "/api/auth/register" in RATE_LIMITS
        max_req, window = RATE_LIMITS["/api/auth/register"]
        assert max_req == 3
        assert window == 60


class TestRateLimitMiddleware:
    def test_get_requests_pass_through(self):
        """GET requests should not be rate limited."""
        middleware = RateLimitMiddleware(app=MagicMock())

        import asyncio

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/auth/login"

        next_called = False
        async def mock_next(req):
            nonlocal next_called
            next_called = True
            return MagicMock()

        asyncio.run(middleware.dispatch(request, mock_next))
        assert next_called

    def test_non_rate_limited_post_passes_through(self):
        """POST to non-rate-limited paths should pass through."""
        middleware = RateLimitMiddleware(app=MagicMock())

        import asyncio

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/tracks/bulk"

        next_called = False
        async def mock_next(req):
            nonlocal next_called
            next_called = True
            return MagicMock()

        asyncio.run(middleware.dispatch(request, mock_next))
        assert next_called

    @patch("rate_limit._get_redis")
    def test_post_to_login_checks_redis(self, mock_redis_fn):
        """POST to /api/auth/login should check Redis."""
        middleware = RateLimitMiddleware(app=MagicMock())

        import asyncio

        mock_r = MagicMock()
        mock_r.incr.return_value = 1
        mock_r.ttl.return_value = 60
        mock_redis_fn.return_value = mock_r

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/auth/login"
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

        import asyncio

        mock_r = MagicMock()
        mock_r.incr.return_value = 10  # Exceeds limit of 5
        mock_r.ttl.return_value = 45
        mock_redis_fn.return_value = mock_r

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"

        async def mock_next(req):
            return MagicMock()

        response = asyncio.run(middleware.dispatch(request, mock_next))
        assert response.status_code == 429

    @patch("rate_limit._get_redis")
    def test_redis_failure_passes_through(self, mock_redis_fn):
        """If Redis is unavailable, request should still pass through."""
        middleware = RateLimitMiddleware(app=MagicMock())

        import asyncio

        mock_redis_fn.side_effect = Exception("Redis down")

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/auth/login"
        request.headers = {}
        request.client.host = "127.0.0.1"

        next_called = False
        async def mock_next(req):
            nonlocal next_called
            next_called = True
            return MagicMock()

        asyncio.run(middleware.dispatch(request, mock_next))
        assert next_called
