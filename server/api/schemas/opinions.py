"""Opinion schemas."""

from typing import Literal

from pydantic import BaseModel


class OpinionUpdate(BaseModel):
    entity_type: str
    entity_key: str
    opinion: Literal["liked", "disliked"] | None  # None removes the opinion


class OpinionSetResponse(BaseModel):
    entity_type: str
    entity_key: str
    opinion: str | None = None
