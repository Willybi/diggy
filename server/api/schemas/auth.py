"""Auth schemas."""

from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    picture_url: str | None = None
    is_active: bool
    is_admin: bool = False
    created_at: datetime | None

    model_config = {"from_attributes": True}


class GoogleLoginResponse(BaseModel):
    url: str
