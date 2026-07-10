"""Artist schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .catalog import CatalogEntryOut
from .common import GenreRef


class ArtistAliasOut(BaseModel):
    id: int
    artist_id: int
    alias: str
    normalized_alias: str

    model_config = {"from_attributes": True}


class ArtistOut(BaseModel):
    id: int
    name: str
    normalized_name: str
    deezer_id: Optional[str] = None
    trackid_id: Optional[str] = None
    has_artwork: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ArtistListOut(BaseModel):
    id: int
    name: str
    has_artwork: bool = False
    nb_catalog: int = 0
    nb_lib: int = 0
    nb_liked: int = 0
    avg_rating: Optional[float] = None
    genres: list[GenreRef] = []

    model_config = {"from_attributes": True}


class ArtistListItemOut(ArtistListOut):
    top_track_artworks: list[str] = []
    tracks_with_artwork: int = 0


class ArtistListResponse(BaseModel):
    items: list[ArtistListItemOut]
    total: int
    pillarCounts: dict[str, int] = {}


class ArtistConnectionComponents(BaseModel):
    collabs: float = 0.0
    sets: float = 0.0
    playlists: float = 0.0
    style: float = 0.0


class ArtistConnectionOut(BaseModel):
    artist_id: int
    name: str
    has_artwork: bool = False
    genres: list[GenreRef] = []
    score: float
    components: ArtistConnectionComponents
    shared_tracks: int = 0
    shared_sets: int = 0
    shared_playlists: int = 0


class ArtistSetOut(BaseModel):
    set_id: int
    title: str
    played_date: Optional[datetime] = None
    role: Optional[str] = None
    has_artwork: bool = False
    total_tracks: int = 0
    identified_tracks: int = 0

    model_config = {"from_attributes": True}


class ArtistDetailOut(ArtistOut):
    aliases: list[ArtistAliasOut] = []
    genres: list[GenreRef] = []
    catalog_tracks: list[CatalogEntryOut] = []
    sets: list[ArtistSetOut] = []
    stats: dict = {}
