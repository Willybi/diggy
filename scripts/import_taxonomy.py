"""Import genre taxonomy CSVs (nodes + edges) into the database.

Usage:
    python scripts/import_taxonomy.py out/canonical_nodes.csv out/canonical_edges.csv

Idempotent: safe to re-run (upserts nodes, skips duplicate edges).
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def get_sync_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        sys.exit("ERROR: DATABASE_URL not set")
    return url.replace("+asyncpg", "").replace("+aiopg", "")


def import_nodes(session: Session, csv_path: str) -> dict[str, int]:
    """Import nodes CSV, return mapping wikidata_id -> db id."""
    now = datetime.now(timezone.utc)
    count_insert = 0
    count_update = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wid = row["id"].strip()
            label = row["label"].strip()
            result = session.execute(
                text("""
                    INSERT INTO genre_nodes (wikidata_id, label, created_at)
                    VALUES (:wid, :label, :now)
                    ON CONFLICT (wikidata_id) DO UPDATE SET label = EXCLUDED.label
                    RETURNING id, (xmax = 0) AS inserted
                """),
                {"wid": wid, "label": label, "now": now},
            )
            row_result = result.fetchone()
            if row_result[1]:
                count_insert += 1
            else:
                count_update += 1

    session.flush()

    # Build lookup dict
    rows = session.execute(text("SELECT wikidata_id, id FROM genre_nodes")).fetchall()
    lookup = {r[0]: r[1] for r in rows}

    print(f"  Nodes: {count_insert} inserted, {count_update} updated, {len(lookup)} total")
    return lookup


def import_edges(session: Session, csv_path: str, lookup: dict[str, int]) -> None:
    """Import edges CSV using the node lookup dict."""
    count = 0
    skipped = 0
    missing_nodes = set()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            from_wid = row["from_id"].strip()
            to_wid = row["to_id"].strip()
            edge_type = row["type"].strip()
            source = row["source"].strip()

            from_id = lookup.get(from_wid)
            to_id = lookup.get(to_wid)

            if from_id is None:
                missing_nodes.add(from_wid)
                skipped += 1
                continue
            if to_id is None:
                missing_nodes.add(to_wid)
                skipped += 1
                continue

            result = session.execute(
                text("""
                    INSERT INTO genre_edges (from_node_id, to_node_id, type, source)
                    VALUES (:from_id, :to_id, :type, :source)
                    ON CONFLICT (from_node_id, to_node_id, type) DO NOTHING
                """),
                {"from_id": from_id, "to_id": to_id, "type": edge_type, "source": source},
            )
            count += result.rowcount

    if missing_nodes:
        print(f"  WARNING: {len(missing_nodes)} missing node(s): {', '.join(sorted(missing_nodes)[:10])}")

    print(f"  Edges: {count} inserted, {skipped} skipped (missing nodes)")


def auto_match_mappings(session: Session) -> None:
    """Match raw genre names from catalog.genres to taxonomy nodes."""
    # Get distinct raw genre names from catalog
    rows = session.execute(
        text("SELECT DISTINCT unnest(genres) AS name FROM catalog WHERE genres != '{}' ORDER BY name")
    ).fetchall()
    raw_names = [r[0] for r in rows]

    if not raw_names:
        print("  Mappings: no raw genres found in catalog")
        return

    # Build lowercase label -> node_id lookup
    nodes = session.execute(text("SELECT id, label FROM genre_nodes")).fetchall()
    label_lookup = {r[1].lower(): r[0] for r in nodes}

    matched = 0
    unmatched = []

    for name in raw_names:
        node_id = label_lookup.get(name.lower())
        session.execute(
            text("""
                INSERT INTO genre_mappings (raw_name, node_id)
                VALUES (:name, :node_id)
                ON CONFLICT (raw_name) DO UPDATE SET node_id = COALESCE(genre_mappings.node_id, EXCLUDED.node_id)
            """),
            {"name": name, "node_id": node_id},
        )
        if node_id:
            matched += 1
        else:
            unmatched.append(name)

    print(f"  Mappings: {matched}/{len(raw_names)} auto-matched")
    if unmatched:
        print(f"  Unmatched ({len(unmatched)}): {', '.join(unmatched)}")


def main():
    parser = argparse.ArgumentParser(description="Import genre taxonomy CSVs")
    parser.add_argument("nodes_csv", help="Path to canonical_nodes.csv")
    parser.add_argument("edges_csv", help="Path to canonical_edges.csv")
    args = parser.parse_args()

    engine = create_engine(get_sync_url())

    with Session(engine) as session:
        print("Phase 1: Importing nodes...")
        lookup = import_nodes(session, args.nodes_csv)

        print("Phase 2: Importing edges...")
        import_edges(session, args.edges_csv, lookup)

        print("Phase 3: Auto-matching mappings...")
        auto_match_mappings(session)

        session.commit()
        print("Done!")


if __name__ == "__main__":
    main()
