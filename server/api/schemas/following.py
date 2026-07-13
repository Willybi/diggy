"""Following schemas (followed artists + activity feed)."""

from datetime import date, datetime
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
    """Feed item — `type` maps the DB column activity_type ('release' | 'set').

    When `catalog_id` is set (a crawled release track, C6.c v2) the track fields
    below are populated from the joined catalog entry so the client can render a
    full track card; they stay at their defaults for link-only / set items.
    """

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
    # Crawled-track fields (populated only when catalog_id resolves to a
    # visible catalog entry).
    has_artwork: bool = False
    has_preview: bool = False
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    artist: Optional[str] = None
    release_date: Optional[date] = None


class ActivityListResponse(BaseModel):
    items: list[ArtistActivityOut]
