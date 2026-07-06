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
from dependencies import get_current_user
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
    """Return Google authorization URL and state for CSRF check."""
    state = secrets.token_urlsafe(32)
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
    return JSONResponse({"url": url, "state": state})


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Exchange Google code, create/find user, return HTML that stores JWT."""
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

    # Return HTML that persists JWT client-side then redirects.
    # Avoids hash-fragment redirect which Safari iOS drops silently.
    payload = json.dumps(
        {"token": token, "user": user_data, "state": state}
    ).replace("</", r"<\/")  # prevent script-tag breakout

    html = f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connexion…</title></head>
<body><p style="text-align:center;margin-top:40vh;font-family:system-ui">
Connexion en cours…</p>
<script>
(function(){{
  var d={payload};
  var expected=localStorage.getItem("oauth_state");
  localStorage.removeItem("oauth_state");
  if(!expected||expected!==d.state){{
    document.body.innerHTML='<p style="text-align:center;margin-top:40vh;'
      +'font-family:system-ui;color:#e55">Erreur de s\\u00e9curit\\u00e9.'
      +' <a href="/login">R\\u00e9essayer</a></p>';
    return;
  }}
  localStorage.setItem("diggy_token",d.token);
  localStorage.setItem("diggy_user",JSON.stringify(d.user));
  window.location.replace("/");
}})();
</script></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
