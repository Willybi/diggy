"""
Redis-based rate limiting middleware.
No decorators — limits are defined by path prefix in RATE_LIMITS.
Shared counters across all uvicorn workers via Redis.
"""

import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# path prefix -> (max_requests, window_seconds)
RATE_LIMITS = {
    "/api/auth/google/callback": (5, 60),
    # Stricter than /api/search (external API calls). MUST precede /api/search:
    # matching is `path.startswith(prefix)`, first insertion-order match wins.
    "/api/search/external": (10, 60),
    "/api/search": (30, 60),
    # Manual import triggers external API calls (Deezer/TIDAL fetch + artwork).
    "/api/catalog/import": (20, 60),
    "/api/import/rekordbox": (3, 300),
    # Manual Deezer linking clicks through many artists, one external search per
    # click. Give it its own generous bucket, ahead of /api/admin (startswith
    # match, first insertion-order match wins). Admin-only, and 60/60s stays
    # well under Deezer's own limit (~50 req / 5s).
    "/api/admin/artists/search-deezer": (60, 60),
    # Interactive admin workflows fire GET+PATCH sequences (link, flag, split);
    # 10/60s throttled real cleanup sessions. Admin-gated, so a high cap is safe.
    "/api/admin": (60, 60),
    # Personalised reco can trigger a full on-the-fly similarity compute on a
    # cache miss (bounded by SEED_CAP), so keep it modestly capped.
    "/api/recommendations": (30, 60),
}

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis

        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _get_real_ip(request) -> str:
    # X-Real-IP is set by nginx from $remote_addr and cannot be spoofed by the
    # client. X-Forwarded-For must never be used for identity: its first value
    # is client-controlled, which would let an attacker rotate it per request
    # and bypass any limit.
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # Local dev without nginx in front
    return request.client.host


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        limit_config = None
        for prefix, config in RATE_LIMITS.items():
            if path == prefix or path == prefix + "/" or path.startswith(prefix + "/"):
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
        except Exception as exc:
            # Fail-open by design: availability wins over rate limiting.
            # Log it so a Redis outage doesn't silently disable all limits.
            logger.warning("Rate limiting skipped (Redis unavailable): %s", exc)

        return await call_next(request)
