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
     them, so the script must not kill them. By default a recomputed ``AUTO_ATTACH``
     stays KEPT: the script attaches nothing — merging is a human decision on the
     admin page.

OPT-IN ``--auto-attach``: additionally ATTACH (merge under a virtual parent, via the
admin ``attach_flag`` action) the pairs that are certain duplicates — via three
vectors: (V1) the recomputed verdict is ``AUTO_ATTACH``; (V2) the tracklist is
byte-identical in the same order (overlap/order_corr >= 0.95 with >= 6 shared tracks);
(V3) the two sets carry the SAME reliable date (same full date in the title, or equal
``event_date``) AND their FOLDED titles are within a 0.90 character-level edit ratio —
INDEPENDENT of tracklist overlap, to catch a re-upload whose identified tracklists
diverge on identification noise but whose titles differ only in spelling
("… @ The Lot Radio 08-16-2023" vs "… @TheLotRadio 08-16-2023"). Two distinct gigs
never share the exact same ordered tracklist (V2) nor the same date + near-identical
title (V3), so this is safe; V2's shared-count floor keeps two short sets that merely
coincide on a few anthems apart. Divergent RELIABLE event dates still take precedence
and REJECT the pair before any attach. Without the flag the behaviour is unchanged.

``--auto-attach`` ALSO attaches pending GROUP flags of type ``part_candidate`` (a set
split into distinct part numbers — « … PART 1 » + « … PART 2 »). These are decided
STRUCTURALLY, not on confidence (which is low, being title-similarity based): a
part_candidate is a single set by construction, so it is attached under a shared
virtual parent (via ``attach_flag``) UNLESS its members carry divergent reliable event
dates (>= 2 distinct ``event_date`` = distinct episodes of an emission), in which case
it is LEFT pending. ``part_overlap_anomaly`` group flags are never touched.

In ``--apply`` the script rewrites ``confidence`` (composite) and ``signals`` (full
new dict) on EVERY re-scored flag — kept ones included, so the admin list re-sorts
on the true confidence. Rejected flags additionally get ``status = rejected`` and a
``"auto_rejected": true`` marker in ``signals`` (to tell them apart from manual
rejections). Attached flags get ``status = attached`` (confidence/signals left as-is,
``attach_flag`` owns the transition). It NEVER deletes a flag: a rejected flag is
memorised by its pair uniqueness (``uq_set_flag_pair``) and won't be recreated by
future imports.

OPT-IN ``--reject-episodes``: additionally REJECT a pair whose two titles both carry
an episode/volume/edition number that DIFFERS (« Spectrum Radio 200 » vs « … 251 »,
« Vol. 71 » vs « 72 ») — recurring homonymous emissions, never a duplicate. It fires
regardless of overlap, right after the event-date guard and before any attach.
Without the flag the behaviour is unchanged.

DRY-RUN by default: prints a readable table (flag id, truncated titles, old→new
confidence, recomputed verdict, KEPT / AUTO-REJECT / REJET-DATES / REJET-ÉPISODE /
AUTO-ATTACH / NON-RESCORABLE) plus a summary (counters + new-confidence distribution)
and writes NOTHING. Pass ``--apply`` to commit; a single commit at the end (~150 rows).

Usage (from the VPS):
    docker compose exec api python scripts/rescore_set_flags.py                 # dry-run
    docker compose exec api python scripts/rescore_set_flags.py --apply          # commit
    docker compose exec api python scripts/rescore_set_flags.py --threshold 0.35 # custom cut
    docker compose exec api python scripts/rescore_set_flags.py --auto-attach --apply
    docker compose exec api python scripts/rescore_set_flags.py --reject-episodes --apply
"""

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api

from dataclasses import dataclass

from database import SessionLocal
from models import DJSet, SetFlag, SetFlagStatus, SetFlagType
from services.set_dedup_service import (
    MatchSignals,
    MatchVerdict,
    _levenshtein_ratio,
    _load_set_scoring_data,
    _title_date_signatures,
    attach_flag,
    decide_verdict,
    score_pair,
)
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from utils import search_fold

# Conservative default: the admin PREFERS arbitrating the mid-range cases by hand,
# the script only purges the obvious noise.
DEFAULT_THRESHOLD = 0.30

# Identical-tracklist auto-attach (opt-in --auto-attach): a pair whose recomputed
# verdict is NOT AUTO_ATTACH but whose tracklist is byte-identical in the same order
# is still a re-uploaded duplicate (two distinct gigs never share the exact same
# ordered tracklist). Attach it regardless of the upload date. The shared-count floor
# avoids attaching two SHORT sets that happen to coincide on a few tracks.
IDENTICAL_ATTACH_OVERLAP = 0.95
IDENTICAL_ATTACH_ORDER = 0.95
IDENTICAL_ATTACH_MIN_SHARED = 6

# Near-duplicate title auto-attach (opt-in --auto-attach, V3): two uploads of the
# SAME set on the SAME reliable date whose titles differ only in spelling
# ("… @ The Lot Radio 08-16-2023" vs "… @TheLotRadio 08-16-2023") — the identified
# tracklists diverge (TrackID identification noise), so V1/V2 miss them. A
# character-level edit ratio on the folded titles catches the spelling drift that
# token_set_ratio misses. Attached only when the reliable date matches AND the
# folded titles are this close, INDEPENDENT of tracklist overlap.
TITLE_NEAR_DUP_LEV_RATIO = 0.90

# Decision labels (also the report column value).
DECISION_KEPT = "GARDÉ"
DECISION_REJECTED = "AUTO-REJET"
# L1 hard separator: decide_verdict returns NOTHING for two RELIABLE event_dates
# more than a day apart (distinct performances) — rejected regardless of the
# composite confidence, and counted apart from the low-confidence noise.
DECISION_EVENT_REJECTED = "REJET-DATES"
# Opt-in --auto-attach: pair merged under a virtual parent (verdict AUTO_ATTACH, or
# identical ordered tracklist). Never fires on divergent reliable event dates.
DECISION_AUTO_ATTACHED = "AUTO-ATTACH"
# Opt-in --reject-episodes: both titles carry an episode/volume/edition number and
# they DIFFER → recurring homonymous emissions (same show, distinct episodes), never
# a duplicate. Rejected regardless of overlap, after the event-date guard.
DECISION_EPISODE_REJECTED = "REJET-ÉPISODE"
DECISION_UNSCORABLE = "NON-RESCORABLE"

# --- Episode-number extraction (--reject-episodes) --------------------------
# A number tied to an emission keyword (radio 200, vol. 71, ep 12, #676, session 9)
# OR a bare number at the very end of the title. Deliberately conservative: any
# ambiguity → None (never reject a pair on a guessed number).
_EPISODE_KEYWORDS = (
    r"radio|podcast|show|episode|ep|volume|vol|edition|chapter|session|mix|nr|no"
)
_EPISODE_KEYWORD_RE = re.compile(
    rf"\b(?:{_EPISODE_KEYWORDS})\b\s*\.?\s*#?\s*(\d+)", re.IGNORECASE
)
_EPISODE_HASH_RE = re.compile(r"#\s*(\d+)")
_EPISODE_TRAILING_RE = re.compile(r"(\d+)\s*$")
# Part markers (part 2, pt. 3, p1) are handled by the group path, NOT here → abstain.
_PART_MARKER_RE = re.compile(r"\b(?:part|pt|p)\s*\.?\s*\d+\b", re.IGNORECASE)


def _is_year(n: int) -> bool:
    """A 4-digit year in a plausible range is NOT an episode number."""
    return 1990 <= n <= 2035


def _episode_number(title: str | None) -> tuple[str, int] | None:
    """Extract an unambiguous episode/volume/edition number from a set title.

    Returns ``(kind, number)`` where ``kind`` is:
      - ``"marker"``   : a number anchored to an emission keyword (radio 200,
                         vol. 71, ep 12, session 9) OR preceded by ``#`` — a
                         RELIABLE episode number;
      - ``"trailing"`` : a bare standalone number at the very end of the title —
                         often a date component or an artefact, WEAK.
    The distinction lets the caller reject a pair only when both numbers were
    extracted the SAME way (a marker vs a trailing number is not a divergence).

    Returns None when the title carries a PART marker (parts live on the group
    path), when the only candidate is a plausible year (1990-2035), or when no
    non-ambiguous number is found.
    """
    if not title:
        return None
    # Parts are a different relationship (handled by the group flag path).
    if _PART_MARKER_RE.search(title):
        return None
    # Keyword-anchored number first (most reliable), then a bare "#N" (both
    # "marker"), then a trailing standalone number ("trailing"). Years are
    # excluded at every step.
    for regex, kind in (
        (_EPISODE_KEYWORD_RE, "marker"),
        (_EPISODE_HASH_RE, "marker"),
        (_EPISODE_TRAILING_RE, "trailing"),
    ):
        for m in regex.finditer(title):
            n = int(m.group(1))
            if not _is_year(n):
                return (kind, n)
    return None


def _same_reliable_date(title_a, title_b, event_a, event_b) -> bool:
    """True when both sets share the SAME reliable date (V3 gate).

    Reliable = a full date in the TITLE (``_title_date_signatures`` equal and
    non-empty on both sides) OR a parsed ``event_date`` equal on both (both
    non-NULL). ``played_date`` is DELIBERATELY excluded — it is the upload date,
    not the performance date. Either signal matching is enough (an upload can
    carry the date in the title but not parse it into ``event_date`` and
    vice-versa).
    """
    sig_a = _title_date_signatures(title_a)
    if sig_a and sig_a == _title_date_signatures(title_b):
        return True
    return event_a is not None and event_a == event_b


@dataclass
class RescoreOutcome:
    """Result of re-scoring one flag (what the report renders / a test asserts).

    Two shapes share this record. A PAIR flag carries ``set_id_b`` + a
    ``new_confidence`` / ``verdict`` (the composite re-score). A GROUP flag
    (``part_candidate``, only surfaced under ``--auto-attach``) instead carries
    ``member_set_ids`` / ``member_titles`` and leaves ``set_id_b`` / verdict /
    confidence None — groups are decided structurally (coherent event dates →
    AUTO-ATTACH, divergent → KEPT), never via the confidence gate.
    """

    flag_id: int
    set_id_a: int | None
    set_id_b: int | None
    title_a: str | None
    title_b: str | None
    old_confidence: float | None
    new_confidence: float | None  # None when non-rescorable or a group flag
    verdict: MatchVerdict | None  # None when non-rescorable or a group flag
    decision: str
    member_set_ids: list[int] | None = None  # set only for a group flag
    member_titles: list[str] | None = None  # set only for a group flag


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


async def _load_pending_group_flags(db) -> list[SetFlag]:
    """Pending part_candidate GROUP flags only (never pair / overlap-anomaly flags).

    Mirror of ``_load_pending_pair_flags`` for the group path: a group flag has
    ``set_id_b IS NULL`` and its members live in ``member_set_ids``. Scope is
    STRICT ``part_candidate`` — ``part_overlap_anomaly`` group flags are never
    surfaced here (a genuine overlap anomaly is a human decision).
    """
    stmt = (
        select(SetFlag)
        .where(
            SetFlag.flag_type == SetFlagType.part_candidate,
            SetFlag.status == SetFlagStatus.pending,
            SetFlag.set_id_b.is_(None),
        )
        .order_by(SetFlag.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _group_event_dates_coherent(db, member_set_ids) -> bool:
    """True when at most ONE distinct non-NULL event_date across the members.

    A ``part_candidate`` has, by construction, distinct part numbers on the same
    base title → it is a single set split in parts, coherent by design. The only
    residual risk is two "parts" carrying DIVERGENT reliable event dates (two
    distinct episodes of an emission whose dates were stripped from the base
    title). So: 0 or 1 distinct event_date = coherent (True); >= 2 = divergent
    (False). ``member_set_ids`` is the JSON list of member ids.
    """
    member_ids = list(member_set_ids or [])
    if not member_ids:
        return True
    rows = (
        await db.execute(select(DJSet.event_date).where(DJSet.id.in_(member_ids)))
    ).all()
    distinct = {row[0] for row in rows if row[0] is not None}
    return len(distinct) <= 1


async def rescore_flags(
    db,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    apply: bool = False,
    auto_attach: bool = False,
    reject_episodes: bool = False,
) -> list[RescoreOutcome]:
    """Re-score every pending duplicate_candidate PAIR flag. Returns per-flag outcomes.

    Mutates the flags in-session when ``apply`` is True (confidence + signals on all
    re-scored flags; status=rejected + ``auto_rejected`` marker on the rejected ones).
    When ``auto_attach`` is True, a flag whose recomputed verdict is AUTO_ATTACH — or
    whose tracklist is identical in the same order (overlap/order >= 0.95, >= 6 shared
    tracks) — is instead ATTACHED under a virtual parent via ``attach_flag`` (the admin
    "attacher" action); its confidence/signals are left as-is (attach_flag flips the
    status). Divergent reliable event dates still take precedence and reject the pair.
    When ``reject_episodes`` is True, a pair whose two titles both carry an
    episode/volume/edition number that DIFFERS is rejected (recurring homonymous
    emissions) regardless of overlap, right after the event-date guard and before any
    attach.

    When ``auto_attach`` is True the pending ``part_candidate`` GROUP flags are ALSO
    processed (after the pairwise loop): a group whose members' event dates are
    coherent (<= 1 distinct reliable date) is ATTACHED under a shared virtual parent
    via ``attach_flag`` — no confidence gate — while a group with >= 2 distinct event
    dates is left pending (distinct episodes). ``part_overlap_anomaly`` is never
    touched. Does NOT commit — the caller owns the transaction boundary.
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

        # L1 hard separator: decide_verdict returns NOTHING for two distinct
        # performances regardless of the composite confidence — either two RELIABLE
        # event_dates more than a day apart, OR two RAW titles carrying different
        # full dates (order-agnostic, robust to the C13.e parser abstaining on D/M
        # ambiguity, so it fires even when one event_date is NULL). Reject the pair
        # outright (a high-confidence divergent pair the old confidence cut would
        # have KEPT), counted apart from the low-confidence noise auto-reject.
        event_divergent = verdict == MatchVerdict.NOTHING and (
            (
                signals.both_event_reliable
                and signals.date_gap_days is not None
                and signals.date_gap_days > 1
            )
            or signals.title_dates_diverge
        )

        # Attach eligibility (only when opted in): recomputed AUTO_ATTACH (the import
        # semantics) OR an identical ordered tracklist regardless of the upload date.
        # The shared-track count reuses the existing scoring loader (score_pair already
        # loaded both rows into the identity map → these are cache hits).
        is_attach = False
        if auto_attach:
            loaded_a = await _load_set_scoring_data(db, flag.set_id_a)
            loaded_b = await _load_set_scoring_data(db, flag.set_id_b)
            if loaded_a is not None and loaded_b is not None:
                mtids_a = set(loaded_a[1]["identified_mtids"])
                mtids_b = set(loaded_b[1]["identified_mtids"])
                shared = len(mtids_a & mtids_b)
                # V3: same reliable date + near-identical folded titles, INDEPENDENT
                # of overlap — a re-upload whose tracklists diverge on identification
                # noise ("The Lot Radio" vs "TheLotRadio", same date). event_divergent
                # still runs FIRST (below), so a divergent-date pair is never V3-attached.
                near_dup_title = _same_reliable_date(
                    title_a,
                    title_b,
                    set_a.event_date if set_a is not None else None,
                    set_b.event_date if set_b is not None else None,
                ) and (
                    _levenshtein_ratio(
                        search_fold(title_a or ""), search_fold(title_b or "")
                    )
                    >= TITLE_NEAR_DUP_LEV_RATIO
                )
                is_attach = (
                    verdict == MatchVerdict.AUTO_ATTACH
                    or (
                        signals.overlap >= IDENTICAL_ATTACH_OVERLAP
                        and signals.order_corr is not None
                        and signals.order_corr >= IDENTICAL_ATTACH_ORDER
                        and shared >= IDENTICAL_ATTACH_MIN_SHARED
                    )
                    or near_dup_title
                )

        # Divergent episode numbers (only when opted in): both titles carry an
        # episode/volume/edition number and they DIFFER → recurring homonymous
        # emissions (same resident, distinct episodes), never a duplicate — reject
        # regardless of overlap (a differing episode number outweighs a high overlap).
        episode_divergent = False
        if reject_episodes:
            ep_a = _episode_number(title_a)
            ep_b = _episode_number(title_b)
            # Only a divergence when BOTH numbers came from the same extraction
            # class (marker vs marker, or trailing vs trailing) — a marker number
            # (Radio 1) vs a trailing date component (…2025-03-22 → 22) is NOT.
            episode_divergent = (
                ep_a is not None
                and ep_b is not None
                and ep_a[0] == ep_b[0]
                and ep_a[1] != ep_b[1]
            )

        # Precedence: divergent reliable event dates reject FIRST (two performances,
        # never attach); THEN divergent episode numbers; THEN attach when eligible;
        # THEN the low-confidence noise cut.
        reject = False
        if event_divergent:
            reject = True
            decision = DECISION_EVENT_REJECTED
        elif episode_divergent:
            reject = True
            decision = DECISION_EPISODE_REJECTED
        elif is_attach:
            decision = DECISION_AUTO_ATTACHED
        else:
            reject = confidence < threshold and verdict not in (
                MatchVerdict.FLAG,
                MatchVerdict.AUTO_ATTACH,
            )
            decision = DECISION_REJECTED if reject else DECISION_KEPT
        old_confidence = flag.confidence

        if apply:
            if decision == DECISION_AUTO_ATTACHED:
                # attach_flag creates/reuses the virtual parent + flips status to
                # 'attached'. Do NOT also rewrite confidence/signals here.
                await attach_flag(db, flag.id, resolved_by=None)
            else:
                new_signals = _signals_to_dict(signals)
                if reject:
                    new_signals["auto_rejected"] = True
                    if event_divergent:
                        new_signals["event_date_separated"] = True
                    if episode_divergent:
                        new_signals["episode_separated"] = True
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

    # Group part_candidate flags (only when opted in). A part_candidate is a single
    # set split into distinct part numbers → structurally a duplicate, NOT gated on
    # confidence (which is low, being title-similarity based). Attach it when the
    # members' event dates are coherent (<= 1 distinct reliable date); leave it
    # pending when they diverge (>= 2 distinct dates = distinct episodes — a bad
    # merge costs more than an unmerged split, invariant #4). part_overlap_anomaly
    # is never surfaced (loader filters on part_candidate).
    if auto_attach:
        group_flags = await _load_pending_group_flags(db)
        for flag in group_flags:
            member_ids = list(flag.member_set_ids or [])
            members = (
                await db.execute(select(DJSet).where(DJSet.id.in_(member_ids)))
            ).scalars().all()
            member_titles = [m.title for m in members]
            # Coherent = at most ONE distinct date across the members, on BOTH
            # signals: the STORED event_date (C13.e, NULL on an ambiguous title)
            # AND the RAW title date signatures (order-agnostic, catches parts
            # whose differing dates were left unparsed → event_date NULL). Either
            # divergence (>= 2 distinct dates) is enough to leave the group pending.
            title_sigs: set = set()
            for t in member_titles:
                title_sigs |= _title_date_signatures(t)
            title_dates_coherent = len(title_sigs) <= 1
            coherent = (
                await _group_event_dates_coherent(db, member_ids)
                and title_dates_coherent
            )

            if coherent:
                decision = DECISION_AUTO_ATTACHED
                if apply:
                    # attach_flag's group branch builds the shared virtual parent
                    # and flips the flag to 'attached'.
                    await attach_flag(db, flag.id, resolved_by=None)
            else:
                decision = DECISION_KEPT  # divergent dates → left pending

            outcomes.append(
                RescoreOutcome(
                    flag_id=flag.id,
                    set_id_a=flag.set_id_a,
                    set_id_b=None,
                    title_a=None,
                    title_b=None,
                    old_confidence=flag.confidence,
                    new_confidence=None,
                    verdict=None,
                    decision=decision,
                    member_set_ids=member_ids,
                    member_titles=member_titles,
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
        if o.member_set_ids is not None:
            # Group (part_candidate) row: no set_id_b / verdict / confidence.
            titles = ", ".join(_trunc(t, 18) for t in (o.member_titles or [])) or "?"
            coherent = o.decision == DECISION_AUTO_ATTACHED
            print(
                f"  [flag {o.flag_id:>5}] GROUPE part_candidate "
                f"({len(o.member_set_ids)} membres: {titles}) "
                f"| dates {'cohérentes' if coherent else 'divergentes'} "
                f"| {o.decision}"
            )
            continue
        verdict_label = o.verdict.value if o.verdict is not None else "--"
        print(
            f"  [flag {o.flag_id:>5}] "
            f"{_trunc(o.title_a)!r} <-> {_trunc(o.title_b)!r} "
            f"| conf {_fmt_conf(o.old_confidence)} -> {_fmt_conf(o.new_confidence)} "
            f"| verdict={verdict_label:<11} | {o.decision}"
        )

    kept = sum(1 for o in outcomes if o.decision == DECISION_KEPT)
    rejected = sum(1 for o in outcomes if o.decision == DECISION_REJECTED)
    event_rejected = sum(1 for o in outcomes if o.decision == DECISION_EVENT_REJECTED)
    episode_rejected = sum(
        1 for o in outcomes if o.decision == DECISION_EPISODE_REJECTED
    )
    attached = sum(1 for o in outcomes if o.decision == DECISION_AUTO_ATTACHED)
    unscorable = sum(1 for o in outcomes if o.decision == DECISION_UNSCORABLE)
    # Group breakdown (part_candidate): attaches folded into AUTO-ATTACH, divergent
    # ones into GARDÉ — the pairwise-only kept count is derived by subtracting them
    # (groups never rewrite confidence/signals: they are attached or left pending).
    group_attached = sum(
        1
        for o in outcomes
        if o.decision == DECISION_AUTO_ATTACHED and o.member_set_ids is not None
    )
    group_kept = sum(
        1
        for o in outcomes
        if o.decision == DECISION_KEPT and o.member_set_ids is not None
    )
    pairwise_kept = kept - group_kept

    group_attach_note = (
        f" (dont {group_attached} groupe(s) de parts)" if group_attached else ""
    )
    print(
        f"\n[résumé] {len(outcomes)} flag(s) traité(s) — "
        f"GARDÉ={kept} | AUTO-REJET={rejected} | REJET-DATES={event_rejected} | "
        f"REJET-ÉPISODE={episode_rejected} | AUTO-ATTACH={attached}"
        f"{group_attach_note} | NON-RESCORABLE={unscorable}"
    )
    if group_kept:
        print(
            f"  ({group_kept} groupe(s) de parts laissé(s) pending — "
            f"dates d'événement divergentes)"
        )

    _print_distribution(outcomes)

    if apply:
        total_rejected = rejected + event_rejected + episode_rejected
        print(
            f"\n[apply] {total_rejected} flag(s) passé(s) en 'rejected' "
            f"(auto_rejected, dont {event_rejected} sur dates d'événement divergentes "
            f"et {episode_rejected} sur numéros d'épisode divergents), "
            f"{pairwise_kept + total_rejected} confidence/signals mis à jour. "
            f"Commit effectué."
        )
        if attached:
            print(
                f"[apply] {attached} flag(s) attaché(s) sous parent virtuel "
                f"(statut 'attached'){group_attach_note}."
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


async def run(
    threshold: float, apply: bool, auto_attach: bool, reject_episodes: bool
) -> None:
    async with SessionLocal() as db:
        outcomes = await rescore_flags(
            db,
            threshold=threshold,
            apply=apply,
            auto_attach=auto_attach,
            reject_episodes=reject_episodes,
        )
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
    parser.add_argument(
        "--auto-attach",
        action="store_true",
        help="attach (merge under a virtual parent) the flags whose verdict is "
        "AUTO_ATTACH or whose tracklist is identical in the same order "
        "(default: off — behaviour unchanged)",
    )
    parser.add_argument(
        "--reject-episodes",
        action="store_true",
        help="reject pairs whose two titles carry a DIFFERENT episode/volume/edition "
        "number (recurring homonymous emissions) (default: off — behaviour unchanged)",
    )
    args = parser.parse_args()
    asyncio.run(
        run(args.threshold, args.apply, args.auto_attach, args.reject_episodes)
    )


if __name__ == "__main__":
    main()
