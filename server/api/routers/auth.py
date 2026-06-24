from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from auth import verify_google_token, create_token
from dependencies import get_current_user
from models import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- Schemas ----------

class GoogleLoginIn(BaseModel):
    credential: str  # Google ID token from GSI


class TokenOut(BaseModel):
    token: str
    user_id: int
    username: str
    is_admin: bool = False
    avatar_url: str | None = None


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    is_admin: bool = False
    avatar_url: str | None = None
    created_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- Endpoints ----------

@router.post("/google", response_model=TokenOut)
async def google_login(body: GoogleLoginIn, db: AsyncSession = Depends(get_db)):
    payload = verify_google_token(body.credential)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    google_id = payload["sub"]
    email = payload.get("email", "")
    name = payload.get("name", email.split("@")[0])
    picture = payload.get("picture")

    # Look up by google_id first, then by email
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        # Check if email already exists (link existing account)
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.google_id = google_id
            user.avatar_url = picture
        else:
            # Auto-create account
            user = User(
                email=email,
                username=name,
                google_id=google_id,
                avatar_url=picture,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)

    # Update avatar on each login
    if picture and user.avatar_url != picture:
        user.avatar_url = picture

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    await db.commit()
    await db.refresh(user)

    return TokenOut(
        token=create_token(user.id),
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        avatar_url=user.avatar_url,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
