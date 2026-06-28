import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from rate_limit import limiter
from database import engine, Base
from routers import catalog, tracks, watchlist, radar, artists, sets, auth, admin, genres, opinions, search, taxonomy


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from storage import ensure_bucket
    ensure_bucket()
    yield


app = FastAPI(
    title="Diggy API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGIN", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, RateLimitExceeded):
        return await _rate_limit_exceeded_handler(request, exc)
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
