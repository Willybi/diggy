from database import get_db
from dependencies import require_admin
from fastapi import APIRouter, Depends, HTTPException, Query
from models import GenreEdge, GenreMapping, GenreNode
from schemas import (
    TaxonomyDepthNodeList,
    TaxonomyEdgeNodeList,
    TaxonomyMappingList,
    TaxonomyMappingUpdateResponse,
    TaxonomyNeighborNodeList,
    TaxonomyNode,
    TaxonomyNodeList,
    TaxonomyStats,
)
from sqlalchemy import func, literal, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from utils import like_escape

router = APIRouter(tags=["taxonomy"])


# ── Nodes ─────────────────────────────────────────────────────────────────


@router.get("/nodes", response_model=TaxonomyNodeList)
async def list_nodes(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    base = select(GenreNode.id, GenreNode.wikidata_id, GenreNode.label)
    count_stmt = select(func.count()).select_from(GenreNode)

    if q.strip():
        pattern = f"%{like_escape(q.strip())}%"
        cond = GenreNode.label.ilike(pattern, escape="\\")
        base = base.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await db.execute(count_stmt)).scalar()
    rows = (
        await db.execute(base.order_by(GenreNode.label).limit(limit).offset(offset))
    ).all()

    return {
        "items": [
            {"id": r.id, "wikidataId": r.wikidata_id, "label": r.label} for r in rows
        ],
        "total": total,
    }


@router.get("/nodes/{node_id}", response_model=TaxonomyNode)
async def get_node(node_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(GenreNode.id, GenreNode.wikidata_id, GenreNode.label).where(
                GenreNode.id == node_id
            )
        )
    ).first()
    if not row:
        raise HTTPException(404, "Node not found")
    return {"id": row.id, "wikidataId": row.wikidata_id, "label": row.label}


@router.get("/nodes/{node_id}/children", response_model=TaxonomyEdgeNodeList)
async def get_children(
    node_id: int,
    include_influence: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Subgenres: edges where to_node_id = node_id (from is child of to)."""
    edge_types = ("parent", "influence") if include_influence else ("parent",)
    rows = (
        await db.execute(
            select(
                GenreNode.id,
                GenreNode.wikidata_id,
                GenreNode.label,
                GenreEdge.type,
                GenreEdge.source,
            )
            .select_from(GenreEdge)
            .join(GenreNode, GenreNode.id == GenreEdge.from_node_id)
            .where(GenreEdge.to_node_id == node_id, GenreEdge.type.in_(edge_types))
            .order_by(GenreNode.label)
        )
    ).all()

    return {
        "items": [
            {
                "id": r.id,
                "wikidataId": r.wikidata_id,
                "label": r.label,
                "edgeType": r.type,
                "edgeSource": r.source,
            }
            for r in rows
        ]
    }


@router.get("/nodes/{node_id}/parents", response_model=TaxonomyEdgeNodeList)
async def get_parents(node_id: int, db: AsyncSession = Depends(get_db)):
    """Parent genres: edges where from_node_id = node_id and type = parent."""
    rows = (
        await db.execute(
            select(
                GenreNode.id,
                GenreNode.wikidata_id,
                GenreNode.label,
                GenreEdge.type,
                GenreEdge.source,
            )
            .select_from(GenreEdge)
            .join(GenreNode, GenreNode.id == GenreEdge.to_node_id)
            .where(GenreEdge.from_node_id == node_id, GenreEdge.type == "parent")
            .order_by(GenreNode.label)
        )
    ).all()

    return {
        "items": [
            {
                "id": r.id,
                "wikidataId": r.wikidata_id,
                "label": r.label,
                "edgeType": r.type,
                "edgeSource": r.source,
            }
            for r in rows
        ]
    }


# The two recursive CTEs stay raw SQL: the SQLAlchemy equivalent (cte().union()
# + aliased self-join) is materially less readable than the SQL itself.


@router.get("/nodes/{node_id}/ancestors", response_model=TaxonomyDepthNodeList)
async def get_ancestors(node_id: int, db: AsyncSession = Depends(get_db)):
    """All ancestors via recursive CTE on parent edges (depth max 20)."""
    rows = (
        await db.execute(
            text("""
            WITH RECURSIVE ancestors AS (
                SELECT ge.to_node_id AS id, 1 AS depth
                FROM genre_edges ge
                WHERE ge.from_node_id = :id AND ge.type = 'parent'
              UNION
                SELECT ge.to_node_id, a.depth + 1
                FROM genre_edges ge
                JOIN ancestors a ON ge.from_node_id = a.id
                WHERE ge.type = 'parent' AND a.depth < 20
            )
            SELECT DISTINCT gn.id, gn.wikidata_id, gn.label, MIN(a.depth) AS depth
            FROM ancestors a
            JOIN genre_nodes gn ON gn.id = a.id
            GROUP BY gn.id, gn.wikidata_id, gn.label
            ORDER BY depth
        """),
            {"id": node_id},
        )
    ).fetchall()

    return {
        "items": [
            {"id": r[0], "wikidataId": r[1], "label": r[2], "depth": r[3]} for r in rows
        ]
    }


@router.get("/nodes/{node_id}/descendants", response_model=TaxonomyDepthNodeList)
async def get_descendants(node_id: int, db: AsyncSession = Depends(get_db)):
    """All descendants via recursive CTE on parent edges (depth max 20)."""
    rows = (
        await db.execute(
            text("""
            WITH RECURSIVE descendants AS (
                SELECT ge.from_node_id AS id, 1 AS depth
                FROM genre_edges ge
                WHERE ge.to_node_id = :id AND ge.type = 'parent'
              UNION
                SELECT ge.from_node_id, d.depth + 1
                FROM genre_edges ge
                JOIN descendants d ON ge.to_node_id = d.id
                WHERE ge.type = 'parent' AND d.depth < 20
            )
            SELECT DISTINCT gn.id, gn.wikidata_id, gn.label, MIN(d.depth) AS depth
            FROM descendants d
            JOIN genre_nodes gn ON gn.id = d.id
            GROUP BY gn.id, gn.wikidata_id, gn.label
            ORDER BY depth, gn.label
        """),
            {"id": node_id},
        )
    ).fetchall()

    return {
        "items": [
            {"id": r[0], "wikidataId": r[1], "label": r[2], "depth": r[3]} for r in rows
        ]
    }


@router.get("/nodes/{node_id}/neighbors", response_model=TaxonomyNeighborNodeList)
async def get_neighbors(node_id: int, db: AsyncSession = Depends(get_db)):
    """Genres connected via influence edges (both directions)."""
    influences = (
        select(
            GenreNode.id,
            GenreNode.wikidata_id,
            GenreNode.label,
            literal("influences").label("direction"),
            GenreEdge.source,
        )
        .select_from(GenreEdge)
        .join(GenreNode, GenreNode.id == GenreEdge.to_node_id)
        .where(GenreEdge.from_node_id == node_id, GenreEdge.type == "influence")
    )
    influenced_by = (
        select(
            GenreNode.id,
            GenreNode.wikidata_id,
            GenreNode.label,
            literal("influenced_by").label("direction"),
            GenreEdge.source,
        )
        .select_from(GenreEdge)
        .join(GenreNode, GenreNode.id == GenreEdge.from_node_id)
        .where(GenreEdge.to_node_id == node_id, GenreEdge.type == "influence")
    )
    union = union_all(influences, influenced_by)
    rows = (
        await db.execute(union.order_by(union.selected_columns.wikidata_id))
    ).all()

    return {
        "items": [
            {
                "id": r.id,
                "wikidataId": r.wikidata_id,
                "label": r.label,
                "direction": r.direction,
                "edgeSource": r.source,
            }
            for r in rows
        ]
    }


# ── Roots & Stats ────────────────────────────────────────────────────────


def _has_parent_edge():
    """EXISTS clause: the (correlated) GenreNode has an outgoing parent edge."""
    return (
        select(GenreEdge.id)
        .where(GenreEdge.from_node_id == GenreNode.id, GenreEdge.type == "parent")
        .exists()
    )


@router.get("/roots", response_model=TaxonomyNodeList)
async def get_roots(db: AsyncSession = Depends(get_db)):
    """Nodes with no outgoing parent edges (top-level genres)."""
    rows = (
        await db.execute(
            select(GenreNode.id, GenreNode.wikidata_id, GenreNode.label)
            .where(~_has_parent_edge())
            .order_by(GenreNode.label)
        )
    ).all()

    return {
        "items": [
            {"id": r.id, "wikidataId": r.wikidata_id, "label": r.label} for r in rows
        ]
    }


@router.get("/stats", response_model=TaxonomyStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    node_count = (
        await db.execute(select(func.count()).select_from(GenreNode))
    ).scalar()
    edge_count = (
        await db.execute(select(func.count()).select_from(GenreEdge))
    ).scalar()
    parent_count = (
        await db.execute(
            select(func.count())
            .select_from(GenreEdge)
            .where(GenreEdge.type == "parent")
        )
    ).scalar()
    influence_count = (
        await db.execute(
            select(func.count())
            .select_from(GenreEdge)
            .where(GenreEdge.type == "influence")
        )
    ).scalar()
    root_count = (
        await db.execute(
            select(func.count()).select_from(GenreNode).where(~_has_parent_edge())
        )
    ).scalar()

    return {
        "nodeCount": node_count,
        "edgeCount": edge_count,
        "parentEdgeCount": parent_count,
        "influenceEdgeCount": influence_count,
        "rootCount": root_count,
    }


# ── Mappings ─────────────────────────────────────────────────────────────


@router.get("/mappings", response_model=TaxonomyMappingList)
async def list_mappings(
    unmapped: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(
            GenreMapping.id,
            GenreMapping.raw_name,
            GenreMapping.node_id,
            GenreNode.wikidata_id,
            GenreNode.label,
        )
        .outerjoin(GenreNode, GenreNode.id == GenreMapping.node_id)
        .order_by(GenreMapping.raw_name)
    )
    count_stmt = select(func.count()).select_from(GenreMapping)

    if unmapped:
        base = base.where(GenreMapping.node_id.is_(None))
        count_stmt = count_stmt.where(GenreMapping.node_id.is_(None))

    rows = (await db.execute(base.limit(limit).offset(offset))).all()
    total = (await db.execute(count_stmt)).scalar()

    return {
        "items": [
            {
                "id": r.id,
                "rawName": r.raw_name,
                "nodeId": r.node_id,
                "nodeWikidataId": r.wikidata_id,
                "nodeLabel": r.label,
            }
            for r in rows
        ],
        "total": total,
    }


@router.put("/mappings/{raw_name}", response_model=TaxonomyMappingUpdateResponse)
async def update_mapping(
    raw_name: str,
    node_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Admin: set or update the taxonomy node for a raw genre name."""
    node_exists = (
        await db.execute(select(GenreNode.id).where(GenreNode.id == node_id))
    ).scalar_one_or_none()
    if node_exists is None:
        raise HTTPException(404, "Node not found")

    # Portable upsert (raw_name is UNIQUE): dialect-specific ON CONFLICT would
    # break the SQLite test harness, and admin traffic makes races a non-issue.
    mapping = (
        await db.execute(select(GenreMapping).where(GenreMapping.raw_name == raw_name))
    ).scalar_one_or_none()
    if mapping:
        mapping.node_id = node_id
    else:
        db.add(GenreMapping(raw_name=raw_name, node_id=node_id))
    await db.commit()
    return {"ok": True, "rawName": raw_name, "nodeId": node_id}
