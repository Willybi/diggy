"""Collection schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

# Entities a collection item may reference (C5 v2 polymorphic curation).
COLLECTION_ITEM_TYPES = {"track", "set", "artist", "genre", "playlist"}


class CollectionCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: Optional[str] = Field(None, max_length=20)


class CollectionItemAddIn(BaseModel):
    item_type: str = Field(..., max_length=20)
    item_id: Optional[int] = None
    item_name: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _check_polymorphic_key(self):
        if self.item_type not in COLLECTION_ITEM_TYPES:
            raise ValueError(
                f"item_type must be one of {sorted(COLLECTION_ITEM_TYPES)}"
            )
        # A genre has no table row — it is addressed by name; every other type is
        # addressed by its integer id.
        if self.item_type == "genre":
            if not self.item_name:
                raise ValueError("item_name is required for a genre item")
        elif self.item_id is None:
            raise ValueError("item_id is required for this item_type")
        return self


class FolderCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class FolderUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    position: Optional[int] = None


class FolderOut(BaseModel):
    id: int
    name: str
    position: int = 0
    created_at: Optional[datetime] = None
    collection_count: int = 0

    model_config = {"from_attributes": True}


class CollectionFolderAssignIn(BaseModel):
    """Assign a collection to a folder (folder_id=None removes it from any folder)."""

    folder_id: Optional[int] = None


class CollectionOut(BaseModel):
    id: int
    name: str
    type: str = "playlist"
    folder_id: Optional[int] = None
    created_at: Optional[datetime] = None
    item_count: int = 0

    model_config = {"from_attributes": True}


class CollectionItemOut(BaseModel):
    """A resolved collection item, polymorphic over item_type.

    ``title``/``subtitle``/``has_artwork`` are resolved from the referenced
    entity; ``missing`` is True when that entity no longer exists (or is not
    visible to the viewer for a track). The frontend builds the artwork URL from
    (item_type, item_id). The bpm/key/duration/preview extras are track-only
    (NULL for every other type)."""

    item_type: str
    item_id: Optional[int] = None
    item_name: Optional[str] = None
    position: int = 0
    added_at: Optional[datetime] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    has_artwork: bool = False
    missing: bool = False
    # Track-only render extras (null for the other types).
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration_ms: Optional[int] = None
    has_preview: Optional[bool] = None


class CollectionDetailOut(CollectionOut):
    items: list[CollectionItemOut] = []
