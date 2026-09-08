"""Pure helpers deriving set metadata FROM the TrackID title / channel (C13.e).

No I/O, no session — the same acabit as ``workers.artist_names``, importable from
the worker, the API and the ops scripts alike (NO celery/redis/DB dependency). Two
building blocks the "set metadata" chantier wires at the import funnel and in the
backfill:

- :func:`extract_event_date` — the EVENT date parsed out of the set TITLE, when it
  parses UNAMBIGUOUSLY. TrackID's own ``sets.played_date`` comes from ``createdOn``
  and is often the upload date, not the event's, so a date embedded in the title
  ("Boiler Room Berlin 25/12/2021") is a better event date WHEN we can trust it.
- :func:`canonicalize_channel` — the raw channel normalised through a curated
  gazetteer of known channels, or the cleaned raw string as a passthrough.

Guiding rule everywhere (project invariant #4 — err toward separation): when the
date is ambiguous, out of a plausible range, or the title carries conflicting
dates, return ``None`` rather than emit a wrong date. A missing ``event_date`` is
cheap (the app falls back to ``played_date``); a wrong one is corruption.
"""

import datetime
import re

from workers.artist_names import punct_fold_key

# ── extract_event_date ───────────────────────────────────────────────────────

# A title date is only trusted inside this range: a set older than 1990 or dated
# past 2035 is almost surely a mis-parse (a catalogue number, a bitrate, a phone
# number…), not an event date. Bounds the 2-digit-year expansion too.
_YEAR_MIN = 1990
_YEAR_MAX = 2035

# English month names (full + common abbreviations). Titles are overwhelmingly
# English; a named month makes the "20th Feb 2032" form unambiguous.
_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

# ISO-ish, year first (unambiguous ordering): "2021-12-25", "2021/12/25", "2021.12.25".
_RE_ISO = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
# Separated day/month/year with a 2- or 4-digit trailing year — order of the first
# two components resolved by the >12 rule below (see _parse_dmy).
_RE_DMY = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")
# Named month, day first ("20th Feb 2032", "2 January 2020") — 4-digit year only.
_RE_DAY_MONTH_YEAR = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_ALT + r")\.?\s+(\d{4})\b",
    re.IGNORECASE,
)
# Named month first ("Feb 20 2032", "February 20, 2032") — 4-digit year only.
_RE_MONTH_DAY_YEAR = re.compile(
    r"\b(" + _MONTH_ALT + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)
# Glued digit runs, DAY-MONTH-YEAR order fixed by the form (JJMMAAAA / JJMMAA).
_RE_GLUED8 = re.compile(r"\b(\d{8})\b")
_RE_GLUED6 = re.compile(r"\b(\d{6})\b")


def _make_date(year, month, day):
    """Build a real, plausible ``date`` or ``None``.

    Rejects an out-of-range year (:data:`_YEAR_MIN`/:data:`_YEAR_MAX`) and any
    impossible calendar date (31 Feb → ``None``). The single funnel every parser
    goes through, so plausibility is enforced in ONE place.
    """
    if not (_YEAR_MIN <= year <= _YEAR_MAX):
        return None
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _expand_2digit_year(yy):
    """Expand a 2-digit year to a plausible 4-digit one, else ``None``.

    00–35 → 2000–2035, 90–99 → 1990–1999; 36–89 falls outside the plausible
    window (:data:`_YEAR_MIN`/:data:`_YEAR_MAX`) → ``None`` (abstain).
    """
    if yy <= 35:
        return 2000 + yy
    if yy >= 90:
        return 1900 + yy
    return None


def _parse_dmy(a, b, yearraw):
    """Resolve a separated D/M/Y triple to a date, disambiguating D vs M.

    ``a``/``b`` are the first two numeric components (as ints), ``yearraw`` the
    trailing year token (2 or 4 digits). The >12 rule slices the order: a value
    >12 can only be the DAY. When BOTH are ≤12 the D/M order is genuinely ambiguous
    → ``None`` (abstain); when both are >12 neither can be a month → ``None``.
    """
    if len(yearraw) == 4:
        year = int(yearraw)
    else:
        year = _expand_2digit_year(int(yearraw))
        if year is None:
            return None
    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        day, month = b, a
    else:
        # both ≤ 12 (ambiguous) or both > 12 (invalid) → abstain
        return None
    return _make_date(year, month, day)


def _scan_dates(title):
    """Yield every plausible, unambiguous ``date`` the title spells out.

    Runs each recognised form over the whole title; an ambiguous or out-of-range
    match contributes nothing. Bare years (no month/day) match no pattern, so they
    never become candidates (deliberately too coarse for an event date).
    """
    out = []

    for m in _RE_ISO.finditer(title):
        d = _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            out.append(d)

    for m in _RE_DMY.finditer(title):
        d = _parse_dmy(int(m.group(1)), int(m.group(2)), m.group(3))
        if d:
            out.append(d)

    for m in _RE_DAY_MONTH_YEAR.finditer(title):
        d = _make_date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        if d:
            out.append(d)

    for m in _RE_MONTH_DAY_YEAR.finditer(title):
        d = _make_date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        if d:
            out.append(d)

    # Glued forms are day-month-year by definition (JJMMAAAA / JJMMAA); a
    # YYYYMMDD run fails the day/month check of this fixed order and drops out.
    for m in _RE_GLUED8.finditer(title):
        s = m.group(1)
        d = _make_date(int(s[4:8]), int(s[2:4]), int(s[0:2]))
        if d:
            out.append(d)

    for m in _RE_GLUED6.finditer(title):
        s = m.group(1)
        year = _expand_2digit_year(int(s[4:6]))
        if year is not None:
            d = _make_date(year, int(s[2:4]), int(s[0:2]))
            if d:
                out.append(d)

    return out


def extract_event_date(title):
    """Extract the event date from a set title, or ``None`` when it isn't safe.

    Recognises ISO ``YYYY-MM-DD``, separated ``D/M/Y`` (with the >12 day rule),
    glued ``JJMMAAAA`` / ``JJMMAA`` and named-month forms ("20th Feb 2032"). A
    date is returned ONLY when the title yields exactly one distinct, plausible,
    unambiguous date: no date → ``None``; an ambiguous D/M or a bare year →
    ``None``; conflicting dates in the same title → ``None`` (abstain). Multiple
    matches spelling the SAME date collapse to that one date.
    """
    if not title:
        return None
    distinct = []
    for d in _scan_dates(title):
        if d not in distinct:
            distinct.append(d)
    return distinct[0] if len(distinct) == 1 else None


# ── canonicalize_channel ───────────────────────────────────────────────────────

# Curated gazetteer of well-known DJ-set channels: canonical display name → the
# raw forms/aliases it should absorb. A channel matches an entry when the entry's
# folded token sequence appears as a contiguous run inside the channel's folded
# tokens (whole-token containment, never a raw substring — so a 2-letter alias
# like "RA" can't fire on "radio rudina"). Seeded with the big names — TO BE
# REFINED from a real prod top-N of trackid_index.channel once mined.
_GAZETTEER = {
    "Boiler Room": ["Boiler Room"],
    "Cercle": ["Cercle"],
    "HÖR": ["HÖR", "HÖR Berlin", "HOER"],
    "NTS Radio": ["NTS", "NTS Radio"],
    "Rinse FM": ["Rinse FM"],
    "Rinse France": ["Rinse France"],
    "The Lot Radio": ["The Lot Radio"],
    "Keep Hush": ["Keep Hush"],
    "Mixmag": ["Mixmag"],
    "DJ Mag": ["DJ Mag"],
    "Dekmantel": ["Dekmantel"],
    "Resident Advisor": ["Resident Advisor", "RA"],
    "Radio Rudina": ["Radio Rudina"],
    "Sunset Radio": ["Sunset Radio"],
    "Kaltblut": ["Kaltblut"],
}

# Trailing descriptive words dropped before matching ("Foo Records" → "Foo").
_RE_CHANNEL_DESC_SUFFIX = re.compile(r"\s+(?:official|records)$", re.IGNORECASE)


def _fold_tokens(s):
    """Whitespace tokens of the punctuation-insensitive fold of ``s`` (may be ())."""
    key = punct_fold_key(s)
    return tuple(key.split()) if key else ()


# Flat (alias_tokens, canonical) list, longest alias first so a more specific
# entry wins the containment test.
_GAZETTEER_ENTRIES = []
for _canonical, _aliases in _GAZETTEER.items():
    for _alias in _aliases:
        _toks = _fold_tokens(_alias)
        if _toks:
            _GAZETTEER_ENTRIES.append((_toks, _canonical))
_GAZETTEER_ENTRIES.sort(key=lambda e: len(e[0]), reverse=True)


def _is_token_run(needle, haystack):
    """True when ``needle`` is a contiguous sub-run of the ``haystack`` tokens."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _clean_channel(raw):
    """Trim + drop an obvious descriptive suffix ("Foo: episode 3" / "Foo Records").

    Keeps the channel brand: the part before a ':' (marketplace/show suffix) and
    a trailing "Official"/"Records" word. Casing is preserved (passthrough).
    """
    s = raw.strip()
    if ":" in s:
        s = s.split(":", 1)[0].strip()
    return _RE_CHANNEL_DESC_SUFFIX.sub("", s).strip()


def canonicalize_channel(raw):
    """Canonicalise a raw channel string, or ``None`` when it is empty.

    Cleans the raw string, then matches it against the curated :data:`_GAZETTEER`
    by whole-token containment ("Boiler Room: Streaming from Isolation" → "Boiler
    Room", "HÖR Berlin" → "HÖR"). On no match the cleaned raw string is returned
    verbatim (passthrough), so an unknown channel still gets a stable, trimmed
    form. A blank / whitespace-only input returns ``None``.
    """
    if not raw:
        return None
    cleaned = _clean_channel(raw)
    if not cleaned:
        return None
    tokens = _fold_tokens(cleaned)
    for alias_tokens, canonical in _GAZETTEER_ENTRIES:
        if _is_token_run(alias_tokens, tokens):
            return canonical
    return cleaned
