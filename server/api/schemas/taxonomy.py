"""Taxonomy schemas."""

from pydantic import BaseModel


class TaxonomyNode(BaseModel):
    id: int
    wikidataId: str
    label: str


class TaxonomyNodeList(BaseModel):
    items: list[TaxonomyNode]
    total: int = 0


class TaxonomyEdgeNode(BaseModel):
    id: int
    wikidataId: str
    label: str
    edgeType: str
    edgeSource: str


class TaxonomyEdgeNodeList(BaseModel):
    items: list[TaxonomyEdgeNode]


class TaxonomyDepthNode(BaseModel):
    id: int
    wikidataId: str
    label: str
    depth: int


class TaxonomyDepthNodeList(BaseModel):
    items: list[TaxonomyDepthNode]


class TaxonomyNeighborNode(BaseModel):
    id: int
    wikidataId: str
    label: str
    direction: str
    edgeSource: str


class TaxonomyNeighborNodeList(BaseModel):
    items: list[TaxonomyNeighborNode]


class TaxonomyStats(BaseModel):
    nodeCount: int
    edgeCount: int
    parentEdgeCount: int
    influenceEdgeCount: int
    rootCount: int


class TaxonomyMapping(BaseModel):
    id: int
    rawName: str
    nodeId: int | None = None
    nodeWikidataId: str | None = None
    nodeLabel: str | None = None


class TaxonomyMappingList(BaseModel):
    items: list[TaxonomyMapping]
    total: int


class TaxonomyMappingUpdateResponse(BaseModel):
    ok: bool = True
    rawName: str
    nodeId: int
