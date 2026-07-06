"""Models package — re-exports all models for backward compatibility."""

from database import Base  # noqa: F401

from .admin import AdminAuditLog, CrawlLog  # noqa: F401
from .artist import Artist, ArtistAlias, ArtistFlag  # noqa: F401
from .base import StringArray  # noqa: F401
from .catalog import CatalogArtist, CatalogEntry, UserTrack  # noqa: F401
from .collection import CollectionItem, UserCollection  # noqa: F401
from .genre import GenreEdge, GenreMapping, GenreNode  # noqa: F401
from .opinion import UserOpinion  # noqa: F401
from .radar import (  # noqa: F401
    RadarTrack,
    RadarTrend,
    UserFollow,
    UserRadarState,
    WatchedEntity,
)
from .sets import DJSet, SetArtist, SetTrack, UserSetFollow  # noqa: F401
from .user import User  # noqa: F401
