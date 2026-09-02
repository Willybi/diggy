#!/usr/bin/env python
"""One-shot OPS backfill: re-title dedup virtual parents with the best child title (lot L4).

A deduplication virtual parent (``sets.is_virtual = true``) groups its child sets
(``parent_set_id = parent.id``) and carries a title meant to NAME the group. The
title heuristic was corrected in lot L2 (``pick_best_parent_title`` now picks the
MOST DESCRIPTIVE child title — most significant tokens — rather than an arbitrary
or shortest one). Every virtual parent materialized BEFORE that fix may carry a
worse title. This script recomputes each virtual parent's title from its children
so the corrected heuristic takes effect on the EXISTING parents.

It reuses the SINGLE source of the rule — ``pick_best_parent_title`` from
``set_dedup_service`` (L2) — so this backfill can never diverge from how the
importer/materializer names a fresh parent. When the picked title differs from the
parent's current title, the parent's ``title`` is updated AND its ``search_text``
is refreshed with ``search_fold(new_title)`` (L1) so search stays consistent with
the new title (the L1 fold is the search authority). A virtual parent with NO child
(``pick_best_parent_title`` would return "") is skipped, never blanked.

Convention: DRY-RUN by default (reads only, prints what WOULD change), ``--apply``
to write, ``--limit N`` to cap the number of parents scanned (validate a sample
first). Idempotent, keyset by ``id`` ascending, committed every batch.

>>> ``--apply`` mutates rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed; the operation is idempotent).

Usage (from the VPS):
    docker compose exec api python scripts/retitle_virtual_parents.py            # dry-run
    docker compose exec api python scripts/retitle_virtual_parents.py --limit 100  # sample
    docker compose exec api python scripts/retitle_virtual_parents.py --apply     # write
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api on path

from models import DJSet

# Single source of the parent-title rule (L2) and the search-fold rule (L1) —
# never re-implement either here.
from services.set_dedup_service import pick_best_parent_title
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
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


def _child_titles(session, parent_ids):
    """Return ``{parent_id: [child title, ...]}`` for the given virtual parents.

    Only non-null child titles are collected; a parent with no child is simply
    absent from the map and read by the caller as an empty list (→ skipped).
    """
    if not parent_ids:
        return {}
    rows = session.execute(
        select(DJSet.parent_set_id, DJSet.title).where(
            DJSet.parent_set_id.in_(parent_ids),
            DJSet.title.isnot(None),
        )
    ).all()
    result = {}
    for parent_id, title in rows:
        result.setdefault(parent_id, []).append(title)
    return result


def retitle_virtual_parents(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Recompute every virtual parent's title from its children, via the L2 rule.

    Iterates the virtual parents by keyset (``id`` ascending). For each parent it
    loads its children's titles and picks the best one with
    ``pick_best_parent_title``. A parent with NO child (empty pick) is SKIPPED — its
    title is never blanked. When the picked title differs from the current title, the
    parent's ``title`` is recorded (and in ``apply`` mode written) together with a
    refreshed ``search_text = search_fold(new_title)``.

    ``apply=False`` (default) mutates nothing; the returned counts describe what
    WOULD change. Returns ``{"scanned", "childless", "retitled", "examples"}`` where
    ``examples`` is a list of ``(parent_id, old_title, new_title)``.
    """
    scanned = childless = retitled = 0
    examples = []
    pending = 0
    last_id = 0

    while True:
        if limit is not None and scanned >= limit:
            break
        take = batch_size
        if limit is not None:
            take = min(batch_size, limit - scanned)
        parents = (
            session.execute(
                select(DJSet)
                .where(DJSet.is_virtual.is_(True), DJSet.id > last_id)
                .order_by(DJSet.id.asc())
                .limit(take)
            )
            .scalars()
            .all()
        )
        if not parents:
            break

        titles_by_parent = _child_titles(session, [p.id for p in parents])
        for p in parents:
            last_id = p.id
            scanned += 1
            child_titles = titles_by_parent.get(p.id, [])
            best = pick_best_parent_title(child_titles)
            if not best:
                childless += 1  # no child (or all blank) → never blank the parent
                continue
            if best != p.title:
                retitled += 1
                if len(examples) < max_examples:
                    examples.append((p.id, p.title, best))
                if apply:
                    p.title = best
                    p.search_text = search_fold(best)
                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0

    if apply and pending:
        session.commit()

    return {
        "scanned": scanned,
        "childless": childless,
        "retitled": retitled,
        "examples": examples,
    }


def _print_report(stats, apply):
    verb = "re-titled" if apply else "would re-title"
    print(
        f"\nScanned {stats['scanned']} virtual parent(s): {verb} {stats['retitled']} "
        f"({stats['childless']} childless skipped)."
    )
    for parent_id, old, new in stats["examples"]:
        print(f"    #{parent_id} {old!r} -> {new!r}")


def main(apply, limit=None):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total = session.execute(
                select(func.count())
                .select_from(DJSet)
                .where(DJSet.is_virtual.is_(True))
            ).scalar_one()
            print(f"Virtual parents: {total}")

            head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            print(f"\n=== {head} ===")

            stats = retitle_virtual_parents(session, apply=apply, limit=limit)
            _print_report(stats, apply)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. Each virtual parent's title is recomputed with "
                    "the L2 rule (pick_best_parent_title) from its children; a "
                    "changed title also refreshes search_text (L1 search_fold). A "
                    "childless parent is skipped, never blanked. Re-run with --apply "
                    "to write — DUMP PROD FIRST (see docs/restore.md)."
                )
                return

            # Convergence check: idempotent, so a dry re-scan must find no change.
            stats2 = retitle_virtual_parents(session, apply=False, limit=limit)
            print(
                f"\nConvergence re-check (expected 0): retitled={stats2['retitled']}."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-title dedup virtual parents with the best child title using "
        "the L2 rule (pick_best_parent_title), refreshing search_text. Dry-run by "
        "default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the titles / search_text (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of virtual parents processed (validate a sample first)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit)
