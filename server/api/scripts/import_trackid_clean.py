#!/usr/bin/env python
"""OPS import: ingest a pre-computed enrichment BUNDLE into prod (clean-import).

CONTEXT — a LOCAL pipeline (run outside the server) computes the ENTIRE
enrichment of a batch of TrackID.net sets — the TrackID detail, the Deezer hit,
the Beatport match, the estimated BPM and the audio embedding — and emits a
"bundle" as NDJSON (one JSON object per set). This script runs on the VPS and
INGESTS that bundle by REPLAYING the real import/enrichment funnel VERBATIM,
resolving identity against the LIVE database. It does ZERO network I/O: every
enrichment value (and every artwork) comes from the bundle, never from a fetch.

It deliberately does NOT re-implement any mapping or matching logic — it IMPORTS
and calls the funnel functions (``trackid.importer.import_audiostream``,
``workers.db.bulk_get_or_create_catalog``, ``workers.deezer_enrich.enrich_entry``
+ artist/album linkers, ``beatport.enrich.enrich_from_beatport``,
``workers.enrichment._mark_searched``). A re-implementation would re-introduce the
wrong-platform-id corruption fixed under X1/X3/X4 (a platform id is NOT a
per-recording identity; a bad merge is expensive corruption, invariant #4).

BUNDLE CONTRACT (one JSON object per line, read from stdin by default or --file):

    {
      "trackid_id": <int>, "slug": <str>, "score": <float|null>,
      "set_artwork_b64": <str|null>,      # base64 of the TrackID set cover bytes
      "detail": { <raw TrackID detail payload, as fetched> },
      "tracks": [
        {"position": <int>, "raw_title": <str>, "raw_artist": <str>,
         "is_id": <bool>, "musicTrackId": <int|null>, ...,
         "deezer":   {"track": <dict /track/{id}>, "cover_catalog_b64": <str|null>,
                      "cover_album_b64": <str|null>} | null,
         "beatport": {"bp_track": <dict, enrich_from_beatport shape>} | null,
         "bpm":      {"value": <float>, "conf": <float>} | null,
         "key":      <str|null>,            # Camelot, beatport provenance
         "embedding": [<1280 float32>] | null}
      ]
    }

  * ``detail`` is consumed by ``import_audiostream(prefetched_detail=...)`` — it is
    passed as BOTH the ``audiostream`` positional (for its ``id``/``slug``) AND the
    ``prefetched_detail`` so the TrackID client is NEVER used for the network.
  * Every enrichment field is OPTIONAL: a track can be deezer-only, or fully
    un-enriched (fallback = a bare catalog row, to be enriched by the VPS later).
  * ``is_id`` tracks are skipped (no catalog row).

PER SET, inside ONE transaction (async session; the sync funnel runs through
``AsyncSession.run_sync`` so import + resolution + enrichment share the SAME
connection and commit atomically):

  1. ``import_audiostream(prefetched_detail=detail, min_age_hours=0)`` — create /
     refresh ``sets`` + ``set_tracks`` (catalog_id NULL), the ``unreliable`` flag,
     the ``match_set`` dedup. The TrackID client is short-circuited: a BARE
     ``TrackIDClient()`` (never entered as a context manager → no httpx client) is
     passed, and because ``prefetched_detail`` is truthy, ``get_set_detail`` is
     never called — only the PURE ``client.merge_tracklist(detail)`` runs.
  2. ``bulk_get_or_create_catalog`` — dedup ISRC→normalized_key against the LIVE
     DB and create the missing rows; link every ``set_tracks.catalog_id``.
  3. Apply each bundle track's enrichment WITHOUT network, reusing the funnel:
       - Deezer: ``enrich_entry(session=…)`` (folds a deezer_id collision via
         ``merge_catalog_entries`` → ``CatalogEntryMerged``) + the artist/album
         linkers + ``_mark_searched(deezer)``. The ONLY adaptation: the cover is
         uploaded from the bundle BYTES (``cover_catalog_b64``/``cover_album_b64`` →
         ``ImageService.upload_bytes``) instead of the funnel's network
         ``upload_from_url`` — that method is globally suppressed for the whole run
         (see ``_suppress_url_uploads``) so NO Deezer/Beatport/TrackID CDN fetch can
         happen, and the bytes are uploaded here afterwards. The SET cover is
         handled the same way, from the top-level ``set_artwork_b64`` bytes (see
         ``_upload_set_artwork``) — otherwise a hydrated set (never re-crawled)
         would stay coverless. Only the Beatport cover is NOT carried by the bundle
         (redundant with the Deezer catalog cover) and is thus not uploaded here.
       - Beatport: ``enrich_from_beatport(session=…)`` + ``_mark_searched(beatport)``
         (mirrors ``import_beatport_matches.py``).
       - BPM: if present and ``entry.bpm IS NULL`` → set ``bpm`` / ``bpm_source
         ='analysis'`` (lower authority, never over a beatport/rekordbox value). The
         key is already set by Beatport — NO 'analysis' key is written.
       - Embedding: insert into ``track_embeddings`` (model constants from
         ``models.embedding``), skip if the ``(catalog_id, model, version)`` row
         already exists (portable ON CONFLICT DO NOTHING).
       - ``enrich_priority``: MAX-merge from ``bundle["score"]`` (``round(score)``,
         or ``FLUX_PRIORITY`` when null), mirroring ``workers.tasks.sets``.
  4. Flip ``trackid_index.hydration_state='hydrated'`` + link ``set_id`` for this
     ``trackid_id`` (idempotent, mirrors ``import_trackid_index.seed_hydration``).

FRESHNESS / IDEMPOTENCE: a row already carrying a ``deezer_id`` / ``beatport_id``
is left untouched for that source (counted ``already_*`` — never clobber a fresher
server-side result), the BPM is only set where NULL, the embedding only inserted
when absent, the hydration flip is a no-op once hydrated. A re-run therefore
counts everything ``already_*`` and re-stamps nothing (the sets themselves are
re-imported cleanly — ``import_audiostream`` deletes+re-inserts ``set_tracks`` on
every pass, and the catalog dedup re-links them without creating duplicates).

DRY-RUN by default: NOTHING is written externally — the DB transaction is rolled
back per set AND no ``upload_bytes``/``ensure_bucket`` MinIO call is made (the
network ``upload_from_url`` is suppressed regardless) — while the reused funnel
still runs so the counters are accurate. Pass ``--apply`` to commit (and upload
the bundle artwork bytes).

>>> ``--apply`` MUTATES rows. DUMP PROD FIRST (encrypted, see docs/restore.md). <<<
A crash mid-run is safe (each set commits independently and the operation is
idempotent), but a bad dump is not recoverable.

Prod sequence: deploy this script (push → CI → image) → dry-run and read the
counters → ENCRYPTED DUMP → ``--apply`` → re-dry-run to confirm convergence.

Usage (from the VPS — ships in the image under api/):
    cat bundle.ndjson | docker compose exec -T api python scripts/import_trackid_clean.py           # dry-run
    cat bundle.ndjson | docker compose exec -T api python scripts/import_trackid_clean.py --apply   # write
    docker compose exec api python scripts/import_trackid_clean.py --file /tmp/bundle.ndjson --apply
"""

import argparse
import base64
import contextlib
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from beatport.enrich import enrich_from_beatport
from models import Album, CatalogEntry, DJSet, SetTrack, TrackEmbedding  # noqa: F401
from models.embedding import EMBEDDING_DIM, MODEL_NAME, MODEL_VERSION
from services.image_service import (
    BUCKET_ALBUM,
    BUCKET_CATALOG,
    BUCKET_SET,
    ImageService,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import ObjectDeletedError
from trackid.client import TrackIDClient
from trackid.importer import import_audiostream
from utils import make_normalized_key
from workers.catalog_merge import CatalogEntryMerged
from workers.db import bulk_get_or_create_catalog
from workers.deezer_enrich import (
    enrich_entry,
    link_catalog_album_from_hit,
    link_catalog_artist_from_hit,
)
from workers.enrichment import _mark_searched

logger = logging.getLogger("import_trackid_clean")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# C12 — priority for a catalog row whose source set is NOT scored in the bundle
# (recent live-flux set): above every backfill phase. Mirrors
# workers.tasks.sets.FLUX_PRIORITY, kept LOCAL so this standalone script stays
# independent of the celery worker package (same choice as import_trackid_sets).
FLUX_PRIORITY = int(os.environ.get("C12_FLUX_PRIORITY", "100"))

# Global run-level counters. Set-level counters (returned by _enrich_set_sync) are
# folded into this dict; sets_imported / sets_skipped / malformed / errors are
# accounted at the orchestration layer.
_STAT_KEYS = (
    "total",
    "malformed",
    "errors",
    "sets_imported",
    "sets_skipped",
    "tracks_linked",
    "deezer_applied",
    "beatport_applied",
    "bpm_set",
    "embeddings_inserted",
    "merged",
    "hydrated",
    "already_deezer",
    "already_beatport",
    "already_bpm",
    "already_embedded",
    "already_hydrated",
    "hydration_index_missing",
    "missing",
)
# Keys produced by the per-set sync core (folded into the run-level dict).
_SET_STAT_KEYS = tuple(
    k
    for k in _STAT_KEYS
    if k not in ("total", "malformed", "errors", "sets_imported", "sets_skipped")
)


# ── artwork suppression (no network image fetch, ever) ──────────────────────────


@contextlib.contextmanager
def _suppress_url_uploads():
    """Neutralise ``ImageService.upload_from_url`` for the WHOLE run.

    The reused funnel fetches covers over the network in three places —
    ``import_audiostream`` (TrackID set artwork), ``enrich_entry`` /
    ``link_catalog_album_from_hit`` (Deezer catalog/album cover) and
    ``enrich_from_beatport`` (Beatport cover). This clean-import must do ZERO
    network I/O: everything comes from the bundle. So ``upload_from_url`` is
    swapped for a no-op returning False (its "upload failed" contract → callers
    leave ``has_artwork`` untouched) for the whole run, and the Deezer cover BYTES
    carried by the bundle are uploaded explicitly via ``ImageService.upload_bytes``
    afterwards (see ``_upload_deezer_covers``). The SET cover rides the bundle too
    (``set_artwork_b64`` → ``_upload_set_artwork``) since a hydrated set is never
    re-crawled to fetch it later. Only the Beatport cover is not carried by the
    bundle (redundant with the Deezer catalog cover) — a deliberate reserve.

    Captures the classmethod descriptor from ``__dict__`` so the restore puts back
    the exact descriptor, not a bound method (mirrors import_beatport_matches).
    """
    original = ImageService.__dict__["upload_from_url"]
    ImageService.upload_from_url = staticmethod(lambda *a, **k: False)
    try:
        yield
    finally:
        ImageService.upload_from_url = original


def _decode_b64(b64):
    """Decode a base64 cover string to raw bytes, or None if absent/invalid."""
    if not b64:
        return None
    try:
        return base64.b64decode(b64)
    except (ValueError, TypeError):
        return None


def _upload_set_artwork(dj_set, bundle):
    """Upload the SET artwork from the bundle BYTES (apply mode, best-effort).

    ``import_audiostream`` normally fetches the TrackID set cover over the network
    (``upload_from_url``, suppressed for the whole run), so a hydrated set would
    otherwise arrive WITHOUT a cover and never be re-crawled to get one. The bytes
    ride the bundle in the top-level ``set_artwork_b64`` field; upload them here
    with the same has_artwork guard and MinIO key the funnel uses. A failure
    simply leaves ``has_artwork`` False (twin of ``_upload_deezer_covers``).
    """
    if dj_set.has_artwork:
        return
    data = _decode_b64(bundle.get("set_artwork_b64"))
    if data and ImageService.upload_bytes(data, BUCKET_SET, f"{dj_set.id}.jpg"):
        dj_set.has_artwork = True


def _upload_deezer_covers(session, entry, dz, track):
    """Upload the catalog + album cover BYTES from the bundle (apply mode only).

    Replaces the funnel's network ``upload_from_url`` (suppressed for the run):
    the same has_artwork guard and MinIO keys are used, so the result is
    indistinguishable from a live enrichment — only the source of the bytes
    differs. Best-effort: a failed upload simply leaves ``has_artwork`` False.
    """
    cat_bytes = _decode_b64(dz.get("cover_catalog_b64"))
    if cat_bytes and not entry.has_artwork:
        if ImageService.upload_bytes(cat_bytes, BUCKET_CATALOG, f"{entry.id}.jpg"):
            entry.has_artwork = True

    alb_bytes = _decode_b64(dz.get("cover_album_b64"))
    if alb_bytes:
        album_obj = track.get("album") or {}
        raw_id = album_obj.get("id")
        if raw_id:
            album = session.execute(
                select(Album).where(Album.deezer_album_id == str(raw_id))
            ).scalar_one_or_none()
            if album is not None and not album.has_artwork:
                if ImageService.upload_bytes(alb_bytes, BUCKET_ALBUM, f"{album.id}.jpg"):
                    album.has_artwork = True


# ── priority (mirror of workers.tasks.sets._merge_priority) ─────────────────────


def _merge_priority(existing, new):
    """MAX-merge a new enrich priority onto a possibly-NULL existing one.

    Mirror of ``workers.tasks.sets._merge_priority`` (kept local, same reason as
    ``FLUX_PRIORITY``). Handles the NULL start (bulk_get_or_create_catalog creates
    rows with enrich_priority NULL) and keeps the highest priority across runs.
    """
    return new if existing is None else max(existing, new)


def _set_priority(bundle):
    """The enrich priority a set stamps on its catalog rows (C12).

    ``round(bundle["score"])`` when the set is scored, else ``FLUX_PRIORITY`` (an
    unscored live-flux set is priority-absolute). Mirrors the resolve_set_tracks
    stamping in ``workers.tasks.sets``.
    """
    score = bundle.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return FLUX_PRIORITY
    return int(round(score))


# ── per-track enrichment (sync — reuses the funnel verbatim) ────────────────────


def _apply_track(session, entry, bt, *, apply, now, counts):
    """Apply ONE bundle track's enrichment to its catalog ``entry`` (sync session).

    Order matters: Deezer first (may fold the row on a deezer_id collision),
    then Beatport (authoritative bpm/key), then the estimated BPM (only where
    ``bpm IS NULL`` so Beatport wins), then the embedding. A ``CatalogEntryMerged``
    from either enrich step means ``entry`` was folded into a canonical and
    deleted — stop touching it (twin of the drain's per-entry handling).
    """
    # ── Deezer ──
    dz = bt.get("deezer")
    if dz and isinstance(dz.get("track"), dict):
        track = dz["track"]
        if entry.deezer_id:
            # The VPS drain (or a previous push) already linked it — never
            # re-stamp; leave the fresher server-side id untouched.
            counts["already_deezer"] += 1
        else:
            try:
                enrich_entry(entry, track, s3=None, _known_isrcs=None, session=session)
            except CatalogEntryMerged:
                counts["merged"] += 1
                return
            try:
                # Same wiring as workers.enrichment._enrich_one (best-effort).
                link_catalog_artist_from_hit(session, entry.id, track)
                link_catalog_album_from_hit(session, entry.id, track)
            except Exception:
                logger.warning(
                    "artist/album link failed for catalog %s", entry.id, exc_info=True
                )
            _mark_searched(entry, "deezer", now)
            counts["deezer_applied"] += 1
            if apply:
                _upload_deezer_covers(session, entry, dz, track)

    # ── Beatport ──
    bp = bt.get("beatport")
    if bp and isinstance(bp.get("bp_track"), dict):
        if entry.beatport_id:
            counts["already_beatport"] += 1
        else:
            try:
                enrich_from_beatport(entry, bp["bp_track"], s3=None, session=session)
            except CatalogEntryMerged:
                counts["merged"] += 1
                return
            _mark_searched(entry, "beatport", now)
            counts["beatport_applied"] += 1

    # ── BPM (estimated, analysis provenance) — only where bpm IS NULL ──
    bpm = bt.get("bpm")
    if isinstance(bpm, dict) and bpm.get("value") is not None:
        if entry.bpm is None:
            entry.bpm = float(bpm["value"])
            entry.bpm_source = "analysis"
            counts["bpm_set"] += 1
        else:
            counts["already_bpm"] += 1

    # ── Embedding — portable INSERT ... ON CONFLICT DO NOTHING ──
    emb = bt.get("embedding")
    if isinstance(emb, list) and len(emb) == EMBEDDING_DIM:
        existing = session.execute(
            select(TrackEmbedding.id).where(
                TrackEmbedding.catalog_id == entry.id,
                TrackEmbedding.model_name == MODEL_NAME,
                TrackEmbedding.model_version == MODEL_VERSION,
            )
        ).first()
        if existing:
            counts["already_embedded"] += 1
        else:
            session.add(
                TrackEmbedding(
                    catalog_id=entry.id,
                    model_name=MODEL_NAME,
                    model_version=MODEL_VERSION,
                    embedding=emb,
                    created_at=now,
                )
            )
            session.flush()
            counts["embeddings_inserted"] += 1


def _flip_hydration(session, trackid_id, set_id, counts):
    """Mark this set's ``trackid_index`` row hydrated + link ``set_id`` (idempotent).

    Mirrors ``import_trackid_index.seed_hydration`` but scoped to ONE trackid_id.
    Dialect-neutral (no ``IS DISTINCT FROM``): a plain SELECT decides, so a re-run
    that finds it already hydrated to the same set is a no-op (``already_hydrated``).
    A trackid_id absent from the index (anomaly — the bundle set should be indexed)
    cannot be flipped (``hydration_index_missing``).
    """
    row = session.execute(
        text(
            "SELECT hydration_state, set_id FROM trackid_index "
            "WHERE trackid_id = :t"
        ),
        {"t": trackid_id},
    ).first()
    if row is None:
        counts["hydration_index_missing"] += 1
        return
    if row[0] == "hydrated" and row[1] == set_id:
        counts["already_hydrated"] += 1
        return
    session.execute(
        text(
            "UPDATE trackid_index SET hydration_state = 'hydrated', set_id = :s "
            "WHERE trackid_id = :t"
        ),
        {"s": set_id, "t": trackid_id},
    )
    counts["hydrated"] += 1


def _enrich_set_sync(session, set_id, bundle, apply, now):
    """Resolve + enrich one imported set (SYNC session). Never commits.

    The single testable core of the write path (runs directly on a sync Session
    in tests, or through ``AsyncSession.run_sync`` in prod). It resolves the
    freshly-imported ``set_tracks`` to catalog rows, links them, applies each
    bundle track's enrichment, stamps ``enrich_priority`` and flips the hydration
    state. Returns a stats dict over ``_SET_STAT_KEYS``.
    """
    counts = {k: 0 for k in _SET_STAT_KEYS}

    # 1. The set_tracks just (re-)created by import_audiostream have catalog_id
    #    NULL (import deletes+re-inserts on every pass). Resolve the non-ID ones.
    set_tracks = (
        session.execute(
            select(SetTrack).where(
                SetTrack.set_id == set_id,
                SetTrack.is_id == False,  # noqa: E712
                SetTrack.raw_title.isnot(None),
            )
        )
        .scalars()
        .all()
    )

    # 2. Dedup ISRC→normalized_key against the LIVE DB and create the missing rows.
    if set_tracks:
        track_dicts = [
            {"title": st.raw_title, "artist": st.raw_artist} for st in set_tracks
        ]
        catalog_map = bulk_get_or_create_catalog(session, track_dicts)
    else:
        catalog_map = {}

    prio = _set_priority(bundle)

    # 3. Link set_tracks → catalog, stamp priority, and index entries by musicTrackId
    #    (the reliable join to the bundle enrichment) and by normalized_key.
    entry_by_mtid = {}
    for st in set_tracks:
        nk = make_normalized_key(st.raw_title, st.raw_artist)
        entry = catalog_map.get(nk)
        if entry is None:
            continue
        st.catalog_id = entry.id
        counts["tracks_linked"] += 1
        entry.enrich_priority = _merge_priority(entry.enrich_priority, prio)
        if st.trackid_music_track_id is not None:
            entry_by_mtid[st.trackid_music_track_id] = entry
    session.flush()

    # 4. Apply each bundle track's enrichment to its catalog entry.
    for bt in bundle.get("tracks", []):
        if not isinstance(bt, dict) or bt.get("is_id"):
            continue
        entry = None
        mtid = bt.get("musicTrackId")
        if mtid is not None:
            entry = entry_by_mtid.get(mtid)
        if entry is None:
            entry = catalog_map.get(
                make_normalized_key(bt.get("raw_title"), bt.get("raw_artist"))
            )
        if entry is None:
            counts["missing"] += 1
            continue
        try:
            _apply_track(session, entry, bt, apply=apply, now=now, counts=counts)
        except ObjectDeletedError:
            # The row was folded away by a merge triggered on a sibling track in
            # this same set — nothing left to enrich here.
            counts["missing"] += 1

    # 5. Flip hydration for this set.
    trackid_id = bundle.get("trackid_id")
    if trackid_id is None:
        trackid_id = bundle["detail"].get("id")
    _flip_hydration(session, int(trackid_id), set_id, counts)

    return counts


# ── orchestration (async — reuses import_audiostream) ───────────────────────────


def _valid_bundle(obj):
    """True when ``obj`` satisfies the minimal bundle shape needed to process it:
    a dict with a ``detail`` dict carrying an ``id``, a list ``tracks`` and a
    resolvable ``trackid_id`` (top-level int or the detail ``id``)."""
    if not isinstance(obj, dict):
        return False
    detail = obj.get("detail")
    if not isinstance(detail, dict) or detail.get("id") is None:
        return False
    if not isinstance(obj.get("tracks"), list):
        return False
    tid = obj.get("trackid_id")
    if tid is None:
        tid = detail.get("id")
    try:
        int(tid)
    except (TypeError, ValueError):
        return False
    return True


def _fold_counts(dst, src):
    for k, v in src.items():
        dst[k] += v


async def _process_set(factory, bundle, *, apply, now, counts):
    """Import + enrich ONE set in its own async session/transaction.

    ``import_audiostream`` is async; the enrichment funnel is sync. They share ONE
    transaction via ``AsyncSession.run_sync`` (the sync core runs on the session's
    underlying connection). Commit on --apply, rollback otherwise (dry-run writes
    nothing to the DB; the artwork bytes are only uploaded inside the sync core
    under ``apply``, and ``upload_from_url`` is suppressed for the whole run).
    """
    detail = bundle["detail"]
    async with factory() as db:
        # Bare client: NOT entered as a context manager → no httpx client is ever
        # created. With prefetched_detail truthy, get_set_detail is never called;
        # only the PURE merge_tracklist(detail) runs. Zero network.
        client = TrackIDClient()
        dj_set, _track_count = await import_audiostream(
            db, client, detail, prefetched_detail=detail, min_age_hours=0
        )
        if dj_set is None:
            counts["sets_skipped"] += 1
            await db.rollback()
            return
        await db.flush()

        # Set artwork from the bundle bytes (the funnel's network fetch is
        # suppressed for the run). Best-effort; committed with the rest below.
        if apply:
            _upload_set_artwork(dj_set, bundle)

        set_counts = await db.run_sync(_enrich_set_sync, dj_set.id, bundle, apply, now)
        _fold_counts(counts, set_counts)
        counts["sets_imported"] += 1

        if apply:
            await db.commit()
        else:
            await db.rollback()


async def import_bundles(factory, lines, *, apply, now):
    """Stream the NDJSON ``lines`` and process each bundle. Returns the run stats.

    A malformed line (bad JSON or bad shape) is counted and skipped. An unexpected
    error while processing a set is isolated (counted ``errors``) so one bad set
    never aborts the whole run — the operation is idempotent, so a re-run retries.
    """
    counts = {k: 0 for k in _STAT_KEYS}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        counts["total"] += 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            counts["malformed"] += 1
            continue
        if not _valid_bundle(obj):
            counts["malformed"] += 1
            continue
        try:
            await _process_set(factory, obj, apply=apply, now=now, counts=counts)
        except Exception:
            counts["errors"] += 1
            tid = obj.get("trackid_id") or obj.get("detail", {}).get("id")
            logger.warning("failed to process set %s", tid, exc_info=True)
    return counts


def _iter_lines(file_path):
    """Yield raw lines from ``file_path`` or stdin (streamed, never fully buffered)."""
    if file_path:
        with open(file_path, "r", encoding="utf-8") as fh:
            yield from fh
    else:
        yield from sys.stdin


def _print_report(counts, apply):
    verb = "processed" if apply else "would process"
    print(f"\nRead {counts['total']} bundle line(s); {verb}:")
    print(f"    sets_imported        : {counts['sets_imported']}")
    print(f"    tracks_linked        : {counts['tracks_linked']}")
    print(f"    deezer_applied       : {counts['deezer_applied']}")
    print(f"    beatport_applied     : {counts['beatport_applied']}")
    print(f"    bpm_set              : {counts['bpm_set']}")
    print(f"    embeddings_inserted  : {counts['embeddings_inserted']}")
    print(f"    merged               : {counts['merged']}  (folded into a canonical row)")
    print(f"    hydrated             : {counts['hydrated']}")
    print(f"    already_deezer       : {counts['already_deezer']}")
    print(f"    already_beatport     : {counts['already_beatport']}")
    print(f"    already_bpm          : {counts['already_bpm']}")
    print(f"    already_embedded     : {counts['already_embedded']}")
    print(f"    already_hydrated     : {counts['already_hydrated']}")
    print(f"    hydration_missing    : {counts['hydration_index_missing']}  (no index row)")
    print(f"    sets_skipped         : {counts['sets_skipped']}  (import returned nothing)")
    print(f"    missing              : {counts['missing']}  (track had no catalog entry)")
    print(f"    malformed            : {counts['malformed']}  (bad line, skipped)")
    print(f"    errors               : {counts['errors']}  (set aborted, rolled back)")


async def main(apply, file_path=None):
    if not DATABASE_URL:
        sys.exit("DATABASE_URL is not set")

    now = datetime.now(timezone.utc)
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if not apply:
        print("=== DRY-RUN — nothing will be written (use --apply) ===")
    else:
        print("=== APPLY — ingesting the enrichment bundle ===")
        # The buckets the reused funnel assumes already exist; the artwork bytes go
        # straight to upload_bytes (which does not ensure_bucket). Dry-run skips
        # this to make NO MinIO call.
        ImageService.ensure_bucket(BUCKET_CATALOG)
        ImageService.ensure_bucket(BUCKET_ALBUM)
        ImageService.ensure_bucket(BUCKET_SET)

    try:
        with _suppress_url_uploads():
            counts = await import_bundles(
                factory, _iter_lines(file_path), apply=apply, now=now
            )
    finally:
        await engine.dispose()

    _print_report(counts, apply)

    if not apply:
        print(
            "\nDry-run only. The reused funnel ran to compute the counts, then each "
            "set's transaction was rolled back — NO external write (DB / MinIO / "
            "network). Re-run with --apply to write — DUMP PROD FIRST (docs/restore.md)."
        )
    else:
        print(
            "\nDone. Idempotent: a re-run re-imports the sets cleanly and counts the "
            "already-linked rows as already_* (nothing re-stamped)."
        )


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(
        description="Ingest a pre-computed TrackID enrichment bundle (NDJSON) into "
        "prod by replaying the import/enrichment funnel verbatim against the live DB "
        "— zero network I/O. Reads stdin or --file. Dry-run by default; --apply to "
        "commit."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write (default: dry-run, rolled back)",
    )
    parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="read the NDJSON bundle from this path instead of stdin",
    )
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply, file_path=args.file_path))
