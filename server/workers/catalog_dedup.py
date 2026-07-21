"""Collision guard for the enrichment write points (X1/L2 prevention).

``catalog`` dedups ingestion on ``normalized_key``/``isrc`` but never on the
platform ids — those are stamped by enrichment AFTER the row exists. So the same
Deezer/Beatport track can end up on two catalog rows. This helper is called by
every enrichment function right BEFORE it assigns a ``deezer_id``/``beatport_id``.

Sharing a platform id is NOT sufficient to merge, though: Deezer returns hits[0]
unchecked (a remix inherits the original's deezer_id) and the Beatport release
fallback stamps one beatport_id on every track of an EP — measured on prod, 77%
of deezer id-groups and 94% of beatport id-groups are DISTINCT recordings.
Merging on the id alone would destroy those versions (project invariant #4).
So this guard folds ONLY when :func:`same_track` confirms the pre-existing row
is the same recording; otherwise it does nothing and the caller stamps the id,
harmlessly duplicating it (id-uniqueness on catalog is deliberately abandoned).

It builds on the L1 primitive; it never modifies it.
"""

from sqlalchemy import select
from workers.catalog_merge import (
    CatalogEntryMerged,
    merge_catalog_entries,
    same_track,
)


def fold_if_platform_id_taken(session, entry, field: str, value: str) -> None:
    """Fold ``entry`` into a pre-existing row that is the SAME recording.

    Queries the catalog rows (``id != entry.id``) whose ``field`` already equals
    ``value``. Among them, the first row that :func:`same_track` confirms to be
    the same recording as ``entry`` becomes the canonical: ``entry`` (the loser)
    is folded into it via :func:`merge_catalog_entries` and
    :class:`CatalogEntryMerged` is raised so the caller stops touching the now
    deleted row.

    If NO holder is the same recording (a remix/EP track merely sharing the id),
    this returns normally WITHOUT merging or raising — the caller then stamps the
    id, letting the two distinct rows coexist under one platform id. That is the
    safe outcome: id-uniqueness is abandoned precisely because the id is not a
    per-recording identity.

    FIXED rule: the pre-existing row is ALWAYS the canonical — it is already
    connected, so keeping it is the safe choice. This is deliberately NOT
    ``pick_canonical`` (that heuristic is reserved for the L3 cleanup script).
    """
    from models import CatalogEntry

    holders = (
        session.execute(
            select(CatalogEntry)
            .where(getattr(CatalogEntry, field) == value, CatalogEntry.id != entry.id)
            .order_by(CatalogEntry.id.asc())
        )
        .scalars()
        .all()
    )

    for holder in holders:
        if same_track(entry, holder):
            merge_catalog_entries(session, canonical_id=holder.id, loser_id=entry.id)
            raise CatalogEntryMerged(holder.id)
    # No holder is confidently the same recording — leave both rows apart.
