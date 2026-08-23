#!/usr/bin/env python
"""One-shot OPS cleanup: delete fully-orphaned ARTIST rows (referenced by nothing).

The pipeline (multi-artist splits, merges, set re-imports that drop then re-create
``set_artists`` links) accumulates ``artists`` rows that end up pointed at by NOTHING.
They never surface in the app (the admin "no deezer_id" panel already excludes
unattached rows, C-lot) — they are pure clutter. This deletes them.

DELETABLE = an artist referenced by NONE of the six tables that FK ``artists.id``:
``catalog_artists``, ``set_artists``, ``followed_artists``, ``artist_activity`` and
``albums.artist_id`` — plus ``artist_aliases``, which is deliberately NOT a keep-
reason (an alias of a nobody is itself dead) and CASCADE-deletes with the row. A row
that is followed, has an activity-feed entry, or backs an album is KEPT (deleting it
would silently CASCADE those away / null an album's artist). Measured 2026-08-23: of
~10.7k unattached rows, ZERO were followed / in activity / album-linked, so the
attachment predicate and this stricter one coincided — but the guard stays, cheap
and correct, in case that changes.

Both un-linked orphans (``deezer_id`` NULL) and Deezer-LINKED orphans (a real
``deezer_id`` + often an ``artist-artworks/{id}.jpg`` in MinIO) qualify: nothing
references either, so both are dead weight. For a linked orphan with ``has_artwork``
the script also deletes the MinIO object (best-effort, AFTER the DB commit — a
storage hiccup never rolls back the delete; a leftover file is harmless and a re-run
won't re-find the row). ``--keep-artwork`` skips the MinIO side entirely.

NOTE (accepted residual): a deleted artist id can still linger inside the JSON of an
``artist_flags`` / ``set_flags`` row (``resolved_artist_ids`` etc.) — those are NOT
foreign keys (admin review artefacts, resolved by hand), so a dangling id there is
cosmetic and out of scope.

>>> DESTRUCTIVE (deletes artist rows + MinIO objects). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump (docs/restore.md) BEFORE running with --apply. A crash
mid-run is safe (batches are committed; the operation is idempotent — a re-run finds
the still-orphaned rows), but a bad dump is not recoverable.

DRY-RUN by default and READ-ONLY: prints how many rows WOULD be deleted (split
null / linked, and how many carry artwork) plus a few examples, WITHOUT writing.
Pass --apply to act.

Usage (from the VPS):
    docker compose exec api python scripts/cleanup_orphan_artists.py            # dry-run
    docker compose exec api python scripts/cleanup_orphan_artists.py --apply    # delete
    docker compose exec api python scripts/cleanup_orphan_artists.py --apply --keep-artwork
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers/services

from models import (
    Album,
    Artist,
    ArtistActivity,
    CatalogArtist,
    FollowedArtist,
    SetArtist,
)
from sqlalchemy import and_, create_engine, delete, exists, not_, select
from sqlalchemy.orm import Session

_NOT_FOUND = "NOT_FOUND"
_COMMIT_EVERY = 500  # rows per committed transaction in --apply (sibling-script batching)
_MAX_EXAMPLES = 10

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def orphan_predicate():
    """SQLAlchemy predicate: an ``Artist`` referenced by NONE of the six FK tables.

    ``artist_aliases`` is intentionally absent — an alias is not a keep-reason and
    CASCADE-deletes with the row.
    """
    return and_(
        not_(exists().where(CatalogArtist.artist_id == Artist.id)),
        not_(exists().where(SetArtist.artist_id == Artist.id)),
        not_(exists().where(FollowedArtist.artist_id == Artist.id)),
        not_(exists().where(ArtistActivity.artist_id == Artist.id)),
        not_(exists().where(Album.artist_id == Artist.id)),
    )


def select_orphan_batch(session, after_id, limit):
    """Keyset page of orphan rows with id > ``after_id`` (ascending), as tuples
    ``(id, name, deezer_id, has_artwork)``."""
    rows = session.execute(
        select(Artist.id, Artist.name, Artist.deezer_id, Artist.has_artwork)
        .where(orphan_predicate(), Artist.id > after_id)
        .order_by(Artist.id.asc())
        .limit(limit)
    ).all()
    return [tuple(r) for r in rows]


def _delete_artwork(keys):
    """Best-effort MinIO delete of ``artist-artworks/<key>`` objects. Never raises."""
    if not keys:
        return 0
    from services.image_service import BUCKET_ARTIST, ImageService

    s3 = ImageService._get_s3()
    deleted = 0
    for key in keys:
        try:
            s3.delete_object(Bucket=BUCKET_ARTIST, Key=key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001 — storage cleanup is best-effort
            print(f"  ! artwork delete failed for {key}: {exc}", file=sys.stderr)
    return deleted


def run(apply=False, keep_artwork=False, limit=None):
    engine = _get_engine()
    scanned = deleted = artwork_deleted = 0
    n_null = n_linked = n_artwork = 0
    examples = []
    after_id = 0

    with Session(engine) as session:
        while True:
            page = min(_COMMIT_EVERY, limit - scanned) if limit else _COMMIT_EVERY
            if page <= 0:
                break
            batch = select_orphan_batch(session, after_id, page)
            if not batch:
                break
            after_id = batch[-1][0]
            scanned += len(batch)

            for _id, name, dz, has_art in batch:
                if dz and dz != _NOT_FOUND:
                    n_linked += 1
                elif dz is None:
                    n_null += 1
                if has_art:
                    n_artwork += 1
                if len(examples) < _MAX_EXAMPLES:
                    tag = "linked" if (dz and dz != _NOT_FOUND) else ("NOT_FOUND" if dz else "null")
                    examples.append(f"{_id} · {name!r} [{tag}{', art' if has_art else ''}]")

            if apply:
                ids = [r[0] for r in batch]
                art_keys = [f"{r[0]}.jpg" for r in batch if r[3]]  # has_artwork
                # DELETE the rows first; artist_aliases CASCADE at the DB level.
                session.execute(delete(Artist).where(Artist.id.in_(ids)))
                session.commit()
                deleted += len(ids)
                if not keep_artwork:
                    artwork_deleted += _delete_artwork(art_keys)

    verb = "DELETED" if apply else "WOULD DELETE"
    print(f"\n=== cleanup_orphan_artists ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"{verb}: {scanned}  (null={n_null}, linked={n_linked}, with_artwork={n_artwork})")
    if apply:
        print(f"artist rows deleted: {deleted}")
        if not keep_artwork:
            print(f"MinIO artworks deleted: {artwork_deleted}")
        else:
            print("MinIO artworks: skipped (--keep-artwork)")
    print("examples:")
    for e in examples:
        print(f"  {e}")
    return {"scanned": scanned, "deleted": deleted, "artwork_deleted": artwork_deleted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    parser.add_argument(
        "--keep-artwork", action="store_true", help="Do NOT delete MinIO artist artworks"
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap rows scanned (for a bounded run)")
    args = parser.parse_args()
    run(apply=args.apply, keep_artwork=args.keep_artwork, limit=args.limit)


if __name__ == "__main__":
    main()
