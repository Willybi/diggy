#!/usr/bin/env python
"""One-shot OPS backfill: compute ``sets.unreliable`` for pre-C8 sets (C8 L3).

The C8 reliability flag (``sets.unreliable``) is computed at IMPORT and refreshed
on every re-crawl by ``trackid.reliability.compute_set_unreliable`` (lot L1). But
every set that was imported BEFORE that flag shipped defaults to ``unreliable =
false`` (the column's server_default) — so a genuinely low-trust set stays visible
until its next re-crawl. This script recomputes the flag for the existing sets so
the exclusion (lot L2) takes effect immediately, WITHOUT deleting any track.

It reuses the SINGLE source of the rule — ``compute_set_unreliable`` from L1 — so
the backfill can never diverge from the import/recrawl definition. Per set it
re-observes the three signals ``compute_set_unreliable`` needs:

  - track counts: ``total`` tracks and the ``is_id`` (unidentified) subset, counted
    from ``set_tracks`` — the dominant ID-ratio signal;
  - provenance: the set's ``source_url`` (see "effective source_url" below);
  - placeholder artwork: at import the signal reads the audiostream detail's
    ``artworkUrl``; here — with no live payload — it reads the STORED artwork bytes
    from MinIO (bucket ``set-artworks``, key ``{id}.jpg``) and hashes them against
    the shared placeholder md5 (``artwork_bytes_are_placeholder`` from L1). A
    missing object or any MinIO error is treated as "not placeholder" and logged
    (it can only ever suppress the SECONDARY signal, never create a false flag).

Effective source_url — the reliability pass and the provenance bonus below
interact through one field, so the flag is computed against the EFFECTIVE source
url = the stored ``source_url`` if present, else the trackid audiostream url
recoverable from ``external_slug`` (the exact value the provenance bonus writes),
else None. A set whose provenance is recoverable from its slug therefore is NOT
treated as provenance-less. This makes the two passes ORDER-INDEPENDENT and the
whole script IDEMPOTENT (dry-run == apply, and a re-run finds nothing to change),
regardless of whether the provenance bonus has already stored the url.

BONUS — provenance recovery (clearly separate section, counted apart): for a
trackid set with ``source_url IS NULL`` but an ``external_slug``, the public
audiostream url is deterministically recoverable as
``https://trackid.net/audiostream/{external_slug}`` (the same form the SetsView
registration placeholder shows). The bonus stores it so the set regains a
clickable origin. It writes nothing else and never touches a set that already has
a ``source_url``.

Convention: DRY-RUN by default (reads only, prints what WOULD change), ``--apply``
to write, ``--limit N`` to cap the number of sets scanned per pass (validate a
sample first). Idempotent: a second ``--apply`` recomputes identical flags and
finds no null-source slug to recover.

>>> ``--apply`` mutates rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed; the operation is idempotent).

Usage (from the VPS):
    docker compose exec api python scripts/backfill_set_reliability.py            # dry-run
    docker compose exec api python scripts/backfill_set_reliability.py --limit 500  # sample
    docker compose exec api python scripts/backfill_set_reliability.py --apply     # write
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api on path

from models import DJSet, SetTrack
from sqlalchemy import case, create_engine, func, select
from sqlalchemy.orm import Session

# Single source of the reliability rule + the placeholder constant (lot L1) — never
# re-implement the threshold or the md5 here.
from trackid.reliability import artwork_bytes_are_placeholder, compute_set_unreliable

logger = logging.getLogger("backfill_set_reliability")

SET_ARTWORK_BUCKET = "set-artworks"
# Public trackid audiostream url recoverable from a set's slug. Same form as the
# SetsView registration placeholder ("https://trackid.net/audiostream/…"); the
# stored source_url normally comes from the audiostream detail's ``url`` field.
TRACKID_AUDIOSTREAM_URL = "https://trackid.net/audiostream/{slug}"

# Rows scanned per DB round-trip and rows mutated per committed transaction.
_BATCH = 500
_COMMIT_EVERY = 200

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors reverify_platform_ids: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _effective_source_url(dj_set):
    """The set's provenance url, recovering it from the slug when unstored.

    Returns the stored ``source_url`` if present, else the trackid audiostream url
    derivable from ``external_slug`` (exactly what the provenance bonus writes),
    else None. Using this — rather than the raw stored column — keeps the
    reliability flag stable whether or not the provenance bonus has run yet, so the
    two passes are order-independent and the script is idempotent.
    """
    if dj_set.source_url and dj_set.source_url.strip():
        return dj_set.source_url
    if dj_set.external_slug:
        return TRACKID_AUDIOSTREAM_URL.format(slug=dj_set.external_slug)
    return None


def _placeholder_from_minio(set_id):
    """True if the set's STORED artwork bytes are the TrackID placeholder cover.

    Reads ``set-artworks/{id}.jpg`` and hashes it via the L1 helper. A missing
    object or any MinIO/boto error is treated as "not placeholder" (logged): the
    placeholder is only a SECONDARY signal (it also requires a missing source_url),
    so a read failure can suppress a flag but never invent one.
    """
    try:
        from services.image_service import ImageService

        obj = ImageService._get_s3().get_object(
            Bucket=SET_ARTWORK_BUCKET, Key=f"{set_id}.jpg"
        )
        data = obj["Body"].read()
    except Exception as exc:  # noqa: BLE001 — a read failure is a non-placeholder
        logger.debug("artwork read failed for set %s: %s", set_id, exc)
        return False
    return artwork_bytes_are_placeholder(data)


def _track_counts(session, set_ids):
    """Return ``{set_id: (total_tracks, id_tracks)}`` for the given sets.

    ``id_tracks`` is summed via ``case`` (portable across PG + the SQLite test
    harness — a raw ``sum(boolean)`` fails on PG). Sets with no ``set_tracks`` rows
    are simply absent from the map; the caller reads them as ``(0, 0)`` → a
    zero-track set, which ``compute_set_unreliable`` flags unreliable.
    """
    if not set_ids:
        return {}
    id_sum = func.sum(case((SetTrack.is_id.is_(True), 1), else_=0))
    rows = session.execute(
        select(SetTrack.set_id, func.count(SetTrack.id), id_sum)
        .where(SetTrack.set_id.in_(set_ids))
        .group_by(SetTrack.set_id)
    ).all()
    return {sid: (int(total or 0), int(id_tracks or 0)) for sid, total, id_tracks in rows}


def backfill_reliability(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    placeholder_probe=_placeholder_from_minio,
    max_examples=10,
):
    """Recompute ``unreliable`` for every trackid set, via the L1 rule.

    Iterates the ``trackid`` sets by keyset (``id`` ascending) so the whole table
    is never loaded at once. For each set it recomputes the flag with
    ``compute_set_unreliable`` fed the effective source url and — only when there is
    NO effective source and the set carries stored artwork — the placeholder probe
    (the sole case where the secondary signal can matter, so the MinIO read is rare).

    ``apply=False`` (default) mutates nothing and the returned counts describe what
    WOULD change. In ``apply`` mode the flag is written and committed every
    ``commit_every`` mutated rows. Returns ``{"scanned", "changed", "to_flag",
    "to_unflag", "placeholder_reads", "examples"}`` where ``changed`` counts rows
    whose flag differs from its stored value and ``examples`` is a list of
    ``(set_id, old_flag, new_flag, title)``.
    """
    scanned = changed = to_flag = to_unflag = placeholder_reads = 0
    examples = []
    pending = 0
    last_id = 0

    while True:
        if limit is not None and scanned >= limit:
            break
        take = batch_size
        if limit is not None:
            take = min(batch_size, limit - scanned)
        rows = (
            session.execute(
                select(DJSet)
                .where(DJSet.source == "trackid", DJSet.id > last_id)
                .order_by(DJSet.id.asc())
                .limit(take)
            )
            .scalars()
            .all()
        )
        if not rows:
            break

        counts = _track_counts(session, [s.id for s in rows])
        for s in rows:
            last_id = s.id
            scanned += 1
            total, id_tracks = counts.get(s.id, (0, 0))
            eff_source = _effective_source_url(s)
            placeholder = False
            if eff_source is None and s.has_artwork:
                placeholder = placeholder_probe(s.id)
                placeholder_reads += 1

            new_flag = compute_set_unreliable(total, id_tracks, eff_source, placeholder)
            old_flag = bool(s.unreliable)
            if new_flag != old_flag:
                changed += 1
                to_flag += new_flag
                to_unflag += not new_flag
                if len(examples) < max_examples:
                    examples.append((s.id, old_flag, new_flag, s.title))
                if apply:
                    s.unreliable = new_flag
                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0

    if apply and pending:
        session.commit()

    return {
        "scanned": scanned,
        "changed": changed,
        "to_flag": to_flag,
        "to_unflag": to_unflag,
        "placeholder_reads": placeholder_reads,
        "examples": examples,
    }


def backfill_source_url(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Recover ``source_url`` from ``external_slug`` for trackid sets missing it (bonus).

    Selects trackid sets with ``source_url IS NULL`` and a non-null
    ``external_slug`` and stores
    ``https://trackid.net/audiostream/{external_slug}``. Reads/writes NOTHING else —
    this is a strictly separate, additive provenance recovery, counted apart from
    the reliability pass. Idempotent: a recovered set has a non-null ``source_url``
    and drops out of the selection on a re-run.

    ``apply=False`` (default) counts what WOULD be recovered without writing.
    Returns ``{"recovered", "examples"}`` where ``examples`` is a list of
    ``(set_id, source_url)``.
    """
    recovered = 0
    examples = []
    pending = 0
    last_id = 0

    while True:
        if limit is not None and recovered >= limit and apply:
            break
        rows = (
            session.execute(
                select(DJSet)
                .where(
                    DJSet.source == "trackid",
                    DJSet.source_url.is_(None),
                    DJSet.external_slug.isnot(None),
                    DJSet.id > last_id,
                )
                .order_by(DJSet.id.asc())
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not rows:
            break

        for s in rows:
            last_id = s.id
            if limit is not None and recovered >= limit:
                rows = []
                break
            url = TRACKID_AUDIOSTREAM_URL.format(slug=s.external_slug)
            recovered += 1
            if len(examples) < max_examples:
                examples.append((s.id, url))
            if apply:
                s.source_url = url
                pending += 1
                if pending >= commit_every:
                    session.commit()
                    pending = 0
        if limit is not None and recovered >= limit:
            break

    if apply and pending:
        session.commit()

    return {"recovered": recovered, "examples": examples}


def _print_reliability(stats, apply):
    verb = "flagged" if apply else "would flag"
    unverb = "un-flagged" if apply else "would un-flag"
    print(
        f"\n[reliability] scanned {stats['scanned']} trackid set(s): "
        f"{verb} {stats['to_flag']} unreliable, {unverb} {stats['to_unflag']} "
        f"({stats['changed']} change(s) total; {stats['placeholder_reads']} "
        f"artwork read(s))."
    )
    for set_id, old, new, title in stats["examples"]:
        print(f"    #{set_id} {old} -> {new}  {title!r}")


def _print_source_url(stats, apply):
    verb = "recovered" if apply else "would recover"
    print(
        f"\n[provenance] {verb} source_url from external_slug for "
        f"{stats['recovered']} trackid set(s)."
    )
    for set_id, url in stats["examples"]:
        print(f"    #{set_id} -> {url}")


def main(apply, limit=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total_sets = session.execute(
                select(func.count()).select_from(DJSet).where(DJSet.source == "trackid")
            ).scalar_one()
            print(f"TrackID sets: {total_sets}")

            head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            print(f"\n=== {head} ===")

            rel = backfill_reliability(session, apply=apply, limit=limit)
            _print_reliability(rel, apply)

            prov = backfill_source_url(session, apply=apply, limit=limit)
            _print_source_url(prov, apply)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. The reliability flag is recomputed with the L1 "
                    "rule (compute_set_unreliable) against the EFFECTIVE source_url "
                    "(stored, else recoverable from the slug); the placeholder signal "
                    "reads the stored artwork bytes, a MinIO miss/error counts as "
                    "'not placeholder'. Re-run with --apply to write — DUMP PROD "
                    "FIRST (see docs/restore.md)."
                )
                return

            # Convergence check: idempotent, so a dry re-scan must find no change.
            rel2 = backfill_reliability(session, apply=False, limit=limit)
            prov2 = backfill_source_url(session, apply=False, limit=limit)
            print(
                f"\nConvergence re-check (expected 0/0): "
                f"reliability changes={rel2['changed']}, "
                f"provenance recoverable={prov2['recovered']}."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill sets.unreliable for pre-C8 sets using the L1 rule, and "
        "recover source_url from external_slug (bonus). Dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the flags / urls (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of sets processed per pass (validate a sample first)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit)
