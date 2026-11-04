"""Twin rules — is a tracklist-less YouTube set the same performance as another set?

PURE decision module (no DB, no network). Without a tracklist only the title, the
channel, the duration and the date can be compared, so the rules run from the
strongest evidence to the weakest and every doubt separates (invariant #4: a
duplicate is cheap, a bad merge corrupts data).

Imports ``set_dedup_service``, never the other way around.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import Enum
from urllib.parse import parse_qs, urlsplit

from utils import search_fold

from services.set_dedup_service import (
    _RE_TITLE_DATE,
    _levenshtein_ratio,
    _title_date_signatures,
)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

DATE_STEP_MAX_DURATION_GAP = 0.05
DATE_STEP_MIN_CONTAINMENT = 0.8
DATE_STEP_MIN_LEV_RATIO = 0.90
# The title-wide ratio tolerates a whole different name in a long title: each word
# proper to one title must also be a long-enough misspelling of a word of the other.
DATE_STEP_MIN_OWN_WORD_LEN = 5
DATE_STEP_MIN_OWN_WORD_RATIO = 0.7
CHANNEL_STEP_MAX_DURATION_GAP = 0.02
# Publication window of an undated YouTube set against a dated one: a recurring show
# reuses its title, so the upload date tells the episodes apart.
CHANNEL_STEP_MAX_UPLOAD_BEFORE_EVENT_DAYS = 7
CHANNEL_STEP_MAX_UPLOAD_AFTER_EVENT_DAYS = 30
CHANNEL_STEP_MAX_UPLOAD_REVIEW_DAYS = 90  # beyond it, another episode: no review
CHANNEL_STEP_MIN_CONTAINMENT = 0.99
# A title this short cannot absorb words of its own: "Kora Core" vs "Queer Cult
# Takeover: Kora Core" may be another show of the same artist.
CHANNEL_STEP_SHORT_TITLE_MAX_WORDS = 2
# A one-word title ("Vitaline") says little: only a near-exact duration confirms it.
CHANNEL_STEP_SINGLE_WORD_MAX_DURATION_GAP = 0.005

# A collaboration marker in only one title: a solo set and a B2B are distinct
# performances. Never generic: these words must stay comparable.
COLLAB_WORDS = frozenset({"b2b", "b3b", "vs"})

# Words that identify the format of a set, not the performance. In FOLDED form
# (search_fold strips accents: "présente" → "presente").
GENERIC_TITLE_WORDS = frozenset(
    {
        "dj", "set", "sets", "live", "mix", "session", "sessions", "full",
        "the", "at", "with", "w", "in", "by", "de", "la", "le", "x",
        "and", "et", "und", "feat", "ft",
        "invite", "invites", "presente", "presentent", "presentes",
        "presents", "present",
    }
)

# Folded month names FR/EN/DE + abbreviations → month number. Only ever consumed
# inside a full date: on its own, "May" can be an artist name ("Derrick May").
_MONTHS = {
    "janvier": 1, "january": 1, "januar": 1, "jan": 1,
    "fevrier": 2, "february": 2, "februar": 2, "feb": 2,
    "mars": 3, "march": 3, "marz": 3, "maerz": 3, "mar": 3,
    "avril": 4, "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juin": 6, "june": 6, "juni": 6, "jun": 6,
    "juillet": 7, "july": 7, "juli": 7, "jul": 7,
    "aout": 8, "august": 8, "aug": 8,
    "septembre": 9, "september": 9, "sept": 9, "sep": 9,
    "octobre": 10, "october": 10, "oktober": 10, "oct": 10, "okt": 10,
    "novembre": 11, "november": 11, "nov": 11,
    "decembre": 12, "december": 12, "dezember": 12, "dec": 12, "dez": 12,
}

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
_YOUTUBE_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_YOUTUBE_PATH_PREFIXES = frozenset({"live", "embed"})
_RE_VIDEO_ID = re.compile(r"^[\w-]+$")

# "31 07 2026": the space-separated form _RE_TITLE_DATE deliberately ignores.
_RE_SPACED_DATE = re.compile(r"(?<!\d)(\d{1,2})\s+(\d{1,2})\s+(\d{4})(?!\d)")
_MONTH_ALTERNATION = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORDINAL_SUFFIX = r"(?:st|nd|rd|th|er|e|eme|\.)?"
# "21st June 2025", "07 juin 2026", "21. Juni 2025"
_RE_NAMED_DATE_DAY_FIRST = re.compile(
    rf"(?<!\d)(?P<day>\d{{1,2}}){_ORDINAL_SUFFIX}[\s,]+(?:of\s+)?"
    rf"(?P<month>{_MONTH_ALTERNATION})\b\.?[\s,]*(?P<year>\d{{4}})(?!\d)"
)
# "June 21, 2025"
_RE_NAMED_DATE_MONTH_FIRST = re.compile(
    rf"\b(?P<month>{_MONTH_ALTERNATION})\b\.?\s+(?P<day>\d{{1,2}}){_ORDINAL_SUFFIX}"
    rf"[\s,]+(?P<year>\d{{4}})(?!\d)"
)
_RE_LETTER_RUN = re.compile(r"[^\W\d_]+")

# Episode-number extraction — mirrors scripts/rescore_set_flags.py (a script, not
# importable from a service): a number tied to an emission keyword or a "#" is a
# reliable "marker", a bare trailing number a weak "trailing" one. Only two
# numbers of the SAME kind can diverge.
_EPISODE_KEYWORDS = (
    r"radio|podcast|show|episode|ep|volume|vol|edition|chapter|session|mix|nr|no"
)
_RE_EPISODE_KEYWORD = re.compile(
    rf"\b(?:{_EPISODE_KEYWORDS})\b\s*\.?\s*#?\s*(\d+)", re.IGNORECASE
)
_RE_EPISODE_HASH = re.compile(r"#\s*(\d+)")
_RE_EPISODE_TRAILING = re.compile(r"(?<![A-Za-z0-9])(\d+)\s*$")
_RE_PART_MARKER = re.compile(r"\b(?:part|pt|p)\s*\.?\s*\d+\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TwinInput:
    title: str | None
    channel: str | None = None
    channel_canonical: str | None = None
    duration_ms: int | None = None
    event_date: date | None = None
    part_number: int | None = None
    source_url: str | None = None
    external_id: str | None = None
    source: str | None = None
    unreliable: bool = False
    upload_date: date | None = None  # YouTube publication date, yt side only


class TwinVerdict(str, Enum):
    ATTACH = "attach"
    REVIEW = "review"
    NOTHING = "nothing"


@dataclass(frozen=True)
class TwinDecision:
    verdict: TwinVerdict
    step: str  # "video" | "date" | "channel" | ""
    reason: str
    signals: dict


@dataclass(frozen=True)
class _ParsedTitle:
    dates: frozenset  # order-agnostic signatures, see _title_date_signatures
    residue: str  # lowercased, accent-stripped title with its full dates removed


# ---------------------------------------------------------------------------
# Video id
# ---------------------------------------------------------------------------


def video_id_from_url(url: str | None) -> str | None:
    """Extract the video id of a YouTube URL; None when it is not one.

    Handles watch?v=, youtu.be/, /live/ and /embed/. The host is checked: an
    unrelated site with a "?v=" parameter must never read as a video match.
    """
    if not url:
        return None
    url = url.strip()
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]

    candidate = None
    if host in _YOUTUBE_SHORT_HOSTS:
        candidate = segments[0] if segments else None
    elif host in _YOUTUBE_HOSTS:
        if segments[:1] == ["watch"]:
            candidate = parse_qs(parts.query).get("v", [None])[0]
        elif len(segments) >= 2 and segments[0] in _YOUTUBE_PATH_PREFIXES:
            candidate = segments[1]
    if candidate and _RE_VIDEO_ID.match(candidate):
        return candidate
    return None


# ---------------------------------------------------------------------------
# Title parsing
# ---------------------------------------------------------------------------


def _strip_accents_lower(text: str) -> str:
    """Lowercase + accent folding, punctuation kept (same folding as search_fold)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _parse_title(title: str | None) -> _ParsedTitle:
    """Split a raw title into its full dates and the text left once they are gone.

    Every signature goes through ``_title_date_signatures`` (same plausibility
    filter, same order-agnostic shape), so "31 07 2026", "31.07.2026" and
    "31 juillet 2026" are one date. An implausible match ("89.3 - 1995") stays in
    the text. Bare years and month-year pairs are NOT dates: "Awakenings 2024" vs
    "2025" and "Juin 2026" vs "Juillet 2026" must keep their differing words.
    """
    raw = title or ""
    dates = set(_title_date_signatures(raw))

    def mask_standard(match: re.Match) -> str:
        return " " if _title_date_signatures(match.group(0)) else match.group(0)

    def mask_parts(match: re.Match, day: str, month: int | str, year: str) -> str:
        signatures = _title_date_signatures(f"{day}.{month}.{year}")
        if not signatures:
            return match.group(0)
        dates.update(signatures)
        return " "

    def mask_spaced(match: re.Match) -> str:
        return mask_parts(match, match.group(1), match.group(2), match.group(3))

    def mask_named(match: re.Match) -> str:
        month = _MONTHS[match.group("month")]
        return mask_parts(match, match.group("day"), month, match.group("year"))

    text = _RE_SPACED_DATE.sub(mask_spaced, _RE_TITLE_DATE.sub(mask_standard, raw))
    text = _strip_accents_lower(text)
    for regex in (_RE_NAMED_DATE_DAY_FIRST, _RE_NAMED_DATE_MONTH_FIRST):
        text = regex.sub(mask_named, text)
    return _ParsedTitle(dates=frozenset(dates), residue=text)


def _fold_title(text: str | None) -> str:
    """search_fold, plus the non-ASCII letter runs search_fold would erase.

    search_fold blanks non-Latin scripts: without this, "Иван x Boris" and
    "Пётр x Boris" would compare as the same title. Glued glyphs ("Frida╚═") are
    not letters and fold away.
    """
    if not text:
        return ""
    extras = [
        run
        for run in _RE_LETTER_RUN.findall(_strip_accents_lower(text))
        if not run.isascii()
    ]
    return " ".join([search_fold(text), *extras]).strip()


def _channel_words(*channels: str | None) -> set[str]:
    """Words of the channel names, plus their glued form ("thelotradio")."""
    words: set[str] = set()
    for channel in channels:
        tokens = _fold_title(channel).split()
        words.update(tokens)
        if tokens:
            words.add("".join(tokens))
    return words


def _significant_words(residue: str, excluded: set[str]) -> set[str]:
    return {
        word
        for word in _fold_title(residue).split()
        if word not in excluded and word not in GENERIC_TITLE_WORDS
    }


def _digit_words(words: set[str]) -> set[str]:
    return {word for word in words if any(char.isdigit() for char in word)}


def _own_words_pair_up(own_a: set[str], own_b: set[str]) -> bool:
    """Is every word of own_a a long-enough misspelling of a word of own_b?"""
    return all(
        len(word) >= DATE_STEP_MIN_OWN_WORD_LEN
        and any(
            _levenshtein_ratio(word, candidate) >= DATE_STEP_MIN_OWN_WORD_RATIO
            for candidate in own_b
        )
        for word in own_a
    )


def _signature_dates(signature: tuple) -> set[date]:
    """Every valid date of a (year, {day, month}) signature; {7} means 07/07."""
    year, parts = signature
    first, second = (*parts, *parts)[:2]
    dates = set()
    for day, month in ((first, second), (second, first)):
        try:
            dates.add(date(year, month, day))
        except ValueError:
            continue
    return dates


def _upload_delta_days(
    yt: TwinInput,
    other: TwinInput,
    title_yt: _ParsedTitle,
    title_other: _ParsedTitle,
) -> int | None:
    """Days from the closest date of other to yt's upload; None when not applicable.

    Applies only to an undated YouTube set facing a dated one. other.upload_date is
    never read: the date of a TrackID set is not reliable.
    """
    if yt.upload_date is None or yt.event_date is not None or title_yt.dates:
        return None
    dates = {other.event_date} if other.event_date is not None else set()
    for signature in title_other.dates:
        dates |= _signature_dates(signature)
    if not dates:
        return None
    return min(((yt.upload_date - day).days for day in sorted(dates)), key=abs)


def _episode_number(residue: str) -> tuple[str, int] | None:
    """(kind, number) of a date-free title; None on a part marker or any ambiguity."""
    if _RE_PART_MARKER.search(residue):
        return None
    for regex, kind in (
        (_RE_EPISODE_KEYWORD, "marker"),
        (_RE_EPISODE_HASH, "marker"),
        (_RE_EPISODE_TRAILING, "trailing"),
    ):
        for match in regex.finditer(residue):
            number = int(match.group(1))
            if not 1990 <= number <= 2035:
                return kind, number
    return None


def _episodes_diverge(residue_a: str, residue_b: str) -> bool:
    episode_a = _episode_number(residue_a)
    episode_b = _episode_number(residue_b)
    return (
        episode_a is not None
        and episode_b is not None
        and episode_a[0] == episode_b[0]
        and episode_a[1] != episode_b[1]
    )


def _same_channel(a: TwinInput, b: TwinInput) -> bool:
    if a.channel_canonical and a.channel_canonical == b.channel_canonical:
        return True
    fold_a = _fold_title(a.channel)
    return bool(fold_a) and fold_a == _fold_title(b.channel)


def _separation_reason(
    yt: TwinInput,
    other: TwinInput,
    title_yt: _ParsedTitle,
    title_other: _ParsedTitle,
) -> str | None:
    """Why the two sets are distinct performances; None when nothing separates them."""
    if not yt.duration_ms or not other.duration_ms:
        return "missing duration"
    if (
        yt.part_number is not None
        and other.part_number is not None
        and yt.part_number != other.part_number
    ):
        return "different part numbers"
    if (
        title_yt.dates
        and title_other.dates
        and not title_yt.dates & title_other.dates
    ):
        return "different title dates"
    if (
        yt.event_date is not None
        and other.event_date is not None
        and yt.event_date != other.event_date
    ):
        return "different event dates"
    if _episodes_diverge(title_yt.residue, title_other.residue):
        return "different episode numbers"
    return None


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


def decide_twin(yt: TwinInput, other: TwinInput) -> TwinDecision:
    """Decide whether a YouTube set and another set are the same performance.

    The rules run in a fixed order. The only upload date read is yt.upload_date, in
    the channel step's publication window: a set's played_date is deliberately not
    an input and other.upload_date is ignored, because the date of a TrackID set is
    not reliable. The word comparison comes first because every decision carries
    its signals, including the ones that never read them.
    """
    title_yt = _parse_title(yt.title)
    title_other = _parse_title(other.title)

    excluded = _channel_words(
        yt.channel, yt.channel_canonical, other.channel, other.channel_canonical
    )
    words_yt = _significant_words(title_yt.residue, excluded)
    words_other = _significant_words(title_other.residue, excluded)
    shortest = min(len(words_yt), len(words_other))
    common = len(words_yt & words_other)

    cont = common / shortest if shortest else 0.0
    dd = None
    if yt.duration_ms and other.duration_ms:
        dd = abs(yt.duration_ms - other.duration_ms) / max(
            yt.duration_ms, other.duration_ms
        )
    own_yt = words_yt - words_other
    own_other = words_other - words_yt
    extras = own_yt | own_other
    collab_words = extras & COLLAB_WORDS
    both_own = bool(own_yt) and bool(own_other)
    same_date = bool(title_yt.dates & title_other.dates) or (
        yt.event_date is not None and yt.event_date == other.event_date
    )
    same_channel = _same_channel(yt, other)

    signals = {
        "cont": round(cont, 4),
        "dd": round(dd, 4) if dd is not None else None,
        "both_own": both_own,
        "same_date": same_date,
        "same_channel": same_channel,
    }

    def decision(verdict: TwinVerdict, step: str, reason: str) -> TwinDecision:
        return TwinDecision(verdict=verdict, step=step, reason=reason, signals=signals)

    # 0. An unreliable set has nothing to offer; re-evaluated at its re-import.
    if other.unreliable:
        return decision(TwinVerdict.NOTHING, "", "other set is unreliable")

    # 1. Same video: certain, whatever the titles and durations say.
    if yt.external_id and yt.external_id == video_id_from_url(other.source_url):
        return decision(TwinVerdict.ATTACH, "video", "same video id")

    # 2. Strict separation.
    separation = _separation_reason(yt, other, title_yt, title_other)
    if separation is not None:
        return decision(TwinVerdict.NOTHING, "", separation)

    # 3. Same reliable date. A solo set and a B2B the same day stay a human decision.
    # The Levenshtein runs on the sorted significant words, so channel names and word
    # order cannot inflate it. It only forgives spelling: a differing number ("Gabbie
    # Mobili 007" vs "008") is another episode, a differing short name ("Ana" vs "Aya")
    # another artist. Two empty word sets would score 1.0 on no evidence, hence the
    # guard.
    if same_date and dd <= DATE_STEP_MAX_DURATION_GAP:
        contained = cont >= DATE_STEP_MIN_CONTAINMENT
        if collab_words and contained:
            return decision(
                TwinVerdict.REVIEW,
                "date",
                f"collaboration marker in one title only: {sorted(collab_words)}",
            )
        if contained and not both_own:
            return decision(TwinVerdict.ATTACH, "date", "same date, contained title")
        if words_yt and words_other:
            lev = _levenshtein_ratio(
                " ".join(sorted(words_yt)), " ".join(sorted(words_other))
            )
            signals["lev"] = round(lev, 4)
            if (
                lev >= DATE_STEP_MIN_LEV_RATIO
                and _digit_words(words_yt) == _digit_words(words_other)
                and _own_words_pair_up(own_yt, own_other)
                and _own_words_pair_up(own_other, own_yt)
            ):
                return decision(
                    TwinVerdict.ATTACH, "date", "same date, near-identical words"
                )
        if contained:
            return decision(
                TwinVerdict.REVIEW, "date", "same date, each title has own words"
            )

    # 4. Same channel, no date to rely on: the bar is higher. cont >= 0.99 means the
    # shortest title is contained in the other, so only the longest has extra words.
    if (
        same_channel
        and cont >= CHANNEL_STEP_MIN_CONTAINMENT
        and dd <= CHANNEL_STEP_MAX_DURATION_GAP
    ):
        upload_delta = _upload_delta_days(yt, other, title_yt, title_other)
        if upload_delta is not None:
            signals["upload_delta_days"] = upload_delta
            if upload_delta < -CHANNEL_STEP_MAX_UPLOAD_BEFORE_EVENT_DAYS:
                return decision(TwinVerdict.NOTHING, "", "uploaded before the event")
            if upload_delta > CHANNEL_STEP_MAX_UPLOAD_REVIEW_DAYS:
                return decision(
                    TwinVerdict.NOTHING, "", "uploaded long after the event"
                )
            if upload_delta > CHANNEL_STEP_MAX_UPLOAD_AFTER_EVENT_DAYS:
                return decision(
                    TwinVerdict.REVIEW, "channel", "uploaded long after the event"
                )
        if collab_words:
            return decision(
                TwinVerdict.REVIEW,
                "channel",
                f"collaboration marker in one title only: {sorted(collab_words)}",
            )
        digit_extras = _digit_words(extras)
        if digit_extras:
            return decision(
                TwinVerdict.REVIEW,
                "channel",
                f"number in one title only: {sorted(digit_extras)}",
            )
        if shortest <= CHANNEL_STEP_SHORT_TITLE_MAX_WORDS and extras:
            return decision(
                TwinVerdict.REVIEW, "channel", "short title, the other has extra words"
            )
        if shortest <= 1:
            if dd <= CHANNEL_STEP_SINGLE_WORD_MAX_DURATION_GAP:
                return decision(
                    TwinVerdict.ATTACH, "channel", "one-word title, same duration"
                )
            return decision(
                TwinVerdict.REVIEW, "channel", "one-word title, close duration"
            )
        return decision(TwinVerdict.ATTACH, "channel", "same channel, contained title")

    # 5. Not enough evidence.
    return decision(TwinVerdict.NOTHING, "", "not enough evidence")
