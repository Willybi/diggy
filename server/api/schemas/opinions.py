"""Opinion schemas."""

from pydantic import BaseModel


class OpinionUpdate(BaseModel):
    entity_type: str
    entity_key: str
    opinion: str | None  # 'liked' | 'disliked' | None (remove)


class OpinionSetResponse(BaseModel):
    entity_type: str
    entity_key: str
    opinion: str | None = None
