"""
Tests for the JWT auth middleware.

Re-enables the middleware (disabled globally in conftest) to test
that unauthenticated requests are rejected on protected endpoints
and allowed on public ones.
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import auth_middleware
from auth import create_token
from main import app


@pytest_asyncio.fixture
async def mw_client(auth_user):
    """Client with middleware enabled, keeping only the DB override."""
    from database import get_db
    from dependencies import get_redis
    old = auth_middleware.enabled
    auth_middleware.enabled = True
    saved = dict(app.dependency_overrides)
    # Keep DB + Redis overrides — strip auth overrides so middleware is tested
    db_override = saved.get(get_db)
    redis_override = saved.get(get_redis)
    app.dependency_overrides.clear()
    if db_override:
        app.dependency_overrides[get_db] = db_override
    if redis_override:
        app.dependency_overrides[get_redis] = redis_override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as c:
        yield c, auth_user
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)
    auth_middleware.enabled = old


class TestPublicEndpoints:
    """Public endpoints should be accessible without a token."""

    async def test_health(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/health")
        assert r.status_code == 200

    async def test_auth_google_login_no_token_needed(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/auth/google/login")
        assert r.status_code == 200
        assert "url" in r.json()

    async def test_auth_google_callback_no_token_needed(self, mw_client):
        client, _ = mw_client
        # Will fail at app level (invalid code), but middleware should not block it
        r = await client.get(
            "/api/auth/google/callback?code=x&state=y",
            follow_redirects=False,
        )
        # 302 = app-level redirect to /login/callback?error=... (not 401 from middleware)
        assert r.status_code == 302

    async def test_catalog_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/catalog/")
        assert r.status_code == 200

    async def test_artists_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/artists/")
        assert r.status_code == 200

    async def test_sets_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/sets/")
        assert r.status_code == 200

    async def test_albums_get_public(self, mw_client):
        # C7: album detail is guest-accessible (open discovery, like /api/sets).
        # A guest must reach the route (404 for a missing id), never a 401 from
        # the middleware — the router's optional reader only runs past the gate.
        client, _ = mw_client
        r = await client.get("/api/albums/1")
        assert r.status_code == 404

    async def test_radar_trends_get_public(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/radar/trends?limit=20")
        assert r.status_code == 200


class TestProtectedEndpoints:
    """Non-public endpoints should require a valid JWT."""

    async def test_collections_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/collections/")
        assert r.status_code == 401
        assert r.json()["detail"] == "Not authenticated"

    async def test_collections_invalid_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/collections/", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid or expired token"

    async def test_collections_valid_token_passes_middleware(self, mw_client):
        client, user = mw_client
        token = create_token(user.id)
        r = await client.get("/api/collections/", headers={
            "Authorization": f"Bearer {token}",
        })
        # Should pass middleware (200 from route handler)
        assert r.status_code == 200

    async def test_radar_new_count_no_token_returns_401(self, mw_client):
        # Guard: the /trends allowlist entry must not open the rest of /api/radar.
        client, _ = mw_client
        r = await client.get("/api/radar/new-count")
        assert r.status_code == 401

    async def test_opinions_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.get("/api/opinions/")
        assert r.status_code == 401

    async def test_catalog_patch_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.patch("/api/catalog/1/avis", json={"avis": "liked"})
        assert r.status_code == 401

    async def test_admin_no_token_returns_401(self, mw_client):
        client, _ = mw_client
        r = await client.post("/api/admin/artists/sync")
        assert r.status_code == 401

    async def test_watchlist_active_no_token_returns_401(self, mw_client):
        # A6-10: the endpoint was removed (crawl_radar reads the DB directly)
        # and its _OPEN_PREFIXES exemption with it — guests must get 401.
        client, _ = mw_client
        r = await client.get("/api/watchlist/active")
        assert r.status_code == 401

    async def test_artists_follow_post_no_token_returns_401(self, mw_client):
        # /api/artists is public in GET only — non-GET (follow) requires a JWT.
        client, _ = mw_client
        r = await client.post("/api/artists/1/follow")
        assert r.status_code == 401

    async def test_following_no_token_returns_401(self, mw_client):
        # /api/following is absent from the allowlists — protected by default.
        client, _ = mw_client
        r = await client.get("/api/following/")
        assert r.status_code == 401


class TestOptionsPreflightAllowed:
    """CORS preflight (OPTIONS) should always pass through."""

    async def test_options_no_token_ok(self, mw_client):
        client, _ = mw_client
        r = await client.options("/api/collections/")
        # FastAPI returns 405 for OPTIONS on routes without explicit OPTIONS handler,
        # but the middleware should NOT block it with 401
        assert r.status_code != 401

    async def test_cors_preflight_returns_headers(self, mw_client):
        # A real preflight (Origin + Access-Control-Request-Method) is answered by
        # CORSMiddleware with 200 + the allow-origin header, ahead of the JWT
        # middleware — proves the outermost CORS layer still short-circuits under
        # the Starlette bump.
        client, _ = mw_client
        r = await client.options(
            "/api/collections/",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


class TestErrorPropagation:
    """The app's catch-all ``Exception`` handler must still convert an unhandled
    error into the JSON 500 *through* the two BaseHTTPMiddleware layers (JWTAuth
    + RateLimit). BaseHTTPMiddleware is the most-rewritten Starlette API on a
    major bump, and the CI suite normally runs with the middleware DISABLED — so
    this is the only place the full stack + ServerErrorMiddleware are exercised
    end to end. Both the 401 short-circuit and the 500 pass-through are asserted
    on the same protected route to cover both directions of the stack.
    """

    async def test_401_and_catch_all_500_through_full_stack(self, mw_client):
        _, user = mw_client
        token = create_token(user.id)

        async def _boom():
            raise RuntimeError("boom through the middleware stack")

        # Protected path (not in the public GET allowlist): a JWT is required.
        app.add_api_route("/api/_mw_boom", _boom, methods=["GET"])
        try:
            # raise_app_exceptions=False: ServerErrorMiddleware re-raises after
            # sending the 500, so we must let httpx swallow it to read the body.
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                # (1) No token -> JWTAuthMiddleware short-circuits before the route.
                r401 = await c.get("/api/_mw_boom")
                assert r401.status_code == 401
                assert r401.json()["detail"] == "Not authenticated"

                # (2) Valid token -> traverses JWTAuth + RateLimit, the route
                #     raises, ServerErrorMiddleware returns the app JSON 500
                #     (not a bare Starlette 500 page).
                r500 = await c.get(
                    "/api/_mw_boom", headers={"Authorization": f"Bearer {token}"}
                )
                assert r500.status_code == 500
                assert r500.json() == {"detail": "Internal server error"}
        finally:
            app.router.routes = [
                rt
                for rt in app.router.routes
                if getattr(rt, "path", None) != "/api/_mw_boom"
            ]
