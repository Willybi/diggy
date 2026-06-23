from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import catalog, tracks, watchlist, radar, artists, sets, auth, admin, genres


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(tracks.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(radar.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(artists.router, prefix="/api")
app.include_router(sets.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(genres.router, prefix="/api/genres")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
