#!/usr/bin/env python
"""One-shot OPS backfill: populate the TrackID set signals on ``sets`` (C13.a).

C13.a added six columns to ``sets`` — ``channel`` + ``styles`` (surfaced in the UI)
and the data-only ``time_hit_rate`` / ``track_hit_rate`` / ``favourite_count`` /
``like_count``. They are written at the import funnel, so every set imported BEFORE
that shipped carries them NULL until its next re-crawl. This script REPORTS the
signals from the raw listing mirror ``trackid_index`` onto ``sets`` right away — no
network, purely a SQL report between two local tables.

The join is ``sets.external_id = trackid_index.trackid_id::text`` (``external_id`` is
a String, ``trackid_id`` an Integer — hence the cast), restricted to trackid-sourced
sets (the only ones whose ``external_id`` is a TrackID id). A set is only written
when at least one of its six signals differs from the ``trackid_index`` value, so the
script is IDEMPOTENT: a second ``--apply`` recomputes identical values and changes
nothing.

Convention: DRY-RUN by default (reads only, prints what WOULD change), ``--apply``
to write, ``--limit N`` to cap the number of sets scanned (validate a sample first).
Idempotent, keyset by ``id`` ascending (the whole table is never loaded at once),
committed every batch.

>>> ``--apply`` mutates rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed; the operation is idempotent).

Usage (from the VPS):
    docker compose exec api python scripts/backfill_set_signals.py            # dry-run
    docker compose exec api python scripts/backfill_set_signals.py --limit 500  # sample
    docker compose exec api python scripts/backfill_set_signals.py --apply     # write
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api on path

from models import DJSet, TrackIdIndex
from sqlalchemy import String, cast, create_engine, func, select
from sqlalchemy.orm import Session

# Rows scanned per DB round-trip and rows mutated per committed transaction.
_BATCH = 500
_COMMIT_EVERY = 200

# (sets column, trackid_index column) reported by this backfill.
_SIGNALS = [
    ("channel", "channel"),
    ("styles", "styles"),
    ("time_hit_rate", "time_hit_rate"),
    ("track_hit_rate", "track_hit_rate"),
    ("favourite_count", "favourite_count"),
    ("like_count", "like_count"),
]

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors the sibling OPS scripts: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _differs(col, new_value, old_value):
    """True when the freshly reported value differs from the stored one.

    ``styles`` is a StringArray (list on both columns — ``[]`` for NULL): compared
    element-wise as lists. Scalars compare directly.
    """
    if col == "styles":
        return list(old_value or []) != list(new_value or [])
    return old_value != new_value


def backfill_set_signals(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Report ``trackid_index`` signals onto ``sets`` for every trackid-sourced set.

    Iterates trackid-sourced sets by keyset (``id`` ascending), inner-joined to
    ``trackid_index`` on ``sets.external_id = trackid_index.trackid_id::text``. For
    each matched set it copies the six C13.a signals when at least one differs from
    the stored value. ``apply=False`` (default) mutates nothing; the returned counts
    describe what WOULD change.

    Returns ``{"scanned", "changed", "examples"}`` where ``scanned`` counts matched
    sets, ``changed`` counts sets whose stored signals differ, and ``examples`` is a
    list of ``(set_id, changed_field_names)``.
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
        rows = session.execute(
            select(DJSet, TrackIdIndex)
            .join(
                TrackIdIndex,
                DJSet.external_id == cast(TrackIdIndex.trackid_id, String),
            )
            .where(DJSet.source == "trackid", DJSet.id > last_id)
            .order_by(DJSet.id.asc())
            .limit(take)
        ).all()
        if not rows:
            break

        for s, idx in rows:
            last_id = s.id
            scanned += 1
            changed_fields = [
                set_col
                for set_col, idx_col in _SIGNALS
                if _differs(set_col, getattr(idx, idx_col), getattr(s, set_col))
            ]
            if changed_fields:
                changed += 1
                if len(examples) < max_examples:
                    examples.append((s.id, changed_fields))
                if apply:
                    for set_col, idx_col in _SIGNALS:
                        setattr(s, set_col, getattr(idx, idx_col))
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
        f"\nScanned {stats['scanned']} matched set(s): {verb} signals on "
        f"{stats['changed']} row(s)."
    )
    for set_id, fields in stats["examples"]:
        print(f"    #{set_id}: {', '.join(fields)}")


def main(apply, limit=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total = session.execute(
                select(func.count())
                .select_from(DJSet)
                .join(
                    TrackIdIndex,
                    DJSet.external_id == cast(TrackIdIndex.trackid_id, String),
                )
                .where(DJSet.source == "trackid")
            ).scalar_one()
            print(f"Trackid-sourced sets matched in trackid_index: {total}")

            head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            print(f"\n=== {head} ===")

            stats = backfill_set_signals(session, apply=apply, limit=limit)
            _print_report(stats, apply)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. Signals are reported from trackid_index; a row is "
                    "written only when at least one signal differs from the stored "
                    "value. Re-run with --apply to write — DUMP PROD FIRST "
                    "(see docs/restore.md)."
                )
                return

            # Convergence check: idempotent, so a dry re-scan must find no change.
            stats2 = backfill_set_signals(session, apply=False, limit=limit)
            print(
                f"\nConvergence re-check (expected 0): signal changes={stats2['changed']}."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill sets.channel/styles + hit-rate/favourite/like counts "
        "from trackid_index for existing trackid-sourced sets. Dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the signals (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of sets processed (validate a sample first)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit)
