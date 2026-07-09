import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from jose import JWTError, jwt

logger = logging.getLogger("auth")

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7 days

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI", "https://diggy-music.fr/api/auth/google/callback"
)


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM
    )


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


async def verify_google_token(code: str) -> dict:
    """Exchange Google authorization code for id_token, return user info."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            # Do not log resp.text: the Google token endpoint response may carry
            # sensitive material. Status code is enough to diagnose failures.
            logger.warning("Google token endpoint returned %s", resp.status_code)
        resp.raise_for_status()
        token_data = resp.json()

    # Lazy import — google-auth may not be installed in test env
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    id_info = google_id_token.verify_oauth2_token(
        token_data["id_token"], google_requests.Request(), GOOGLE_CLIENT_ID
    )
    return {
        "google_id": id_info["sub"],
        "email": id_info["email"],
        "name": id_info.get("name", id_info["email"].split("@")[0]),
        "picture": id_info.get("picture"),
    }
