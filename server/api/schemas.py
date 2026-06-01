from pydantic import BaseModel, field_validator
from datetime import datetime
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
