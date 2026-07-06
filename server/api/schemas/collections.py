"""Collection schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .common import ArtistRef


class CollectionCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: Optional[str] = Field(None, max_length=20)


class CollectionItemAddIn(BaseModel):
    catalog_id: int


class CollectionOut(BaseModel):
    id: int
    name: str
    type: str = "playlist"
    created_at: Optional[datetime] = None
    item_count: int = 0

    model_config = {"from_attributes": True}


class CollectionItemOut(BaseModel):
    catalog_id: int
    position: int = 0
    added_at: Optional[datetime] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    artists: list[ArtistRef] = []
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    has_artwork: bool = False
    has_preview: bool = False

    model_config = {"from_attributes": True}


class CollectionDetailOut(CollectionOut):
    items: list[CollectionItemOut] = []
