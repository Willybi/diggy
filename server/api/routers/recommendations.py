from database import get_db
from dependencies import get_current_user, get_redis
from fastapi import APIRouter, Depends, HTTPException, Query
from models import User
from schemas import RecommendationList
from services import recommendation_service
from sqlalchemy.ext.asyncio import AsyncSession

# /api/recommendations is absent from the middleware allowlists: every route
# here requires a JWT by default (get_current_user is kept by convention).
router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/", response_model=RecommendationList)
async def get_recommendations(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    user: User = Depends(get_current_user),
):
    try:
        return await recommendation_service.get_recommendations(
            db, user.id, limit=limit, redis=redis
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
