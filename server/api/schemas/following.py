"""Following schemas (followed artists + activity feed)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FollowStateResponse(BaseModel):
    following: bool


class FollowedArtistOut(BaseModel):
    artist_id: int
    name: str
    has_artwork: bool = False
    followed_at: Optional[datetime] = None


class FollowingListResponse(BaseModel):
    items: list[FollowedArtistOut]


class ArtistActivityOut(BaseModel):
    """Feed item — `type` maps the DB column activity_type ('release' | 'set')."""

    id: int
    artist_id: int
    artist_name: Optional[str] = None
    type: str
    source: str
    title: Optional[str] = None
    external_url: Optional[str] = None
    catalog_id: Optional[int] = None
    set_id: Optional[int] = None
    detected_at: Optional[datetime] = None
    payload: Optional[dict] = None


class ActivityListResponse(BaseModel):
    items: list[ArtistActivityOut]
