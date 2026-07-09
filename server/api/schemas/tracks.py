"""User track schemas (Rekordbox library)."""

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Cap the artwork payload to guard against memory-DoS on bulk import (an image
# per track, up to MAX_BULK_IMPORT_SIZE items). base64 inflates ~33 %, so ~3 MiB
# of base64 caps a ~2.2 MiB source image — well above any real Rekordbox embedded
# artwork (typically a few hundred KB).
MAX_IMAGE_BASE64_LEN = 3 * 1024 * 1024


class TrackOut(BaseModel):
    id: int
    title: Optional[str]
    artist: Optional[str]
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration: Optional[int] = None
    rating: Optional[int] = None
    file_path: Optional[str] = None
    date_added: Optional[datetime] = None
    tags: list[str] = []
    has_artwork: bool = False
    catalog_id: Optional[int] = None
    has_preview: bool = False

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if isinstance(v, list):
            return v or []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return []

    model_config = {"from_attributes": True, "populate_by_name": True}


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
    image_base64: Optional[str] = Field(default=None, max_length=MAX_IMAGE_BASE64_LEN)


class BulkImportResult(BaseModel):
    inserted: int
    updated: int
    artworks_uploaded: int
