from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional
import json


class TrackOut(BaseModel):
    id: int
    title: Optional[str]
    artist: Optional[str]
    bpm: Optional[float]
    key: Optional[str]
    duration: Optional[int]
    rating: Optional[int]
    file_path: Optional[str]
    date_added: Optional[datetime]
    tags: list[str] = []
    has_artwork: bool = False

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v or []

    model_config = {"from_attributes": True}


class TrackList(BaseModel):
    total: int
    items: list[TrackOut]


class TrackExisting(BaseModel):
    id: int
    has_artwork: bool

    model_config = {"from_attributes": True}


class TrackImport(BaseModel):
    id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration: Optional[int] = None
    rating: Optional[int] = None
    file_path: Optional[str] = None
    date_added: Optional[datetime] = None
    tags: list[str] = []
    image_base64: Optional[str] = None  # JPEG encodé en base64, None si pas d'image


class BulkImportResult(BaseModel):
    inserted: int
    updated: int
    artworks_uploaded: int


class RadarTrackIn(BaseModel):
    watched_playlist_id: int
    external_track_id: str
    source: str
    title: str
    artist: Optional[str] = None
    isrc: Optional[str] = None


class RadarTrackOut(BaseModel):
    id: int
    watched_playlist_id: int
    external_track_id: str
    source: str
    title: str
    artist: Optional[str]
    isrc: Optional[str]
    detected_at: Optional[datetime]

    model_config = {"from_attributes": True}


class CatalogEntryOut(BaseModel):
    id: int
    title: str
    artist: Optional[str]
    isrc: Optional[str]
    bpm: Optional[float]
    key: Optional[str]
    duration_ms: Optional[int]
    genre: Optional[str]
    release_date: Optional[date]
    preview_url: Optional[str]
    has_artwork: bool = False
    created_at: Optional[datetime]
    # Stats calculées
    in_lib: bool = False
    nb_radar_playlists: int = 0
    nb_radar_sets: int = 0

    model_config = {"from_attributes": True}


class WatchedPlaylistIn(BaseModel):
    external_id: str
    source: str
    description: Optional[str] = None


class WatchedPlaylistOut(BaseModel):
    id: int
    external_id: str
    source: str
    title: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]
    last_crawled_at: Optional[datetime]

    model_config = {"from_attributes": True}
