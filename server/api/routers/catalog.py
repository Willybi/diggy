from datetime import datetime
from typing import Literal

from database import get_db
from dependencies import get_current_user, get_current_user_optional
from dependencies import uid as _uid
from fastapi import APIRouter, Depends, HTTPException, Query
from models import User
from schemas import CatalogAvisUpdate, CatalogDetailOut, CatalogList
from services import catalog_service, similarity_service
from services.genre_service import _ensure_pillar_cache, genre_pillar
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/catalog", tags=["catalog"])

CatalogSortField = Literal[
    "title",
    "nb_radar_playlists",
    "detected_at",
    "rating",
    "bpm",
    "duration_ms",
    "key",
    "style",
    "in_lib",
    "avis",
]


@router.get("/genres")
async def list_genres(db: AsyncSession = Depends(get_db)):
    """Return all distinct genres with track counts (unnested from arrays)."""
    from models import CatalogEntry

    await _ensure_pillar_cache(db)
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
    min_radar_playlists: int | None = Query(None),
    search: str | None = Query(None, max_length=200),
    genre: str | None = Query(None, max_length=100),
    sort: CatalogSortField | None = Query(None),
    order: Literal["asc", "desc"] | None = Query("desc"),
    view: Literal["radar"] | None = Query(None),
    detected_after: datetime | None = Query(None),
    avis: Literal["liked", "disliked"] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    return await catalog_service.list_catalog(
        db, _uid(user),
        skip=skip, limit=limit, in_lib=in_lib,
        min_radar_playlists=min_radar_playlists, search=search, genre=genre,
        sort=sort, order=order or "desc", view=view,
        detected_after=detected_after, avis=avis,
    )


@router.get("/{catalog_id}/similar")
async def get_similar_tracks(
    catalog_id: int,
    limit: int = Query(10, ge=1, le=50),
    w_bpm: float = Query(0.30, ge=0, le=1),
    w_key: float = Query(0.25, ge=0, le=1),
    w_genre: float = Query(0.30, ge=0, le=1),
    w_label: float = Query(0.10, ge=0, le=1),
    w_era: float = Query(0.05, ge=0, le=1),
    min_score: float = Query(0.4, ge=0, le=1),
    in_lib: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    try:
        return await similarity_service.get_similar_tracks(
            db, catalog_id, _uid(user),
            limit=limit, w_bpm=w_bpm, w_key=w_key, w_genre=w_genre,
            w_label=w_label, w_era=w_era, min_score=min_score, in_lib=in_lib,
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


@router.get("/{catalog_id}/preview-url")
async def get_preview_url(catalog_id: int, db: AsyncSession = Depends(get_db)):
    """Retourne une preview URL fraîche depuis l'API Deezer."""
    try:
        return await catalog_service.get_preview_url(db, catalog_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.patch("/{catalog_id}/avis")
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
