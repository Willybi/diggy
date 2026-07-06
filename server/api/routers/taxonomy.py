from database import get_db
from dependencies import require_admin
from fastapi import APIRouter, Depends, HTTPException, Query
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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["taxonomy"])


# ── Nodes ─────────────────────────────────────────────────────────────────


@router.get("/nodes", response_model=TaxonomyNodeList)
async def list_nodes(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    has_q = bool(q.strip())
    pattern = f"%{q.strip().lower()}%"

    total = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM genre_nodes WHERE (:no_q OR LOWER(label) LIKE :p)"
            ),
            {"no_q": not has_q, "p": pattern},
        )
    ).scalar()

    rows = (
        await db.execute(
            text("""
            SELECT id, wikidata_id, label
            FROM genre_nodes
            WHERE (:no_q OR LOWER(label) LIKE :p)
            ORDER BY label
            LIMIT :lim OFFSET :off
        """),
            {"no_q": not has_q, "p": pattern, "lim": limit, "off": offset},
        )
    ).fetchall()

    return {
        "items": [{"id": r[0], "wikidataId": r[1], "label": r[2]} for r in rows],
        "total": total,
    }


@router.get("/nodes/{node_id}", response_model=TaxonomyNode)
async def get_node(node_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            text("SELECT id, wikidata_id, label FROM genre_nodes WHERE id = :id"),
            {"id": node_id},
        )
    ).fetchone()
    if not row:
        raise HTTPException(404, "Node not found")
    return {"id": row[0], "wikidataId": row[1], "label": row[2]}


@router.get("/nodes/{node_id}/children", response_model=TaxonomyEdgeNodeList)
async def get_children(
    node_id: int,
    include_influence: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Subgenres: edges where to_node_id = node_id (from is child of to)."""
    type_filter = (
        "ge.type IN ('parent', 'influence')"
        if include_influence
        else "ge.type = 'parent'"
    )
    rows = (
        await db.execute(
            text(f"""
            SELECT gn.id, gn.wikidata_id, gn.label, ge.type, ge.source
            FROM genre_edges ge
            JOIN genre_nodes gn ON gn.id = ge.from_node_id
            WHERE ge.to_node_id = :id AND {type_filter}
            ORDER BY gn.label
        """),
            {"id": node_id},
        )
    ).fetchall()

    return {
        "items": [
            {
                "id": r[0],
                "wikidataId": r[1],
                "label": r[2],
                "edgeType": r[3],
                "edgeSource": r[4],
            }
            for r in rows
        ]
    }


@router.get("/nodes/{node_id}/parents", response_model=TaxonomyEdgeNodeList)
async def get_parents(node_id: int, db: AsyncSession = Depends(get_db)):
    """Parent genres: edges where from_node_id = node_id and type = parent."""
    rows = (
        await db.execute(
            text("""
            SELECT gn.id, gn.wikidata_id, gn.label, ge.type, ge.source
            FROM genre_edges ge
            JOIN genre_nodes gn ON gn.id = ge.to_node_id
            WHERE ge.from_node_id = :id AND ge.type = 'parent'
            ORDER BY gn.label
        """),
            {"id": node_id},
        )
    ).fetchall()

    return {
        "items": [
            {
                "id": r[0],
                "wikidataId": r[1],
                "label": r[2],
                "edgeType": r[3],
                "edgeSource": r[4],
            }
            for r in rows
        ]
    }


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
    rows = (
        await db.execute(
            text("""
            SELECT gn.id, gn.wikidata_id, gn.label, 'influences' AS direction, ge.source
            FROM genre_edges ge
            JOIN genre_nodes gn ON gn.id = ge.to_node_id
            WHERE ge.from_node_id = :id AND ge.type = 'influence'
            UNION ALL
            SELECT gn.id, gn.wikidata_id, gn.label, 'influenced_by', ge.source
            FROM genre_edges ge
            JOIN genre_nodes gn ON gn.id = ge.from_node_id
            WHERE ge.to_node_id = :id AND ge.type = 'influence'
            ORDER BY 2
        """),
            {"id": node_id},
        )
    ).fetchall()

    return {
        "items": [
            {
                "id": r[0],
                "wikidataId": r[1],
                "label": r[2],
                "direction": r[3],
                "edgeSource": r[4],
            }
            for r in rows
        ]
    }


# ── Roots & Stats ────────────────────────────────────────────────────────


@router.get("/roots", response_model=TaxonomyNodeList)
async def get_roots(db: AsyncSession = Depends(get_db)):
    """Nodes with no outgoing parent edges (top-level genres)."""
    rows = (
        await db.execute(
            text("""
            SELECT gn.id, gn.wikidata_id, gn.label
            FROM genre_nodes gn
            WHERE NOT EXISTS (
                SELECT 1 FROM genre_edges ge
                WHERE ge.from_node_id = gn.id AND ge.type = 'parent'
            )
            ORDER BY gn.label
        """),
        )
    ).fetchall()

    return {"items": [{"id": r[0], "wikidataId": r[1], "label": r[2]} for r in rows]}


@router.get("/stats", response_model=TaxonomyStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    node_count = (await db.execute(text("SELECT COUNT(*) FROM genre_nodes"))).scalar()
    edge_count = (await db.execute(text("SELECT COUNT(*) FROM genre_edges"))).scalar()
    parent_count = (
        await db.execute(text("SELECT COUNT(*) FROM genre_edges WHERE type = 'parent'"))
    ).scalar()
    influence_count = (
        await db.execute(
            text("SELECT COUNT(*) FROM genre_edges WHERE type = 'influence'")
        )
    ).scalar()
    root_count = (
        await db.execute(
            text("""
        SELECT COUNT(*) FROM genre_nodes gn
        WHERE NOT EXISTS (SELECT 1 FROM genre_edges ge WHERE ge.from_node_id = gn.id AND ge.type = 'parent')
    """)
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
    where = "WHERE gm.node_id IS NULL" if unmapped else ""
    rows = (
        await db.execute(
            text(f"""
            SELECT gm.id, gm.raw_name, gm.node_id, gn.wikidata_id, gn.label
            FROM genre_mappings gm
            LEFT JOIN genre_nodes gn ON gn.id = gm.node_id
            {where}
            ORDER BY gm.raw_name
            LIMIT :lim OFFSET :off
        """),
            {"lim": limit, "off": offset},
        )
    ).fetchall()

    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM genre_mappings gm {where}"),
        )
    ).scalar()

    return {
        "items": [
            {
                "id": r[0],
                "rawName": r[1],
                "nodeId": r[2],
                "nodeWikidataId": r[3],
                "nodeLabel": r[4],
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
    # Verify node exists
    node = (
        await db.execute(
            text("SELECT id FROM genre_nodes WHERE id = :id"),
            {"id": node_id},
        )
    ).fetchone()
    if not node:
        raise HTTPException(404, "Node not found")

    await db.execute(
        text("""
            INSERT INTO genre_mappings (raw_name, node_id)
            VALUES (:name, :nid)
            ON CONFLICT (raw_name) DO UPDATE SET node_id = :nid
        """),
        {"name": raw_name, "nid": node_id},
    )
    await db.commit()
    return {"ok": True, "rawName": raw_name, "nodeId": node_id}
