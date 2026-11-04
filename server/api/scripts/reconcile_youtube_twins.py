#!/usr/bin/env python
"""One-shot OPS catch-up: reconcile the existing YouTube sets with their twins.

The entry control (``set_twin_service``) only sees sets as they arrive. This script
applies the SAME decisions to the sets already in base, through the service's
``plan_twin_for_set`` / ``apply_twin_plan`` — it holds no rule and no index of its own,
so prevention and catch-up cannot diverge. It adds one rule only a whole-base view can
see: when two YouTube sets aim at one family outside the video step, neither is
attached, both go to REVIEW.

Two modes:

  * ``--mode repair-parents`` — walks the virtual parents and derives their metadata
    from their children (``sync_parent_metadata``). Tracks are not rebuilt.
  * ``--mode twins [--steps video,date,channel]`` — plans every root YouTube set
    (read-only), then with ``--apply`` writes the plans of the requested steps.
    Pending flags for the REVIEW plans are only created with ``--flag-review``.

Writes nothing unless ``--apply`` is passed: a dry-run reads and decides, without any
database write, MinIO copy or network call.

OPS sequence:
  1. deploy this script (push -> CI -> image);
  2. dry-run each mode and read the counters + the sample;
  3. take an encrypted dump (docs/restore.md) — REQUIRED before any --apply;
  4. --apply, in this order: repair-parents -> video -> date -> channel;
  5. re-dry-run to confirm convergence (idempotent: 0 attachment left to apply).

Usage (from the VPS):
    docker compose exec api python scripts/reconcile_youtube_twins.py --mode repair-parents
    docker compose exec api python scripts/reconcile_youtube_twins.py --mode repair-parents --apply
    docker compose exec api python scripts/reconcile_youtube_twins.py --mode twins
    docker compose exec api python scripts/reconcile_youtube_twins.py --mode twins --steps video --apply
    docker compose exec api python scripts/reconcile_youtube_twins.py --mode twins --steps date --apply
    docker compose exec api python scripts/reconcile_youtube_twins.py --mode twins --steps channel --apply --flag-review

``--limit`` caps the parents processed in repair-parents. In twins it caps the sets
scanned by a dry-run (a quick sample, whose collisions are only seen within that
window) and the plans written by an --apply, which always plans the whole base first:
a partial view would miss collisions and attach sets it should not.
"""

import argparse
import asyncio
import contextlib
import os
import random
import sys
from collections import Counter
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api

from database import SessionLocal
from models import ArtistActivity, DJSet, SetArtist, UserOpinion
from services.set_dedup_service import sync_parent_metadata
from services.set_twin_rules import TwinVerdict
from services.set_twin_service import TwinPlan, apply_twin_plan, plan_twin_for_set
from sqlalchemy import func, select

ALL_STEPS = ("video", "date", "channel")
REASON_COLLISION = "ambiguous: several youtube sets on one twin"
DUMP_REMINDER = "Encrypted dump REQUIRED before --apply (see docs/restore.md)."

_BATCH = 200
_IN_CHUNK = 1000
_SAMPLE_SEED = 20261104


@contextlib.contextmanager
def _suppress_artwork_copy():
    """Neutralise ``ImageService.copy_object``, the one non-transactional write.

    Reports success so a dry-run counts the covers an --apply would copy.
    """
    from services.image_service import ImageService

    original = ImageService.__dict__["copy_object"]
    ImageService.copy_object = staticmethod(lambda *a, **k: True)
    try:
        yield
    finally:
        ImageService.copy_object = original


def _chunks(items: list, size: int = _IN_CHUNK):
    for start in range(0, len(items), size):
        yield items[start : start + size]


# ---------------------------------------------------------------------------
# --mode repair-parents
# ---------------------------------------------------------------------------


async def _parent_state(db, parent_id: int):
    """Plain columns: the metadata the repair may change, read before and after."""
    artists = (
        select(func.count())
        .select_from(SetArtist)
        .where(SetArtist.set_id == parent_id)
        .scalar_subquery()
    )
    children = (
        select(func.count())
        .select_from(DJSet)
        .where(DJSet.parent_set_id == parent_id)
        .scalar_subquery()
    )
    stmt = select(
        DJSet.source_url,
        DJSet.channel,
        DJSet.event_date,
        DJSet.has_artwork,
        DJSet.unreliable,
        artists.label("artists"),
        children.label("children"),
    ).where(DJSet.id == parent_id)
    return (await db.execute(stmt)).one()


async def _repair_parent(db, parent_id: int, stats: Counter) -> None:
    before = await _parent_state(db, parent_id)
    await sync_parent_metadata(db, parent_id)
    after = await _parent_state(db, parent_id)

    stats["parents"] += 1
    stats["childless"] += int(after.children == 0)
    stats["links_gained"] += int(not before.source_url and bool(after.source_url))
    stats["channels_gained"] += int(not before.channel and bool(after.channel))
    stats["dates_gained"] += int(
        before.event_date is None and after.event_date is not None
    )
    stats["djs_gained"] += after.artists - before.artists
    stats["artworks_copied"] += int(not before.has_artwork and after.has_artwork)
    stats["became_unreliable"] += int(not before.unreliable and after.unreliable)


async def repair_parents(
    db, *, apply: bool = False, limit: int | None = None, sleep: float = 0.0
) -> Counter:
    """Derive every virtual parent's metadata from its children. Returns counters."""
    stats = Counter()
    guard = contextlib.nullcontext() if apply else _suppress_artwork_copy()
    last_id = 0

    with guard:
        while limit is None or stats["parents"] + stats["errors"] < limit:
            take = _BATCH
            if limit is not None:
                take = min(_BATCH, limit - stats["parents"] - stats["errors"])
            parent_ids = (
                await db.execute(
                    select(DJSet.id)
                    .where(DJSet.is_virtual.is_(True), DJSet.id > last_id)
                    .order_by(DJSet.id)
                    .limit(take)
                )
            ).scalars().all()
            if not parent_ids:
                break
            last_id = parent_ids[-1]

            # A batch succeeds or fails whole: its counters only count once it is done.
            batch = Counter()
            try:
                for parent_id in parent_ids:
                    await _repair_parent(db, parent_id, batch)
                if apply:
                    await db.commit()
                else:
                    await db.rollback()
                stats.update(batch)
            except Exception as exc:
                await db.rollback()
                stats["errors"] += len(parent_ids)
                print(f"  batch up to id {last_id}: {exc!r}", file=sys.stderr)
            finally:
                db.expunge_all()
            print(f"  ... {stats['parents']} parent(s), up to id {last_id}", flush=True)
            if sleep:
                await asyncio.sleep(sleep)

    return stats


def _print_repair_report(stats: Counter, apply: bool) -> None:
    verb = "Repaired" if apply else "Would repair"
    print(f"\n{verb} {stats['parents']} virtual parent(s):")
    print(f"    links gained      : {stats['links_gained']}")
    print(f"    channels gained   : {stats['channels_gained']}")
    print(f"    dates gained      : {stats['dates_gained']}")
    print(f"    DJs gained        : {stats['djs_gained']}")
    print(f"    artworks copied   : {stats['artworks_copied']}")
    print(f"    became unreliable : {stats['became_unreliable']}  (hidden from listings)")
    print(f"    childless         : {stats['childless']}  (left untouched)")
    print(f"    errors            : {stats['errors']}  (parents of failed batches, rerun)")


# ---------------------------------------------------------------------------
# --mode twins: plan
# ---------------------------------------------------------------------------


async def _scan_plans(
    db, stats: Counter, *, limit: int | None, sleep: float
) -> list[TwinPlan]:
    """Plan every root YouTube set. Keeps only the plans that have a winner."""
    plans = []
    last_id = 0

    while limit is None or stats["scanned"] + stats["plan_errors"] < limit:
        take = _BATCH
        if limit is not None:
            take = min(_BATCH, limit - stats["scanned"] - stats["plan_errors"])
        set_ids = (
            await db.execute(
                select(DJSet.id)
                .where(
                    DJSet.source == "youtube",
                    DJSet.parent_set_id.is_(None),
                    DJSet.is_virtual.is_(False),
                    DJSet.id > last_id,
                )
                .order_by(DJSet.id)
                .limit(take)
            )
        ).scalars().all()
        if not set_ids:
            break
        last_id = set_ids[-1]

        for set_id in set_ids:
            try:
                plan = await plan_twin_for_set(db, set_id)
            except Exception as exc:
                await db.rollback()
                stats["plan_errors"] += 1
                print(f"  set {set_id}: {exc!r}", file=sys.stderr)
                continue
            stats["scanned"] += 1
            stats["excluded_existing_flag"] += int(plan.decided)
            stats["excluded_channel_truncated"] += int(plan.channel_truncated)
            if plan.winner_id is not None:
                plans.append(plan)

        # Never keep a transaction open across a long read-only scan.
        await db.rollback()
        print(f"  ... planned {stats['scanned']} set(s), up to id {last_id}", flush=True)
        if sleep:
            await asyncio.sleep(sleep)

    return plans


def demote_collisions(plans: list[TwinPlan]) -> list[TwinPlan]:
    """Send to REVIEW the sets aiming at one family outside the video step.

    Read on every plan whatever ``--steps`` asks, so the outcome does not depend on
    the order the steps are run in. Only attachments contend, like in the service.
    """
    aiming = Counter(
        plan.winner_family_id
        for plan in plans
        if plan.verdict == TwinVerdict.ATTACH and plan.step != "video"
    )
    return [
        replace(plan, verdict=TwinVerdict.REVIEW, reason=REASON_COLLISION)
        if plan.verdict == TwinVerdict.ATTACH
        and plan.step != "video"
        and aiming[plan.winner_family_id] >= 2
        else plan
        for plan in plans
    ]


# ---------------------------------------------------------------------------
# --mode twins: apply
# ---------------------------------------------------------------------------


async def apply_plans(
    db,
    plans: list[TwinPlan],
    *,
    flag_review: bool = False,
    limit: int | None = None,
    sleep: float = 0.0,
) -> Counter:
    """Write the plans, one commit per pair: a failure costs only that pair.

    A plan is decided again right before its write: the crawlers and the admin keep
    working during the run, and a decision taken meanwhile must not be overridden.
    A plan that no longer holds is skipped; the next run re-decides it.
    """
    stats = Counter()
    rank = {step: index for index, step in enumerate(ALL_STEPS)}
    todo = sorted(
        (p for p in plans if p.verdict == TwinVerdict.ATTACH or flag_review),
        key=lambda p: (p.verdict != TwinVerdict.ATTACH, rank[p.step], p.set_id),
    )
    if limit is not None:
        todo = todo[:limit]

    for index, plan in enumerate(todo, start=1):
        try:
            fresh = await plan_twin_for_set(db, plan.set_id)
            if fresh.winner_id != plan.winner_id or (
                plan.verdict == TwinVerdict.ATTACH
                and fresh.verdict != TwinVerdict.ATTACH
            ):
                await db.rollback()
                stats["stale"] += 1
                continue
            counts = await apply_twin_plan(db, plan)
            await db.commit()
            stats["attached"] += counts["attached"]
            stats["flagged"] += counts["flagged"]
            stats["different_parents"] += counts["attach_errors"]
        except Exception as exc:
            await db.rollback()
            stats["errors"] += 1
            print(
                f"  set {plan.set_id} -> {plan.winner_id}: {exc!r}", file=sys.stderr
            )
        finally:
            db.expunge_all()

        if index % _BATCH == 0:
            print(f"  ... wrote {index}/{len(todo)} plan(s)", flush=True)
            if sleep:
                await asyncio.sleep(sleep)

    return stats


# ---------------------------------------------------------------------------
# --mode twins: report
# ---------------------------------------------------------------------------


async def _count_linked(db, attach_ids: list[int]) -> tuple[int, int]:
    """Opinions and activities pointing at the sets to attach. Nothing is moved."""
    opinions = activities = 0
    for chunk in _chunks(attach_ids):
        opinions += (
            await db.execute(
                select(func.count())
                .select_from(UserOpinion)
                .where(
                    UserOpinion.entity_type == "set",
                    UserOpinion.entity_key.in_([str(i) for i in chunk]),
                )
            )
        ).scalar_one()
        activities += (
            await db.execute(
                select(func.count())
                .select_from(ArtistActivity)
                .where(ArtistActivity.set_id.in_(chunk))
            )
        ).scalar_one()
    return opinions, activities


async def _count_artworks_to_copy(db, attaches: list[TwinPlan]) -> int:
    """Families the attachments would give a cover: one copy per family lacking it."""
    ids = {p.set_id for p in attaches} | {p.winner_id for p in attaches}
    ids |= {p.winner_family_id for p in attaches}
    has_artwork = {}
    for chunk in _chunks(sorted(ids)):
        rows = await db.execute(
            select(DJSet.id, DJSet.has_artwork).where(DJSet.id.in_(chunk))
        )
        has_artwork.update({row.id: bool(row.has_artwork) for row in rows})

    families = set()
    for plan in attaches:
        # A twin without a parent is its own family: the parent to come has no cover.
        parent_has_cover = plan.winner_family_id != plan.winner_id and has_artwork.get(
            plan.winner_family_id, False
        )
        has_donor = has_artwork.get(plan.set_id, False) or has_artwork.get(
            plan.winner_id, False
        )
        if has_donor and not parent_has_cover:
            families.add(plan.winner_family_id)
    return len(families)


async def _print_sample(db, plans: list[TwinPlan], size: int) -> None:
    """Random sample per step and verdict, with a fixed seed so runs compare."""
    if size <= 0 or not plans:
        return
    rng = random.Random(_SAMPLE_SEED)
    groups = {}
    for plan in sorted(plans, key=lambda p: p.set_id):
        groups.setdefault((plan.step, plan.verdict), []).append(plan)

    picked = {
        key: rng.sample(group, min(size, len(group)))
        for key, group in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1].value))
    }
    ids = {p.set_id for group in picked.values() for p in group}
    ids |= {p.winner_id for group in picked.values() for p in group}
    rows = {}
    for chunk in _chunks(sorted(ids)):
        result = await db.execute(
            select(
                DJSet.id,
                DJSet.source,
                DJSet.title,
                DJSet.channel,
                DJSet.duration_ms,
                DJSet.played_date,
                DJSet.event_date,
            ).where(DJSet.id.in_(chunk))
        )
        rows.update({row.id: row for row in result})

    def line(set_id: int) -> str:
        row = rows.get(set_id)
        if row is None:
            return f"#{set_id} (gone)"
        minutes = round(row.duration_ms / 60000) if row.duration_ms else None
        return (
            f"#{row.id} [{row.source}] {row.title!r} | channel={row.channel!r} "
            f"| {minutes} min | published={row.played_date} | event={row.event_date}"
        )

    for (step, verdict), group in picked.items():
        print(f"\n--- sample: {step} / {verdict.value} ({len(group)}) ---")
        for plan in group:
            signals = plan.signals or {}
            print(f"  {line(plan.set_id)}")
            print(f"    -> {line(plan.winner_id)}")
            print(
                f"    dd={signals.get('dd')} cont={signals.get('cont')} "
                f"upload_delta_days={signals.get('upload_delta_days')} "
                f"reason={plan.reason!r}"
            )


def _print_twins_report(stats: Counter, plans: list[TwinPlan], apply: bool) -> None:
    print(f"\nScanned {stats['scanned']} root YouTube set(s).")
    print("Volumes by step and verdict (requested steps):")
    volumes = Counter((p.step, p.verdict.value) for p in plans)
    for (step, verdict), count in sorted(volumes.items()):
        print(f"    {step:8} {verdict:7} : {count}")
    print(f"    other steps, left out : {stats['other_steps']}")
    print(f"Collisions sent to REVIEW : {stats['collisions']}")
    print("Excluded:")
    print(f"    existing flag         : {stats['excluded_existing_flag']}")
    print(f"    channel list ignored  : {stats['excluded_channel_truncated']}")
    print(f"    plan errors           : {stats['plan_errors']}")
    print("Pointing at the sets to attach (counted, nothing moved):")
    print(f"    user_opinions         : {stats['opinions']}")
    print(f"    artist_activity       : {stats['activities']}")
    print(f"Artworks to copy          : {stats['artworks_to_copy']} (estimate)")
    if apply:
        print("Written:")
        print(f"    attached              : {stats['attached']}")
        print(f"    review flags created  : {stats['flagged']}")
        print(f"    no longer held, skipped: {stats['stale']}")
        print(f"    different parents     : {stats['different_parents']}")
        print(f"    errors                : {stats['errors']}")
    else:
        print("Written: nothing (dry-run).")
        print("    review flags created  : 0")


async def reconcile_twins(
    db,
    *,
    steps: tuple[str, ...] = ALL_STEPS,
    apply: bool = False,
    flag_review: bool = False,
    limit: int | None = None,
    sleep: float = 0.0,
    sample: int = 0,
) -> Counter:
    """Plan the root YouTube sets and, with ``apply``, write the requested steps."""
    stats = Counter()
    all_plans = await _scan_plans(
        db, stats, limit=None if apply else limit, sleep=sleep
    )
    demoted = demote_collisions(all_plans)
    plans = [p for p in demoted if p.step in steps]
    stats["other_steps"] = len(demoted) - len(plans)
    stats["collisions"] = sum(p.reason == REASON_COLLISION for p in plans)

    attaches = [p for p in plans if p.verdict == TwinVerdict.ATTACH]
    stats["would_attach"] = len(attaches)
    stats["would_review"] = len(plans) - len(attaches)
    stats["opinions"], stats["activities"] = await _count_linked(
        db, [p.set_id for p in attaches]
    )
    stats["artworks_to_copy"] = await _count_artworks_to_copy(db, attaches)
    await _print_sample(db, plans, sample)
    await db.rollback()

    if apply:
        stats.update(
            await apply_plans(
                db, plans, flag_review=flag_review, limit=limit, sleep=sleep
            )
        )
    _print_twins_report(stats, plans, apply)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_steps(value: str) -> tuple[str, ...]:
    steps = tuple(s.strip() for s in value.split(",") if s.strip())
    unknown = set(steps) - set(ALL_STEPS)
    if unknown or not steps:
        raise argparse.ArgumentTypeError(
            f"steps must be among {','.join(ALL_STEPS)}, got {value!r}"
        )
    return steps


async def run(args: argparse.Namespace) -> None:
    head = "APPLY" if args.apply else "DRY-RUN — nothing will be modified (use --apply)"
    print(f"=== {args.mode}: {head} ===")
    async with SessionLocal() as db:
        if args.mode == "repair-parents":
            stats = await repair_parents(
                db, apply=args.apply, limit=args.limit, sleep=args.sleep
            )
            _print_repair_report(stats, args.apply)
        else:
            await reconcile_twins(
                db,
                steps=args.steps,
                apply=args.apply,
                flag_review=args.flag_review,
                limit=args.limit,
                sleep=args.sleep,
                sample=args.sample,
            )
    print(f"\n{DUMP_REMINDER}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile the existing YouTube sets with their twins, with the "
        "decisions of the entry control. Dry-run by default."
    )
    parser.add_argument("--mode", required=True, choices=("repair-parents", "twins"))
    parser.add_argument(
        "--steps",
        type=_parse_steps,
        default=ALL_STEPS,
        help="twins: steps to write, comma-separated (default: video,date,channel)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write (default: dry-run, no changes). DUMP PROD FIRST",
    )
    parser.add_argument(
        "--flag-review",
        action="store_true",
        help="twins: with --apply, also create pending flags for the REVIEW plans",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="repair-parents: parents processed. twins: sets scanned by a dry-run, "
        "plans written by an --apply (which still plans the whole base)",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.0, help="pause in seconds between batches"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=30,
        help="twins: sample size per step and verdict (default: 30)",
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
