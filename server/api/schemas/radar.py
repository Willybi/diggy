"""Radar schemas."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

from .common import ArtistRef

RadarStatus = Literal["new", "seen", "added", "ignored", "liked", "disliked"]


class RadarTrackIn(BaseModel):
    watched_playlist_id: int
    external_track_id: str
    source: str
    title: str
    artist: Optional[str] = None
    isrc: Optional[str] = None


class RadarTrackOut(BaseModel):
    id: int
    watched_playlist_id: Optional[int] = None
    watched_entity_id: Optional[int] = None
    external_track_id: str
    source: str
    title: str
    artist: Optional[str]
    isrc: Optional[str]
    detected_at: Optional[datetime]

    @field_validator("watched_playlist_id", mode="before")
    @classmethod
    def coerce_entity_id(cls, v):
        return v

    model_config = {"from_attributes": True, "populate_by_name": True}

    def model_post_init(self, __context):
        if self.watched_playlist_id is None and self.watched_entity_id is not None:
            self.watched_playlist_id = self.watched_entity_id


class RadarFullOut(BaseModel):
    """Enriched radar track for the RadarView."""

    catalog_id: int
    title: str
    artist: Optional[str] = None
    artists: list[ArtistRef] = []
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    genres: list[str] = []
    has_artwork: bool = False
    has_preview: bool = False
    detected_at: Optional[datetime] = None
    playlist_id: Optional[int] = None
    playlist_title: Optional[str] = None
    status: str = "new"
    in_lib: bool = False
    trend_score: Optional[float] = None
    trend_rank: Optional[int] = None
    trend_family: Optional[str] = None
    trend_rank_family: Optional[int] = None
    velocity: Optional[float] = None
    source_count: Optional[int] = None

    model_config = {"from_attributes": True}


class RadarFullList(BaseModel):
    total: int
    items: list[RadarFullOut]
    counts: dict[str, int] = {}


class RadarStateUpdate(BaseModel):
    status: RadarStatus


class RadarBatchItem(BaseModel):
    catalog_id: int
    status: RadarStatus


class TrendItem(BaseModel):
    catalog_id: int
    title: str
    artist: Optional[str] = None
    has_artwork: bool = False
    has_preview: bool = False
    bpm: Optional[float] = None
    key: Optional[str] = None
    trend_score: float = 0
    rank: int = 1
    family: Optional[str] = None
    source_count: int = 0


class TrendList(BaseModel):
    items: list[TrendItem]
    family_counts: dict[str, int] = {}


class NewCountResponse(BaseModel):
    count: int


class RadarStateResponse(BaseModel):
    catalog_id: int
    status: str


class RadarBatchResponse(BaseModel):
    updated: int
