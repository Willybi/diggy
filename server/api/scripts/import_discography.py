#!/usr/bin/env python
"""OPS import: write an artist-discography backfill BUNDLE into prod (C14.a Phase 2).

CONTEXT — a LOCAL tool (``worker/discography_backfill/``, run on the operator's
residential IP, outside the server) walks the full Deezer discography of a decided
cohort of artists (C14.a Phase 2: the "library" + "active DJ" tiers), classifies each
track NET-NEW vs our catalog, and fetches the full ``/track/{id}`` hit for the net-new
ones — a mass-Deezer workload FORBIDDEN on the VPS (fair-use, the AV10 lesson). That
local tool ONLY reads; it NEVER writes to the database. The WRITE happens here, on the
server, by REPLAYING the fil-de-l'eau Deezer enrichment funnel VERBATIM
(``workers.db.bulk_get_or_create_catalog`` + ``workers.deezer_enrich.enrich_entry`` +
the artist/album linkers + ``workers.enrichment._mark_searched``), resolving identity
against the LIVE database. It deliberately does NOT re-implement any get-or-create /
matching / merge logic — a re-implementation re-introduces the wrong-platform-id and
artist-identity corruption fixed under X1/X3/X4 (a platform id is NOT a per-recording
identity; a bad merge/link is expensive corruption, invariant #4).

Deezer enrichment (deezer_id, isrc, duration, preview, cover, contributors, album) is
applied here from the bundle hit; BPM/key/genres are LEFT to the VPS Beatport drain —
the rows are stamped a LOW ``enrich_priority`` so that Beatport work NEVER runs ahead
of the TrackID set tracks (C12).

BUNDLE CONTRACT (one JSON object per line = ONE artist, read from stdin or --file):

    {"artist_id": <int>, "deezer_id": <str>, "name": <str>, "tier": <str>,
     "tracks": [ <full Deezer /track hit>, ... ]}

  * each track = the raw ``/track/{id}`` payload the local tool fetched:
    ``{id, title, isrc, duration, preview, artist:{id,name}, contributors:[...],
    album:{id,title,cover_medium,cover_big}}``.
  * ``tracks`` are the artist's NET-NEW tracks only (classified locally); the list may
    be empty (a fully-covered artist — a completed attempt).
  * ``artist_id`` / ``name`` / ``tier`` are for logging + the dry-run sample; identity
    is resolved from the hit's ``contributors`` (the sampled artist among them).

Per artist (idempotent, one transaction per artist in --apply):

  1. ``bulk_get_or_create_catalog`` over ``{title, artist, isrc}`` dicts — dedups
     ISRC→normalized_key against the LIVE DB and creates the missing rows. Because the
     hit carries the ISRC, a track that is net-new BY TITLE but already in base BY ISRC
     (a cosmetic title variant) folds into the existing row here → no duplicate.
  2. For each hit, on its catalog entry:
       - already has a ``deezer_id`` → ``already_deezer`` (never clobber a fresher
         server-side result);
       - else ``enrich_entry`` (may fold the row on a deezer_id collision →
         ``CatalogEntryMerged``) + ``link_catalog_artist_from_hit`` (contributors →
         catalog_artists M2M) + ``link_catalog_album_from_hit`` (C7 album) +
         ``_mark_searched(deezer)`` + a MAX-merged LOW ``enrich_priority``.
     Beatport is NOT touched here (``beatport_searched_at`` left NULL → the VPS drain
     enriches bpm/key/genres later, at this low priority).

FRESHNESS / IDEMPOTENCE: a row already carrying a ``deezer_id`` is left untouched
(``already_deezer``); a re-run therefore re-links nothing and re-stamps nothing (the
get-or-create re-resolves the same rows without creating duplicates). The local tool's
per-artist checkpoint means a normal re-run does not even re-fetch a done artist.

DRY-RUN by default: NOTHING is written — ``ImageService.upload_from_url`` is suppressed
for the whole run (no MinIO / CDN write) and the transaction is rolled back — while the
reused funnel still runs so the counters + a precision SAMPLE (artist → n net-new) are
accurate. Pass ``--apply`` to commit; in --apply the covers ARE fetched from the Deezer
CDN and uploaded (the normal funnel path — a cheap CDN GET, NOT the rate-limited Deezer
API, so it does not breach the "VPS stays off the Deezer API" intent of this pipeline).

>>> ``--apply`` MUTATES rows (creates ``catalog`` + ``catalog_artists`` + ``albums`` +
    ``catalog_albums`` rows, may fold a row on a deezer_id collision). DUMP PROD FIRST
    (encrypted, see docs/restore.md). <<<  A crash mid-run is safe (each artist commits
    independently and the operation is idempotent), but a bad dump is not recoverable.

Prod sequence: deploy this script (push → CI → image) → dry-run and read the counters +
sample → ENCRYPTED DUMP → ``--apply`` (in salvos, driven by the local tool) →
re-dry-run to confirm convergence.

Usage (from the VPS — ships in the image under api/):
    cat bundle.ndjson | docker compose exec -T api python scripts/import_discography.py           # dry-run
    cat bundle.ndjson | docker compose exec -T api python scripts/import_discography.py --apply   # write
    docker compose exec api python scripts/import_discography.py --file /tmp/bundle.ndjson --apply
"""

import argparse
import contextlib
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from services.image_service import ImageService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from utils import make_normalized_key
from workers.catalog_merge import CatalogEntryMerged
from workers.db import bulk_get_or_create_catalog
from workers.deezer_enrich import (
    enrich_entry,
    link_catalog_album_from_hit,
    link_catalog_artist_from_hit,
)
from workers.enrichment import _mark_searched

logger = logging.getLogger("import_discography")

# LOW priority for a discography-backfilled row: strictly below the C12 backfill
# baseline (bulk_get_or_create_catalog folds NULL → 75 at the Beatport gate) and every
# set phase (60-100), so this work NEVER runs ahead of the TrackID set tracks. MAX-merged
# so a row ALSO reached by a set keeps its higher set priority.
# NB: a non-default ENRICH_PRIORITY_FLOOR > this value set on the VPS EXCLUDES these rows
# from the Beatport Tier-1 drain while active (they are never_tried, not a 30/90d retry) —
# keep that floor at/below this value (or unset) until the backfill has drained.
DISCOGRAPHY_PRIORITY = int(os.environ.get("DISCOGRAPHY_ENRICH_PRIORITY", "10"))

_SAMPLE_SIZE = 40

_STAT_KEYS = (
    "total",
    "malformed",
    "errors",
    "artists",
    "artists_no_new",
    "tracks_seen",
    "created_or_linked",
    "deezer_applied",
    "already_deezer",
    "merged",
    "missing",
)

_MALFORMED = object()

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py + import_set_artists_matches: strip +asyncpg)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


@contextlib.contextmanager
def _suppress_url_uploads():
    """Neutralise ``ImageService.upload_from_url`` (no CDN/MinIO write) for a dry-run.

    ``enrich_entry`` and ``link_catalog_album_from_hit`` fetch covers from the Deezer
    CDN and upload them to MinIO via ``upload_from_url``. In dry-run that would be an
    external WRITE even though the DB transaction is rolled back, so it is swapped for a
    no-op returning False (its "upload failed" contract → callers leave ``has_artwork``
    untouched). Only used around the dry-run path; --apply keeps the real upload (a cheap
    CDN GET, not the rate-limited Deezer API). Captures the classmethod descriptor from
    ``__dict__`` so the restore puts back the exact descriptor (mirrors import_trackid_clean).
    """
    original = ImageService.__dict__["upload_from_url"]
    ImageService.upload_from_url = staticmethod(lambda *a, **k: False)
    try:
        yield
    finally:
        ImageService.upload_from_url = original


def _merge_priority(existing, new):
    """MAX-merge a new enrich priority onto a possibly-NULL existing one (mirror C12)."""
    return new if existing is None else max(existing, new)


def _read_ndjson(stream):
    """Yield one parsed JSON object per non-blank line, or ``_MALFORMED`` on bad JSON."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            yield _MALFORMED


def _validate(record):
    """Return ``(artist_id, name, tier, tracks)`` for a valid record, else None.

    Contract: a dict with an int ``artist_id`` (not bool) and a list ``tracks``. Each
    track is validated lazily in :func:`_track_dicts` (a non-dict / id-less hit is
    skipped). ``name``/``tier`` are optional (logging + sample).
    """
    if record is _MALFORMED or not isinstance(record, dict):
        return None
    artist_id = record.get("artist_id")
    if not isinstance(artist_id, int) or isinstance(artist_id, bool):
        return None
    tracks = record.get("tracks")
    if not isinstance(tracks, list):
        return None
    return artist_id, record.get("name") or "", record.get("tier") or "", tracks


def _hit_artist_name(hit):
    """The primary artist name of a Deezer track hit (top-level ``artist.name``).

    Mirrors ``source_clients.fetch_deezer_tracks`` — the single lead artist feeds the
    ingestion identity key, NOT a contributor join.
    """
    art = hit.get("artist")
    return (art or {}).get("name") if isinstance(art, dict) else None


def _valid_hits(tracks):
    """The well-formed track hits (dict with an ``id`` and a ``title``)."""
    out = []
    for h in tracks:
        if isinstance(h, dict) and h.get("id") is not None and h.get("title"):
            out.append(h)
    return out


def _import_artist(session, hits, stats):
    """Get-or-create + enrich one artist's net-new track hits. Returns the # linked.

    Reuses the funnel VERBATIM: ``bulk_get_or_create_catalog`` (ISRC→normalized_key
    dedup against the LIVE DB — the hit's ISRC folds a cosmetic title variant into the
    existing row) then per-hit ``enrich_entry`` + artist/album linkers +
    ``_mark_searched(deezer)`` + a LOW MAX-merged ``enrich_priority``. A row that already
    carries a ``deezer_id`` is left untouched (``already_deezer``). Never commits.
    """
    now = datetime.now(timezone.utc)
    track_dicts = [
        {"title": h["title"], "artist": _hit_artist_name(h), "isrc": h.get("isrc")}
        for h in hits
    ]
    if not track_dicts:
        return 0
    catalog_map = bulk_get_or_create_catalog(session, track_dicts)

    new_links = 0
    for h in hits:
        stats["tracks_seen"] += 1
        entry = catalog_map.get(make_normalized_key(h["title"], _hit_artist_name(h)))
        if entry is None:
            stats["missing"] += 1
            continue
        if entry.deezer_id:
            stats["already_deezer"] += 1
            continue
        try:
            enrich_entry(entry, h, s3=None, _known_isrcs=None, session=session)
        except CatalogEntryMerged:
            stats["merged"] += 1
            continue
        try:
            link_catalog_artist_from_hit(session, entry.id, h)
            link_catalog_album_from_hit(session, entry.id, h)
        except Exception:  # noqa: BLE001 — best-effort links (mirrors import_trackid_clean)
            logger.warning(
                "artist/album link failed for catalog %s", entry.id, exc_info=True
            )
        _mark_searched(entry, "deezer", now)
        entry.enrich_priority = _merge_priority(entry.enrich_priority, DISCOGRAPHY_PRIORITY)
        stats["deezer_applied"] += 1
        stats["created_or_linked"] += 1
        new_links += 1
    session.flush()
    return new_links


def import_discography(session, records, *, apply=False):
    """Import an iterable of NDJSON ``records`` (parsed dicts / ``_MALFORMED``).

    The single testable core. In --apply it commits per artist (crash-resumable,
    idempotent); in dry-run it commits NOTHING (the caller rolls back) while running the
    funnel so counts + sample are accurate. Returns ``(stats, sample)`` where ``sample``
    is a list of ``(artist_name, n_new_tracks)`` for human precision review.
    """
    stats = {k: 0 for k in _STAT_KEYS}
    sample = []

    for record in records:
        stats["total"] += 1
        parsed = _validate(record)
        if parsed is None:
            stats["malformed"] += 1
            continue
        artist_id, name, _tier, tracks = parsed
        hits = _valid_hits(tracks)
        try:
            new_links = _import_artist(session, hits, stats)
        except Exception:  # noqa: BLE001 — one bad artist must not abort the run
            stats["errors"] += 1
            session.rollback()
            continue
        stats["artists"] += 1
        if new_links == 0:
            stats["artists_no_new"] += 1
        elif len(sample) < _SAMPLE_SIZE:
            sample.append((name or str(artist_id), new_links))
        if apply:
            session.commit()

    return stats, sample


def _print_sample(sample):
    if not sample:
        print("\n(no net-new tracks would be created — nothing to review)")
        return
    print(f"\nSample of artists that would gain tracks (first {len(sample)}) — REVIEW:")
    for name, n in sample:
        shown = (name[:60] + "…") if len(name) > 60 else name
        print(f"    {shown!r}  →  +{n} net-new track(s)")


def _print_report(stats, apply):
    verb = "imported" if apply else "would import"
    print(f"\nRead {stats['total']} artist bundle(s); {verb}:")
    print(f"    artists              : {stats['artists']}")
    print(f"    artists_no_new       : {stats['artists_no_new']}  (fully covered already)")
    print(f"    tracks_seen          : {stats['tracks_seen']}")
    print(f"    created_or_linked    : {stats['created_or_linked']}  (net-new catalog rows enriched)")
    print(f"    deezer_applied       : {stats['deezer_applied']}")
    print(f"    already_deezer       : {stats['already_deezer']}  (row already linked, left as is)")
    print(f"    merged               : {stats['merged']}  (folded into a canonical row)")
    print(f"    missing              : {stats['missing']}  (hit had no catalog entry)")
    print(f"    malformed            : {stats['malformed']}  (bad line, skipped)")
    print(f"    errors               : {stats['errors']}  (artist aborted, rolled back)")


def main(apply, file_path=None):
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set")
    engine = _get_engine()

    def _run(session):
        if file_path:
            with open(file_path, "r", encoding="utf-8") as fh:
                return import_discography(session, _read_ndjson(fh), apply=apply)
        return import_discography(session, _read_ndjson(sys.stdin), apply=apply)

    try:
        with Session(engine) as session:
            if not apply:
                print("=== DRY-RUN — nothing will be written (use --apply) ===")
                with _suppress_url_uploads():
                    stats, sample = _run(session)
                session.rollback()
            else:
                print("=== APPLY — importing the discography backfill ===")
                stats, sample = _run(session)

            _print_report(stats, apply)
            if not apply:
                _print_sample(sample)
                print(
                    "\nDry-run only. The reused funnel ran to compute the counts + "
                    "sample, then the transaction was rolled back — NO write of any kind "
                    "(DB / MinIO / CDN). REVIEW THE SAMPLE; re-run with --apply to write "
                    "— DUMP PROD FIRST (docs/restore.md)."
                )
            else:
                print(
                    "\nDone. Idempotent: a re-run counts the linked rows as already_deezer "
                    "(nothing re-created). Beatport (bpm/key/genres) drains later on the "
                    f"VPS at enrich_priority {DISCOGRAPHY_PRIORITY} (behind set tracks)."
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Write an artist-discography backfill bundle (NDJSON) into prod by "
        "replaying the Deezer enrichment funnel verbatim against the live DB. Reads "
        "stdin or --file. Dry-run by default (prints a precision sample); --apply to "
        "commit (DUMP PROD FIRST)."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually write (default: dry-run, rolled back)",
    )
    parser.add_argument(
        "--file", dest="file_path", default=None,
        help="read the NDJSON bundle from this path instead of stdin",
    )
    args = parser.parse_args()
    main(apply=args.apply, file_path=args.file_path)
