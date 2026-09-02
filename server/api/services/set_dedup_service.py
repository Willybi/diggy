"""Set deduplication service — title normalization + matching engine (C6.0)."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from math import log2
from statistics import median as _median

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils import normalize, search_fold

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class NormalizedTitle:
    text: str
    base_title: str
    part_number: int | None
    part_total: int | None
    extracted_date: date | None


# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

_RE_AT_SPACE = re.compile(r"@(\S)")
_RE_SEPARATORS = re.compile(r" \| | \u2013 | \u2014 ")  # | / en-dash / em-dash
_RE_DATE_BRACKETS = re.compile(r"\[(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\]")
_RE_DATE_PARENS = re.compile(r"\((\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\)")
_RE_DATE_BARE = re.compile(r"(\d{2})[.\-](\d{2})[.\-](\d{4})$")
_RE_SPACES = re.compile(r"\s+")
# Branch 1: standard digit suffix — part N / pt N / p N
_RE_PART = re.compile(r"(?:part|pt\.?|p)\s*(\d+)\s*$", re.IGNORECASE)
# Branch 2: roman numeral (keyword required to avoid false positives on event editions)
_RE_PART_ROMAN = re.compile(
    r"(?:part|pt\.?)\s+(I{1,3}|IV|VI{0,3}|V|IX|X)\s*$", re.IGNORECASE
)
_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
}
# Anti-date guard: M/D/YY or D/M/YYYY patterns with 3 components
_RE_DATE_FRACTION = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\s*$")
# Branch 3: fraction N/M
_RE_PART_FRACTION = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*$")

_DECO_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\[full set hd\]",
        r"\[full set\]",
        r"\[4k\]",
        r"\[hd\]",
        r"\(official video\)",
        r"\(official\)",
        r"official video",
        r"\[official\]",
        r"\(full set\)",
    )
]

# Channel prefix separators: hyphen-minus and en-dash
_CHANNEL_SEPS = (" - ", " \u2013 ")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(day: str, month: str, year: str) -> date | None:
    """Convert day/month/year strings to a date; expands 2-digit years."""
    try:
        d, m, y = int(day), int(month), int(year)
        if y < 100:
            y = 2000 + y if y <= 50 else 1900 + y
        return date(y, m, d)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_set_title(
    raw_title: str, channel: str | None = None
) -> NormalizedTitle:
    """Normalize a DJ set title for deduplication matching.

    Applies transformations in this exact order:
    1. Underscores → spaces
    2. Strip channel prefix  ('{channel} - ' / '{channel} – ')
    3. Strip channel watermark suffix  ('-{channel}' / '- {channel}')
    4. Normalise @ spacing  ('@word' → '@ word')
    5. Unify separators  (' | ', ' – ', ' — ' → ' - ')
    6. Extract and remove date patterns; store in extracted_date
    7. Strip decorative tags
    8. Collapse whitespace + strip
    9. Lowercase
    10. Extract part number; compute base_title
    """
    titre = raw_title.replace("_", " ")

    # 2. Strip channel prefix (case-insensitive, first 40 chars heuristic)
    if channel:
        for sep in _CHANNEL_SEPS:
            prefix = channel + sep
            if titre.lower().startswith(prefix.lower()):
                titre = titre[len(prefix) :]
                break

    # 3. Strip channel watermark suffix (case-insensitive)
    if channel:
        for suffix in (f"-{channel}", f"- {channel}"):
            if titre.lower().endswith(suffix.lower()):
                titre = titre[: -len(suffix)].rstrip()
                break

    # 4. Normalise @ spacing: "@word" → "@ word"
    titre = _RE_AT_SPACE.sub(r"@ \1", titre)

    # 5. Unify separators
    titre = _RE_SEPARATORS.sub(" - ", titre)

    # 6. Extract and remove dates (first match wins)
    extracted_date: date | None = None
    for regex in (_RE_DATE_BRACKETS, _RE_DATE_PARENS, _RE_DATE_BARE):
        m = regex.search(titre)
        if m:
            extracted_date = _parse_date(m.group(1), m.group(2), m.group(3))
            titre = regex.sub("", titre, count=1)
            break

    # 7. Strip decorative tags
    for pat in _DECO_PATTERNS:
        titre = pat.sub("", titre)

    # 8. Collapse whitespace
    titre = _RE_SPACES.sub(" ", titre).strip()

    # 9. Lowercase
    titre = titre.lower()

    # 10. Extract part number (three branches, tested in order)
    part_number: int | None = None
    part_total: int | None = None
    base_title: str = titre

    # Branch 1: standard digit suffix (part N / pt N / p N)
    pm = _RE_PART.search(titre)
    if pm:
        part_number = int(pm.group(1))
        base_title = titre[: pm.start()].rstrip(" -")
    else:
        # Branch 2: roman numeral with obligatory part/pt keyword
        rm = _RE_PART_ROMAN.search(titre)
        if rm:
            part_number = _ROMAN_MAP[rm.group(1).upper()]
            base_title = titre[: rm.start()].rstrip(" -")
        else:
            # Branch 3: fraction N/M — anti-date guard first
            if not _RE_DATE_FRACTION.search(titre):
                fm = _RE_PART_FRACTION.search(titre)
                if fm:
                    n, m_val = int(fm.group(1)), int(fm.group(2))
                    if n <= m_val and 2 <= m_val <= 20:
                        part_number = n
                        part_total = m_val
                        base_title = titre[: fm.start()].rstrip(" -")

    return NormalizedTitle(
        text=titre,
        base_title=base_title,
        part_number=part_number,
        part_total=part_total,
        extracted_date=extracted_date,
    )


# ---------------------------------------------------------------------------
# Matching types (L3)
# ---------------------------------------------------------------------------

# Composite confidence below this never flags (title-identical rule aside)
FLAG_CONFIDENCE_THRESHOLD = 0.45
# Two known played_dates further apart than this block AUTO_ATTACH
AUTO_ATTACH_MAX_DATE_GAP_DAYS = 2


class MatchVerdict(str, Enum):
    AUTO_ATTACH = "auto_attach"
    FLAG = "flag"
    NOTHING = "nothing"


@dataclass
class MatchSignals:
    overlap: float
    title_sim: float
    date_match: bool
    first_track_match: bool
    # IDF-weighted overlap: anthems shared across many sets weigh less
    weighted_overlap: float = 0.0
    # Absolute gap in days between played_dates; None if either is unknown
    date_gap_days: int | None = None
    # Spearman rank correlation on shared-track positions; None if < 3 shared
    order_corr: float | None = None


@dataclass
class MatchCandidate:
    set_id: int
    shared_count: int
    total_identified: int  # nb identified tracks (is_id=False) in candidate set


@dataclass
class MatchResult:
    candidate_id: int
    signals: MatchSignals
    verdict: MatchVerdict
    flag_type: str | None  # "duplicate_candidate" or None
    confidence: float = 0.0


@dataclass
class GroupMatchResult:
    group_key: str
    member_set_ids: list[int]
    signals: dict
    confidence: float
    flag_type: str  # "part_candidate" | "part_overlap_anomaly"


# ---------------------------------------------------------------------------
# Helpers (L3)
# ---------------------------------------------------------------------------


def token_set_ratio(a: str, b: str) -> float:
    """Jaccard similarity on token sets (no external dependencies)."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Candidate generation (L3)
# ---------------------------------------------------------------------------


async def get_match_candidates(
    db: AsyncSession,
    set_id: int,
    incoming_mtids: list[int],
) -> list[MatchCandidate]:
    """Return sets sharing >= 3 identified tracks with the given set."""
    if len(incoming_mtids) < 3:
        return []

    from models import DJSet, SetTrack

    stmt = (
        select(
            SetTrack.set_id,
            func.count().label("shared"),
        )
        .join(DJSet, DJSet.id == SetTrack.set_id)
        .where(
            SetTrack.trackid_music_track_id.in_(incoming_mtids),
            SetTrack.is_id.is_(False),
            DJSet.is_virtual.is_(False),
            DJSet.id != set_id,
        )
        .group_by(SetTrack.set_id)
        .having(func.count() >= 3)
    )
    rows = (await db.execute(stmt)).all()

    results = []
    for row in rows:
        total_q = (
            select(func.count())
            .select_from(SetTrack)
            .where(
                SetTrack.set_id == row.set_id,
                SetTrack.is_id.is_(False),
            )
        )
        total = (await db.execute(total_q)).scalar_one()
        results.append(
            MatchCandidate(
                set_id=row.set_id,
                shared_count=row.shared,
                total_identified=total,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Part-candidate generation (C6.1)
# ---------------------------------------------------------------------------


def _compute_base_title(normalized_title: str) -> str:
    """Strip part suffix from a normalized title to get the grouping base_title."""
    for regex in (_RE_PART, _RE_PART_ROMAN):
        m = regex.search(normalized_title)
        if m:
            return normalized_title[: m.start()].rstrip(" -")
    if not _RE_DATE_FRACTION.search(normalized_title):
        m = _RE_PART_FRACTION.search(normalized_title)
        if m:
            n, m_val = int(m.group(1)), int(m.group(2))
            if n <= m_val and 2 <= m_val <= 20:
                return normalized_title[: m.start()].rstrip(" -")
    return normalized_title


def _validate_part_group(members: list[dict]) -> bool:
    """Return True if the group of part-members is coherent.

    members: list of {"id": int, "part_number": int, "part_total": int|None}
    Rules:
    - part_numbers must be distinct (two copies of Part 1 are duplicates, not parts)
    - If part_total is set on any member, all non-None part_totals must be identical
    """
    part_numbers = [m["part_number"] for m in members]
    if len(set(part_numbers)) != len(part_numbers):
        return False
    totals = [m["part_total"] for m in members if m["part_total"] is not None]
    if len(set(totals)) > 1:
        return False
    return True


def _compute_pairwise_overlap(mtids_a: list[int], mtids_b: list[int]) -> float:
    """Compute overlap ratio: shared / min(len_a, len_b)."""
    if not mtids_a or not mtids_b:
        return 0.0
    shared = len(set(mtids_a) & set(mtids_b))
    return shared / min(len(mtids_a), len(mtids_b))


async def get_part_candidates(
    db: AsyncSession,
    set_id: int,
    part_number: int,
    normalized_title: str,
) -> list[dict]:
    """Return physical sets whose base_title is similar enough to be parts of the same set.

    Returns list of {"id", "part_number", "part_total", "played_date", "normalized_title"}.
    """
    from models import DJSet

    base_title_incoming = _compute_base_title(normalized_title)
    if not base_title_incoming:
        return []

    candidates = (
        await db.execute(
            select(DJSet).where(
                DJSet.is_virtual.is_(False),
                DJSet.id != set_id,
                DJSet.part_number.isnot(None),
                DJSet.normalized_title.isnot(None),
            )
        )
    ).scalars().all()

    results = []
    for c in candidates:
        base_title_cand = _compute_base_title(c.normalized_title)
        if token_set_ratio(base_title_incoming, base_title_cand) >= 0.85:
            results.append(
                {
                    "id": c.id,
                    "part_number": c.part_number,
                    "part_total": c.part_total,
                    "played_date": c.played_date,
                    "normalized_title": c.normalized_title,
                }
            )
    return results


async def _build_group_match_result(
    db: AsyncSession,
    incoming_set_id: int,
    incoming_part_number: int,
    incoming_part_total: int | None,
    incoming_played_date,
    incoming_normalized_title: str,
    candidate_members: list[dict],
) -> GroupMatchResult:
    """Build a GroupMatchResult from the incoming set + candidate members."""
    from models import SetTrack

    # All members including the incoming set
    all_members = candidate_members + [
        {
            "id": incoming_set_id,
            "part_number": incoming_part_number,
            "part_total": incoming_part_total,
            "played_date": incoming_played_date,
            "normalized_title": incoming_normalized_title,
        }
    ]

    member_ids = [m["id"] for m in all_members]
    base_title = _compute_base_title(incoming_normalized_title)

    # Load mtids for all members
    member_mtids: dict[int, list[int]] = {}
    for mid in member_ids:
        rows = (
            await db.execute(
                select(SetTrack.trackid_music_track_id)
                .where(
                    SetTrack.set_id == mid,
                    SetTrack.is_id.is_(False),
                    SetTrack.trackid_music_track_id.isnot(None),
                )
            )
        ).scalars().all()
        member_mtids[mid] = list(rows)

    # Pairwise overlaps
    pairwise_max = 0.0
    for i in range(len(member_ids)):
        for j in range(i + 1, len(member_ids)):
            ov = _compute_pairwise_overlap(
                member_mtids[member_ids[i]], member_mtids[member_ids[j]]
            )
            if ov > pairwise_max:
                pairwise_max = ov

    flag_type = "part_overlap_anomaly" if pairwise_max > 0.30 else "part_candidate"

    # Title similarities between all pairs (min)
    title_sims = []
    for i in range(len(all_members)):
        for j in range(i + 1, len(all_members)):
            title_sims.append(
                token_set_ratio(
                    all_members[i]["normalized_title"] or "",
                    all_members[j]["normalized_title"] or "",
                )
            )
    title_sim_min = min(title_sims) if title_sims else 1.0

    # Date span
    dates = [m["played_date"] for m in all_members if m["played_date"] is not None]
    date_span_days = (max(dates) - min(dates)).days if len(dates) >= 2 else 0

    # Consistent part_total
    totals = [m["part_total"] for m in all_members if m["part_total"] is not None]
    part_total = totals[0] if len(set(totals)) == 1 else None

    part_numbers = sorted(m["part_number"] for m in all_members)

    signals = {
        "group_key": base_title,
        "title_sim_min": round(title_sim_min, 4),
        "part_numbers": part_numbers,
        "part_total": part_total,
        "pairwise_overlaps_max": round(pairwise_max, 4),
        "date_span_days": date_span_days,
        "member_count": len(all_members),
    }

    # Confidence formula
    confidence = title_sim_min
    # Bonus: consecutive complete sequence
    if part_total and sorted(part_numbers) == list(range(1, part_total + 1)):
        confidence = min(1.0, confidence + 0.05)
    elif part_total and len(part_numbers) == part_total:
        confidence = min(1.0, confidence + 0.03)
    # Malus: very long date span suggests recurring series
    if date_span_days > 60:
        confidence = max(0.0, confidence - 0.10)
    # Malus: members with no identified tracks
    empty_members = sum(1 for mid in member_ids if not member_mtids[mid])
    if empty_members:
        confidence = max(0.0, confidence - 0.05 * empty_members)

    return GroupMatchResult(
        group_key=base_title,
        member_set_ids=sorted(member_ids),
        signals=signals,
        confidence=round(confidence, 4),
        flag_type=flag_type,
    )


# ---------------------------------------------------------------------------
# Signal computation (L3)
# ---------------------------------------------------------------------------


def _idf_weight(df: int) -> float:
    """IDF weight of a track: 1 / log2(1 + df). df=1 (unique) → 1.0."""
    return 1.0 / log2(1 + max(df, 1))


def _weighted_overlap(
    mtids_a: list[int],
    mtids_b: list[int],
    mtid_df: dict[int, int],
) -> float:
    """Rarity-weighted overlap: shared weight / total weight of the smaller set.

    Anthems (high df) contribute little; rare tracks dominate. Same denominator
    convention as the raw overlap: the set with fewer identified mtids.
    """
    set_a, set_b = set(mtids_a), set(mtids_b)
    smaller = set_a if len(mtids_a) <= len(mtids_b) else set_b
    denom = sum(_idf_weight(mtid_df.get(m, 1)) for m in smaller)
    if denom == 0:
        return 0.0
    shared = sum(_idf_weight(mtid_df.get(m, 1)) for m in set_a & set_b)
    return shared / denom


def _order_correlation(mtids_a: list[int], mtids_b: list[int]) -> float | None:
    """Spearman rank correlation on shared-track positions (first occurrence).

    A re-upload of the same set shares the ORDER of its tracks; two different
    sets sharing genre anthems do not. None if fewer than 3 shared tracks.
    """
    idx_a: dict[int, int] = {}
    for i, m in enumerate(mtids_a):
        idx_a.setdefault(m, i)
    idx_b: dict[int, int] = {}
    for i, m in enumerate(mtids_b):
        idx_b.setdefault(m, i)

    shared = [m for m in idx_a if m in idx_b]
    n = len(shared)
    if n < 3:
        return None

    rank_a = {m: r for r, m in enumerate(sorted(shared, key=lambda m: idx_a[m]))}
    rank_b = {m: r for r, m in enumerate(sorted(shared, key=lambda m: idx_b[m]))}
    d_squared = sum((rank_a[m] - rank_b[m]) ** 2 for m in shared)
    return 1.0 - 6.0 * d_squared / (n * (n * n - 1))


def compute_signals(
    set_a_data: dict,
    set_b_data: dict,
    shared_count: int,
    mtid_df: dict[int, int] | None = None,
) -> MatchSignals:
    """Compute matching signals from injected set data (no DB access, fully testable).

    set_a_data / set_b_data keys: normalized_title, played_date, identified_mtids
    (ordered by position). mtid_df maps mtid → nb of distinct sets containing it
    (missing key → 1, i.e. unique track).
    """
    mtids_a = set_a_data["identified_mtids"]
    mtids_b = set_b_data["identified_mtids"]
    min_len = min(len(mtids_a), len(mtids_b))
    overlap = shared_count / min_len if min_len > 0 else 0.0

    weighted_overlap = _weighted_overlap(mtids_a, mtids_b, mtid_df or {})

    title_sim = token_set_ratio(
        set_a_data["normalized_title"] or "",
        set_b_data["normalized_title"] or "",
    )

    date_a = set_a_data["played_date"]
    date_b = set_b_data["played_date"]
    date_gap_days = (
        abs((date_a - date_b).days)
        if date_a is not None and date_b is not None
        else None
    )
    date_match = date_gap_days is not None and date_gap_days <= 1

    first_track_match = bool(mtids_a and mtids_b and mtids_a[0] == mtids_b[0])

    return MatchSignals(
        overlap=overlap,
        title_sim=title_sim,
        date_match=date_match,
        first_track_match=first_track_match,
        weighted_overlap=weighted_overlap,
        date_gap_days=date_gap_days,
        order_corr=_order_correlation(mtids_a, mtids_b),
    )


def compute_confidence(signals: MatchSignals) -> float:
    """Composite confidence in [0, 1] from weighted signals.

    Weighted overlap dominates; title, track order and first track corroborate;
    the date gap acts as a multiplier (same day boosts, distant dates crush).
    """
    order_component = (
        max(0.0, signals.order_corr) if signals.order_corr is not None else 0.0
    )
    base = (
        0.55 * signals.weighted_overlap
        + 0.25 * signals.title_sim
        + 0.10 * order_component
        + 0.10 * (1.0 if signals.first_track_match else 0.0)
    )

    gap = signals.date_gap_days
    if gap is None:
        date_factor = 1.0
    elif gap <= 1:
        date_factor = 1.15
    elif gap == 2:
        date_factor = 1.0
    elif gap <= 30:
        date_factor = 0.6
    else:
        date_factor = 0.3

    return min(1.0, round(base * date_factor, 4))


# ---------------------------------------------------------------------------
# Verdict (L3)
# ---------------------------------------------------------------------------


def decide_verdict(
    signals: MatchSignals,
    confidence: float,
    set_a_part: int | None,
    set_b_part: int | None,
) -> tuple[MatchVerdict, str | None]:
    """Return (verdict, flag_type).

    Sets with distinct part_numbers are handled by the parts path — not pairwise.
    """
    # Distinct part numbers → handled by get_part_candidates, not duplicate path
    if set_a_part is not None and set_b_part is not None and set_a_part != set_b_part:
        return MatchVerdict.NOTHING, None
    if signals.overlap >= 0.80 and (signals.title_sim >= 0.50 or signals.date_match):
        if (
            signals.date_gap_days is not None
            and signals.date_gap_days > AUTO_ATTACH_MAX_DATE_GAP_DAYS
        ):
            # Two clearly distinct dates = two performances: a bad merge costs
            # more than an unmerged duplicate — demote to admin review
            return MatchVerdict.FLAG, "duplicate_candidate"
        return MatchVerdict.AUTO_ATTACH, None
    if confidence >= FLAG_CONFIDENCE_THRESHOLD:
        return MatchVerdict.FLAG, "duplicate_candidate"
    if signals.title_sim >= 0.90 and signals.overlap >= 0.30:
        return MatchVerdict.FLAG, "duplicate_candidate"
    return MatchVerdict.NOTHING, None


# ---------------------------------------------------------------------------
# Orchestration (L3)
# ---------------------------------------------------------------------------


async def _load_set_scoring_data(db: AsyncSession, set_id: int):
    """Load a set row + the dict expected by compute_signals.

    Returns (row, set_data) or None if the set does not exist.
    """
    from models import DJSet, SetTrack

    row = (
        await db.execute(select(DJSet).where(DJSet.id == set_id))
    ).scalar_one_or_none()
    if row is None:
        return None

    mtids = (
        await db.execute(
            select(SetTrack.trackid_music_track_id)
            .where(
                SetTrack.set_id == set_id,
                SetTrack.is_id.is_(False),
                SetTrack.trackid_music_track_id.isnot(None),
            )
            .order_by(SetTrack.position)
        )
    ).scalars().all()

    return row, {
        "normalized_title": row.normalized_title or "",
        "played_date": row.played_date,
        "identified_mtids": list(mtids),
    }


async def _load_mtid_df(db: AsyncSession, mtids: set[int]) -> dict[int, int]:
    """Document frequency per mtid: nb of distinct sets containing it (is_id=False)."""
    from models import SetTrack

    if not mtids:
        return {}

    rows = (
        await db.execute(
            select(
                SetTrack.trackid_music_track_id,
                func.count(func.distinct(SetTrack.set_id)),
            )
            .where(
                SetTrack.trackid_music_track_id.in_(mtids),
                SetTrack.is_id.is_(False),
            )
            .group_by(SetTrack.trackid_music_track_id)
        )
    ).all()
    return {mtid: df for mtid, df in rows}


async def score_pair(
    db: AsyncSession, set_id_a: int, set_id_b: int
) -> tuple[MatchSignals, float] | None:
    """Score an arbitrary pair of sets — entry point for flag re-scoring.

    Returns (signals, confidence), or None if either set is missing or virtual.
    """
    loaded_a = await _load_set_scoring_data(db, set_id_a)
    loaded_b = await _load_set_scoring_data(db, set_id_b)
    if loaded_a is None or loaded_b is None:
        return None
    row_a, data_a = loaded_a
    row_b, data_b = loaded_b
    if row_a.is_virtual or row_b.is_virtual:
        return None

    mtids_a = set(data_a["identified_mtids"])
    mtids_b = set(data_b["identified_mtids"])
    mtid_df = await _load_mtid_df(db, mtids_a | mtids_b)

    signals = compute_signals(data_a, data_b, len(mtids_a & mtids_b), mtid_df)
    return signals, compute_confidence(signals)


async def match_set(
    db: AsyncSession, set_id: int
) -> tuple[list[MatchResult], list[GroupMatchResult]]:
    """Full matching pipeline: load set → candidates → signals → verdicts.

    Returns (pair_results, group_results).
    """
    loaded = await _load_set_scoring_data(db, set_id)
    if loaded is None:
        return [], []
    row, set_a_data = loaded
    incoming_mtids = set_a_data["identified_mtids"]

    candidates = await get_match_candidates(db, set_id, incoming_mtids)

    # Load candidate tracklists sequentially (one shared session — never
    # gather db.execute calls), then ONE batched df query over all mtids.
    loaded_candidates = []
    all_mtids: set[int] = set(incoming_mtids)
    for candidate in candidates:
        cand_loaded = await _load_set_scoring_data(db, candidate.set_id)
        if cand_loaded is None:
            continue
        cand_row, set_b_data = cand_loaded
        loaded_candidates.append((candidate, cand_row, set_b_data))
        all_mtids.update(set_b_data["identified_mtids"])

    mtid_df = await _load_mtid_df(db, all_mtids) if loaded_candidates else {}

    pair_results: list[MatchResult] = []
    for candidate, cand_row, set_b_data in loaded_candidates:
        signals = compute_signals(
            set_a_data, set_b_data, candidate.shared_count, mtid_df
        )
        confidence = compute_confidence(signals)
        verdict, flag_type = decide_verdict(
            signals, confidence, row.part_number, cand_row.part_number
        )

        pair_results.append(
            MatchResult(
                candidate_id=candidate.set_id,
                signals=signals,
                verdict=verdict,
                flag_type=flag_type,
                confidence=confidence,
            )
        )

    # Parts path: only when the incoming set has a known part_number
    group_results: list[GroupMatchResult] = []
    if row.part_number is not None and row.normalized_title:
        part_cands = await get_part_candidates(
            db, set_id, row.part_number, row.normalized_title
        )
        if part_cands:
            incoming_member = {
                "id": set_id,
                "part_number": row.part_number,
                "part_total": getattr(row, "part_total", None),
            }
            all_members = part_cands + [incoming_member]
            if _validate_part_group(all_members):
                group_result = await _build_group_match_result(
                    db,
                    set_id,
                    row.part_number,
                    getattr(row, "part_total", None),
                    row.played_date,
                    row.normalized_title,
                    part_cands,
                )
                group_results.append(group_result)

    return pair_results, group_results


# ---------------------------------------------------------------------------
# Backfill (L3 — called from L8 audit script and L5 import hook)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Merge helpers (L4)
# ---------------------------------------------------------------------------


def _same_track(a: dict, b: dict) -> bool:
    """Return True if two track dicts represent the same track (boundary dedup)."""
    mtid_a = a.get("trackid_music_track_id")
    mtid_b = b.get("trackid_music_track_id")
    if mtid_a is not None and mtid_b is not None:
        return mtid_a == mtid_b
    key_a = normalize((a.get("raw_artist") or "") + "|" + (a.get("raw_title") or ""))
    key_b = normalize((b.get("raw_artist") or "") + "|" + (b.get("raw_title") or ""))
    if not key_a or not key_b or key_a == "|" or key_b == "|":
        return False
    return key_a == key_b


def _merge_duplicates(
    children: list,
    child_tracks: dict,
) -> list[dict]:
    """Merge tracks from duplicate sets with timecode alignment via median offset."""
    reference = max(
        children,
        key=lambda c: sum(1 for t in child_tracks[c.id] if not t["is_id"]),
    )
    ref_tracks = child_tracks[reference.id]

    ref_mtid_tc: dict[int, int] = {
        t["trackid_music_track_id"]: t["timecode_ms"]
        for t in ref_tracks
        if t["trackid_music_track_id"] is not None and t["timecode_ms"] is not None
    }

    all_tracks: list[dict] = [dict(t) for t in ref_tracks]

    for child in children:
        if child.id == reference.id:
            continue
        tracks = child_tracks[child.id]

        deltas = [
            t["timecode_ms"] - ref_mtid_tc[t["trackid_music_track_id"]]
            for t in tracks
            if (
                t["trackid_music_track_id"] is not None
                and t["trackid_music_track_id"] in ref_mtid_tc
                and t["timecode_ms"] is not None
            )
        ]
        offset = int(_median(deltas)) if len(deltas) >= 3 else 0

        for t in tracks:
            adj = dict(t)
            if adj["timecode_ms"] is not None:
                adj["timecode_ms"] = adj["timecode_ms"] - offset
            all_tracks.append(adj)

    # Dedup pass 1: by trackid_music_track_id (prefer non-None timecode)
    mtid_best: dict[int, dict] = {}
    no_mtid: list[dict] = []
    for t in all_tracks:
        mtid = t["trackid_music_track_id"]
        if mtid is None:
            no_mtid.append(t)
        elif mtid not in mtid_best:
            mtid_best[mtid] = t
        elif mtid_best[mtid]["timecode_ms"] is None and t["timecode_ms"] is not None:
            mtid_best[mtid] = t

    pool = list(mtid_best.values()) + no_mtid

    # Dedup pass 2: by normalize(artist|title) (prefer track with mtid)
    norm_best: dict[str, dict] = {}
    for t in pool:
        key = normalize(
            (t.get("raw_artist") or "") + "|" + (t.get("raw_title") or "")
        )
        if not key or key == "|":
            key = f"_blank_{id(t)}"
        if key not in norm_best:
            norm_best[key] = t
        elif (
            norm_best[key]["trackid_music_track_id"] is None
            and t["trackid_music_track_id"] is not None
        ):
            norm_best[key] = t

    deduped = list(norm_best.values())
    deduped.sort(key=lambda t: (t["timecode_ms"] is None, t["timecode_ms"] or 0))
    return deduped


def _merge_parts(
    children: list,
    child_tracks: dict,
) -> list[dict]:
    """Concatenate tracks from set parts with cumulative timecode offsets."""
    sorted_children = sorted(
        children,
        key=lambda c: (c.part_number is None, c.part_number or 0),
    )

    merged: list[dict] = []
    cumulative_offset = 0
    last_known_tc = 0

    for i, child in enumerate(sorted_children):
        tracks = child_tracks[child.id]

        adjusted: list[dict] = []
        for t in tracks:
            adj = dict(t)
            if adj["timecode_ms"] is not None:
                adj["timecode_ms"] = adj["timecode_ms"] + cumulative_offset
                last_known_tc = adj["timecode_ms"]
            adjusted.append(adj)

        if merged and adjusted and _same_track(merged[-1], adjusted[0]):
            adjusted = adjusted[1:]

        merged.extend(adjusted)

        if i + 1 < len(sorted_children):
            if child.duration_ms is not None:
                cumulative_offset += child.duration_ms
            else:
                cumulative_offset = last_known_tc + 180_000

    return merged


# ---------------------------------------------------------------------------
# Merge/materialisation public API (L4)
# ---------------------------------------------------------------------------


def pick_best_parent_title(titles: list[str]) -> str:
    """Pick the MOST DESCRIPTIVE title from a list (not the shortest).

    A virtual dedup parent should carry the title that best names the set — e.g.
    "Barry Can't Swim DJ Set (Brooklyn, NYC - 20th June 2026)" over
    "BCS @ 314 Scholes, Brooklyn [DJ Mix]" — so a plain shortest-title heuristic
    is wrong. Ranks by the number of significant alphabetic tokens (words of
    length >= 2 after a simple split), tie-broken by longer total length, then
    stable (first). Empty/None entries are ignored defensively; an all-empty
    input returns "".
    """
    candidates = [t for t in titles if t]
    if not candidates:
        return ""

    def _significant_tokens(title: str) -> int:
        return sum(1 for tok in title.split() if len(tok) >= 2 and tok.isalpha())

    best_idx = 0
    best_key: tuple[int, int] | None = None
    for idx, title in enumerate(candidates):
        key = (_significant_tokens(title), len(title))
        if best_key is None or key > best_key:
            best_key = key
            best_idx = idx
    return candidates[best_idx]


async def find_or_create_virtual_parent(
    db: AsyncSession,
    set_id_a: int,
    set_id_b: int,
    played_date,
    title: str | None,
) -> tuple[int, bool]:
    """Find or create a virtual parent for two sets.

    Returns (parent_id, created).  Does not commit — caller is responsible.
    """
    from models import DJSet

    set_a = await db.get(DJSet, set_id_a)
    set_b = await db.get(DJSet, set_id_b)

    if set_a.parent_set_id is not None or set_b.parent_set_id is not None:
        parent_id = (
            set_a.parent_set_id
            if set_a.parent_set_id is not None
            else set_b.parent_set_id
        )
        if set_a.parent_set_id is None:
            set_a.parent_set_id = parent_id
        if set_b.parent_set_id is None:
            set_b.parent_set_id = parent_id
        await db.flush()
        return parent_id, False

    now = datetime.now(timezone.utc)
    chosen_title = (
        title
        if title is not None
        else pick_best_parent_title([set_a.title, set_b.title])
    )
    artwork_donor = next(
        (s for s in (set_a, set_b) if s.has_artwork), None
    )
    parent = DJSet(
        source="virtual",
        is_virtual=True,
        title=chosen_title,
        search_text=search_fold(chosen_title),
        played_date=played_date if played_date is not None else set_a.played_date,
        has_artwork=artwork_donor is not None,
        created_at=now,
        last_crawled_at=now,
    )
    db.add(parent)
    await db.flush()

    set_a.parent_set_id = parent.id
    set_b.parent_set_id = parent.id
    await db.flush()

    if artwork_donor is not None:
        try:
            from services.image_service import BUCKET_SET, ImageService
            ImageService.copy_object(BUCKET_SET, f"{artwork_donor.id}.jpg", f"{parent.id}.jpg")
        except Exception:
            pass

    return parent.id, True


async def materialize_parent(db: AsyncSession, parent_id: int) -> int:
    """Rebuild the virtual parent's set_tracks from all its children. Returns track count."""
    from models import DJSet, SetTrack

    parent = await db.get(DJSet, parent_id)
    children = (
        await db.execute(select(DJSet).where(DJSet.parent_set_id == parent_id))
    ).scalars().all()

    await db.execute(delete(SetTrack).where(SetTrack.set_id == parent_id))

    if not children:
        await db.flush()
        return 0

    child_tracks: dict[int, list[dict]] = {}
    for child in children:
        rows = (
            await db.execute(
                select(SetTrack)
                .where(SetTrack.set_id == child.id)
                .order_by(SetTrack.position)
            )
        ).scalars().all()
        child_tracks[child.id] = [
            {
                "timecode_ms": t.timecode_ms,
                "raw_title": t.raw_title,
                "raw_artist": t.raw_artist,
                "is_id": t.is_id,
                "trackid_music_track_id": t.trackid_music_track_id,
            }
            for t in rows
        ]

    part_numbers = {c.part_number for c in children}
    is_parts_case = len(part_numbers) > 1

    if is_parts_case:
        merged_tracks = _merge_parts(children, child_tracks)
        parent.duration_ms = sum(c.duration_ms or 0 for c in children)
    else:
        merged_tracks = _merge_duplicates(children, child_tracks)
        parent.duration_ms = max(
            (c.duration_ms or 0 for c in children), default=0
        )

    for pos, track_data in enumerate(merged_tracks, start=1):
        db.add(
            SetTrack(
                set_id=parent_id,
                position=pos,
                timecode_ms=track_data["timecode_ms"],
                raw_title=track_data["raw_title"],
                raw_artist=track_data["raw_artist"],
                is_id=track_data["is_id"],
                trackid_music_track_id=track_data["trackid_music_track_id"],
            )
        )

    await db.flush()
    return len(merged_tracks)


# ---------------------------------------------------------------------------
# Admin flag resolution (attach / reject / detach)
#
# Business logic for the admin set-dedup endpoints. These raise LookupError
# (→ 404) / ValueError (→ 400) — never HTTPException — and do NOT commit; the
# router owns the audit log + the commit.
# ---------------------------------------------------------------------------


async def attach_flag(
    db: AsyncSession, flag_id: int, resolved_by: int
) -> tuple[int, dict]:
    """Resolve a pending set-dedup flag by attaching its sets under a virtual parent.

    Handles both a group flag (``member_set_ids``) and a pairwise flag, then
    marks the flag ``attached``. Raises LookupError if the flag is missing or
    already resolved, or a member set cannot be found.

    Returns ``(parent_id, audit_details)`` for the caller's audit log. Does not
    commit — the caller is responsible.
    """
    from models import DJSet, SetFlag, SetFlagStatus

    flag = (
        await db.execute(select(SetFlag).where(SetFlag.id == flag_id))
    ).scalar_one_or_none()
    if not flag or flag.status != SetFlagStatus.pending:
        raise LookupError("Flag not found or already resolved")

    now = datetime.now(timezone.utc)

    if flag.member_set_ids:
        # Group flag: attach all members to a shared virtual parent
        member_ids: list[int] = flag.member_set_ids
        members = (
            await db.execute(select(DJSet).where(DJSet.id.in_(member_ids)))
        ).scalars().all()
        if len(members) < 2:
            raise LookupError("Not enough member sets found")

        dates = [m.played_date for m in members if m.played_date is not None]
        played_date = min(dates) if dates else None
        base_title = flag.group_key or members[0].title

        parent_id, _ = await find_or_create_virtual_parent(
            db, member_ids[0], member_ids[1], played_date, base_title
        )
        # Attach remaining members (beyond the first pair)
        for mid in member_ids[2:]:
            member = await db.get(DJSet, mid)
            if member and member.parent_set_id is None:
                member.parent_set_id = parent_id
        await db.flush()

        await materialize_parent(db, parent_id)

        audit_details = {
            "member_set_ids": member_ids,
            "parent_id": parent_id,
            "group_key": flag.group_key,
        }
    else:
        # Pairwise flag
        set_a = (
            await db.execute(select(DJSet).where(DJSet.id == flag.set_id_a))
        ).scalar_one_or_none()
        set_b = (
            await db.execute(select(DJSet).where(DJSet.id == flag.set_id_b))
        ).scalar_one_or_none()
        if not set_a or not set_b:
            raise LookupError("Set not found")

        parent_id, created = await find_or_create_virtual_parent(
            db, flag.set_id_a, flag.set_id_b, None, None
        )
        if created:
            await materialize_parent(db, parent_id)

        audit_details = {
            "set_id_a": flag.set_id_a,
            "set_id_b": flag.set_id_b,
            "parent_id": parent_id,
        }

    flag.status = SetFlagStatus.attached
    flag.resolved_by = resolved_by
    flag.resolved_at = now

    return parent_id, audit_details


async def reject_flag(db: AsyncSession, flag_id: int, resolved_by: int) -> dict:
    """Reject a pending set-dedup flag.

    Raises LookupError if the flag is missing or already resolved. Returns the
    audit_details. Does not commit — the caller is responsible.
    """
    from models import SetFlag, SetFlagStatus

    flag = (
        await db.execute(select(SetFlag).where(SetFlag.id == flag_id))
    ).scalar_one_or_none()
    if not flag or flag.status != SetFlagStatus.pending:
        raise LookupError("Flag not found or already resolved")

    now = datetime.now(timezone.utc)
    flag.status = SetFlagStatus.rejected
    flag.resolved_by = resolved_by
    flag.resolved_at = now

    return {
        "set_id_a": flag.set_id_a,
        "set_id_b": flag.set_id_b,
        **({"group_key": flag.group_key} if flag.group_key else {}),
    }


async def detach_set_from_parent(db: AsyncSession, set_id: int) -> dict:
    """Detach a set from its virtual parent, collapsing a now-orphaned parent.

    Raises LookupError if the set is missing, ValueError if it has no parent.
    Only a virtual parent (``is_virtual=True``) is ever deleted — a real set
    (and its set_tracks) must never be removed by detaching a child
    (invariant #4). Returns the audit_details. Does not commit — the caller is
    responsible.
    """
    from models import DJSet

    dj_set = (
        await db.execute(select(DJSet).where(DJSet.id == set_id))
    ).scalar_one_or_none()
    if not dj_set:
        raise LookupError("Set not found")
    if dj_set.parent_set_id is None:
        raise ValueError("Ce set n'est pas attaché à un parent")

    parent_id = dj_set.parent_set_id
    dj_set.parent_set_id = None
    await db.flush()

    siblings = (
        await db.execute(select(DJSet).where(DJSet.parent_set_id == parent_id))
    ).scalars().all()

    if len(siblings) <= 1:
        if len(siblings) == 1:
            siblings[0].parent_set_id = None
        # Only ever delete a virtual parent — a real set (and its set_tracks)
        # must never be removed by detaching a child (invariant #4).
        await db.execute(
            delete(DJSet).where(DJSet.id == parent_id, DJSet.is_virtual.is_(True))
        )

    return {"parent_id": parent_id}


async def apply_match_results(
    db: AsyncSession,
    set_id: int,
    pair_results: list[MatchResult],
    group_results: list[GroupMatchResult] | None = None,
) -> dict:
    """Apply match results: attach duplicates, insert flags, or ignore.

    Does not commit — caller is responsible.
    """
    from models import DJSet, SetFlag, SetFlagStatus, SetFlagType

    counts = {"attached": 0, "flagged": 0, "nothing": 0}
    now = datetime.now(timezone.utc)

    for result in pair_results:
        if result.verdict == MatchVerdict.AUTO_ATTACH:
            set_a = await db.get(DJSet, set_id)
            set_b = await db.get(DJSet, result.candidate_id)
            played_date = (
                set_a.played_date
                if set_a is not None and set_a.played_date is not None
                else (set_b.played_date if set_b is not None else None)
            )
            parent_id, _ = await find_or_create_virtual_parent(
                db, set_id, result.candidate_id, played_date, None
            )
            await materialize_parent(db, parent_id)
            counts["attached"] += 1

        elif result.verdict == MatchVerdict.FLAG:
            a_id = min(set_id, result.candidate_id)
            b_id = max(set_id, result.candidate_id)

            existing = (
                await db.execute(
                    select(SetFlag).where(
                        SetFlag.set_id_a == a_id,
                        SetFlag.set_id_b == b_id,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                db.add(
                    SetFlag(
                        set_id_a=a_id,
                        set_id_b=b_id,
                        flag_type=SetFlagType[result.flag_type],
                        confidence=result.confidence,
                        signals={
                            "overlap": result.signals.overlap,
                            "title_sim": result.signals.title_sim,
                            "date_match": result.signals.date_match,
                            "first_track_match": result.signals.first_track_match,
                            "weighted_overlap": result.signals.weighted_overlap,
                            "date_gap_days": result.signals.date_gap_days,
                            "order_corr": result.signals.order_corr,
                        },
                        status=SetFlagStatus.pending,
                        created_at=now,
                    )
                )
                counts["flagged"] += 1

        else:
            counts["nothing"] += 1

    # Group flags (part_candidate / part_overlap_anomaly)
    for gr in group_results or []:
        existing = (
            await db.execute(
                select(SetFlag).where(SetFlag.group_key == gr.group_key)
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.status == SetFlagStatus.rejected:
                # Rejection is memorised per group_key — do not recreate
                counts["nothing"] += 1
                continue
            # Extend pending flag with new member data
            # Use flag_modified for JSON columns (SQLAlchemy doesn't track in-place mutation)
            from sqlalchemy.orm.attributes import flag_modified
            existing.member_set_ids = list(gr.member_set_ids)
            existing.signals = dict(gr.signals)
            flag_modified(existing, "member_set_ids")
            flag_modified(existing, "signals")
            existing.confidence = gr.confidence
            existing.flag_type = SetFlagType[gr.flag_type]
            await db.flush()
            counts["flagged"] += 1
        else:
            db.add(
                SetFlag(
                    set_id_a=min(gr.member_set_ids),
                    set_id_b=None,
                    group_key=gr.group_key,
                    member_set_ids=gr.member_set_ids,
                    flag_type=SetFlagType[gr.flag_type],
                    confidence=gr.confidence,
                    signals=gr.signals,
                    status=SetFlagStatus.pending,
                    created_at=now,
                )
            )
            counts["flagged"] += 1

    return counts


async def backfill_normalized_titles(db: AsyncSession) -> int:
    """Fill normalized_title for all DJSet rows where it is NULL."""
    from models import DJSet

    sets = (
        await db.execute(
            select(DJSet).where(
                DJSet.normalized_title.is_(None),
                DJSet.is_virtual.is_(False),
            )
        )
    ).scalars().all()

    count = 0
    for s in sets:
        result = normalize_set_title(s.title)
        s.normalized_title = result.text
        if s.part_number is None and result.part_number is not None:
            s.part_number = result.part_number
        if s.part_total is None and result.part_total is not None:
            s.part_total = result.part_total
        count += 1
    await db.flush()
    return count
