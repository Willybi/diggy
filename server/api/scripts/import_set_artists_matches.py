#!/usr/bin/env python
"""OPS import: write the set-artist links found by the LOCAL resolver into the DB.

CONTEXT — a LOCAL tool (``worker/set_artist_backfill/``, run on the operator's
residential IP, outside the server) resolves the artists of the ~42k existing
unlinked TrackID sets from ``(title, channel)``, hitting Deezer on a base miss —
a mass-Deezer workload FORBIDDEN on the VPS (fair-use, the AV10 lesson). That local
tool ONLY resolves; it NEVER writes to the database. The WRITE happens here, on the
server, by REUSING the fil-de-l'eau identity code path VERBATIM
(``deezer_enrich._resolve_or_create_artist`` + the ``SetArtist`` model) — it
deliberately does NOT re-implement the get-or-create, because a re-implementation
re-introduces the artist-identity bugs the dedup chantier fixed (invariant #4: a bad
merge/link is expensive corruption; err toward separation).

NDJSON CONTRACT (one JSON object per line, read from stdin by default or --file):

    {"set_id": <int>, "title": <str>, "channel": <str|null>, "links": [
       {"source": "base",   "name": <str>, "artist_id": <int>},
       {"source": "deezer", "name": <str>, "deezer_id": <str>}
    ]}

  * ``set_id`` — the ``sets.id`` the local tool resolved.
  * ``source`` is the IDENTITY LANE:
      - ``"base"``   → ``artist_id`` is a prod artist id resolved offline against the
        base the tool pulled; verified to still exist here, then linked.
      - ``"deezer"`` → ``deezer_id`` (+ ``name``) is a Deezer-confirmed match; the
        artist is get-or-created LIVE via ``_resolve_or_create_artist`` (a placeholder
        name → skipped, never a graph node).
  * ``links`` may be EMPTY (a set that resolved to no artist — a completed attempt).
  * ``title`` — used ONLY for the dry-run precision sample (set title → artist[s]).

Per-line logic:

  1. Load the ``DJSet`` by id — absent → counted ``missing``, skipped.
  2. Load the set's EXISTING ``set_artists`` ids once (idempotence: a re-run, or the
     fil-de-l'eau task having linked it meanwhile, skips those → ``already_linked``).
  3. For each link, in order (``position`` = its index in ``links``):
       - ``base``   → verify the ``Artist`` row still exists; gone → ``artist_missing``,
         skip. Else link.
       - ``deezer`` → ``_resolve_or_create_artist(session, name, deezer_id)``; a
         placeholder → ``placeholder_skipped``, skip. Else link the returned artist.
       - A link already present → ``already_linked``; a new ``SetArtist(role="dj")`` →
         ``linked``.
  4. A set that produced zero NEW links (empty or all-skipped) is counted ``no_links``.

DRY-RUN by default (no ``--apply``): NOTHING is committed — the whole run is rolled
back at the end — and the plan + counters + a SAMPLE of the links that WOULD be
created (set title → artist name[s]) are printed. That sample is the PRECISION-review
vector at scale (invariant #4): read it before any ``--apply``. Because
``_resolve_or_create_artist`` may create an artist row (from a Deezer-confirmed id)
to compute the accurate counts, dry-run RUNS it and rolls the transaction back —
there is NO external I/O in that function (pure DB), so a dry-run makes no external
write of any kind. Pass ``--apply`` to commit. Idempotent: a re-run counts the
now-linked rows as ``already_linked`` (nothing re-created).

>>> ``--apply`` MUTATES rows (writes ``set_artists`` + may create ``artists`` rows).
    DUMP PROD FIRST (see docs/restore.md). <<<  A crash mid-run is safe (work is
    committed in batches and the operation is idempotent), but a bad dump is not
    recoverable.

Usage (from the VPS — ships in the image under api/):
    cat links.ndjson | docker compose exec -T api python scripts/import_set_artists_matches.py           # dry-run
    cat links.ndjson | docker compose exec -T api python scripts/import_set_artists_matches.py --apply   # write
    docker compose exec api python scripts/import_set_artists_matches.py --file /tmp/links.ndjson --apply
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Artist, DJSet, SetArtist
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from workers.deezer_enrich import _resolve_or_create_artist

# Rows per committed transaction in --apply mode (mirrors the other OPS scripts).
_COMMIT_EVERY = 50

# How many resolved sets to show in the dry-run precision sample.
_SAMPLE_SIZE = 40

# All stat buckets, initialised to 0 so the report always prints every key.
# ``total`` = NDJSON records read; ``malformed`` = records that violated the contract
# (bad JSON, missing/invalid set_id, non-list links) and were skipped.
_STAT_KEYS = (
    "total",
    "malformed",
    "missing",
    "no_links",
    "linked",
    "already_linked",
    "artist_missing",
    "placeholder_skipped",
    "malformed_link",
)

# Sentinel yielded by _read_ndjson for a line that is not valid JSON.
_MALFORMED = object()

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _read_ndjson(stream):
    """Yield one parsed JSON object per non-blank line, or ``_MALFORMED`` on bad JSON.

    Streams line-by-line so a multi-hundred-k NDJSON is never fully in memory, and a
    single bad line never aborts the import (it is counted + skipped downstream).
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
    """Return ``(set_id, title, links)`` for a valid record, else None.

    Enforces the contract: a dict with an int ``set_id`` (not a bool) and a list
    ``links``. ``title`` is optional (used only for the sample); ``links`` may be
    empty. Per-link validation happens in :func:`_resolve_link`.
    """
    if record is _MALFORMED or not isinstance(record, dict):
        return None
    set_id = record.get("set_id")
    if not isinstance(set_id, int) or isinstance(set_id, bool):
        return None
    links = record.get("links")
    if not isinstance(links, list):
        return None
    return set_id, record.get("title") or "", links


def _resolve_link(session, link):
    """Resolve ONE link dict to ``(artist, outcome)``.

    ``artist`` is a live ``Artist`` (to link) or None; ``outcome`` is one of
    ``"ok"`` / ``"artist_missing"`` / ``"placeholder_skipped"`` / ``"malformed_link"``.
    Reuses ``_resolve_or_create_artist`` VERBATIM for the deezer lane (get-or-create,
    placeholder → None). The base lane only VERIFIES the prod id still exists (never
    creates): the id was resolved offline against a base snapshot, so a since-merged/
    deleted artist must not be resurrected.
    """
    if not isinstance(link, dict):
        return None, "malformed_link"
    source = link.get("source")
    name = link.get("name") or ""

    if source == "base":
        artist_id = link.get("artist_id")
        if not isinstance(artist_id, int) or isinstance(artist_id, bool):
            return None, "malformed_link"
        artist = session.get(Artist, artist_id)
        if artist is None:
            return None, "artist_missing"
        return artist, "ok"

    if source == "deezer":
        deezer_id = link.get("deezer_id")
        if not deezer_id or not name:
            return None, "malformed_link"
        artist = _resolve_or_create_artist(session, name, str(deezer_id))
        if artist is None:
            return None, "placeholder_skipped"
        return artist, "ok"

    return None, "malformed_link"


def _link_set(session, set_id, title, links, stats, sample):
    """Link one set's resolved artists; update ``stats`` in place. Returns nothing.

    Set-level accounting: ``missing`` (no such set) short-circuits; otherwise the set
    is counted ``linked`` if ≥1 NEW ``SetArtist`` was added, else ``no_links``.
    Per-link counts (``linked`` / ``already_linked`` / ``artist_missing`` /
    ``placeholder_skipped`` / ``malformed_link``) accumulate across links. Idempotent:
    an existing ``(set, artist)`` link is ``already_linked`` and never re-added.
    Fills ``sample`` (up to _SAMPLE_SIZE) with ``(title, [artist names])`` for the
    dry-run precision review.
    """
    dj_set = session.get(DJSet, set_id)
    if dj_set is None:
        stats["missing"] += 1
        return

    existing = {
        r[0]
        for r in session.execute(
            select(SetArtist.artist_id).where(SetArtist.set_id == set_id)
        ).all()
    }
    linked_names = []
    for idx, link in enumerate(links):
        artist, outcome = _resolve_link(session, link)
        if outcome != "ok":
            stats[outcome] += 1
            continue
        if artist.id in existing:
            stats["already_linked"] += 1
            continue
        session.add(
            SetArtist(set_id=set_id, artist_id=artist.id, role="dj", position=idx)
        )
        existing.add(artist.id)
        stats["linked"] += 1
        linked_names.append(artist.name)

    if linked_names:
        if sample is not None and len(sample) < _SAMPLE_SIZE:
            sample.append((title, linked_names))
    else:
        stats["no_links"] += 1


def import_links(session, records, *, apply=False, commit_every=_COMMIT_EVERY):
    """Import an iterable of NDJSON ``records`` (parsed dicts / ``_MALFORMED``).

    The single testable core, extracted from ``main`` so it runs without the CLI. In
    ``--apply`` mode it commits every ``commit_every`` sets that added ≥1 link (plus a
    trailing commit). In dry-run it commits NOTHING (the caller rolls back) while still
    running ``_resolve_or_create_artist`` so the counts + sample are accurate — that
    function does pure-DB work (no external I/O), so dry-run makes no external write.
    Returns ``(stats, sample)`` where ``sample`` is a list of ``(set_title,
    [artist_names])`` for human precision review.
    """
    stats = {k: 0 for k in _STAT_KEYS}
    sample = []
    pending = 0

    for record in records:
        stats["total"] += 1
        parsed = _validate(record)
        if parsed is None:
            stats["malformed"] += 1
            continue
        set_id, title, links = parsed
        before = stats["linked"]
        _link_set(session, set_id, title, links, stats, sample)
        if apply and stats["linked"] > before:
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return stats, sample


def _print_sample(sample):
    if not sample:
        print("\n(no links would be created — nothing to review)")
        return
    print(f"\nSample of proposed links (first {len(sample)} sets) — REVIEW FOR PRECISION:")
    for title, names in sample:
        shown = (title[:70] + "…") if len(title) > 70 else title
        print(f"    {shown!r}  →  {', '.join(names)}")


def _print_report(stats, apply):
    verb = "linked" if apply else "would link"
    print(f"\nRead {stats['total']} NDJSON record(s); {verb}:")
    print(f"    linked              : {stats['linked']}  (new set_artists rows)")
    print(f"    already_linked      : {stats['already_linked']}  (link already present)")
    print(f"    no_links            : {stats['no_links']}  (set resolved to nothing new)")
    print(f"    artist_missing      : {stats['artist_missing']}  (base artist_id gone)")
    print(f"    placeholder_skipped : {stats['placeholder_skipped']}  (deezer name a placeholder)")
    print(f"    missing             : {stats['missing']}  (no such set)")
    print(f"    malformed           : {stats['malformed']}  (bad record, skipped)")
    print(f"    malformed_link      : {stats['malformed_link']}  (bad link entry, skipped)")


def main(apply, file_path=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            if not apply:
                print("=== DRY-RUN — nothing will be committed (use --apply) ===")
            else:
                print("=== APPLY — writing set-artist links ===")

            if file_path:
                with open(file_path, "r", encoding="utf-8") as fh:
                    stats, sample = import_links(session, _read_ndjson(fh), apply=apply)
            else:
                stats, sample = import_links(
                    session, _read_ndjson(sys.stdin), apply=apply
                )

            if not apply:
                # Discard every in-memory mutation (SetArtist adds + any artist
                # get-or-create) made while computing the accurate counts + sample.
                session.rollback()

            _print_report(stats, apply)
            if not apply:
                _print_sample(sample)
                print(
                    "\nDry-run only. Identity was resolved live to compute the counts "
                    "+ sample, then the transaction was rolled back — NO write of any "
                    "kind. REVIEW THE SAMPLE above; re-run with --apply to write — "
                    "DUMP PROD FIRST (docs/restore.md)."
                )
            else:
                print(
                    "\nDone. Idempotent: a re-run counts the now-linked rows as "
                    "already_linked (nothing re-created)."
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Write the set-artist links found by the LOCAL resolver into the "
        "DB, reusing the fil-de-l'eau identity code (deezer_enrich._resolve_or_create_"
        "artist + the SetArtist model). Reads an NDJSON stream (stdin or --file). "
        "Dry-run by default (prints a precision sample); --apply to commit."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the links (default: dry-run, rolled back)",
    )
    parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="read NDJSON from this path instead of stdin",
    )
    args = parser.parse_args()
    main(apply=args.apply, file_path=args.file_path)
