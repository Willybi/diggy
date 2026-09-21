"""Album schemas."""

from datetime import date
from typing import Optional

from pydantic import BaseModel

from .common import ArtistRef


class AlbumTrackOut(BaseModel):
    """One track of an album's tracklist (a catalog row linked via catalog_albums,
    already restricted to the viewer's visible perimeter)."""

    id: int
    title: str
    artist: Optional[str] = None
    artists: list[ArtistRef] = []
    bpm: Optional[float] = None
    key: Optional[str] = None
    bpm_source: Optional[str] = None
    duration_ms: Optional[int] = None
    has_artwork: bool = False
    has_preview: bool = False
    in_lib: bool = False
    # D12: Beatport embed fallback when the row has no Deezer preview.
    beatport_id: Optional[str] = None

    model_config = {"from_attributes": True}


class AlbumDetailOut(BaseModel):
    id: int
    title: str
    record_type: Optional[str] = None
    release_date: Optional[date] = None
    label: Optional[str] = None
    artist: Optional[ArtistRef] = None
    has_artwork: bool = False
    total_tracks: int = 0
    tracklist: list[AlbumTrackOut] = []

    model_config = {"from_attributes": True}
