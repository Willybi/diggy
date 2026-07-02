"""Direct DB access for worker tasks — replaces HTTP self-calls.

Provides:
  - Sync engine/session factory (centralized)
  - bulk_get_or_create_catalog: batch catalog dedup + insert
  - bulk_insert_radar_tracks: batch radar track insertion with dedup
"""

import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

sys.path.insert(0, "/app")
from models import CatalogEntry, RadarTrack
from utils import make_normalized_key

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    return _engine


def get_session() -> Session:
    return Session(get_engine())


def bulk_get_or_create_catalog(
    session: Session,
    tracks: list[dict],
) -> dict[str, CatalogEntry]:
    """Batch lookup/create catalog entries for a list of tracks.

    Each track dict should have: title, artist, isrc (optional), duration_ms (optional).
    Returns a dict mapping normalized_key -> CatalogEntry.
    """
    if not tracks:
        return {}

    # Compute normalized keys and collect ISRCs
    for t in tracks:
        t["_norm_key"] = make_normalized_key(t["title"], t.get("artist"))

    isrcs = [t["isrc"] for t in tracks if t.get("isrc")]
    norm_keys = [t["_norm_key"] for t in tracks]

    # Batch lookup by ISRC
    isrc_map: dict[str, CatalogEntry] = {}
    if isrcs:
        existing = (
            session.execute(select(CatalogEntry).where(CatalogEntry.isrc.in_(isrcs)))
            .scalars()
            .all()
        )
        isrc_map = {e.isrc: e for e in existing}

    # Batch lookup by normalized_key
    norm_map: dict[str, CatalogEntry] = {}
    existing = (
        session.execute(
            select(CatalogEntry).where(CatalogEntry.normalized_key.in_(norm_keys))
        )
        .scalars()
        .all()
    )
    norm_map = {e.normalized_key: e for e in existing}

    # Resolve each track: ISRC first, then norm_key, then create
    result: dict[str, CatalogEntry] = {}
    seen_isrcs = set(isrc_map.keys())
    seen_norms = set(norm_map.keys())
    to_insert = []

    for t in tracks:
        nk = t["_norm_key"]
        isrc = t.get("isrc")

        # 1. Try ISRC match
        if isrc and isrc in isrc_map:
            result[nk] = isrc_map[isrc]
            continue

        # 2. Try normalized_key match
        if nk in norm_map:
            entry = norm_map[nk]
            # Update ISRC if we have one and entry doesn't
            if isrc and not entry.isrc and isrc not in seen_isrcs:
                entry.isrc = isrc
                seen_isrcs.add(isrc)
            result[nk] = entry
            continue

        # 3. Already queued in this batch
        if nk in seen_norms:
            continue

        # 4. Queue for insert
        to_insert.append(
            {
                "title": t["title"],
                "artist": t.get("artist"),
                "normalized_key": nk,
                "isrc": isrc if (isrc and isrc not in seen_isrcs) else None,
                "duration_ms": t.get("duration_ms"),
                "created_at": datetime.now(timezone.utc),
            }
        )
        if isrc:
            seen_isrcs.add(isrc)
        seen_norms.add(nk)

    # Bulk insert with ON CONFLICT DO NOTHING — safe against concurrent workers
    if to_insert:
        stmt = (
            pg_insert(CatalogEntry)
            .values(to_insert)
            .on_conflict_do_nothing(index_elements=["normalized_key"])
        )
        session.execute(stmt)
        session.flush()

        # Re-fetch all newly inserted + conflict-skipped rows
        new_nks = [row["normalized_key"] for row in to_insert]
        fetched = (
            session.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key.in_(new_nks))
            )
            .scalars()
            .all()
        )
        for entry in fetched:
            result[entry.normalized_key] = entry

    return result


def bulk_insert_radar_tracks(
    session: Session,
    entity_id: int,
    source: str,
    source_tracks: list,
    catalog_map: dict[str, CatalogEntry],
    is_initial_crawl: bool = False,
) -> dict:
    """Bulk insert RadarTrack rows with dedup + diff lifecycle.

    source_tracks: list of SourceTrack dataclass instances.
    catalog_map: dict from bulk_get_or_create_catalog (norm_key -> entry).
    Returns dict with 'inserted' and 'removed' counts.
    """
    if not source_tracks:
        return {"inserted": 0, "removed": 0}

    # Load existing external_track_ids for this entity
    existing_ext_ids = {
        r[0]
        for r in session.execute(
            select(RadarTrack.external_track_id).where(
                RadarTrack.watched_entity_id == entity_id
            )
        ).all()
    }

    now = datetime.now(timezone.utc)
    to_insert = []

    for st in source_tracks:
        if st.external_id in existing_ext_ids:
            continue

        nk = make_normalized_key(st.title, st.artist)
        entry = catalog_map.get(nk)

        to_insert.append(
            {
                "watched_entity_id": entity_id,
                "external_track_id": st.external_id,
                "source": source,
                "title": st.title,
                "artist": st.artist,
                "isrc": st.isrc,
                "detected_at": now,
                "catalog_id": entry.id if entry else None,
                "is_initial_detection": is_initial_crawl,
            }
        )
        existing_ext_ids.add(st.external_id)

    inserted = 0
    if to_insert:
        stmt = (
            pg_insert(RadarTrack)
            .values(to_insert)
            .on_conflict_do_nothing(constraint="uq_radar_playlist_track")
        )
        result = session.execute(stmt)
        session.flush()
        inserted = result.rowcount

    # Diff: mark removed tracks, clear re-appeared tracks
    crawled_ext_ids = {st.external_id for st in source_tracks}

    # Mark absent tracks as removed (only if not already marked)
    removed = session.execute(
        update(RadarTrack)
        .where(
            RadarTrack.watched_entity_id == entity_id,
            RadarTrack.external_track_id.notin_(crawled_ext_ids),
            RadarTrack.removed_at.is_(None),
        )
        .values(removed_at=now)
    ).rowcount

    # Clear removed_at for re-appeared tracks
    session.execute(
        update(RadarTrack)
        .where(
            RadarTrack.watched_entity_id == entity_id,
            RadarTrack.external_track_id.in_(crawled_ext_ids),
            RadarTrack.removed_at.isnot(None),
        )
        .values(removed_at=None)
    )

    session.flush()
    return {"inserted": inserted, "removed": removed}
