"""Shared reference schemas used across multiple domains."""

from typing import Optional

from pydantic import BaseModel


class GenreRef(BaseModel):
    name: str
    pillar: str = "autres"
    depth: int = 0


class ArtistRef(BaseModel):
    id: int
    name: str
    role: Optional[str] = None
    has_artwork: bool = False

    model_config = {"from_attributes": True}


class TopGenreOut(BaseModel):
    """A dominant genre of a track collection: raw name (links to /style/{name}),
    its pillar/depth for styling, and the share of genre-bearing tracks carrying
    it. Shared by the playlist and set detail aggregates."""

    name: str
    pillar: str = "autres"
    depth: int = 0
    pct: int = 0


class OkResponse(BaseModel):
    ok: bool = True


class RandomTrackResponse(BaseModel):
    catalog_id: int
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
