"""
Redis-based rate limiting middleware.
No decorators — limits are defined by path prefix in RATE_LIMITS.
Shared counters across all uvicorn workers via Redis.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# path prefix -> (max_requests, window_seconds)
RATE_LIMITS = {
    "/api/auth/login": (5, 60),
    "/api/auth/register": (3, 60),
}

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _get_real_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != "POST":
            return await call_next(request)

        path = request.url.path
        limit_config = None
        for prefix, config in RATE_LIMITS.items():
            if path == prefix or path == prefix + "/":
                limit_config = config
                break

        if limit_config is None:
            return await call_next(request)

        max_requests, window = limit_config
        ip = _get_real_ip(request)
        key = f"ratelimit:{path}:{ip}"

        try:
            r = _get_redis()
            current = r.incr(key)
            if current == 1:
                r.expire(key, window)
            ttl = r.ttl(key)

            if current > max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Rate limit exceeded. Try again in {ttl}s."},
                    headers={"Retry-After": str(ttl)},
                )
        except Exception:
            # If Redis is unavailable, let the request through
            pass

        return await call_next(request)
