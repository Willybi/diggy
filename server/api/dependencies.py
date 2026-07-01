import os

from auth import decode_token
from database import get_db
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Soft-mode: returns user if token valid, None otherwise. Does not raise."""
    if not credentials:
        return None
    user_id = decode_token(credentials.credentials)
    if not user_id:
        return None
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin required"
        )
    return user


# ── Soft-mode user ID (auth not enforced yet) ──

_DEFAULT_USER_ID = 1


def uid(user: User | None) -> int:
    """Return user.id if authenticated, else fallback to default."""
    return user.id if user else _DEFAULT_USER_ID


async def get_redis():
    """Yield an async Redis connection (decoded responses)."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()
