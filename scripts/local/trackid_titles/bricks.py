"""Pure brick recognisers + title skeletonisation (no I/O, no network, stdlib).

C13.b — corpus mining. TrackID.net exposes NO artist field on a set: the DJ only
lives in the ``channel`` and/or buried in the ``title``. Before writing the
SUBTRACTIVE artist extractor (C13.c) we need a GATE: mine the ~381k set titles to
measure the distribution of title "skeletons" and decide, ON NUMBERS, whether a
LLM will be needed. This module is the recognition core the miner consumes.

The idea is subtractive: recognise the ~few kinds of NOISE bricks and the
CONNECTORS that structure artists, replace each recognised span by a placeholder,
and reduce a title to its SKELETON — the sequence of placeholders and unrecognised
residues. A residue (``?``) is what's left once the noise is peeled away — most
often an artist name, which is exactly the material C13.c will extract.

Placeholders emitted in a skeleton:
  * ``<DATE>``   — a date, any form (05/09/2025, 05092025, 2025-09-05, 20th Feb
                   2032, June 2026, ISO, a bare 19xx/20xx year…)
  * ``<EP>``     — an episode/volume marker (EP12, #12, Vol.3, Part 2, S01E02, a
                   bare 3+ digit run…)
  * ``<FORMAT>`` — a format word (DJ Set, Live, Podcast, Guest Mix, Exclusive,
                   FREE DOWNLOAD, Official…)
  * ``<DELIM>``  — a connector that STRUCTURES artists (B2B, B3B, VS, X, &, feat.,
                   ft., presents…)
  * ``?``        — an unrecognised residue word (candidate artist / other text)

This module is DELIBERATELY stdlib-only and does NOT import the ``server`` package
(nor ``workers/artist_names``): the miner must stay a standalone local tool. It is
aligned in spirit with ``server/workers/artist_names.py`` (fold/normalise arsenal)
which the DETERMINISTIC extractor of C13.c will reuse — but the mining gate needs
none of that machinery, only coarse structural recognition.

The brick vocabularies (format words, delimiters, month names) are module-level
constants, tunable in one place. Recognition is coarse by design: exact
disambiguation is not the point of a mining gate, consistent placeholdering is.
"""

import re

# ── vocabularies (tunable in one place) ──────────────────────────────────────

# Month names (full + common 3-letter abbreviations), for the textual date forms.
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)

# FORMAT words/phrases — the non-artist "what kind of recording" noise. Multi-word
# phrases MUST come before their single-word constituents (regex alternation is
# leftmost-FIRST, not longest), so the list is sorted longest-first when compiled.
# DELIBERATELY no bare "set"/"mix": those belong to the EP brick ("SET 5"/"MIX 5")
# and to the multi-word phrases here ("dj set", "guest mix"); a lone "set"/"mix"
# would either steal the number from an EP marker or the join from "b2b set".
_FORMAT_TERMS = [
    "free download",
    "guest mix",
    "radio show",
    "dj set",
    "dj mix",
    "live set",
    "full set",
    "opening set",
    "closing set",
    "warm up",
    "warmup",
    "mixtape",
    "mixset",
    "liveset",
    "livestream",
    "residency",
    "aftermovie",
    "recording",
    "showcase",
    "takeover",
    "podcast",
    "exclusive",
    "official",
    "session",
    "sessions",
    "live",
]

# DELIM connectors that STRUCTURE the artists around them. Conservative on purpose:
# the very common English words "with"/"and" are LEFT OUT (they'd over-mark residue
# that isn't a real join). The symbol "&" and the standalone "x" ARE included (they
# would otherwise be dropped as punctuation and lose the join signal).
_DELIM_WORDS = [
    "b2b",
    "b3b",
    "b4b",
    "f2f",
    "versus",
    "vs",
    "featuring",
    "feat",
    "ft",
    "presents",
    "pres",
    "x",
]

# ── brick patterns (order matters: most specific first) ───────────────────────

# DATE — all the forms C13.b enumerates. Alternatives ordered most-specific first.
# Numeric-only forms are guarded by (?<!\d)/(?!\d) so they don't bite a chunk out
# of a longer number.
_DATE = re.compile(
    r"(?<!\w)(?:"
    # separated d/m/y, y/m/d, d.m.yy, ISO y-m-d (slash, dot OR dash separators)
    r"\d{1,4}[-./]\d{1,2}[-./]\d{1,4}"
    # day (opt. ordinal) + month (+ opt. year):  "20th Feb 2032", "5 June"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:" + _MONTHS + r")\.?(?:\s+\d{2,4})?"
    # month (+ opt. day) + year:  "Feb 20 2032", "June 2026", "Feb 2026"
    r"|(?:" + _MONTHS + r")\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?\d{2,4}"
    # numeric ddmmyyyy / ddmmyy
    r"|\d{8}|\d{6}"
    # bare 4-digit year 1900-2039
    r"|(?:19|20)\d{2}"
    r")(?!\w)",
    re.IGNORECASE,
)

# EP — episode / volume / part markers, plus a bare 3+ digit run (an episode
# number that survived the DATE pass). Runs AFTER date so years are already gone.
_EP = re.compile(
    r"(?<!\w)(?:"
    r"s\d{1,3}e\d{1,3}"                                   # S01E02
    r"|(?:ep|episode|vol|volume|part|pt|set|mix|chapter|ch|day|week|night|"
    r"edition|edt|no|nr)\.?\s*#?\s*\d{1,4}"               # Vol.3, Part 2, EP 12
    r"|#\s*\d{1,4}"                                       # #12
    r"|\d{3,}"                                            # bare 3+ digit run
    r")(?!\w)",
    re.IGNORECASE,
)

_FORMAT = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(t) for t in sorted(_FORMAT_TERMS, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)

# DELIM — word connectors (with optional trailing dot: "feat.", "pres.") OR the
# "&" symbol. Word connectors are word-bounded; "&" needs no boundary.
_DELIM = re.compile(
    r"(?<!\w)(?:"
    + "|".join(w for w in sorted(_DELIM_WORDS, key=len, reverse=True))
    + r")\.?(?!\w)"
    r"|&",
    re.IGNORECASE,
)

# Applied IN THIS ORDER. Date first (a year must be a DATE, not EP's bare \d{3,}).
# Then FORMAT phrases BEFORE EP so "Guest Mix #128" -> <FORMAT> <EP> ("guest mix"
# claimed as a phrase before EP's "mix #128" rule could steal it), while a lone
# "Set 5"/"Mix 5" still falls to EP. DELIM last (& / word joins around artists).
# Each recognised span is swapped for a spaced sentinel \x00NAME\x00.
_BRICK_PASSES = (
    ("DATE", _DATE),
    ("FORMAT", _FORMAT),
    ("EP", _EP),
    ("DELIM", _DELIM),
)

# Token scanner over the sentinel-substituted string: a sentinel (tried FIRST) OR a
# run of unicode word chars (minus underscore) = a residue word. Everything else
# (punctuation, spaces) is ignored.
_TOKEN = re.compile(r"\x00(?P<ph>DATE|EP|FORMAT|DELIM)\x00|(?P<word>[^\W_]+)")

PLACEHOLDERS = ("<DATE>", "<EP>", "<FORMAT>", "<DELIM>", "?")


def tag_bricks(title):
    """Replace every recognised brick in ``title`` by a ``\\x00NAME\\x00`` sentinel.

    Returns the sentinel-tagged string (internal helper, exposed for tests). Passes
    run in ``_BRICK_PASSES`` order so a year is claimed by DATE before EP's bare
    ``\\d{3,}`` could grab it.
    """
    s = title or ""
    for name, pattern in _BRICK_PASSES:
        s = pattern.sub(f" \x00{name}\x00 ", s)
    return s


def tokenize(title):
    """Reduce ``title`` to its ordered list of tokens: ``<PLACEHOLDER>`` for a
    recognised brick, ``?`` for an unrecognised residue word.

    No collapsing here — ``["?", "?", "<FORMAT>"]`` for "Artist Name DJ Set".
    """
    tagged = tag_bricks(title)
    out = []
    for m in _TOKEN.finditer(tagged):
        ph = m.group("ph")
        out.append(f"<{ph}>" if ph else "?")
    return out


def _collapse(tokens):
    """Drop consecutive duplicate tokens: ``? ? <FORMAT> <FORMAT>`` -> ``? <FORMAT>``.

    A skeleton abstracts STRUCTURE, not multiplicity — "how many unknown words"
    varies wildly while the shape ("a name region, then a format word") is what
    defines a family. Collapsing runs is what makes the distribution converge onto
    a small, decidable top-N.
    """
    out = []
    for tok in tokens:
        if not out or out[-1] != tok:
            out.append(tok)
    return out


def skeletonize(title, collapse=True):
    """Return the skeleton of ``title`` as a space-joined placeholder string.

    ``"Artist B2B Artist2 @ Boiler Room 05/09/2025"`` -> ``"? <DELIM> ? <DATE>"``
    (with ``collapse=True``, the default). Set ``collapse=False`` to keep the exact
    token multiplicity (``"? <DELIM> ? ? ? <DATE>"``).

    Degenerate cases: an empty / whitespace-only title -> ``""`` (the empty
    skeleton); a title made of pure noise -> a skeleton with no ``?``
    (e.g. ``"<FORMAT> <DATE>"``); a title that is a single bare name -> ``"?"``.
    """
    tokens = tokenize(title)
    if collapse:
        tokens = _collapse(tokens)
    return " ".join(tokens)
