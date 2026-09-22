"""Watched-channel admin schemas (C14.b, L3 — YouTube-first slice)."""

from datetime import datetime

from pydantic import BaseModel


class ChannelOut(BaseModel):
    id: int
    platform: str
    # Platform-side channel id (YouTube « UC… »), NULL until resolved.
    external_id: str | None = None
    name: str
    # 'artist' | 'label' | 'organizer' | 'radio' (plain String, no enum).
    channel_type: str | None = None
    artist_id: int | None = None
    watched: bool
    excluded: bool
    # Stamped by the watch lot; drives the per-channel cadence.
    last_checked_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChannelListOut(BaseModel):
    total: int
    items: list[ChannelOut]


class ChannelCandidateOut(BaseModel):
    """A channel KNOWN to the base (from ``trackid_index``) but not yet curated.

    ``trackid_count`` = number of indexed TrackID sets carrying this channel;
    ``set_count`` = how many of those are already linked to a Diggy set (the
    covered share). The gap between them is the discovery value the seed ranks on.
    """

    name: str
    set_count: int
    trackid_count: int


class ChannelCandidateListOut(BaseModel):
    items: list[ChannelCandidateOut]


class ChannelCreateIn(BaseModel):
    # A YouTube URL / @handle / raw « UC… » id — resolved to a channel id server-side.
    url: str
    # Optional display name (falls back to the resolved channel id when absent).
    name: str | None = None
    channel_type: str | None = None


class ChannelUpdateIn(BaseModel):
    # PATCH semantics: a field ABSENT from the body is left untouched (the router
    # reads the provided keys via model_dump(exclude_unset=True)). watched/excluded
    # are boolean toggles (applied only when present AND non-null); channel_type /
    # artist_id are applied whenever their key is present — an explicit null clears
    # the value.
    watched: bool | None = None
    excluded: bool | None = None
    channel_type: str | None = None
    artist_id: int | None = None
