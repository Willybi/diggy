"""Admin schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ArtistFlagOut(BaseModel):
    id: int
    raw_artist_string: str
    reason: str
    tokens: list[str]
    deezer_ids: dict
    status: str
    resolved_artist_ids: list[int] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SyncQueued(BaseModel):
    status: str
    task_id: str


class SyncStatus(BaseModel):
    status: str
    result: dict | None = None
    error: str | None = None


class ResolveIn(BaseModel):
    action: Literal["split", "keep", "skip"]


class ArtistDeezerIn(BaseModel):
    deezer_id: str


class FlagManualIn(BaseModel):
    raw_artist_string: str
    tokens: list[str]
    reason: str = "manual"


class SetArtistIn(BaseModel):
    artist_id: int
    role: str = "dj"


class DeezerArtistHit(BaseModel):
    deezer_id: str
    name: str
    picture: str | None = None
    nb_fan: int | None = None


class LinkDeezerResponse(BaseModel):
    id: int
    name: str
    deezer_id: str | None = None
    has_artwork: bool = False
    merged: bool = False
    merged_id: int | None = None
    merged_name: str | None = None


class NoDeezerResponse(BaseModel):
    id: int
    name: str


class SetArtistAddResponse(BaseModel):
    set_id: int
    artist_id: int
    role: str


class ResetBeatportResponse(BaseModel):
    status: str = "reset"
    cleared: int
    bpm_reverted: int
    key_reverted: int


class EnrichBeatportResponse(BaseModel):
    status: str
    catalog_id: int
    bpm: float | None = None
    key: str | None = None
    label: str | None = None
    genres: list[str] = []
    beatport_id: str | None = None


class UnclassifiedCountResponse(BaseModel):
    count: int


class DeezerGenreLookupResponse(BaseModel):
    status: str
    genres: list[str] = []
    applied: bool | None = None


class FetchPlaylistArtworksResponse(BaseModel):
    fetched: int
    failed: int
    total: int


class CrawlLogItem(BaseModel):
    id: int
    task_type: str
    target_id: int | None = None
    target_label: str | None = None
    source: str | None = None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    stats: dict | None = None
    error_message: str | None = None
    celery_task_id: str | None = None


class CrawlLogsResponse(BaseModel):
    items: list[CrawlLogItem]
    total: int
    page: int
    per_page: int


# ── Monitoring (GET /admin/monitoring) ──


class BacklogSnapshotItem(BaseModel):
    captured_at: str
    # Free-form dict keyed by domain (enrich/artists/sets/catalog).
    payload: dict


class ThroughputItem(BaseModel):
    day: str
    task_type: str
    source: str | None = None
    runs: int
    errors: int
    enriched: int
    not_found: int
    merged: int
    hit_rate: float | None = None
    duration_ms_avg: int | None = None
    duration_ms_max: int | None = None


class LastRunItem(BaseModel):
    task_type: str
    source: str | None = None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None


class MonitoringStatus(BaseModel):
    last_runs: list[LastRunItem]
    latest_snapshot: BacklogSnapshotItem | None = None


class MonitoringResponse(BaseModel):
    backlog_series: list[BacklogSnapshotItem]
    throughput_series: list[ThroughputItem]
    status: MonitoringStatus


# ── Backlog dashboard (GET /admin/backlog) ──


class EnrichBacklog(BaseModel):
    pending: int
    total_missing: int
    abandoned: int


class ArtistsBacklog(BaseModel):
    to_link: int
    no_artwork: int


class SetsBacklog(BaseModel):
    recrawl: int
    flags_pending: int


class ArtistFlagsBacklog(BaseModel):
    pending: int


class GenresBacklog(BaseModel):
    unclassified: int
    mappings_unmapped: int


class CatalogBacklog(BaseModel):
    bpm_missing: int


class CrawlBacklog(BaseModel):
    playlists_due: int
    dlq: int | None = None


class BacklogResponse(BaseModel):
    captured_at: str | None = None
    beatport: EnrichBacklog
    deezer: EnrichBacklog
    artists: ArtistsBacklog
    sets: SetsBacklog
    artist_flags: ArtistFlagsBacklog
    genres: GenresBacklog
    catalog: CatalogBacklog
    crawl: CrawlBacklog
