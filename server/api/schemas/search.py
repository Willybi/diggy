"""Search schemas."""

from pydantic import BaseModel


class SearchItem(BaseModel):
    type: str
    # track
    id: int | None = None
    title: str | None = None
    artist: str | None = None
    bpm: float | None = None
    key: str | None = None
    duration_ms: int | None = None
    has_artwork: bool = False
    has_preview: bool = False
    in_lib: bool = False
    # artist
    name: str | None = None
    track_count: int | None = None
    in_lib_count: int = 0
    # set
    played_date: str | None = None
    # playlist
    source: str | None = None
    # genre
    pillar: str | None = None
    depth: int | None = None
    artist_count: int | None = None
    bpm_lo: int | None = None
    bpm_hi: int | None = None


class SearchTotals(BaseModel):
    track: int = 0
    artist: int = 0
    set: int = 0
    playlist: int = 0
    genre: int = 0


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    totals: SearchTotals
