#!/usr/bin/env python
"""One-shot OPS cleanup: delete non-artist PLACEHOLDER rows ("Various Artists"…).

"Various Artists", "Unknown Artist", "V/A" and friends are not real artists — they
are compilation/unknown placeholders that nonetheless became ``artists`` rows linked
to hundreds of unrelated tracks (measured: "Various Artists" alone → 325
``catalog_artists`` links). As graph nodes they are FALSE co-occurrence hubs that
skew artist-based similarity / reco. This deletes them.

DETECTION is the shared ``workers.artist_names.is_placeholder_artist`` — an EXACT
normalized match against a tight whitelist, NEVER a substring (real artists
"Unknown Mortal Orchestra", "Origin Unknown", "Unknown T" must survive). A broad SQL
prefilter narrows the scan; the pure predicate makes the final call.

Deleting a placeholder row CASCADES its ``catalog_artists`` / ``set_artists`` /
``artist_aliases`` links away (all three FKs are ON DELETE CASCADE) — exactly the
desired un-link. The tracks keep their flat ``catalog.artist`` string for display;
only the derived M2M graph node is removed. A MinIO artwork (rare — only a mislinked
placeholder like "Various" has one) is deleted best-effort after the commit.

>>> DESTRUCTIVE (deletes artist rows + their links). DUMP PROD FIRST. <<<
DRY-RUN by default (prints the matched names + link counts, writes nothing). Pass
--apply to act. Idempotent — a re-run finds nothing.

Usage (from the VPS):
    docker compose exec api python scripts/cleanup_placeholder_artists.py           # dry-run
    docker compose exec api python scripts/cleanup_placeholder_artists.py --apply    # delete
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers/services

from models import Artist, CatalogArtist, SetArtist
from sqlalchemy import create_engine, delete, func, or_, select
from sqlalchemy.orm import Session
from workers.artist_names import is_placeholder_artist

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def select_placeholders(session):
    """Broad SQL prefilter → exact confirmation by is_placeholder_artist. Returns
    ``[(id, name, has_artwork), ...]``."""
    low = func.lower(Artist.name)
    candidates = session.execute(
        select(Artist.id, Artist.name, Artist.has_artwork).where(
            or_(
                low.like("various%"),
                low.like("unknown%"),
                low.in_(["va", "v/a", "v.a", "v.a.", "n/a", "no artist", "compilation", "artist unknown"]),
            )
        )
    ).all()
    return [(i, n, art) for (i, n, art) in candidates if is_placeholder_artist(n)]


def _delete_artwork(keys):
    if not keys:
        return 0
    from services.image_service import BUCKET_ARTIST, ImageService

    s3 = ImageService._get_s3()
    n = 0
    for key in keys:
        try:
            s3.delete_object(Bucket=BUCKET_ARTIST, Key=key)
            n += 1
        except Exception as exc:  # noqa: BLE001 — storage cleanup is best-effort
            print(f"  ! artwork delete failed for {key}: {exc}", file=sys.stderr)
    return n


def run(apply=False, keep_artwork=False):
    engine = _get_engine()
    with Session(engine) as session:
        rows = select_placeholders(session)
        ids = [r[0] for r in rows]
        cat_links = set_links = 0
        if ids:
            cat_links = session.execute(
                select(func.count()).select_from(CatalogArtist).where(CatalogArtist.artist_id.in_(ids))
            ).scalar() or 0
            set_links = session.execute(
                select(func.count()).select_from(SetArtist).where(SetArtist.artist_id.in_(ids))
            ).scalar() or 0

        print(f"\n=== cleanup_placeholder_artists ({'APPLY' if apply else 'DRY-RUN'}) ===")
        print(f"placeholder artists matched: {len(rows)}")
        print(f"catalog_artists links (will CASCADE): {cat_links}")
        print(f"set_artists links (will CASCADE): {set_links}")
        for _id, name, _art in sorted(rows, key=lambda r: r[1].lower()):
            print(f"  {_id} · {name!r}")

        artwork_deleted = 0
        if apply and ids:
            session.execute(delete(Artist).where(Artist.id.in_(ids)))
            session.commit()
            if not keep_artwork:
                artwork_deleted = _delete_artwork([f"{r[0]}.jpg" for r in rows if r[2]])
            print(f"DELETED {len(ids)} artist rows (+ cascaded links).")
            if not keep_artwork:
                print(f"MinIO artworks deleted: {artwork_deleted}")
    return {"deleted": len(ids) if apply else 0, "matched": len(rows), "cat_links": cat_links}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    parser.add_argument("--keep-artwork", action="store_true", help="Do NOT delete MinIO artworks")
    args = parser.parse_args()
    run(apply=args.apply, keep_artwork=args.keep_artwork)


if __name__ == "__main__":
    main()
