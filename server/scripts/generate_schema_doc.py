"""Generate docs/database-schema.md from SQLAlchemy model metadata.

No database connection required — pure declarative introspection.
Run from repo root:  python server/scripts/generate_schema_doc.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: database.py needs DATABASE_URL at import time.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///unused.db")

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "server" / "api"
sys.path.insert(0, str(API_DIR))

from models import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Domain grouping for tables
# ---------------------------------------------------------------------------
DOMAIN_ORDER: list[tuple[str, list[str]]] = [
    (
        "Catalog hub",
        ["catalog", "catalog_artists", "user_tracks"],
    ),
    (
        "Users",
        ["users", "user_opinions", "user_collections", "collection_items"],
    ),
    (
        "Radar",
        [
            "watched_entities",
            "user_follows",
            "radar_tracks",
            "radar_trends",
            "user_radar_state",
        ],
    ),
    (
        "Artists",
        ["artists", "artist_aliases", "artist_flags"],
    ),
    (
        "Sets",
        ["sets", "set_artists", "set_tracks", "set_flags", "user_set_follows"],
    ),
    (
        "Genres",
        ["genre_nodes", "genre_edges", "genre_mappings"],
    ),
    (
        "System",
        ["admin_audit_log", "crawl_logs"],
    ),
]

MANUAL_BLOCK_MARKER_BEGIN = "<!-- MANUAL:BEGIN -->"
MANUAL_BLOCK_MARKER_END = "<!-- MANUAL:END -->"

INITIAL_MANUAL_BLOCK = """\
<!-- MANUAL:BEGIN -->
## Conventions & domain rules

These notes are maintained by hand. Everything below the END marker
is auto-generated — do not edit it directly.

### Sentinels
- `artists.deezer_id = "NOT_FOUND"` marks an artist confirmed absent from Deezer.

### Deduplication
- `catalog.normalized_key` = lower(`artist|title`). Primary dedup key.
- `catalog.isrc` = secondary dedup key when available.

### Genre system
- `catalog.genres` is a `TEXT[]` of raw genre names as received from sources.
- Normalization uses the Wikidata-based graph: `genre_nodes` (canonical genres)
  linked by `genre_edges` (subgenre_of, related_to) and mapped from raw names
  via `genre_mappings`.
- Artist genres are computed dynamically from their catalog tracks
  (`artist_service._artist_genres()`), there is no association table.

### Provenance columns
- `catalog.bpm_source` / `catalog.key_source`: track which external source
  provided the authoritative BPM / key value (e.g. `"beatport"`, `"deezer"`).

### Lifecycle & radar columns
- `catalog.scope`: `"shared"` (default) or `"private"` (Rekordbox-only entries before enrichment).
- `catalog.origin`: how the entry entered the catalog (`"deezer"`, `"rekordbox"`, etc.).
- `catalog.status`: `"official"` (default), `"pending"`, etc.
- `radar_tracks.removed_at`: soft-delete timestamp for tracks removed from a playlist.
- `radar_tracks.is_initial_detection`: `true` for tracks present at first crawl
  (avoids inflating trend scores).

### Merge asymmetry
- Duplicate rows (false negatives) are cheap storage debt.
- Bad merges (false positives) are expensive data corruption.
- Always err toward separation.

### Model vs DB caveat
- This doc reflects SQLAlchemy model declarations. The actual DB may diverge
  if a migration altered a constraint manually (e.g. `ON DELETE`). When in
  doubt, check `alembic/versions/`.
<!-- MANUAL:END -->"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _col_type_str(col) -> str:
    """Human-readable column type."""
    try:
        t = col.type
        type_name = type(t).__name__
        # Common SA types
        if type_name == "String" and hasattr(t, "length") and t.length:
            return f"String({t.length})"
        if type_name == "Float":
            return "Float"
        if type_name == "Integer":
            return "Integer"
        if type_name == "Boolean":
            return "Boolean"
        if type_name == "Text":
            return "Text"
        if type_name == "Date":
            return "Date"
        if type_name == "DateTime":
            tz = getattr(t, "timezone", False)
            return "DateTime(tz)" if tz else "DateTime"
        if type_name == "JSON":
            return "JSON"
        if type_name == "StringArray":
            return "TEXT[]"
        return type_name
    except Exception:
        return "?"


def _default_str(col) -> str:
    """Notable default or server_default, if any."""
    parts = []
    if col.server_default is not None:
        arg = col.server_default.arg
        if callable(arg):
            parts.append("server_default=func")
        elif isinstance(arg, str):
            parts.append(f"server_default={arg!r}")
        else:
            # ClauseElement (e.g. func.now()): str() compiles to stable SQL,
            # repr() would embed a memory address and break diff stability
            parts.append(f"server_default={arg}")
    if col.default is not None:
        arg = col.default.arg
        if callable(arg):
            parts.append("default=func")
        else:
            parts.append(f"default={arg!r}")
    return ", ".join(parts)


def _fk_info(col) -> str:
    """FK target + ON DELETE behavior."""
    fks = list(col.foreign_keys)
    if not fks:
        return ""
    fk = fks[0]
    target = fk.target_fullname
    on_delete = fk.ondelete or ""
    on_del_str = f" ON DELETE {on_delete}" if on_delete else ""
    return f"FK → {target}{on_del_str}"


def _render_table(table) -> list[str]:
    """Render a single table as markdown lines."""
    lines: list[str] = []
    name = table.name

    # Detect composite PK
    pk_cols = [c.name for c in table.primary_key.columns]
    pk_label = (
        f"Composite PK: (`{'`, `'.join(pk_cols)}`)"
        if len(pk_cols) > 1
        else f"PK: `{pk_cols[0]}`"
    )

    lines.append(f"### `{name}`")
    lines.append("")
    lines.append(pk_label)
    lines.append("")

    # Columns table
    lines.append("| Column | Type | Nullable | Unique | FK | Default |")
    lines.append("|--------|------|----------|--------|----|---------|")
    for col in table.columns:
        nullable = "yes" if col.nullable else "no"
        unique = "yes" if col.unique else ""
        fk = _fk_info(col)
        default = _default_str(col)
        pk_marker = " **PK**" if col.primary_key else ""
        lines.append(
            f"| `{col.name}`{pk_marker} | {_col_type_str(col)} "
            f"| {nullable} | {unique} | {fk} | {default} |"
        )

    # Indexes
    indexes = [idx for idx in table.indexes]
    if indexes:
        lines.append("")
        lines.append("**Indexes:**")
        for idx in indexes:
            cols = ", ".join(f"`{c.name}`" for c in idx.columns)
            unique = " (unique)" if idx.unique else ""
            lines.append(f"- `{idx.name}`: {cols}{unique}")

    # Unique constraints (non-PK, non-single-column-unique already shown)
    uqs = [
        c
        for c in table.constraints
        if c.__class__.__name__ == "UniqueConstraint" and len(c.columns) > 1
    ]
    if uqs:
        lines.append("")
        lines.append("**Unique constraints:**")
        for uq in uqs:
            cols = ", ".join(f"`{c.name}`" for c in uq.columns)
            uq_name = f" (`{uq.name}`)" if uq.name else ""
            lines.append(f"- {cols}{uq_name}")

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------
def generate() -> str:
    metadata = Base.metadata
    all_tables = {t.name: t for t in metadata.sorted_tables}

    # Check for tables not in any domain group
    grouped = {t for _, tables in DOMAIN_ORDER for t in tables}
    ungrouped = set(all_tables.keys()) - grouped
    if ungrouped:
        print(f"WARNING: tables not in any domain group: {ungrouped}")

    lines: list[str] = []

    # Header
    lines.append("# Diggy - Database Schema")
    lines.append("")
    lines.append(
        "> **Auto-generated** from `server/api/models/`. "
        "Do not edit below the MANUAL block — regenerate via `/schema_doc`."
    )
    lines.append(f"> {len(all_tables)} tables across {len(DOMAIN_ORDER)} domains.")
    lines.append("")

    # Placeholder for manual block — will be replaced below
    lines.append("{MANUAL_BLOCK}")
    lines.append("")

    # Table of contents
    lines.append("## Table of contents")
    lines.append("")
    for domain, tables in DOMAIN_ORDER:
        lines.append(f"**{domain}:** " + " · ".join(f"`{t}`" for t in tables))
    if ungrouped:
        lines.append(
            "**Ungrouped:** " + " · ".join(f"`{t}`" for t in sorted(ungrouped))
        )
    lines.append("")

    # Render each domain
    for domain, table_names in DOMAIN_ORDER:
        lines.append(f"## {domain}")
        lines.append("")
        for tname in table_names:
            table = all_tables.get(tname)
            if table is None:
                lines.append(f"### `{tname}` — **TABLE NOT FOUND IN MODELS**\n")
                continue
            lines.extend(_render_table(table))

    # Ungrouped tables
    if ungrouped:
        lines.append("## Ungrouped")
        lines.append("")
        for tname in sorted(ungrouped):
            lines.extend(_render_table(all_tables[tname]))

    return "\n".join(lines)


def main() -> None:
    output_path = REPO_ROOT / "docs" / "database-schema.md"

    # Read existing manual block if present
    manual_block = INITIAL_MANUAL_BLOCK
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        m = re.search(
            rf"{re.escape(MANUAL_BLOCK_MARKER_BEGIN)}.*?{re.escape(MANUAL_BLOCK_MARKER_END)}",
            existing,
            re.DOTALL,
        )
        if m:
            manual_block = m.group(0)

    doc = generate()
    doc = doc.replace("{MANUAL_BLOCK}", manual_block)

    output_path.write_text(doc, encoding="utf-8")
    print(f"Generated {output_path} ({len(doc)} bytes, {doc.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
