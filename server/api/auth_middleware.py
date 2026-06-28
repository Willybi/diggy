"""
JWT authentication middleware.
Rejects unauthenticated requests on non-public endpoints.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from auth import decode_token

# Public path prefixes (GET only) — browsing without auth
_PUBLIC_GET_PREFIXES = (
    "/api/catalog",
    "/api/artists",
    "/api/sets",
    "/api/genres",
    "/api/search",
    "/api/taxonomy",
)

# Always open (any method)
_OPEN_PREFIXES = (
    "/api/auth/",
    "/api/health",
    "/api/docs",
    "/api/openapi.json",
)

# Module flag — disabled in tests where dependency overrides handle auth
enabled = True


def _is_exempt(method: str, path: str) -> bool:
    """Return True if the request does not require a JWT."""
    for prefix in _OPEN_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return True

    if method == "GET" and any(path.startswith(p) for p in _PUBLIC_GET_PREFIXES):
        return True

    return False


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not enabled:
            return await call_next(request)

        path = request.url.path
        method = request.method

        # OPTIONS always allowed (CORS preflight)
        if method == "OPTIONS" or _is_exempt(method, path):
            return await call_next(request)

        # Extract and validate JWT
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        token = auth_header[7:]
        user_id = decode_token(token)
        if user_id is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        return await call_next(request)
