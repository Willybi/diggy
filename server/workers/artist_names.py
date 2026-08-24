"""Pure helpers for artist-name hygiene (no I/O, no session).

Importable from the worker, the API and the ops scripts alike — this module has
NO celery/redis/DB dependency. It ships the four building blocks the "artist
string hygiene" chantier needs to keep junk artists out of the graph and to
recognise equivalent spellings, but it wires nothing: the callers (L2/L3/L4)
decide when to strip, when to fold and when to merge.

Guiding rule everywhere here (project invariant #4 — always err toward
separation): when a transform is not confidently safe, do nothing. A noisy name
left intact is cheap; an altered real name or a wrong match is corruption.
"""

import re
import unicodedata

# ── strip_artist_noise ──────────────────────────────────────────────────────

# Performing-rights organisations (PROs / collecting societies). A metadata
# export sometimes tags an artist with the society that manages its rights, e.g.
# "Ioannis Siopis (GEMA)". That parenthesised suffix is NON-ambiguous noise — no
# artist is really named "… (GEMA)" — so it is safe to drop. This is an explicit
# WHITELIST: only these exact tokens are stripped (a "(Sofa Beats)" label suffix
# or a Discogs "(4)" disambiguator is NOT a PRO and must stay untouched).
_PRO_SOCIETIES = frozenset(
    {
        "GEMA", "ASCAP", "BMI", "SACEM", "PRS", "SABAM", "BUMA", "STIM",
        "SUISA", "SIAE", "SOUNDEXCHANGE", "PPL", "GVL",
    }
)

# Trailing "(<PRO>)" only (anchored at end, case-insensitive, whitespace-tolerant
# inside and around the parens). The parenthesised content must be EXACTLY one of
# the whitelisted societies — anything else is left in place.
_RE_PRO_SUFFIX = re.compile(
    r"\s*\(\s*(?:" + "|".join(sorted(_PRO_SOCIETIES)) + r")\s*\)\s*$",
    re.IGNORECASE,
)

# Leading "Vinyl • " / "• " marketplace bullet (Discogs/Bandcamp listing cruft):
# the optional "vinyl" word, then a bullet (U+2022) or middle dot (U+00B7). Only
# at the very start of the string.
_RE_BULLET_PREFIX = re.compile(r"^\s*(?:vinyl\s*)?[•·]\s*", re.IGNORECASE)

_RE_SPACES = re.compile(r"\s+")


def strip_artist_noise(name: str) -> str:
    """Remove ONLY unambiguous noise from an artist name, else return it as-is.

    Two conservative rewrites: a trailing performing-rights-organisation suffix
    from the explicit :data:`_PRO_SOCIETIES` whitelist ("Ioannis Siopis (GEMA)"
    → "Ioannis Siopis") and a leading marketplace bullet ("Vinyl • Harvey Mason"
    → "Harvey Mason"). When neither pattern matches, the input is returned
    UNCHANGED (identical object) — so a Discogs "(4)" suffix, a vinyl-face marker
    ("A1 Bassline"), a "/" in "AC/DC", a legit group ("Tomeka Reid Quartet"), a
    non-PRO label ("Kapchiz (Sofa Beats)") and a non-ASCII name all pass through.
    If a strip would empty the string, the original is returned instead.
    """
    if not name:
        return name
    stripped = _RE_BULLET_PREFIX.sub("", name)
    stripped = _RE_PRO_SUFFIX.sub("", stripped)
    if stripped == name:
        return name
    stripped = _RE_SPACES.sub(" ", stripped).strip()
    return stripped or name


# ── fold_base ───────────────────────────────────────────────────────────────

# Latin-script letters with NO Unicode decomposition: an NFKD + ascii-ignore fold
# would DROP them silently ("Altın" -> "altn", losing the i), so transliterate them
# to their conventional ASCII form FIRST. Plus the "smart" punctuation glyphs that
# ascii-ignore also drops — mapping a curly apostrophe "’" (U+2019) to a straight
# "'" (U+0027) lets "Angel’in" fold identically to "Angel'in". Deliberately
# Latin-only: CJK / Hebrew / etc. are left to fold to the empty string (the
# load-bearing "no signal" guard — invariant #4).
_TRANSLIT = str.maketrans(
    {
        "ı": "i", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "ß": "ss",
        "þ": "th", "æ": "ae", "œ": "oe", "ħ": "h", "ŧ": "t", "ĸ": "k",
        "’": "'", "‘": "'", "‛": "'", "‚": "'",
        "“": '"', "”": '"', "„": '"',
        "–": "-", "—": "-", "―": "-",
    }
)


def fold_base(name: str) -> str:
    """Shared accent/transliteration fold underneath every match key.

    lowercase → transliterate the non-decomposable Latin letters + smart
    punctuation of :data:`_TRANSLIT` → NFKD → drop remaining non-ASCII → trim.
    The transliteration step is what stops ascii-ignore from silently deleting a
    Turkish dotless "ı" ("Altın" -> "altin", not "altn") and unifies a curly
    apostrophe "’" with a straight "'". A fully non-Latin name still folds to ""
    (no ASCII survives) — callers treat that as "no signal, do not match".
    """
    s = (name or "").lower().strip().translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode().strip()


# ── is_placeholder_artist ────────────────────────────────────────────────────

# Non-artist placeholders that must NOT become nodes in the artist graph: they act
# as false co-occurrence hubs (325 unrelated tracks all "share" Various Artists),
# skewing artist-based similarity / reco. EXACT normalized match ONLY — a substring
# test would wrongly catch real artists ("Unknown Mortal Orchestra", "Origin
# Unknown", "Unknown T", "Daft Punk"). "Na" and "Traditional" are deliberately OUT
# (a real Korean name / a legit folk credit).
_PLACEHOLDER_ARTISTS = frozenset(
    {
        "various artists", "various artist", "various", "va", "v/a", "v.a", "v.a.",
        "unknown artist", "unknown artists", "unknown", "artist unknown",
        "n/a", "no artist", "compilation",
    }
)


def is_placeholder_artist(name: str) -> bool:
    """True when ``name`` is a compilation/unknown PLACEHOLDER, not a real artist.

    Exact match against :data:`_PLACEHOLDER_ARTISTS` after lowercasing and compacting
    internal whitespace — NEVER a substring test (invariant #4: real artist names
    contain these words). Callers keep placeholders out of the artist graph (blocked
    at the creation funnel, unlinked by the cleanup script).
    """
    if not name:
        return False
    key = " ".join(name.strip().lower().split())
    return key in _PLACEHOLDER_ARTISTS


# ── punct_fold_key ──────────────────────────────────────────────────────────

# Punctuation dropped when building a MATCH key: dots, commas, apostrophes,
# hyphens and the two bullet glyphs. Removed (not replaced by a space) so
# "Cro-Magnon" and "Cromagnon" fold together. Deliberately EXCLUDES "& | /" —
# those are artist-string separators handled elsewhere, not intra-name punctuation.
_RE_PUNCT_STRIP = re.compile(r"[.,'\-·•]")


def punct_fold_key(name: str) -> str:
    """Punctuation-insensitive fold key for MATCHING (never an identity key).

    Builds on :func:`fold_base` (lowercase + transliterate + NFKD + ASCII fold),
    then drops the intra-name punctuation in :data:`_RE_PUNCT_STRIP` and compacts
    whitespace. So "St. Germain" == "St Germain", "Mr. Oizo" == "Mr Oizo",
    "N.E.R.D." == "N.E.R.D", "Cro-Magnon" == "Cromagnon", "Fred again.." == "Fred
    Again", and (via fold_base) "Angel’in" == "Angel'in".

    A fully non-ASCII name folds to "" (the ASCII fold drops every ideograph) —
    the caller MUST treat an empty key as "no signal, do not match", since any
    other non-Latin name would fold to the same blank.
    """
    folded = _RE_PUNCT_STRIP.sub("", fold_base(name))
    return _RE_SPACES.sub(" ", folded).strip()


def punct_sep_key(name: str) -> str:
    """Sibling of :func:`punct_fold_key` that maps intra-name punctuation to a
    SPACE instead of dropping it, then compacts whitespace.

    This is the key that recognises "punctuation where the other spelling has a
    space": "R.Kelly" == "R. Kelly", "ICE T" == "Ice-T", "Mr.Oizo" == "Mr. Oizo",
    "JAY-Z" == "JAY Z" — cases :func:`punct_fold_key` MISSES because it removes the
    dot without collapsing the resulting whitespace mismatch ("rkelly" vs
    "r kelly").

    Crucially it does NOT fold a pure space insertion that involves no
    punctuation: "Will I Am" stays "will i am" (never "william") and "George S."
    stays "george s" (never "georges"). Mapping punctuation to a space keeps a
    separator on both sides, so it can never collapse two words the way full
    space-removal would — which is exactly what stops the "Will I Am" -> "William"
    / "George S." -> "Georges" FALSE merges (invariant #4). The complementary
    :func:`punct_fold_key` still covers no-separator compounds ("Cro-Magnon" ==
    "Cromagnon"), so a caller matches on EITHER key; a pure space insertion with
    no punctuation ("DJ Rum" vs "Djrum") is caught by neither of these two — that
    is the job of the riskier, hard-gated :func:`space_fold_key`.

    Same blank-on-fully-non-ASCII contract as :func:`punct_fold_key`: an empty
    key means "no signal, do not match".
    """
    folded = _RE_PUNCT_STRIP.sub(" ", fold_base(name))
    return _RE_SPACES.sub(" ", folded).strip()


# ── space_fold_key ──────────────────────────────────────────────────────────

# Minimum length of a space-fold key for it to be trusted. Drops short collisions
# ("Co Ro" -> "coro", "A B" -> "ab") that whitespace removal makes dangerously
# easy; "aux88" (5) clears it, "coro" (4) does not.
SPACE_FOLD_MIN_LEN = 5


def space_fold_key(name: str) -> str:
    """Punctuation- AND whitespace-insensitive fold key — the RISKIEST fold.

    :func:`fold_base` then drops every punctuation char AND every space, so
    "AUX 88" and "AUX88" both fold to "aux88", "Minus 8" == "Minus8", "DJ Rum" ==
    "Djrum". Unlike :func:`punct_sep_key` it WILL collapse a pure space insertion
    with no punctuation — which also collapses genuinely different names
    ("Will I Am" -> "william", "George S." -> "georges"). So a caller MUST gate it
    hard: acronym guard on both sides, a fan floor, a :data:`SPACE_FOLD_MIN_LEN`
    length check, AND ambiguity rejection (link only a SINGLE distinct hit). Same
    blank-on-fully-non-ASCII contract as the other keys.
    """
    folded = _RE_PUNCT_STRIP.sub("", fold_base(name))
    return _RE_SPACES.sub("", folded).strip()


# ── dominant_by_fans ────────────────────────────────────────────────────────

# A duplicate-spelling pair is only merged toward the "dominant" side when that
# side is BOTH popular in absolute terms (``FAN_FLOOR``) AND clearly ahead of the
# other (``FAN_RATIO`` ×). The floor stops two tiny artists (10 vs 12 fans) from
# ever being treated as a confident dominance; the ratio stops two comparably
# popular artists (50k vs 48k) from collapsing. Tunable, deliberately strict.
FAN_FLOOR = 1000
FAN_RATIO = 10


def dominant_by_fans(
    high: int, low: int, *, floor: int = FAN_FLOOR, ratio: int = FAN_RATIO
) -> bool:
    """True when the ``high`` side confidently dominates the ``low`` side.

    Requires ``high >= max(floor, ratio * low)`` — i.e. above the absolute
    popularity floor AND at least ``ratio``× the other side's fan count. With
    ``low == 0`` the ratio term vanishes and the floor alone decides.
    """
    return high >= max(floor, ratio * low)


# ── looks_acronym ───────────────────────────────────────────────────────────

# Dotted initials spanning the WHOLE name: at least two "letter." pairs, then an
# optional trailing letter or dot — "N.E.R.D.", "L.I.L.Y", "D.S.L". "[^\W\d_]"
# is a Unicode letter (word char minus digit/underscore), so accented initials
# count too. "St. Germain"/"Mr. Oizo" fail: "St"/"Mr" are two letters before the
# dot, not a single-letter initial.
_RE_DOTTED_INITIALS = re.compile(r"^(?:[^\W\d_]\.){2,}[^\W\d_]?\.?$")


def looks_acronym(name: str) -> bool:
    """True when ``name`` reads as initials — dotted ("N.E.R.D.") or a run of at
    least two consecutive single-character tokens ("A X L").

    Serves as an anti-false-positive guard for the punctuation fold: an acronym
    collapses to a short letter run ("N.E.R.D." → "nerd") that could spuriously
    match an unrelated word, so a caller checks this before trusting a fold match.
    "St. Germain", "Mr. Oizo" and "Tomeka Reid Quartet" are NOT acronyms.
    """
    s = (name or "").strip()
    if not s:
        return False
    if _RE_DOTTED_INITIALS.match(s):
        return True
    run = 0
    for token in s.split():
        if len(token) == 1:
            run += 1
            if run >= 2:
                return True
        else:
            run = 0
    return False
