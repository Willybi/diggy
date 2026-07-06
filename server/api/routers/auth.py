import base64
import json
import logging
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
from dependencies import get_current_user, get_redis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from models import User
from schemas import GoogleLoginResponse, UserOut
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- Endpoints ----------


@router.get("/google/login", response_model=GoogleLoginResponse)
async def google_login(redis=Depends(get_redis)):
    """Return Google authorization URL and state for CSRF check."""
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", 300, "1")  # valid 5 min
    params = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    return JSONResponse({"url": url})


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Exchange Google code, create/find user, set cookie + redirect."""
    # Server-side state validation (Redis, one-time use)
    consumed = await redis.delete(f"oauth_state:{state}")
    if not consumed:
        logging.getLogger("auth").warning("OAuth state invalid or expired: %s", state)
        return RedirectResponse(
            "/login/callback?error=invalid_state", status_code=302
        )

    try:
        google_info = await verify_google_token(code)
    except Exception as exc:
        logging.getLogger("auth").warning("Google token exchange failed: %s", exc)
        return RedirectResponse("/login/callback?error=google_failed", status_code=302)

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

    user_data = {"id": user.id, "username": user.username, "is_admin": user.is_admin}

    # Pass credentials via a short-lived cookie, then redirect to the SPA
    # callback page. Avoids hash fragments (Safari iOS drops them) and
    # inline scripts (blocked by CSP script-src 'self').
    cookie_value = (
        base64.urlsafe_b64encode(
            json.dumps({"token": token, "user": user_data}).encode()
        )
        .decode()
        .rstrip("=")  # strip padding — '=' triggers cookie quoting
    )

    response = RedirectResponse("/login/callback", status_code=302)
    response.set_cookie(
        "auth_callback",
        cookie_value,
        max_age=60,
        httponly=False,  # must be readable by frontend JS
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
