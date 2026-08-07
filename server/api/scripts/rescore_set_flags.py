#!/usr/bin/env python
"""Re-score pending duplicate-candidate set flags with the composite engine (dry-run by default).

The pairwise dedup scoring was rebuilt (composite ``compute_confidence`` +
``decide_verdict`` in ``services.set_dedup_service``). In prod ~150 ``set_flags``
pairs of type ``duplicate_candidate`` still sit in ``pending`` carrying the OLD
confidence (= raw overlap). Most are false positives — unrelated sets sharing a
handful of genre anthems. This one-shot re-scores every such flag with the new
engine and AUTO-REJECTS the obvious noise so the admin only arbitrates plausible
candidates.

Scope (STRICT): only ``flag_type = duplicate_candidate`` PAIR flags in status
``pending`` — ``set_id_b IS NOT NULL`` and ``group_key IS NULL``. Group flags
(``part_candidate`` / ``part_overlap_anomaly``) are left entirely alone.

For each targeted flag:
  1. ``score_pair(db, set_id_a, set_id_b)`` → (signals, confidence). ``None`` when
     a set is gone or has become virtual → the flag is reported as NON-RESCORABLE
     and left untouched.
  2. ``decide_verdict(signals, confidence, part_a, part_b)`` recomputes the verdict.
  3. AUTO-REJECT only when ``confidence < threshold`` AND the verdict is NEITHER
     ``FLAG`` NOR ``AUTO_ATTACH``. The date guard and the title-identical rule emit
     LEGITIMATE flags at a low composite confidence (e.g. overlap 0.85, title 0.6,
     40-day gap → confidence ~0.23 but verdict FLAG) — the new engine would create
     them, so the script must not kill them. A recomputed ``AUTO_ATTACH`` also stays
     KEPT: the script NEVER attaches anything — merging is a human decision on the
     admin page.

In ``--apply`` the script rewrites ``confidence`` (composite) and ``signals`` (full
new dict) on EVERY re-scored flag — kept ones included, so the admin list re-sorts
on the true confidence. Rejected flags additionally get ``status = rejected`` and a
``"auto_rejected": true`` marker in ``signals`` (to tell them apart from manual
rejections). It NEVER deletes a flag: a rejected flag is memorised by its pair
uniqueness (``uq_set_flag_pair``) and won't be recreated by future imports.

DRY-RUN by default: prints a readable table (flag id, truncated titles, old→new
confidence, recomputed verdict, KEPT / AUTO-REJECT / NON-RESCORABLE) plus a summary
(counters + new-confidence distribution) and writes NOTHING. Pass ``--apply`` to
commit; a single commit at the end (~150 rows).

Usage (from the VPS):
    docker compose exec api python scripts/rescore_set_flags.py                 # dry-run
    docker compose exec api python scripts/rescore_set_flags.py --apply          # commit
    docker compose exec api python scripts/rescore_set_flags.py --threshold 0.35 # custom cut
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api

from dataclasses import dataclass

from database import SessionLocal
from models import DJSet, SetFlag, SetFlagStatus, SetFlagType
from services.set_dedup_service import (
    MatchSignals,
    MatchVerdict,
    decide_verdict,
    score_pair,
)
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

# Conservative default: the admin PREFERS arbitrating the mid-range cases by hand,
# the script only purges the obvious noise.
DEFAULT_THRESHOLD = 0.30

# Decision labels (also the report column value).
DECISION_KEPT = "GARDÉ"
DECISION_REJECTED = "AUTO-REJET"
DECISION_UNSCORABLE = "NON-RESCORABLE"


@dataclass
class RescoreOutcome:
    """Result of re-scoring one flag (what the report renders / a test asserts)."""

    flag_id: int
    set_id_a: int
    set_id_b: int
    title_a: str | None
    title_b: str | None
    old_confidence: float | None
    new_confidence: float | None  # None when non-rescorable
    verdict: MatchVerdict | None  # None when non-rescorable
    decision: str


def _signals_to_dict(signals: MatchSignals) -> dict:
    """Serialize MatchSignals exactly like apply_match_results does (same keys)."""
    return {
        "overlap": signals.overlap,
        "title_sim": signals.title_sim,
        "date_match": signals.date_match,
        "first_track_match": signals.first_track_match,
        "weighted_overlap": signals.weighted_overlap,
        "date_gap_days": signals.date_gap_days,
        "order_corr": signals.order_corr,
    }


async def _load_pending_pair_flags(db) -> list[SetFlag]:
    """Pending duplicate_candidate PAIR flags only (never group flags)."""
    stmt = (
        select(SetFlag)
        .where(
            SetFlag.flag_type == SetFlagType.duplicate_candidate,
            SetFlag.status == SetFlagStatus.pending,
            SetFlag.set_id_b.isnot(None),
            SetFlag.group_key.is_(None),
        )
        .order_by(SetFlag.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def rescore_flags(
    db, *, threshold: float = DEFAULT_THRESHOLD, apply: bool = False
) -> list[RescoreOutcome]:
    """Re-score every pending duplicate_candidate PAIR flag. Returns per-flag outcomes.

    Mutates the flags in-session when ``apply`` is True (confidence + signals on all
    re-scored flags; status=rejected + ``auto_rejected`` marker on the rejected ones).
    Does NOT commit — the caller owns the transaction boundary.
    """
    flags = await _load_pending_pair_flags(db)
    outcomes: list[RescoreOutcome] = []

    for flag in flags:
        scored = await score_pair(db, flag.set_id_a, flag.set_id_b)
        # score_pair already loaded both rows into the identity map → db.get is a
        # cache hit, no extra query (and never gathered — one shared session).
        set_a = await db.get(DJSet, flag.set_id_a)
        set_b = await db.get(DJSet, flag.set_id_b)
        title_a = set_a.title if set_a is not None else None
        title_b = set_b.title if set_b is not None else None

        if scored is None:
            outcomes.append(
                RescoreOutcome(
                    flag_id=flag.id,
                    set_id_a=flag.set_id_a,
                    set_id_b=flag.set_id_b,
                    title_a=title_a,
                    title_b=title_b,
                    old_confidence=flag.confidence,
                    new_confidence=None,
                    verdict=None,
                    decision=DECISION_UNSCORABLE,
                )
            )
            continue

        signals, confidence = scored
        part_a = set_a.part_number if set_a is not None else None
        part_b = set_b.part_number if set_b is not None else None
        verdict, _ = decide_verdict(signals, confidence, part_a, part_b)

        reject = confidence < threshold and verdict not in (
            MatchVerdict.FLAG,
            MatchVerdict.AUTO_ATTACH,
        )
        decision = DECISION_REJECTED if reject else DECISION_KEPT
        old_confidence = flag.confidence

        if apply:
            new_signals = _signals_to_dict(signals)
            if reject:
                new_signals["auto_rejected"] = True
                flag.status = SetFlagStatus.rejected
            flag.confidence = confidence
            flag.signals = new_signals
            # signals is a JSON column — SQLAlchemy needs the explicit mark
            # (same pattern as apply_match_results).
            flag_modified(flag, "signals")

        outcomes.append(
            RescoreOutcome(
                flag_id=flag.id,
                set_id_a=flag.set_id_a,
                set_id_b=flag.set_id_b,
                title_a=title_a,
                title_b=title_b,
                old_confidence=old_confidence,
                new_confidence=confidence,
                verdict=verdict,
                decision=decision,
            )
        )

    return outcomes


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _trunc(text: str | None, width: int = 28) -> str:
    if not text:
        return "?"
    return text if len(text) <= width else text[: width - 1] + "…"


def _fmt_conf(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else " -- "


def _print_report(outcomes: list[RescoreOutcome], threshold: float, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(
        f"=== Re-score flags duplicate_candidate (paires, pending) — "
        f"{mode}, seuil={threshold:.2f} ===\n"
    )

    if not outcomes:
        print("Aucun flag paire duplicate_candidate en attente. Rien à faire.")
        return

    for o in outcomes:
        verdict_label = o.verdict.value if o.verdict is not None else "--"
        print(
            f"  [flag {o.flag_id:>5}] "
            f"{_trunc(o.title_a)!r} <-> {_trunc(o.title_b)!r} "
            f"| conf {_fmt_conf(o.old_confidence)} -> {_fmt_conf(o.new_confidence)} "
            f"| verdict={verdict_label:<11} | {o.decision}"
        )

    kept = sum(1 for o in outcomes if o.decision == DECISION_KEPT)
    rejected = sum(1 for o in outcomes if o.decision == DECISION_REJECTED)
    unscorable = sum(1 for o in outcomes if o.decision == DECISION_UNSCORABLE)

    print(
        f"\n[résumé] {len(outcomes)} flag(s) re-scoré(s) — "
        f"GARDÉ={kept} | AUTO-REJET={rejected} | NON-RESCORABLE={unscorable}"
    )

    _print_distribution(outcomes)

    if apply:
        print(
            f"\n[apply] {rejected} flag(s) passé(s) en 'rejected' (auto_rejected), "
            f"{kept + rejected} confidence/signals mis à jour. Commit effectué."
        )
    else:
        print(
            "\n[dry-run] Aucune modification en base. "
            "Relancer avec --apply pour appliquer."
        )


def _print_distribution(outcomes: list[RescoreOutcome]) -> None:
    """Bucketed histogram of the new (composite) confidences."""
    scored = [o.new_confidence for o in outcomes if o.new_confidence is not None]
    if not scored:
        return
    buckets = [0] * 10  # [0.0-0.1), ..., [0.9-1.0]
    for c in scored:
        idx = min(int(c * 10), 9)
        buckets[idx] += 1
    print("[distribution des nouvelles confiances]")
    for i, count in enumerate(buckets):
        low = i / 10
        high = (i + 1) / 10
        bar = "#" * count
        print(f"  [{low:.1f}-{high:.1f}) {count:>4} {bar}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def run(threshold: float, apply: bool) -> None:
    async with SessionLocal() as db:
        outcomes = await rescore_flags(db, threshold=threshold, apply=apply)
        _print_report(outcomes, threshold, apply)
        if apply:
            await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-score pending duplicate_candidate set flags with the "
        "composite engine and auto-reject the obvious noise (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit the re-scores + auto-rejects (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"auto-reject cutoff on the composite confidence "
        f"(default: {DEFAULT_THRESHOLD}; conservative on purpose)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.threshold, args.apply))


if __name__ == "__main__":
    main()
