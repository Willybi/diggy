from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TagOut(BaseModel):
    id: int
    group: str
    name: str

    model_config = {"from_attributes": True}


class CueOut(BaseModel):
    id: int
    kind: int
    time: float
    color: Optional[str]
    comment: Optional[str]
    is_loop: int
    loop_out: Optional[float]

    model_config = {"from_attributes": True}


class TrackBase(BaseModel):
    title: Optional[str]
    artist: Optional[str]
    album: Optional[str]
    label: Optional[str]
    bpm: Optional[float]
    key: Optional[str]
    duration: Optional[int]
    rating: Optional[int]
    play_count: Optional[int]


class TrackOut(TrackBase):
    id: int
    rekordbox_id: Optional[int]
    file_path: Optional[str]
    date_added: Optional[datetime]
    artwork_url: Optional[str]
    cues: list[CueOut] = []
    tags: list[TagOut] = []

    model_config = {"from_attributes": True}


class TrackList(BaseModel):
    total: int
    items: list[TrackOut]
