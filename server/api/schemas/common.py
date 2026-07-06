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


class OkResponse(BaseModel):
    ok: bool = True


class RandomTrackResponse(BaseModel):
    catalog_id: int
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
