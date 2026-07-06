"""Watchlist (watched playlists) schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .common import ArtistRef


class WatchedEntityIn(BaseModel):
    external_id: str
    source: str
    description: Optional[str] = None


class WatchedEntityOut(BaseModel):
    id: int
    external_id: str
    source: str
    title: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]
    last_crawled_at: Optional[datetime]
    has_artwork: bool = False
    track_count: Optional[int] = None
    owner: Optional[str] = None
    current_task_id: Optional[str] = None

    model_config = {"from_attributes": True}


class WatchedEntityBrowseOut(WatchedEntityOut):
    followed: bool = False


class PlaylistTrackOut(BaseModel):
    catalog_id: int
    title: str
    artist: Optional[str] = None
    artists: list[ArtistRef] = []
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    genre: Optional[str] = None
    has_artwork: bool = False
    has_preview: bool = False
    detected_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WatchedEntityDetailOut(WatchedEntityOut):
    followed: bool = False
    tracks: list[PlaylistTrackOut] = []


class WatchlistListResponse(BaseModel):
    total: int
    items: list[WatchedEntityOut]


class WatchlistBrowseResponse(BaseModel):
    total: int
    items: list[WatchedEntityBrowseOut]


class CrawlQueuedResponse(BaseModel):
    status: str = "crawl_queued"
    playlist_id: int


class CrawlStatusResponse(BaseModel):
    status: str | None = None


class FetchArtworkResponse(BaseModel):
    ok: bool = True
    has_artwork: bool
