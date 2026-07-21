from typing import Annotated, Literal

from database import get_db
from dependencies import get_current_user, get_current_user_optional, get_redis
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException, Query
from models import User
from pydantic import StringConstraints
from schemas import (
    AvisResponse,
    CatalogAvisUpdate,
    CatalogDetailOut,
    CatalogGenreItem,
    CatalogImportIn,
    CatalogImportOut,
    CatalogList,
    PreviewUrlResponse,
    SimilarTrackOut,
)
from services import catalog_service, similarity_service
from services.genre_service import ensure_pillar_cache, genre_pillar
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/catalog", tags=["catalog"])

CatalogSortField = Literal[
    "created_at",
    "title",
    "artist",
    "bpm",
    "key",
    "duration_ms",
    "release_date",
]

# Camelot notation: 1A..12A (minor) / 1B..12B (major)
CamelotKey = Annotated[str, StringConstraints(pattern=r"^(1[0-2]|[1-9])[AB]$")]


@router.get("/genres", response_model=list[CatalogGenreItem])
async def list_genres(db: AsyncSession = Depends(get_db)):
    """Return all distinct genres with track counts (unnested from arrays)."""
    from models import CatalogEntry

    await ensure_pillar_cache(db)
    genre_col = func.unnest(CatalogEntry.genres).label("genre")
    result = await db.execute(
        select(genre_col, func.count())
        .where(func.coalesce(func.array_length(CatalogEntry.genres, 1), 0) > 0)
        .group_by(genre_col)
        .order_by(func.count().desc())
    )
    items = []
    for row in result.all():
        p, d = genre_pillar(row[0])
        items.append({"name": row[0], "count": row[1], "pillar": p, "depth": d})
    return items


@router.get("/", response_model=CatalogList)
async def list_catalog(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    in_lib: bool | None = Query(None),
    search: str | None = Query(None, max_length=200),
    genre: list[str] | None = Query(None),
    bpm_min: float | None = Query(None, ge=0),
    bpm_max: float | None = Query(None, ge=0),
    key: list[CamelotKey] | None = Query(None),
    artist_id: list[int] | None = Query(None),
    duration_min: int | None = Query(None, ge=0),
    duration_max: int | None = Query(None, ge=0),
    has_preview: bool | None = Query(None),
    avis: Literal["liked", "disliked", "none"] | None = Query(None),
    year_min: int | None = Query(None, ge=1, le=9999),
    year_max: int | None = Query(None, ge=1, le=9999),
    label: str | None = Query(None, max_length=200),
    sort: CatalogSortField | None = Query(None),
    order: Literal["asc", "desc"] | None = Query("desc"),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    return await catalog_service.list_catalog(
        db, _uid(user),
        skip=skip, limit=limit, in_lib=in_lib,
        search=search, genre=genre,
        bpm_min=bpm_min, bpm_max=bpm_max, key=key, artist_id=artist_id,
        duration_min=duration_min, duration_max=duration_max,
        has_preview=has_preview, avis=avis,
        year_min=year_min, year_max=year_max, label=label,
        sort=sort, order=order or "desc",
    )


@router.post("/import", response_model=CatalogImportOut)
async def import_track(
    body: CatalogImportIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import an external (Deezer/TIDAL) track into the shared catalog."""
    try:
        return await catalog_service.import_external(
            db, deezer_id=body.deezer_id, tidal_id=body.tidal_id
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{catalog_id}/similar", response_model=list[SimilarTrackOut])
async def get_similar_tracks(
    catalog_id: int,
    limit: int = Query(10, ge=1, le=50),
    top_n: int = Query(20, ge=1, le=100),
    score_floor: float = Query(0.10, ge=0, le=1),
    in_lib: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    try:
        return await similarity_service.get_similar_tracks(
            db, catalog_id, _uid(user),
            limit=limit, top_n=top_n,
            score_floor=score_floor, in_lib=in_lib,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/{catalog_id}", response_model=CatalogDetailOut)
async def get_catalog_detail(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    try:
        return await catalog_service.get_detail(db, catalog_id, _uid(user))
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/{catalog_id}/preview-url", response_model=PreviewUrlResponse)
async def get_preview_url(
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    user: User | None = Depends(get_current_user_optional),
):
    """Retourne une preview URL fraîche depuis l'API Deezer."""
    try:
        return await catalog_service.get_preview_url(db, catalog_id, _uid(user), redis=redis)
    except catalog_service.PreviewUnavailableError as e:
        # Deezer throttled/failed transiently — 503 (not 404) so the player retries.
        raise HTTPException(
            503,
            "Preview temporairement indisponible, réessayez.",
            headers={"Retry-After": "3"},
        ) from e
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.patch("/{catalog_id}/avis", response_model=AvisResponse)
async def update_avis(
    catalog_id: int,
    body: CatalogAvisUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await catalog_service.update_avis(db, catalog_id, user.id, body.avis)
    except LookupError as e:
        raise HTTPException(404, str(e))
