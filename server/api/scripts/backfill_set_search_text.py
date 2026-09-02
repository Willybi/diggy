#!/usr/bin/env python
"""One-shot OPS backfill: populate ``sets.search_text`` for existing sets (lot L4).

The search-only folded column ``sets.search_text`` (lowercased, accent-stripped,
punctuation collapsed — ``utils.search_fold`` of the title, lot L1) is computed at
IMPORT and refreshed on every re-crawl. But every set imported BEFORE that column
shipped carries ``search_text = NULL`` (the column is nullable), so it is invisible
to the accent/punctuation-insensitive set search until its next re-crawl. This
script computes ``search_fold(title)`` for the EXISTING sets so the new search
takes effect immediately.

It reuses the SINGLE source of the fold rule — ``search_fold`` from ``utils`` (L1)
— so the backfill can never diverge from the import/recrawl definition. Every set
is scanned (roots, children AND virtual parents alike: they are all searchable
rows). A set is only written when its stored ``search_text`` is NULL or differs
from the freshly computed value, so the script is IDEMPOTENT: a second ``--apply``
recomputes identical values and finds nothing to change.

Convention: DRY-RUN by default (reads only, prints what WOULD change), ``--apply``
to write, ``--limit N`` to cap the number of sets scanned (validate a sample
first). Idempotent, keyset by ``id`` ascending (the whole table is never loaded at
once), committed every batch.

>>> ``--apply`` mutates rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed; the operation is idempotent).

Usage (from the VPS):
    docker compose exec api python scripts/backfill_set_search_text.py            # dry-run
    docker compose exec api python scripts/backfill_set_search_text.py --limit 500  # sample
    docker compose exec api python scripts/backfill_set_search_text.py --apply     # write
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api on path

from models import DJSet
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

# Single source of the search-fold rule (lot L1) — never re-implement it here.
from utils import search_fold

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


def backfill_search_text(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Compute ``search_text`` = ``search_fold(title)`` for every set.

    Iterates ALL sets by keyset (``id`` ascending) — roots, children and virtual
    parents alike, since they are all searchable rows. For each set it computes
    ``search_fold(title)`` and, when the stored value is NULL or differs, records
    (and in ``apply`` mode writes) the new value. ``apply=False`` (default) mutates
    nothing; the returned counts describe what WOULD change.

    Returns ``{"scanned", "changed", "examples"}`` where ``changed`` counts rows
    whose folded value differs from its stored ``search_text`` and ``examples`` is a
    list of ``(set_id, old_value, new_value, title)``.
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
            new_value = search_fold(s.title)
            old_value = s.search_text
            if new_value != old_value:
                changed += 1
                if len(examples) < max_examples:
                    examples.append((s.id, old_value, new_value, s.title))
                if apply:
                    s.search_text = new_value
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
        f"\nScanned {stats['scanned']} set(s): {verb} search_text on "
        f"{stats['changed']} row(s)."
    )
    for set_id, old, new, title in stats["examples"]:
        print(f"    #{set_id} {old!r} -> {new!r}  ({title!r})")


def main(apply, limit=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total = session.execute(
                select(func.count()).select_from(DJSet)
            ).scalar_one()
            print(f"Sets: {total}")

            head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            print(f"\n=== {head} ===")

            stats = backfill_search_text(session, apply=apply, limit=limit)
            _print_report(stats, apply)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. search_text is recomputed with the L1 rule "
                    "(utils.search_fold) for every set; a row is written only when the "
                    "stored value is NULL or differs. Re-run with --apply to write — "
                    "DUMP PROD FIRST (see docs/restore.md)."
                )
                return

            # Convergence check: idempotent, so a dry re-scan must find no change.
            stats2 = backfill_search_text(session, apply=False, limit=limit)
            print(
                f"\nConvergence re-check (expected 0): "
                f"search_text changes={stats2['changed']}."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill sets.search_text = search_fold(title) for existing sets "
        "using the L1 fold rule. Dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write search_text (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of sets processed (validate a sample first)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit)
