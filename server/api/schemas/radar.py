"""Radar schemas."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

from .catalog import CatalogEntryOut

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


class RadarFeedItem(CatalogEntryOut):
    """A bi-score radar feed row: a full catalog entry plus its two scores.

    ``trend_score_10`` (max-normalised trend, inherited from CatalogEntryOut) and
    ``reco_score_10`` (max-normalised personal reco) are each None when the row
    carries no score on that axis.
    """

    reco_score_10: Optional[float] = None
    velocity: Optional[float] = None


class RadarFeedList(BaseModel):
    total: int  # rows of the union AFTER filters (live counter)
    trend_count: int  # union rows carrying a trend score, BEFORE filters
    reco_count: int  # union rows carrying a reco score, BEFORE filters
    items: list[RadarFeedItem] = []


class TrendItem(BaseModel):
    catalog_id: int
    title: str
    artist: Optional[str] = None
    has_artwork: bool = False
    has_preview: bool = False
    bpm: Optional[float] = None
    key: Optional[str] = None
    release_date: Optional[date] = None
    trend_score: float = 0
    rank: int = 1
    family: Optional[str] = None
    source_count: int = 0


class TrendList(BaseModel):
    items: list[TrendItem]
    family_counts: dict[str, int] = {}


class NewCountResponse(BaseModel):
    count: int
