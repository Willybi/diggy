#!/usr/bin/env python
"""OPS import: write the Beatport matches found by the LOCAL scraper into the DB.

CONTEXT — a LOCAL tool (run on the operator's residential IP, outside the server)
scrapes Beatport in parallel with the VPS hourly drain to burn down the
enrichment backlog faster. That local tool ONLY scrapes + validates a match; it
NEVER writes to the database. The WRITE happens here, on the server, by REUSING
the exact same enrichment code path the drain uses
(``beatport.enrich.enrich_from_beatport`` + ``workers.enrichment._mark_searched``)
— it deliberately does NOT re-implement the mapping or the match logic, because a
re-implementation re-introduces the wrong-platform-id bugs fixed under X1/X3/X4
(a platform id is NOT a per-recording identity; a bad id is expensive corruption,
invariant #4).

NDJSON CONTRACT (one JSON object per line, read from stdin by default or --file):

    {"catalog_id": <int>, "status": "found" | "not_found", "bp_track": <dict|null>}

  * ``catalog_id`` — the ``catalog.id`` the local tool scraped for.
  * ``status="found"``  → ``bp_track`` is the NORMALISED Beatport track dict the
    scraper produced (the same structure ``enrich_from_beatport`` consumes: keys
    ``id``, ``bpm``, ``key`` [Camelot string], ``release``/``label``/``genre``,
    ``publish_date``, ...). It is passed VERBATIM to ``enrich_from_beatport``.
  * ``status="not_found"`` → ``bp_track`` is null; the row is marked as a
    completed (fruitless) Beatport attempt (E1 accounting).
  * The scraper does NOT emit HTTP-error rows: a line that failed to scrape
    (outage) is simply ABSENT from the NDJSON, so the row stays fresh for a later
    re-scan — an outage must never burn one of the 3 E1 attempts.

Per-line logic (mirrors ``enrich_beatport_batch`` in ``workers/enrichment.py``):

  1. Load the ``CatalogEntry`` by id — absent → counted ``missing``, skipped.
  2. FRESHNESS GUARD: if the row ALREADY carries a ``beatport_id`` (the VPS drain
     enriched it between the scrape and this import), skip it — counted
     ``already_linked``, and NOTHING is re-stamped. This keeps the import
     idempotent and never clobbers a fresher server-side result.
  3. ``status="found"`` → ``enrich_from_beatport(entry, bp_track, s3=None,
     session=session)``:
       - ``CatalogEntryMerged`` (the id already belonged to another row → this
         row was folded into it) → counted ``merged``, and the dead row is NOT
         ``_mark_searched`` (exactly as the drain does);
       - else ``_mark_searched(entry, "beatport", now)`` and count ``enriched``
         when it changed something, ``not_matched`` when it did not (a completed
         attempt either way).
  4. ``status="not_found"`` → ``_mark_searched(entry, "beatport", now)`` only,
     counted ``not_found_marked`` (one E1 attempt recorded).

``s3`` is passed as ``None`` exactly like the prod drain: any artwork upload goes
through ``ImageService`` internally, which reaches MinIO on the VPS.

DRY-RUN by default (no ``--apply``): NOTHING is committed — the whole run is
rolled back at the end — and the plan + counters are printed. Because the counts
(``enriched`` vs ``not_matched`` vs ``merged``) are runtime properties of the
reused enrichment code, dry-run RUNS that code to compute them accurately, then
rolls the transaction back. Dry-run makes NO external write of any kind — not the
DB, not MinIO, not the Beatport CDN: the reused code's ONE non-transactional side
effect (``enrich_from_beatport`` uploading a missing cover via
``ImageService.upload_from_url``) is neutralised for the duration of a dry-run (see
``_suppress_artwork_upload``), so a dry-run over a huge batch never fetches a cover
nor writes to MinIO. Pass ``--apply`` to commit (and upload covers normally).
Idempotent: a re-run finds the now-linked rows and counts them ``already_linked``
(nothing re-stamped).

>>> ``--apply`` MUTATES rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (work is committed in batches and the operation is
idempotent), but a bad dump is not recoverable.

Usage (from the VPS — ships in the image under api/):
    # pipe the local tool's NDJSON in
    cat matches.ndjson | docker compose exec -T api python scripts/import_beatport_matches.py           # dry-run
    cat matches.ndjson | docker compose exec -T api python scripts/import_beatport_matches.py --apply   # write
    # or read a file already present in the container
    docker compose exec api python scripts/import_beatport_matches.py --file /tmp/matches.ndjson --apply
"""

import argparse
import contextlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models, beatport, services
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from beatport.enrich import enrich_from_beatport
from models import CatalogEntry
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from workers.catalog_merge import CatalogEntryMerged
from workers.enrichment import _mark_searched

# Rows per committed transaction in --apply mode (mirrors the drain's batch size
# and the other OPS scripts' _COMMIT_EVERY).
_COMMIT_EVERY = 50

# All stat buckets, initialised to 0 so the report always prints every key.
# ``total`` = NDJSON records read; ``malformed`` = records that violated the
# contract (bad JSON, missing/invalid catalog_id or status, found-without-dict
# bp_track) and were skipped without touching the DB.
_STAT_KEYS = (
    "total",
    "malformed",
    "missing",
    "already_linked",
    "enriched",
    "not_matched",
    "merged",
    "not_found_marked",
)
# Outcomes that mutated a row (so the batch-commit counter only counts real work).
_DB_WRITE_OUTCOMES = frozenset(
    {"enriched", "not_matched", "merged", "not_found_marked"}
)

# Sentinel yielded by _read_ndjson for a line that is not valid JSON, so all
# malformed-record handling lives in ONE place (_process_record).
_MALFORMED = object()

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


@contextlib.contextmanager
def _suppress_artwork_upload():
    """Neutralise ``ImageService.upload_from_url`` for the duration of a dry-run.

    ``enrich_from_beatport`` (reused verbatim — out of scope to modify) has ONE
    non-transactional side effect: when the row has no artwork it fetches the
    cover from the Beatport CDN and uploads it to MinIO. A dry-run must be
    read-only (OPS discipline: no external write before a dump), so we swap that
    method for a no-op returning False (its "upload failed" contract → the caller
    simply leaves ``has_artwork`` untouched) and restore the original in a
    ``finally``. enrich_from_beatport imports ImageService locally, so patching the
    class attribute here is what its call resolves to.

    Counter fidelity is preserved: for a "found" row past the freshness guard,
    ``beatport_id`` is ALWAYS stamped by the FIRST branch of enrich_from_beatport,
    so ``changed`` is True regardless of the artwork branch — the enriched /
    not_matched routing does not depend on the upload succeeding.
    """
    from services.image_service import ImageService

    # Capture the original descriptor from the class __dict__ (a classmethod
    # object) so the restore puts back the exact descriptor, not a bound method.
    original = ImageService.__dict__["upload_from_url"]
    ImageService.upload_from_url = staticmethod(lambda *a, **k: False)
    try:
        yield
    finally:
        ImageService.upload_from_url = original


def _read_ndjson(stream):
    """Yield one parsed JSON object per non-blank line of ``stream``.

    A line that fails to parse yields the ``_MALFORMED`` sentinel (rather than
    raising) so a single bad line never aborts the whole import — it is counted
    and skipped downstream. Streams line-by-line so a multi-hundred-k NDJSON file
    is never loaded into memory at once.
    """
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            yield _MALFORMED


def _validate(record):
    """Return ``(catalog_id, status, bp_track)`` for a valid record, else None.

    Enforces the NDJSON contract: a dict with an int ``catalog_id`` (not a bool)
    and ``status`` in {found, not_found}; a ``found`` record must carry a dict
    ``bp_track`` (the normalised Beatport track). A ``not_found`` record's
    ``bp_track`` is ignored and normalised to None.
    """
    if record is _MALFORMED or not isinstance(record, dict):
        return None
    catalog_id = record.get("catalog_id")
    # bool is an int subclass — reject it explicitly (a True catalog_id is a bug).
    if not isinstance(catalog_id, int) or isinstance(catalog_id, bool):
        return None
    status = record.get("status")
    if status not in ("found", "not_found"):
        return None
    bp_track = record.get("bp_track")
    if status == "found":
        if not isinstance(bp_track, dict):
            return None
    else:
        bp_track = None
    return catalog_id, status, bp_track


def _process_record(session, record, *, now, s3=None):
    """Route ONE NDJSON record and return its outcome bucket name.

    Reuses ``enrich_from_beatport`` + ``_mark_searched`` verbatim — the write
    semantics are the drain's, never re-implemented. Mutates the session (in both
    dry-run and apply — the caller controls commit vs rollback). Returns one of
    ``_STAT_KEYS`` (minus ``total``).
    """
    parsed = _validate(record)
    if parsed is None:
        return "malformed"
    catalog_id, status, bp_track = parsed

    entry = session.get(CatalogEntry, catalog_id)
    if entry is None:
        return "missing"

    # Freshness guard: the VPS drain may have linked this row between the scrape
    # and this import — never re-stamp a row that already carries a beatport_id.
    if entry.beatport_id:
        return "already_linked"

    if status == "found":
        try:
            matched = enrich_from_beatport(entry, bp_track, s3=s3, session=session)
        except CatalogEntryMerged as m:
            # The beatport_id already belonged to another row → this (loser) row
            # was folded into the canonical. Do NOT _mark_searched the dead row
            # (twin of enrich_beatport_batch).
            print(
                f"  catalog {catalog_id}: folded into canonical {m.surviving_id}",
                file=sys.stderr,
            )
            return "merged"
        _mark_searched(entry, "beatport", now)
        return "enriched" if matched else "not_matched"

    # status == "not_found": one completed (fruitless) E1 attempt.
    _mark_searched(entry, "beatport", now)
    return "not_found_marked"


def import_matches(
    session, records, *, apply=False, commit_every=_COMMIT_EVERY, now=None, s3=None
):
    """Import an iterable of NDJSON ``records`` (parsed dicts / ``_MALFORMED``).

    The single testable core, extracted from ``main`` so it runs without the CLI.
    In ``--apply`` mode it commits every ``commit_every`` mutating records (plus a
    trailing commit) and uploads covers normally. In dry-run it commits NOTHING
    (the caller rolls the transaction back) AND suppresses the artwork upload (see
    ``_suppress_artwork_upload``) so the run makes no external write at all, while
    still running the reused enrichment code so the returned counts are accurate.
    Returns a stats dict over ``_STAT_KEYS``.
    """
    now = now or datetime.now(timezone.utc)
    stats = {k: 0 for k in _STAT_KEYS}
    pending = 0

    # Dry-run must be read-only: neutralise the only non-transactional side effect
    # of the reused enrichment code (the MinIO/CDN cover upload). In --apply this
    # is a no-op nullcontext, so covers upload normally.
    artwork_guard = (
        contextlib.nullcontext() if apply else _suppress_artwork_upload()
    )

    with artwork_guard:
        for record in records:
            stats["total"] += 1
            outcome = _process_record(session, record, now=now, s3=s3)
            stats[outcome] += 1
            if apply and outcome in _DB_WRITE_OUTCOMES:
                pending += 1
                if pending >= commit_every:
                    session.commit()
                    pending = 0

    if apply and pending:
        session.commit()

    return stats


def _print_report(stats, apply):
    verb = "processed" if apply else "would process"
    print(f"\nRead {stats['total']} NDJSON record(s); {verb}:")
    print(f"    enriched         : {stats['enriched']}")
    print(f"    not_matched      : {stats['not_matched']}  (searched, no data change)")
    print(f"    merged           : {stats['merged']}  (folded into a canonical row)")
    print(f"    not_found_marked : {stats['not_found_marked']}  (E1 attempt recorded)")
    print(f"    already_linked   : {stats['already_linked']}  (skipped, beatport_id present)")
    print(f"    missing          : {stats['missing']}  (no such catalog row)")
    print(f"    malformed        : {stats['malformed']}  (bad line, skipped)")


def main(apply, file_path=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            if not apply:
                print("=== DRY-RUN — nothing will be committed (use --apply) ===")
            else:
                print("=== APPLY — writing Beatport matches ===")

            if file_path:
                with open(file_path, "r", encoding="utf-8") as fh:
                    stats = import_matches(session, _read_ndjson(fh), apply=apply)
            else:
                stats = import_matches(session, _read_ndjson(sys.stdin), apply=apply)

            if not apply:
                # Discard every in-memory mutation the reused enrichment code made
                # while computing the accurate counts above.
                session.rollback()

            _print_report(stats, apply)

            if not apply:
                print(
                    "\nDry-run only. The reused enrichment code ran to compute the "
                    "counts, then the transaction was rolled back — NO external write "
                    "of any kind (DB / MinIO / CDN; cover upload suppressed). Re-run "
                    "with --apply to write — DUMP PROD FIRST (docs/restore.md)."
                )
            else:
                print(
                    "\nDone. Idempotent: a re-run counts the now-linked rows as "
                    "already_linked (nothing re-stamped)."
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Write the Beatport matches found by the LOCAL scraper into the "
        "DB, reusing the drain's enrichment code (beatport.enrich.enrich_from_beatport "
        "+ workers.enrichment._mark_searched). Reads an NDJSON stream (stdin or "
        "--file). Dry-run by default; --apply to commit."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the matches (default: dry-run, rolled back)",
    )
    parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="read NDJSON from this path instead of stdin",
    )
    args = parser.parse_args()
    main(apply=args.apply, file_path=args.file_path)
