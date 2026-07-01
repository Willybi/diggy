import logging
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from rate_limit import RateLimitMiddleware
from auth_middleware import JWTAuthMiddleware
from database import engine, Base
from routers import catalog, tracks, watchlist, radar, artists, sets, auth, admin, genres, opinions, search, taxonomy, collections

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.2,
        environment=os.environ.get("SENTRY_ENV", "production"),
    )

APP_VERSION = "1.0.0"
_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from storage import ensure_bucket
    ensure_bucket()
    yield


app = FastAPI(
    title="Diggy API",
    version=APP_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(JWTAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGIN", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth.router, prefix="/api")
app.include_router(tracks.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(radar.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(sets.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(genres.router, prefix="/api/genres")
app.include_router(opinions.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(taxonomy.router, prefix="/api/taxonomy")
app.include_router(collections.router, prefix="/api")


@app.get("/api/health")
async def health():
    from sqlalchemy import text

    checks = {"db": "ok", "redis": "ok"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        checks["db"] = "error"

    try:
        import redis.asyncio as aioredis
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        r = aioredis.from_url(redis_url)
        await r.ping()
        await r.aclose()
    except ImportError:
        checks["redis"] = "skip"
    except Exception:
        checks["redis"] = "error"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    uptime_s = int(time.time() - _start_time)

    return {
        "status": overall,
        "version": APP_VERSION,
        "uptime_seconds": uptime_s,
        "checks": checks,
    }
