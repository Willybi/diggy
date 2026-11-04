"""Entry control of the YouTube/TrackID twins: find a set's twin, attach or flag it.

Runs on a newly created YouTube set and on every TrackID (re-)import. The decision
itself lives in the pure ``set_twin_rules``; this module retrieves the candidates,
picks a single winner and records the outcome as a ``SetFlag``, which doubles as the
decision memory: a pair that already has a flag is never decided again, so a recrawl
can undo neither an admin rejection nor a detach.

Nothing here commits — the caller owns the transaction.
"""

import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from models import DJSet, SetFlag, SetFlagStatus, SetFlagType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.set_dedup_service import attach_pair
from services.set_twin_rules import (
    CHANNEL_STEP_MAX_DURATION_GAP,
    DATE_STEP_MAX_DURATION_GAP,
    TwinDecision,
    TwinInput,
    TwinVerdict,
    decide_twin,
    video_id_from_url,
)

logger = logging.getLogger(__name__)

TWIN_VIDEO_CANDIDATE_LIMIT = 50
# Largest group measured in prod: 146 sets on one event date.
TWIN_DATE_CANDIDATE_LIMIT = 200
# "Exactly one channel candidate" only holds on a complete list: past this cap the
# whole channel list is ignored, never a part of it.
TWIN_CHANNEL_CANDIDATE_CAP = 10_000

REASON_AMBIGUOUS = "ambiguous: several candidates"
REASON_ALREADY_IN_FAMILY = "youtube set already in another family"
REASON_YOUTUBE_SIDE_TRUNCATED = "youtube set has too many channel candidates"

_STEP_RANK = {"video": 0, "date": 1, "channel": 2}

_YOUTUBE_WATCH_HOSTS = (
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
)

# Plain columns, never ORM entities: this runs once per incoming set during long
# crawls (AV12 memory lesson).
_ROW_COLUMNS = (
    DJSet.id,
    DJSet.title,
    DJSet.channel,
    DJSet.channel_canonical,
    DJSet.duration_ms,
    DJSet.event_date,
    DJSet.played_date,
    DJSet.part_number,
    DJSet.source_url,
    DJSet.external_id,
    DJSet.source,
    DJSet.unreliable,
    DJSet.is_virtual,
    DJSet.parent_set_id,
)


@dataclass(frozen=True)
class _Evaluated:
    row: object
    decision: TwinDecision


@dataclass(frozen=True)
class _Choice:
    target: _Evaluated
    attach: bool
    reason: str
    # Candidates the choice was made between: one with a decision on record freezes
    # the whole choice.
    contested: tuple[_Evaluated, ...]


@dataclass(frozen=True)
class TwinPlan:
    """What the control decided for one set. ``winner_id`` is None when nothing is to do."""

    set_id: int
    candidates: int = 0
    channel_truncated: bool = False
    decided: bool = False  # a flag already on record froze the choice
    winner_id: int | None = None
    winner_family_id: int | None = None
    verdict: TwinVerdict | None = None  # ATTACH or REVIEW when there is a winner
    step: str | None = None
    reason: str | None = None
    signals: dict | None = None


def _is_youtube(row) -> bool:
    return row.source == "youtube"


def _family(row) -> int:
    return row.parent_set_id if row.parent_set_id is not None else row.id


def _to_input(row) -> TwinInput:
    return TwinInput(
        title=row.title,
        channel=row.channel,
        channel_canonical=row.channel_canonical,
        duration_ms=row.duration_ms,
        event_date=row.event_date,
        part_number=row.part_number,
        source_url=row.source_url,
        external_id=row.external_id,
        source=row.source,
        unreliable=row.unreliable,
        # Only the publication date of a YouTube set is reliable.
        upload_date=row.played_date if _is_youtube(row) else None,
    )


def _canonical_video_urls(video_id: str) -> list[str]:
    paths = [f"youtu.be/{video_id}"]
    for host in _YOUTUBE_WATCH_HOSTS:
        paths += [
            f"{host}/watch?v={video_id}",
            f"{host}/live/{video_id}",
            f"{host}/embed/{video_id}",
        ]
    return [f"{scheme}://{path}" for scheme in ("https", "http") for path in paths]


def _duration_window(duration_ms: int, max_gap: float) -> tuple[int, int]:
    """Bounds of ``max_gap``, measured like decide_twin (gap over the longest duration).

    Symmetric on purpose: two sets see each other whichever one arrives first.
    """
    keep = 1 - max_gap
    return math.floor(duration_ms * keep), math.ceil(duration_ms / keep)


async def _load_row(db: AsyncSession, set_id: int):
    return (
        await db.execute(select(*_ROW_COLUMNS).where(DJSet.id == set_id))
    ).first()


async def _search_candidates(db: AsyncSession, row) -> tuple[list, bool]:
    """Sets that could be the twin of ``row``, children of a family included.

    Sequential queries on one session. Returns the candidates and whether the channel
    list was over its cap and left out, in which case only the video and date
    searches contributed.
    """
    base = select(*_ROW_COLUMNS).where(
        DJSet.id != row.id,
        DJSet.is_virtual.is_(False),
        DJSet.unreliable.is_(False),
        DJSet.source != "youtube" if _is_youtube(row) else DJSet.source == "youtube",
    ).order_by(DJSet.id)
    capped_queries = []

    if _is_youtube(row):
        if row.external_id:
            capped_queries.append(
                base.where(
                    DJSet.source_url.in_(_canonical_video_urls(row.external_id))
                ).limit(TWIN_VIDEO_CANDIDATE_LIMIT)
            )
    else:
        video_id = video_id_from_url(row.source_url)
        if video_id:
            capped_queries.append(
                base.where(DJSet.external_id == video_id).limit(
                    TWIN_VIDEO_CANDIDATE_LIMIT
                )
            )

    if row.duration_ms and row.event_date:
        low, high = _duration_window(row.duration_ms, DATE_STEP_MAX_DURATION_GAP)
        capped_queries.append(
            base.where(
                DJSet.event_date == row.event_date,
                DJSet.duration_ms.between(low, high),
            ).limit(TWIN_DATE_CANDIDATE_LIMIT)
        )

    found = {}
    for query in capped_queries:
        for candidate in (await db.execute(query)).all():
            found[candidate.id] = candidate

    channel_truncated = False
    if row.duration_ms and row.channel_canonical:
        low, high = _duration_window(row.duration_ms, CHANNEL_STEP_MAX_DURATION_GAP)
        candidates = (
            await db.execute(
                base.where(
                    DJSet.channel_canonical == row.channel_canonical,
                    DJSet.duration_ms.between(low, high),
                ).limit(TWIN_CHANNEL_CANDIDATE_CAP + 1)
            )
        ).all()
        channel_truncated = len(candidates) > TWIN_CHANNEL_CANDIDATE_CAP
        if channel_truncated:
            logger.warning(
                "twin search: channel list of set %s over %s candidates, ignored",
                row.id,
                TWIN_CHANNEL_CANDIDATE_CAP,
            )
        else:
            found.update((candidate.id, candidate) for candidate in candidates)

    return list(found.values()), channel_truncated


async def _evaluate(db: AsyncSession, row) -> tuple[list[_Evaluated], bool]:
    """Decide every candidate of ``row``, keeping the ones that are not a NOTHING.

    The bool is the channel truncation of the search.
    """
    candidates, channel_truncated = await _search_candidates(db, row)
    evaluated = []
    for candidate in candidates:
        # Already in the same family: nothing left to decide.
        if row.parent_set_id is not None and candidate.parent_set_id == row.parent_set_id:
            continue
        yt, other = (row, candidate) if _is_youtube(row) else (candidate, row)
        decision = decide_twin(_to_input(yt), _to_input(other))
        if decision.verdict != TwinVerdict.NOTHING:
            evaluated.append(_Evaluated(candidate, decision))
    return evaluated, channel_truncated


def _lowest_id(items: list[_Evaluated]) -> _Evaluated:
    return min(items, key=lambda e: e.row.id)


def _choose(row, evaluated: list[_Evaluated]) -> _Choice | None:
    """Pick the single outcome of a call among the decided candidates.

    A video match is certain and a date match on a YouTube set nearly so. Otherwise
    the candidates in contention must come down to one family, else a human decides.
    For a YouTube set only the channel matches contend; for a TrackID set any two
    videos aiming at it outside the video step do.
    """
    attaches = [e for e in evaluated if e.decision.verdict == TwinVerdict.ATTACH]

    def attach_to(items: list[_Evaluated]) -> _Choice:
        target = _lowest_id(items)
        return _Choice(target, True, target.decision.reason, (target,))

    videos = [e for e in attaches if e.decision.step == "video"]
    if videos:
        return attach_to(videos)

    contested = attaches
    if _is_youtube(row):
        dates = [e for e in attaches if e.decision.step == "date"]
        if dates:
            return attach_to(dates)
        contested = [e for e in attaches if e.decision.step == "channel"]

    if len({_family(e.row) for e in contested}) >= 2:
        closest = min(
            contested,
            key=lambda e: (abs(e.row.duration_ms - row.duration_ms), e.row.id),
        )
        return _Choice(closest, False, REASON_AMBIGUOUS, tuple(contested))
    if contested:
        best_rank = min(_STEP_RANK[e.decision.step] for e in contested)
        return attach_to(
            [e for e in contested if _STEP_RANK[e.decision.step] == best_rank]
        )

    reviews = [e for e in evaluated if e.decision.verdict == TwinVerdict.REVIEW]
    if reviews:
        best_rank = min(_STEP_RANK[e.decision.step] for e in reviews)
        target = _lowest_id(
            [e for e in reviews if _STEP_RANK[e.decision.step] == best_rank]
        )
        return _Choice(target, False, target.decision.reason, (target,))
    return None


async def _families_with_decision(
    db: AsyncSession, row, candidates: list
) -> set[int]:
    """Families of ``candidates`` a flag already separates or joins to ``row``'s family.

    Read at family level: a rejection on one child must not be undone through its
    sibling.
    """
    rows = [row, *candidates]
    family_of = {r.id: _family(r) for r in rows}
    parent_ids = {r.parent_set_id for r in rows if r.parent_set_id is not None}
    if parent_ids:
        siblings = await db.execute(
            select(DJSet.id, DJSet.parent_set_id).where(
                DJSet.parent_set_id.in_(parent_ids)
            )
        )
        family_of.update({sid: parent_id for sid, parent_id in siblings})

    ids = list(family_of)
    flags = await db.execute(
        select(SetFlag.set_id_a, SetFlag.set_id_b).where(
            SetFlag.set_id_a.in_(ids), SetFlag.set_id_b.in_(ids)
        )
    )
    own = _family(row)
    decided = set()
    for id_a, id_b in flags:
        family_a, family_b = family_of[id_a], family_of[id_b]
        if family_a == own and family_b != own:
            decided.add(family_b)
        elif family_b == own and family_a != own:
            decided.add(family_a)
    return decided


async def _youtube_side_objection(db: AsyncSession, row, youtube_row) -> str | None:
    """Why a TrackID set must not take this video outside the video step, if any.

    A pair is only ever seen from the set being imported. Without this check, the
    recrawl of one episode would take a video that is ambiguous between two episodes
    (that pair has no flag), and a video already in a family would drag the TrackID
    set in, merging two tracklists on weak evidence. A video whose channel list was
    left out cannot vouch for its choice either.
    """
    if youtube_row.parent_set_id is not None:
        return REASON_ALREADY_IN_FAMILY
    evaluated, channel_truncated = await _evaluate(db, youtube_row)
    if channel_truncated:
        return REASON_YOUTUBE_SIDE_TRUNCATED
    choice = _choose(youtube_row, evaluated)
    if choice is None or not choice.attach or _family(choice.target.row) != _family(row):
        return REASON_AMBIGUOUS
    return None


def _add_flag(db: AsyncSession, plan: TwinPlan, status: SetFlagStatus) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        SetFlag(
            set_id_a=min(plan.set_id, plan.winner_id),
            set_id_b=max(plan.set_id, plan.winner_id),
            flag_type=SetFlagType.duplicate_candidate,
            confidence=None,
            signals={
                **plan.signals,
                "twin_rule": plan.step,
                "reason": plan.reason,
            },
            status=status,
            resolved_at=now if status == SetFlagStatus.attached else None,
            created_at=now,
        )
    )


async def plan_twin_for_set(db: AsyncSession, set_id: int) -> TwinPlan:
    """Decide what the control would do for ``set_id``, without writing anything.

    The plan has no winner on a virtual set, an unreliable TrackID set, a source other
    than YouTube/TrackID, a set without a twin, or a choice a flag already froze.
    """
    plan = TwinPlan(set_id=set_id)

    row = await _load_row(db, set_id)
    if row is None or row.is_virtual or row.source not in ("youtube", "trackid"):
        return plan
    if not _is_youtube(row) and row.unreliable:
        return plan

    evaluated, channel_truncated = await _evaluate(db, row)
    plan = replace(
        plan, candidates=len(evaluated), channel_truncated=channel_truncated
    )
    choice = _choose(row, evaluated)
    if choice is None:
        return plan

    decided = await _families_with_decision(db, row, [e.row for e in evaluated])
    if any(_family(e.row) in decided for e in choice.contested):
        return replace(plan, decided=True)

    if (
        choice.attach
        and not _is_youtube(row)
        and choice.target.decision.step != "video"
    ):
        objection = await _youtube_side_objection(db, row, choice.target.row)
        if objection:
            choice = replace(choice, attach=False, reason=objection)

    decision = choice.target.decision
    return replace(
        plan,
        winner_id=choice.target.row.id,
        winner_family_id=_family(choice.target.row),
        verdict=TwinVerdict.ATTACH if choice.attach else TwinVerdict.REVIEW,
        step=decision.step,
        reason=choice.reason,
        signals=decision.signals,
    )


async def apply_twin_plan(db: AsyncSession, plan: TwinPlan) -> dict:
    """Write a plan that has a winner: attach the pair or flag it. Returns counters.

    Does not commit.
    """
    counts = {"attached": 0, "flagged": 0, "attach_errors": 0}

    if plan.verdict == TwinVerdict.ATTACH:
        try:
            await attach_pair(db, plan.set_id, plan.winner_id)
        except ValueError:
            logger.info(
                "twin attach refused for sets %s and %s",
                plan.set_id,
                plan.winner_id,
                exc_info=True,
            )
            counts["attach_errors"] += 1
            return counts
        _add_flag(db, plan, SetFlagStatus.attached)
        counts["attached"] += 1
    else:
        _add_flag(db, plan, SetFlagStatus.pending)
        counts["flagged"] += 1

    # Inside the caller's savepoint: a constraint error must surface there.
    await db.flush()
    return counts


async def reconcile_twins_for_set(db: AsyncSession, set_id: int) -> dict:
    """Attach ``set_id`` to its twin or flag the pair for review. Returns counters.

    At most one attachment per call. Does nothing on a virtual set, an unreliable
    TrackID set or a source other than YouTube/TrackID. Does not commit.
    """
    plan = await plan_twin_for_set(db, set_id)
    counts = {
        "candidates": plan.candidates,
        "attached": 0,
        "flagged": 0,
        "decided": int(plan.decided),
        "attach_errors": 0,
        "channel_truncated": int(plan.channel_truncated),
    }
    if plan.winner_id is not None:
        counts.update(await apply_twin_plan(db, plan))
    return counts


async def reconcile_twins_best_effort(db: AsyncSession, dj_set: DJSet) -> dict | None:
    """Run the reconcile in a savepoint; a failure never costs the caller its set.

    A savepoint rollback expires what it touched, and a lazy reload would raise on an
    async session: ``dj_set`` is refreshed so the caller can keep reading it.
    """
    set_id = dj_set.id
    try:
        async with db.begin_nested():
            return await reconcile_twins_for_set(db, set_id)
    except Exception:
        logger.warning("twin reconcile failed for set %s", set_id, exc_info=True)

    try:
        await db.refresh(dj_set)
    except Exception:
        logger.warning(
            "refresh after twin reconcile failed for set %s", set_id, exc_info=True
        )
    return None
