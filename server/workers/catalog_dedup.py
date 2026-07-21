"""Collision guard for the enrichment write points (X1/L2 prevention).

``catalog`` dedups ingestion on ``normalized_key``/``isrc`` but never on the
platform ids — those are stamped by enrichment AFTER the row exists. So the same
Deezer/Beatport track can end up on two catalog rows. This helper is called by
every enrichment function right BEFORE it assigns a ``deezer_id``/``beatport_id``:
if another row already carries that id, the two rows are duplicates, so the
current (freshly-selected) row is folded into the pre-existing canonical one and
:class:`CatalogEntryMerged` is raised for the caller to stop touching it.

It builds on the L1 primitive; it never modifies it.
"""

from sqlalchemy import select
from workers.catalog_merge import CatalogEntryMerged, merge_catalog_entries


def fold_if_platform_id_taken(session, entry, field: str, value: str) -> None:
    """Fold ``entry`` into any pre-existing row already holding ``value``.

    Queries for a catalog row (``id != entry.id``) whose ``field`` already equals
    ``value``. If one exists, ``entry`` (the loser) is merged into it (the
    canonical) via :func:`merge_catalog_entries` and :class:`CatalogEntryMerged`
    is raised. No-op when there is no collision.

    FIXED rule: the pre-existing row is ALWAYS the canonical — it is already
    connected, so keeping it is the safe choice. This is deliberately NOT
    ``pick_canonical`` (that heuristic is reserved for the L3 cleanup script).
    """
    from models import CatalogEntry

    existing_id = session.execute(
        select(CatalogEntry.id)
        .where(getattr(CatalogEntry, field) == value, CatalogEntry.id != entry.id)
        .order_by(CatalogEntry.id.asc())
        .limit(1)
    ).scalar()
    if existing_id is None:
        return

    merge_catalog_entries(session, canonical_id=existing_id, loser_id=entry.id)
    raise CatalogEntryMerged(existing_id)
