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


class ChannelSearchResultOut(BaseModel):
    """A YouTube channel search hit (from the Data API ``search.list``).

    Backs the admin add-by-search UX: the operator types a name, sees the matching
    channels, and picks one — its ``channel_id`` feeds the existing add-by-URL path.
    """

    channel_id: str
    title: str
    description: str | None = None
    thumbnail_url: str | None = None


class ChannelSearchListOut(BaseModel):
    items: list[ChannelSearchResultOut]


class ChannelCandidateOut(BaseModel):
    """A channel KNOWN to the base (from ``trackid_index``) but not yet curated.

    ``trackid_count`` = number of indexed TrackID sets carrying this channel;
    ``set_count`` = how many of those are already linked to a Diggy set (the
    covered share). The gap between them is the discovery value the seed ranks on.
    """

    name: str
    set_count: int
    trackid_count: int
    # LC1: the cached YouTube resolution for this name (the 1st hit is the
    # suggested pick), read READ-ONLY from Redis by ``list_candidates`` — None
    # until the name is resolved. A resolution spends 100 quota units, so it only
    # happens on an explicit /candidates/resolve call, never on listing render.
    preselect: list[ChannelSearchResultOut] | None = None


class ChannelCandidateListOut(BaseModel):
    items: list[ChannelCandidateOut]


class ArtistChannelResolveOut(BaseModel):
    """The resolved YouTube channel for an artist (C14.b 🅱, L1).

    Output of the on-demand artist→channel cascade
    (:func:`services.channel_service.resolve_artist_candidate`). ``method`` ∈
    wikidata/musicbrainz/search and ``confidence`` ∈ high/NEEDS_VERIFY tell the
    admin whether the pick is auto-trustworthy or needs a human confirm. Every
    field defaults empty so an unresolved artist serialises cleanly.
    """

    channel_id: str | None = None
    channel_title: str | None = None
    url: str | None = None
    method: str | None = None
    confidence: str | None = None
    has_soundcloud: bool = False


class ArtistCandidateOut(BaseModel):
    """A cohort artist proposed as a YouTube-channel candidate (C14.b 🅱, L2).

    A member of the derived watch cohort (``artist_cohort``) that passed the
    « real artist » gate and is NOT yet curated into ``channels``. Ranked by
    cohort ``tier`` then relevance (``nb_sets`` > ``nb_lib`` > ``nb_catalog``).
    ``preselect`` is the artist→channel resolution READ-ONLY from the Redis cache
    (key ``yt:artcand:v1:{name}``) — None until the operator resolves it on the
    ``/artist-candidates/resolve`` path (a resolution spends 100 quota units, so
    the listing never triggers one).
    """

    artist_id: int
    name: str
    tier: int
    nb_sets: int
    nb_lib: int
    nb_catalog: int
    preselect: ArtistChannelResolveOut | None = None


class ArtistCandidateListOut(BaseModel):
    total: int
    items: list[ArtistCandidateOut]


class ChannelCreateIn(BaseModel):
    # A YouTube URL / @handle / raw « UC… » id — resolved to a channel id server-side.
    url: str
    # Optional display name (falls back to the resolved channel id when absent).
    name: str | None = None
    channel_type: str | None = None
    # The artist this channel belongs to, set when confirming an artist candidate
    # (POST with channel_type='artist'). Optional — a venue/organiser channel has none.
    artist_id: int | None = None


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
