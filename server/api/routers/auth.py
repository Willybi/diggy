import json
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

from auth import (
    GOOGLE_CLIENT_ID,
    GOOGLE_REDIRECT_URI,
    create_token,
    verify_google_token,
)
from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from models import User
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- Schemas ----------


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    picture_url: str | None = None
    is_active: bool
    is_admin: bool = False
    created_at: datetime | None

    model_config = {"from_attributes": True}


# ---------- Endpoints ----------


@router.get("/google/login")
async def google_login():
    """Return Google authorization URL and set CSRF state cookie."""
    state = secrets.token_urlsafe(32)
    params = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
    )
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    response = JSONResponse({"url": url})
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=600,
        path="/api/auth",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Google code, create/find user, return HTML that stores JWT."""
    # CSRF check
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(400, "Invalid state parameter")

    google_info = await verify_google_token(code)

    # Lookup by google_id
    result = await db.execute(
        select(User).where(User.google_id == google_info["google_id"])
    )
    user = result.scalar_one_or_none()

    if not user:
        # First login — create account
        base_username = google_info["name"].replace(" ", "").lower()[:50]
        # Ensure username uniqueness
        username = base_username
        suffix = 1
        while True:
            existing = await db.execute(select(User).where(User.username == username))
            if not existing.scalar_one_or_none():
                break
            username = f"{base_username}{suffix}"
            suffix += 1

        user = User(
            email=google_info["email"],
            username=username,
            google_id=google_info["google_id"],
            picture_url=google_info.get("picture"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Update picture if changed
        if google_info.get("picture") != user.picture_url:
            user.picture_url = google_info.get("picture")
            await db.commit()

    token = create_token(user.id)

    # Build JS-safe values via json.dumps
    token_js = json.dumps(token)
    user_data = json.dumps(
        {"id": user.id, "username": user.username, "is_admin": user.is_admin}
    )
    user_js = json.dumps(user_data)  # double-encode for localStorage string

    html = f"""<!DOCTYPE html>
<html><head><title>Connexion...</title></head>
<body>
<script>
localStorage.setItem('diggy_token', {token_js});
localStorage.setItem('diggy_user', {user_js});
window.location.replace('/');
</script>
<noscript>Connexion reussie. <a href="/">Continuer</a></noscript>
</body></html>"""

    response = HTMLResponse(html)
    response.delete_cookie("oauth_state", path="/api/auth")
    return response


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
