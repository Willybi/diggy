#!/usr/bin/env python
"""One-shot OPS backfill: populate the derived set metadata on ``sets`` (C13.e).

C13.e added two columns to ``sets`` — ``event_date`` (the event date parsed out of
the set TITLE when unambiguous, preferred over the often-upload ``played_date``)
and ``channel_canonical`` (the ``channel`` normalised through a curated gazetteer,
cleaned raw passthrough otherwise). Both are written at the import funnel, so every
set imported BEFORE that shipped carries them NULL until its next re-crawl. This
script computes them RIGHT AWAY from the set's own ``title`` / ``channel`` — no
network, purely local computation over the existing rows.

It reuses the EXACT funnel helpers (``workers.set_title_meta.extract_event_date`` /
``canonicalize_channel``) so a backfilled value is indistinguishable from a
funnel-written one. A set is only written when at least one of the two derived
values differs from what is stored, so the script is IDEMPOTENT: a second
``--apply`` recomputes identical values and changes nothing.

Convention: DRY-RUN by default (reads only, prints what WOULD change), ``--apply``
to write, ``--limit N`` to cap the number of sets scanned (validate a sample first).
Idempotent, keyset by ``id`` ascending (the whole table is never loaded at once),
committed every batch.

>>> ``--apply`` mutates rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed; the operation is idempotent).

Usage (from the VPS):
    docker compose exec api python scripts/backfill_set_metadata.py            # dry-run
    docker compose exec api python scripts/backfill_set_metadata.py --limit 500  # sample
    docker compose exec api python scripts/backfill_set_metadata.py --apply     # write
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import DJSet
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from workers.set_title_meta import canonicalize_channel, extract_event_date

# Rows scanned per DB round-trip and rows mutated per committed transaction.
_BATCH = 500
_COMMIT_EVERY = 200

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors the sibling OPS scripts: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def backfill_set_metadata(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Compute ``event_date`` / ``channel_canonical`` for every set from its own
    ``title`` / ``channel``.

    Iterates sets by keyset (``id`` ascending) and, for each, derives the event
    date from the title and the canonical channel from the raw channel via the
    funnel helpers, writing when at least one differs from the stored value.
    ``apply=False`` (default) mutates nothing; the returned counts describe what
    WOULD change.

    Returns ``{"scanned", "changed", "examples"}`` where ``changed`` counts sets
    whose stored metadata differs and ``examples`` is a list of
    ``(set_id, changed_field_names)``.
    """
    scanned = changed = 0
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
                .where(DJSet.id > last_id)
                .order_by(DJSet.id.asc())
                .limit(take)
            )
            .scalars()
            .all()
        )
        if not rows:
            break

        for s in rows:
            last_id = s.id
            scanned += 1
            new_event = extract_event_date(s.title)
            new_channel = canonicalize_channel(s.channel)
            changed_fields = []
            if s.event_date != new_event:
                changed_fields.append("event_date")
            if s.channel_canonical != new_channel:
                changed_fields.append("channel_canonical")
            if changed_fields:
                changed += 1
                if len(examples) < max_examples:
                    examples.append((s.id, changed_fields))
                if apply:
                    s.event_date = new_event
                    s.channel_canonical = new_channel
                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0

    if apply and pending:
        session.commit()

    return {"scanned": scanned, "changed": changed, "examples": examples}


def _print_report(stats, apply):
    verb = "updated" if apply else "would update"
    print(
        f"\nScanned {stats['scanned']} set(s): {verb} metadata on "
        f"{stats['changed']} row(s)."
    )
    for set_id, fields in stats["examples"]:
        print(f"    #{set_id}: {', '.join(fields)}")


def main(apply, limit=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total = session.execute(
                select(func.count()).select_from(DJSet)
            ).scalar_one()
            print(f"Sets in table: {total}")

            head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            print(f"\n=== {head} ===")

            stats = backfill_set_metadata(session, apply=apply, limit=limit)
            _print_report(stats, apply)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. event_date is parsed from the title, "
                    "channel_canonical from the channel; a row is written only when "
                    "one differs from the stored value. Re-run with --apply to write "
                    "— DUMP PROD FIRST (see docs/restore.md)."
                )
                return

            # Convergence check: idempotent, so a dry re-scan must find no change.
            stats2 = backfill_set_metadata(session, apply=False, limit=limit)
            print(
                f"\nConvergence re-check (expected 0): metadata changes={stats2['changed']}."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill sets.event_date (from title) + sets.channel_canonical "
        "(from channel) for existing sets. Dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the metadata (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of sets processed (validate a sample first)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit)
