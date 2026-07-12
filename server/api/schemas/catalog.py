"""Catalog schemas."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

from .common import ArtistRef, GenreRef


class CatalogEntryOut(BaseModel):
    id: int
    title: str
    artist: Optional[str]
    isrc: Optional[str]
    bpm: Optional[float]
    key: Optional[str]
    bpm_source: Optional[str] = None
    key_source: Optional[str] = None
    label: Optional[str] = None
    deezer_id: Optional[str] = None
    beatport_id: Optional[str] = None
    duration_ms: Optional[int]
    genres: list[GenreRef] = []
    release_date: Optional[date]
    has_artwork: bool = False
    has_preview: bool = False
    created_at: Optional[datetime]
    style: Optional[str] = None
    rating: Optional[int] = None
    lib_track_id: Optional[int] = None
    in_lib: bool = False
    nb_radar_playlists: int = 0
    nb_radar_sets: int = 0
    avis: Optional[str] = None
    artist_id: Optional[int] = None
    artists: list[ArtistRef] = []
    detected_at: Optional[datetime] = None
    source_name: Optional[str] = None
    source_kind: Optional[str] = None
    trend_rank: Optional[int] = None
    trend_score_10: Optional[float] = None

    model_config = {"from_attributes": True}


class CatalogAvisUpdate(BaseModel):
    avis: Literal["liked", "disliked"] | None = None


class CatalogList(BaseModel):
    total: int
    items: list[CatalogEntryOut]


class SimilarityComponents(BaseModel):
    sets: float = 0.0
    playlists: float = 0.0
    style: float = 0.0
    context: float = 0.0


class SimilarityBlock(BaseModel):
    score: float
    components: SimilarityComponents
    available_features: list[str]


class SimilarTrackOut(CatalogEntryOut):
    similarity: SimilarityBlock


class RadarAppearanceOut(BaseModel):
    playlist_id: int
    playlist_title: Optional[str] = None
    playlist_source: str = ""
    detected_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SetAppearanceOut(BaseModel):
    set_id: int
    set_title: str
    set_artist: Optional[str] = None
    played_date: Optional[date] = None
    timecode_ms: Optional[int] = None

    model_config = {"from_attributes": True}


class SameArtistTrackOut(BaseModel):
    id: int
    title: str
    artist: Optional[str] = None
    artists: list[ArtistRef] = []
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    has_artwork: bool = False
    has_preview: bool = False
    in_lib: bool = False
    rating: Optional[int] = None

    model_config = {"from_attributes": True}


class CatalogDetailOut(CatalogEntryOut):
    radar_appearances: list[RadarAppearanceOut] = []
    set_appearances: list[SetAppearanceOut] = []
    same_artist_tracks: list[SameArtistTrackOut] = []
    tags: list[str] = []


class CatalogGenreItem(BaseModel):
    name: str
    count: int
    pillar: str
    depth: int


class PreviewUrlResponse(BaseModel):
    preview_url: str


class AvisResponse(BaseModel):
    catalog_id: int
    avis: str | None = None


class CatalogImportIn(BaseModel):
    """Manual import request: exactly one source id must be provided."""

    deezer_id: Optional[str] = None
    tidal_id: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if bool(self.deezer_id) == bool(self.tidal_id):
            raise ValueError("Provide exactly one of deezer_id or tidal_id")
        return self


class CatalogImportOut(BaseModel):
    catalog_id: int
    created: bool
    title: str
    artist: Optional[str] = None
