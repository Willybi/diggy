#!/usr/bin/env python
"""One-shot OPS backfill: re-base ``sets.completion_pct`` on the TrackID hit rate,
and re-arm the sets that lot L1's earlier (is_id-based) metric finalized by mistake.

Background — before lot L1, ``sets.completion_pct`` was an ``is_id``-based ratio
(share of identified tracks). For a TrackID audiostream that ratio is ~always 1.0
(the importer only stores IDENTIFIED tracks), so ~44k sets were driven to
``completion_pct = 1.0`` and finalized (``recrawl_status = 'final'``) even though
their real identification rate is far lower. The true rate lives in
``trackid_index.time_hit_rate`` (mean ~0.53). Lot L1 re-based the LIVE metric on
``time_hit_rate`` going forward; this script RETROFITS the existing prod rows so
the correction takes effect without waiting for each set's next re-crawl.

Two volets (selectable via ``--volet a|b|both``, default ``both``):

  Volet A — re-base: for every TrackID set that has a ``trackid_index`` row (joined
    on ``trackid_index.set_id = sets.id``) with a non-null ``time_hit_rate``, set
    ``completion_pct = time_hit_rate``. A pure UPDATE, no crawl. Sets WITHOUT a
    ``trackid_index`` row (or with a NULL ``time_hit_rate``) are left untouched — a
    documented edge (~3.5k sets), we have no better metric to substitute for them.

  Volet B — AGGRESSIVE re-arm (decision acted in the chantier brief): for every
    ``recrawl_status = 'final'``, ``source = 'trackid'``, ``is_virtual = false`` set
    whose ``trackid_index.time_hit_rate`` is below ``RECRAWL_FINAL_HITRATE`` (0.95),
    flip ``recrawl_status`` back to ``'active'`` AND reset ``recrawl_count`` to 0 —
    giving it a fresh budget of re-crawl polls so it re-enters the re-crawl loop and
    can genuinely improve its identification rate. Sets with no index row / a NULL
    hit rate / a hit rate already ≥ 0.95 are left ``final``.

This script uses its OWN copy of the L1 constant (same name, same 0.95 default) so
it never imports the worker logic — it must NOT diverge from L1's value, and L1
must be DEPLOYED FIRST (see the OPS sequence below), otherwise the next re-crawl of
a re-armed set would re-finalize it through the old is_id-based rule.

Convention: DRY-RUN by default (reads only, prints what WOULD change), ``--apply``
to write, ``--limit N`` to cap the number of sets scanned per volet (validate a
sample first). Idempotent, keyset by ``sets.id`` ascending (the whole table is
never loaded at once), committed every batch: volet A writes ``time_hit_rate`` so a
re-run finds ``completion_pct`` already equal → no change; volet B flips a set to
``active`` so it drops out of the ``final`` selection on a re-run.

>>> ``--apply`` mutates rows. DUMP PROD FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed; the operation is idempotent).

============================================================================
OPS SEQUENCE (prod) — follow this ORDER strictly:
  (a) DEPLOY LOT L1 FIRST. If a re-armed set is re-crawled while the old
      is_id-based logic is still live, it is immediately re-finalized — the
      re-arm is wasted. L1 (time_hit_rate-based completion_pct) MUST be running
      before this script's --apply.
  (b) DRY-RUN and read the counters:
        docker compose exec api python scripts/backfill_completion_pct.py
  (c) Take an ENCRYPTED PROD DUMP before any --apply (see docs/restore.md).
  (d) Apply:
        docker compose exec api python scripts/backfill_completion_pct.py --apply
  (e) Re-run the dry-run to confirm convergence (expected 0 / 0).
  (f) WATCH CPU. Re-arming ~39k sets means each re-enters the re-crawl loop and
      re-writes its set_tracks (delete + re-insert) on the next run → heavy churn
      that can trip the Hostinger fair-use throttle (cf. the AV10 CPU lesson).
      Throttle the re-crawl throughput via the env RECRAWL_MAX_SETS_PER_RUN:
      start LOW and ramp it up as the burn-down proves the CPU stays healthy.
      Monitor with `ssh diggy-vps "cd /root/diggy && docker stats --no-stream"`
      and `ssh diggy-vps sar`.
============================================================================

Usage (from the VPS):
    docker compose exec api python scripts/backfill_completion_pct.py               # dry-run, both volets
    docker compose exec api python scripts/backfill_completion_pct.py --volet a     # re-base only
    docker compose exec api python scripts/backfill_completion_pct.py --limit 500   # sample
    docker compose exec api python scripts/backfill_completion_pct.py --apply       # write
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api on path

from models import DJSet, TrackIdIndex
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

# Mirror of the L1 worker constant (server/workers/tasks/sets.py). SAME name, SAME
# default — a set at/above this TrackID hit rate is considered "finalized". We keep
# a private copy rather than importing the worker so this OPS script has no worker
# dependency; it must never drift from L1's value.
RECRAWL_FINAL_HITRATE = float(os.environ.get("RECRAWL_FINAL_HITRATE", "0.95"))

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


def _hit_rates(session, set_ids):
    """Return ``{set_id: time_hit_rate}`` from ``trackid_index`` for the given sets.

    Joined on ``trackid_index.set_id`` (the FK back to ``sets.id``). A set without an
    index row is simply absent from the map; a set whose index row has a NULL
    ``time_hit_rate`` maps to ``None``. Both are read by the callers as "no usable
    hit rate" and left untouched. ``set_id`` is effectively unique per set here
    (seeded 1:1 from ``sets.external_id``), so a plain dict is unambiguous.
    """
    if not set_ids:
        return {}
    rows = session.execute(
        select(TrackIdIndex.set_id, TrackIdIndex.time_hit_rate).where(
            TrackIdIndex.set_id.in_(set_ids)
        )
    ).all()
    return {sid: rate for sid, rate in rows}


def rebase_completion_pct(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Volet A — set ``completion_pct = trackid_index.time_hit_rate`` for TrackID sets.

    Iterates the ``trackid`` sets by keyset (``id`` ascending) so the whole table is
    never loaded at once. For each set with an index row carrying a non-null
    ``time_hit_rate``, records (and in ``apply`` mode writes) ``completion_pct =
    time_hit_rate`` when it differs from the stored value. Sets with no index row or
    a NULL hit rate are counted in ``skipped_no_index`` and left as-is.

    ``apply=False`` (default) mutates nothing; the returned counts describe what
    WOULD change. Returns ``{"scanned", "changed", "skipped_no_index", "examples"}``
    where ``examples`` is a list of ``(set_id, old_pct, new_pct, title)``.
    """
    scanned = changed = skipped_no_index = 0
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

        rates = _hit_rates(session, [s.id for s in rows])
        for s in rows:
            last_id = s.id
            scanned += 1
            new_pct = rates.get(s.id)
            if new_pct is None:
                skipped_no_index += 1
                continue
            old_pct = s.completion_pct
            if new_pct != old_pct:
                changed += 1
                if len(examples) < max_examples:
                    examples.append((s.id, old_pct, new_pct, s.title))
                if apply:
                    s.completion_pct = new_pct
                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0

    if apply and pending:
        session.commit()

    return {
        "scanned": scanned,
        "changed": changed,
        "skipped_no_index": skipped_no_index,
        "examples": examples,
    }


def rearm_final_sets(
    session,
    *,
    apply=False,
    batch_size=_BATCH,
    commit_every=_COMMIT_EVERY,
    limit=None,
    max_examples=10,
):
    """Volet B — re-arm final-but-incomplete TrackID sets (AGGRESSIVE).

    Iterates by keyset over the ``recrawl_status='final'``, ``source='trackid'``,
    ``is_virtual=false`` sets. A set whose ``trackid_index.time_hit_rate`` is
    non-null AND below ``RECRAWL_FINAL_HITRATE`` is re-armed: ``recrawl_status`` back
    to ``'active'`` and ``recrawl_count`` reset to 0 (fresh poll budget). Sets with
    no index row / a NULL hit rate / a hit rate already ≥ the threshold are counted
    in ``skipped`` and left ``final``.

    Idempotent: a re-armed set is now ``active`` and drops out of the ``final``
    selection on a re-run. ``apply=False`` (default) mutates nothing; the returned
    counts describe what WOULD change. Returns ``{"scanned", "rearmed", "skipped",
    "examples"}`` where ``examples`` is a list of ``(set_id, hit_rate, title)``.
    """
    scanned = rearmed = skipped = 0
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
                .where(
                    DJSet.source == "trackid",
                    DJSet.is_virtual.is_(False),
                    DJSet.recrawl_status == "final",
                    DJSet.id > last_id,
                )
                .order_by(DJSet.id.asc())
                .limit(take)
            )
            .scalars()
            .all()
        )
        if not rows:
            break

        rates = _hit_rates(session, [s.id for s in rows])
        for s in rows:
            last_id = s.id
            scanned += 1
            hit_rate = rates.get(s.id)
            if hit_rate is None or hit_rate >= RECRAWL_FINAL_HITRATE:
                skipped += 1
                continue
            rearmed += 1
            if len(examples) < max_examples:
                examples.append((s.id, hit_rate, s.title))
            if apply:
                s.recrawl_status = "active"
                s.recrawl_count = 0
                pending += 1
                if pending >= commit_every:
                    session.commit()
                    pending = 0

    if apply and pending:
        session.commit()

    return {
        "scanned": scanned,
        "rearmed": rearmed,
        "skipped": skipped,
        "examples": examples,
    }


def _print_rebase(stats, apply):
    verb = "re-based" if apply else "would re-base"
    print(
        f"\n[volet A / re-base] scanned {stats['scanned']} trackid set(s): "
        f"{verb} completion_pct on {stats['changed']} row(s); "
        f"{stats['skipped_no_index']} left as-is (no trackid_index row / NULL hit rate)."
    )
    for set_id, old, new, title in stats["examples"]:
        print(f"    #{set_id} {old} -> {new}  {title!r}")


def _print_rearm(stats, apply):
    verb = "re-armed" if apply else "would re-arm"
    print(
        f"\n[volet B / re-arm] scanned {stats['scanned']} final trackid set(s): "
        f"{verb} {stats['rearmed']} (hit rate < {RECRAWL_FINAL_HITRATE}); "
        f"{stats['skipped']} kept final (no hit rate / ≥ threshold)."
    )
    for set_id, hit_rate, title in stats["examples"]:
        print(f"    #{set_id} hit_rate={hit_rate}  {title!r}")


def main(apply, limit=None, volet="both"):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total_sets = session.execute(
                select(func.count()).select_from(DJSet).where(DJSet.source == "trackid")
            ).scalar_one()
            print(f"TrackID sets: {total_sets}")

            head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            print(f"\n=== {head} (volet={volet}) ===")

            rebase = rearm = None
            if volet in ("a", "both"):
                rebase = rebase_completion_pct(session, apply=apply, limit=limit)
                _print_rebase(rebase, apply)
            if volet in ("b", "both"):
                rearm = rearm_final_sets(session, apply=apply, limit=limit)
                _print_rearm(rearm, apply)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. Volet A re-bases completion_pct on the TrackID "
                    "time_hit_rate (sets with no index row are left untouched); volet B "
                    "re-arms final trackid sets whose hit rate is below "
                    f"{RECRAWL_FINAL_HITRATE}. Re-run with --apply to write — DUMP PROD "
                    "FIRST (see docs/restore.md). REMINDER: deploy L1 before --apply."
                )
                return

            # Convergence check: idempotent, so a dry re-scan must find no change.
            rebase2 = rearm2 = None
            if volet in ("a", "both"):
                rebase2 = rebase_completion_pct(session, apply=False, limit=limit)
            if volet in ("b", "both"):
                rearm2 = rearm_final_sets(session, apply=False, limit=limit)
            print(
                "\nConvergence re-check (expected 0 / 0): "
                f"re-base changes={rebase2['changed'] if rebase2 else 'skipped'}, "
                f"re-arm={rearm2['rearmed'] if rearm2 else 'skipped'}."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-base sets.completion_pct on trackid_index.time_hit_rate and "
        "re-arm sets finalized by the old is_id-based metric. Dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write completion_pct / re-arm (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of sets processed per volet (validate a sample first)",
    )
    parser.add_argument(
        "--volet",
        choices=("a", "b", "both"),
        default="both",
        help="a = re-base only, b = re-arm only, both = both (default)",
    )
    args = parser.parse_args()
    main(apply=args.apply, limit=args.limit, volet=args.volet)
