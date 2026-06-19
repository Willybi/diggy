from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional
import json


class TrackOut(BaseModel):
    id: int
    title: Optional[str]
    artist: Optional[str]
    # user_tracks colonnes (rb_bpm / rb_key / rb_mytags)
    # exposés sous bpm/key/tags pour rétrocompat frontend
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
    image_base64: Optional[str] = None  # JPEG encodé en base64, None si pas d'image


class BulkImportResult(BaseModel):
    inserted: int
    updated: int
    artworks_uploaded: int


class RadarTrackIn(BaseModel):
    watched_playlist_id: int
    external_track_id: str
    source: str
    title: str
    artist: Optional[str] = None
    isrc: Optional[str] = None


class RadarTrackOut(BaseModel):
    id: int
    # watched_entity_id exposé sous watched_playlist_id pour rétrocompat frontend
    watched_playlist_id: Optional[int] = None
    watched_entity_id: Optional[int] = None
    external_track_id: str
    source: str
    title: str
    artist: Optional[str]
    isrc: Optional[str]
    detected_at: Optional[datetime]

    @field_validator("watched_playlist_id", mode="before")
    @classmethod
    def coerce_entity_id(cls, v):
        return v  # sera rempli via watched_entity_id si None

    model_config = {"from_attributes": True, "populate_by_name": True}

    def model_post_init(self, __context):
        if self.watched_playlist_id is None and self.watched_entity_id is not None:
            self.watched_playlist_id = self.watched_entity_id


class RadarFullOut(BaseModel):
    """Enriched radar track for the RadarView: catalog info + user state + playlist source."""
    catalog_id: int
    title: str
    artist: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    genre: Optional[str] = None
    has_artwork: bool = False
    has_preview: bool = False
    detected_at: Optional[datetime] = None
    playlist_id: Optional[int] = None
    playlist_title: Optional[str] = None
    status: str = "new"
    in_lib: bool = False

    model_config = {"from_attributes": True}


class RadarFullList(BaseModel):
    total: int
    items: list[RadarFullOut]
    counts: dict[str, int] = {}


class RadarStateUpdate(BaseModel):
    status: str  # new, seen, added, ignored


class CatalogEntryOut(BaseModel):
    id: int
    title: str
    artist: Optional[str]
    isrc: Optional[str]
    bpm: Optional[float]
    key: Optional[str]
    bpm_source: Optional[str] = None
    key_source: Optional[str] = None
    label: Optional[str] = None
    beatport_id: Optional[str] = None
    duration_ms: Optional[int]
    genre: Optional[str]
    release_date: Optional[date]
    preview_url: Optional[str]
    has_artwork: bool = False
    has_preview: bool = False
    created_at: Optional[datetime]
    # Données lib (quand in_lib = True)
    style: Optional[str] = None
    rating: Optional[int] = None
    lib_track_id: Optional[int] = None
    # Stats calculées
    in_lib: bool = False
    nb_radar_playlists: int = 0
    nb_radar_sets: int = 0

    model_config = {"from_attributes": True}


class CatalogList(BaseModel):
    total: int
    items: list[CatalogEntryOut]


class WatchedEntityIn(BaseModel):
    external_id: str
    source: str
    description: Optional[str] = None


class WatchedEntityOut(BaseModel):
    id: int
    external_id: str
    source: str
    title: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]
    last_crawled_at: Optional[datetime]
    has_artwork: bool = False
    track_count: Optional[int] = None
    owner: Optional[str] = None

    model_config = {"from_attributes": True}


class WatchedEntityBrowseOut(WatchedEntityOut):
    followed: bool = False


class PlaylistTrackOut(BaseModel):
    catalog_id: int
    title: str
    artist: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    genre: Optional[str] = None
    has_artwork: bool = False
    has_preview: bool = False
    detected_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WatchedEntityDetailOut(WatchedEntityOut):
    followed: bool = False
    tracks: list[PlaylistTrackOut] = []


class GenreOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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
    real_name: Optional[str] = None
    country: Optional[str] = None
    deezer_id: Optional[str] = None
    soundcloud_id: Optional[str] = None
    trackid_id: Optional[str] = None
    bio: Optional[str] = None
    has_artwork: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ArtistListOut(BaseModel):
    id: int
    name: str
    real_name: Optional[str] = None
    country: Optional[str] = None
    has_artwork: bool = False
    nb_catalog: int = 0
    nb_lib: int = 0
    avg_rating: Optional[float] = None
    genres: list[str] = []

    model_config = {"from_attributes": True}


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
    followed: bool = False

    model_config = {"from_attributes": True}


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
    event: Optional[str] = None
    venue: Optional[str] = None
    played_date: Optional[date] = None
    duration_ms: Optional[int] = None
    description: Optional[str] = None
    has_artwork: bool = False
    created_at: Optional[datetime] = None
    last_crawled_at: Optional[datetime] = None
    total_tracks: int = 0
    identified_tracks: int = 0

    model_config = {"from_attributes": True}


class DJSetList(BaseModel):
    total: int
    items: list[DJSetOut]


# ---------- Detail schemas ----------


class RadarAppearanceOut(BaseModel):
    playlist_id: int
    playlist_title: Optional[str] = None
    playlist_source: str = ""
    detected_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SetAppearanceOut(BaseModel):
    set_id: int
    set_title: str
    set_artist: Optional[str] = None
    played_date: Optional[date] = None
    timecode_ms: Optional[int] = None

    model_config = {"from_attributes": True}


class SameArtistTrackOut(BaseModel):
    id: int
    title: str
    artist: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    has_artwork: bool = False
    in_lib: bool = False
    rating: Optional[int] = None

    model_config = {"from_attributes": True}


class CatalogDetailOut(CatalogEntryOut):
    genres: list[GenreOut] = []
    radar_appearances: list[RadarAppearanceOut] = []
    set_appearances: list[SetAppearanceOut] = []
    same_artist_tracks: list[SameArtistTrackOut] = []
    tags: list[str] = []


class ArtistSetOut(BaseModel):
    set_id: int
    title: str
    played_date: Optional[date] = None
    role: Optional[str] = None
    has_artwork: bool = False
    total_tracks: int = 0
    identified_tracks: int = 0

    model_config = {"from_attributes": True}


class ArtistDetailOut(ArtistOut):
    aliases: list[ArtistAliasOut] = []
    genres: list[GenreOut] = []
    catalog_tracks: list[CatalogEntryOut] = []
    sets: list[ArtistSetOut] = []
    stats: dict = {}


class SetTrackDetailOut(SetTrackOut):
    catalog_title: Optional[str] = None
    catalog_artist: Optional[str] = None
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
    genres: list[GenreOut] = []
    tracklist: list[SetTrackDetailOut] = []
