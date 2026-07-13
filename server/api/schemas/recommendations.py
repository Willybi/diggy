"""Recommendation schemas (C4 — "Pour toi")."""

from pydantic import BaseModel

from .catalog import CatalogEntryOut


class RecommendationItem(CatalogEntryOut):
    """A catalog entry plus its aggregated personalised score."""

    reco_score: float


class RecommendationList(BaseModel):
    items: list[RecommendationItem] = []
