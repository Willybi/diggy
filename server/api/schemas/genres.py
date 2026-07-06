"""Genre schemas."""

from pydantic import BaseModel


class GenreRenameIn(BaseModel):
    new_name: str


class GenreMergeIn(BaseModel):
    source: str
    target: str


class GenreListItem(BaseModel):
    name: str
    pillar: str
    depth: int
    trackCount: int
    artistCount: int
    bpmLo: int
    bpmHi: int
    inLibCount: int
    artworks: list[str] = []
    artists: list[dict] = []


class GenreListResponse(BaseModel):
    items: list[GenreListItem]
    total: int
    pillarCounts: dict[str, int] = {}


class GenreDetailResponse(BaseModel):
    name: str
    pillar: str
    depth: int
    trackCount: int
    artistCount: int
    bpmLo: int
    bpmHi: int
    inLibCount: int
    setCount: int
    playlistCount: int
    artworks: list[str] = []
    artists: list[dict] = []


class GenreArtistItem(BaseModel):
    id: int
    name: str
    hasArtwork: bool = False
    trackCount: int = 0
    inLibCount: int = 0


class GenreArtistListResponse(BaseModel):
    items: list[GenreArtistItem]
    total: int


class GenreSetItem(BaseModel):
    id: int
    title: str
    playedDate: str | None = None
    hasArtwork: bool = False
    genreTrackCount: int = 0
    totalTracks: int = 0


class GenreSetListResponse(BaseModel):
    items: list[GenreSetItem]
    total: int


class GenrePlaylistItem(BaseModel):
    id: int
    title: str
    source: str
    hasArtwork: bool = False
    owner: str | None = None
    genreTrackCount: int = 0


class GenrePlaylistListResponse(BaseModel):
    items: list[GenrePlaylistItem]
    total: int


class GenreTrackItem(BaseModel):
    id: int
    title: str
    artist: str
    bpm: float | None = None
    key: str | None = None
    durationMs: int | None = None
    hasArtwork: bool = False
    hasPreview: bool = False
    inLib: bool = False


class GenreTrackListResponse(BaseModel):
    items: list[GenreTrackItem]
    total: int


class GenreNeighborItem(BaseModel):
    name: str
    pillar: str
    depth: int
    commonArtists: int = 0
    trackCount: int = 0


class GenreNeighborResponse(BaseModel):
    items: list[GenreNeighborItem]


class GenreMergeResponse(BaseModel):
    merged: bool = True
    source: str
    target: str
    affected: int


class GenreRenameResponse(BaseModel):
    renamed: bool = True
    source: str = ""  # "from" is reserved, use alias
    to: str
    affected: int

    model_config = {"populate_by_name": True}


class RefreshPillarsResponse(BaseModel):
    ok: bool = True
    cached: int
