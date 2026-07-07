"""Set deduplication service — title normalization + matching engine (C6.0)."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from statistics import median as _median

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils import normalize

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class NormalizedTitle:
    text: str
    base_title: str
    part_number: int | None
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
_RE_PART = re.compile(r"(?:part|pt\.?|p)\s*(\d+)\s*$", re.IGNORECASE)

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

    # 10. Extract part number
    pm = _RE_PART.search(titre)
    if pm:
        part_number = int(pm.group(1))
        base_title = titre[: pm.start()].rstrip(" -")
    else:
        part_number = None
        base_title = titre

    return NormalizedTitle(
        text=titre,
        base_title=base_title,
        part_number=part_number,
        extracted_date=extracted_date,
    )


# ---------------------------------------------------------------------------
# Matching types (L3)
# ---------------------------------------------------------------------------


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
# Signal computation (L3)
# ---------------------------------------------------------------------------


def compute_signals(
    set_a_data: dict,
    set_b_data: dict,
    shared_count: int,
) -> MatchSignals:
    """Compute matching signals from injected set data (no DB access, fully testable).

    set_a_data / set_b_data keys: normalized_title, played_date, identified_mtids.
    """
    mtids_a = set_a_data["identified_mtids"]
    mtids_b = set_b_data["identified_mtids"]
    min_len = min(len(mtids_a), len(mtids_b))
    overlap = shared_count / min_len if min_len > 0 else 0.0

    title_sim = token_set_ratio(
        set_a_data["normalized_title"] or "",
        set_b_data["normalized_title"] or "",
    )

    date_a = set_a_data["played_date"]
    date_b = set_b_data["played_date"]
    date_match = (
        abs((date_a - date_b).days) <= 1
        if date_a is not None and date_b is not None
        else False
    )

    first_track_match = bool(mtids_a and mtids_b and mtids_a[0] == mtids_b[0])

    return MatchSignals(
        overlap=overlap,
        title_sim=title_sim,
        date_match=date_match,
        first_track_match=first_track_match,
    )


# ---------------------------------------------------------------------------
# Verdict (L3)
# ---------------------------------------------------------------------------


def decide_verdict(
    signals: MatchSignals,
    set_a_part: int | None,
    set_b_part: int | None,
) -> tuple[MatchVerdict, str | None]:
    """Return (verdict, flag_type).

    Part-number detection (part_candidate / part_overlap_anomaly) is deferred to L4:
    sets with different part_number values fall through to duplicate_candidate logic.
    """
    if signals.overlap >= 0.80 and (signals.title_sim >= 0.50 or signals.date_match):
        return MatchVerdict.AUTO_ATTACH, None
    if 0.50 <= signals.overlap < 0.80:
        return MatchVerdict.FLAG, "duplicate_candidate"
    if signals.title_sim >= 0.90 and signals.overlap >= 0.30:
        return MatchVerdict.FLAG, "duplicate_candidate"
    return MatchVerdict.NOTHING, None


# ---------------------------------------------------------------------------
# Orchestration (L3)
# ---------------------------------------------------------------------------


async def match_set(db: AsyncSession, set_id: int) -> list[MatchResult]:
    """Full matching pipeline: load set → candidates → signals → verdicts."""
    from models import DJSet, SetTrack

    row = (
        await db.execute(select(DJSet).where(DJSet.id == set_id))
    ).scalar_one_or_none()
    if row is None:
        return []

    tracks = (
        await db.execute(
            select(SetTrack)
            .where(SetTrack.set_id == set_id, SetTrack.is_id.is_(False))
            .order_by(SetTrack.position)
        )
    ).scalars().all()

    incoming_mtids = [
        t.trackid_music_track_id
        for t in tracks
        if t.trackid_music_track_id is not None
    ]

    candidates = await get_match_candidates(db, set_id, incoming_mtids)

    set_a_data = {
        "normalized_title": row.normalized_title or "",
        "played_date": row.played_date,
        "identified_mtids": incoming_mtids,
    }

    results = []
    for candidate in candidates:
        cand_row = (
            await db.execute(select(DJSet).where(DJSet.id == candidate.set_id))
        ).scalar_one_or_none()
        if cand_row is None:
            continue

        cand_tracks = (
            await db.execute(
                select(SetTrack)
                .where(
                    SetTrack.set_id == candidate.set_id,
                    SetTrack.is_id.is_(False),
                )
                .order_by(SetTrack.position)
            )
        ).scalars().all()

        cand_mtids = [
            t.trackid_music_track_id
            for t in cand_tracks
            if t.trackid_music_track_id is not None
        ]

        set_b_data = {
            "normalized_title": cand_row.normalized_title or "",
            "played_date": cand_row.played_date,
            "identified_mtids": cand_mtids,
        }

        signals = compute_signals(set_a_data, set_b_data, candidate.shared_count)
        verdict, flag_type = decide_verdict(
            signals, row.part_number, cand_row.part_number
        )

        results.append(
            MatchResult(
                candidate_id=candidate.set_id,
                signals=signals,
                verdict=verdict,
                flag_type=flag_type,
            )
        )

    return results


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
        title if title is not None else min(set_a.title, set_b.title, key=len)
    )
    parent = DJSet(
        source="virtual",
        is_virtual=True,
        title=chosen_title,
        played_date=played_date if played_date is not None else set_a.played_date,
        has_artwork=bool(set_a.has_artwork or set_b.has_artwork),
        created_at=now,
        last_crawled_at=now,
    )
    db.add(parent)
    await db.flush()

    set_a.parent_set_id = parent.id
    set_b.parent_set_id = parent.id
    await db.flush()

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


async def apply_match_results(
    db: AsyncSession,
    set_id: int,
    results: list[MatchResult],
) -> dict:
    """Apply match results: attach duplicates, insert flags, or ignore.

    Does not commit — caller is responsible.
    """
    from models import DJSet, SetFlag, SetFlagStatus, SetFlagType

    counts = {"attached": 0, "flagged": 0, "nothing": 0}
    now = datetime.now(timezone.utc)

    for result in results:
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
                        confidence=result.signals.overlap,
                        signals={
                            "overlap": result.signals.overlap,
                            "title_sim": result.signals.title_sim,
                            "date_match": result.signals.date_match,
                            "first_track_match": result.signals.first_track_match,
                        },
                        status=SetFlagStatus.pending,
                        created_at=now,
                    )
                )
                counts["flagged"] += 1

        else:
            counts["nothing"] += 1

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
        count += 1
    await db.flush()
    return count
