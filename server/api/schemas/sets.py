"""DJ set schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from .common import ArtistRef


class SetListItemOut(BaseModel):
    id: int
    title: str
    source: str
    source_url: Optional[str] = None
    played_date: Optional[date] = None
    duration_ms: Optional[int] = None
    has_artwork: bool = False
    total_tracks: int = 0
    identified_tracks: int = 0
    artists: list[str] = []

    model_config = {"from_attributes": True}


class SetListResponse(BaseModel):
    total: int
    items: list[SetListItemOut]


class SetTrackOut(BaseModel):
    id: int
    set_id: int
    catalog_id: Optional[int] = None
    position: int
    timecode_ms: Optional[int] = None
    raw_title: Optional[str] = None
    raw_artist: Optional[str] = None
    is_id: bool = False

    model_config = {"from_attributes": True}


class SetArtistOut(BaseModel):
    set_id: int
    artist_id: int
    role: Optional[str] = None
    position: Optional[int] = None

    model_config = {"from_attributes": True}


class DJSetOut(BaseModel):
    id: int
    external_id: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    title: str
    played_date: Optional[date] = None
    duration_ms: Optional[int] = None
    has_artwork: bool = False
    created_at: Optional[datetime] = None
    last_crawled_at: Optional[datetime] = None
    total_tracks: int = 0
    identified_tracks: int = 0

    model_config = {"from_attributes": True}


class DJSetList(BaseModel):
    total: int
    items: list[DJSetOut]


class SetTrackDetailOut(SetTrackOut):
    catalog_title: Optional[str] = None
    catalog_artist: Optional[str] = None
    catalog_artists: list[ArtistRef] = []
    has_artwork: bool = False
    in_lib: bool = False
    has_preview: bool = False


class SetArtistDetailOut(BaseModel):
    artist_id: int
    artist_name: str = ""
    has_artwork: bool = False
    role: Optional[str] = None
    position: Optional[int] = None

    model_config = {"from_attributes": True}


class DJSetDetailOut(DJSetOut):
    artists: list[SetArtistDetailOut] = []
    tracklist: list[SetTrackDetailOut] = []


class SetFlagOut(BaseModel):
    id: int
    set_id_a: int
    set_id_b: Optional[int] = None
    flag_type: str
    confidence: Optional[float] = None
    signals: Optional[dict] = None
    status: str
    created_at: datetime
    title_a: str = ""
    title_b: Optional[str] = None
    group_key: Optional[str] = None
    member_set_ids: Optional[list[int]] = None
    member_titles: list[str] = []

    model_config = {"from_attributes": True}


class SetFlagListResponse(BaseModel):
    total: int
    items: list[SetFlagOut]


class SetFlagAttachResponse(BaseModel):
    ok: bool
    parent_id: int


class SetImportIn(BaseModel):
    url: str | None = None
    slug: str | None = None


class TrackIDSearchResult(BaseModel):
    trackid_id: int
    slug: str
    title: str
    channel: str | None = None
    artwork_url: str | None = None
    track_count: int = 0
    duration: str | None = None
    created_on: str | None = None
    already_imported: bool = False


class SetImportResponse(BaseModel):
    id: int
    title: str
