"""Pure SUBTRACTIVE set-title → artist-candidate extractor (no I/O, no session).

C13.c — TrackID.net exposes NO artist field on a set: the DJ only lives in the
``channel`` (the source-platform account) and/or buried in the ``title``. This
module DERIVES artist CANDIDATES from ``(title, channel)`` by peeling away the
recognisable NOISE (dates, episode/volume markers, format words, venues) and
SPLITTING on the connectors that structure a line-up (B2B, &, feat, vs, x). What
survives the subtraction is the candidate material.

It is DELIBERATELY the same acabit as :mod:`workers.artist_names`: PURE, stdlib +
``workers.artist_names`` only, importable from the worker, the API and the ops
scripts alike (no celery/redis/DB). It reuses ``artist_names`` for the hygiene
(``strip_artist_noise``, ``is_placeholder_artist``, the fold keys, the multi-artist
separators) and PORTS the brick recognisers of ``scripts/local/trackid_titles/
bricks.py`` (which can't be imported here — it lives under ``scripts/local`` and is
excluded from the server image), kept aligned in spirit but independent.

Design, per the roadmap (C13.c) and invariant #4:
  * The extractor PROPOSES, a later lot (verification against Deezer / known
    artists / channel) DISPOSES. So this module does ZERO existence checking and
    NO network — a bad extraction turns into gibberish that matches nothing
    downstream, i.e. it costs recall, never precision.
  * DO NOT gate on "the title starts with the name". The start of the title is
    only a CONFIDENCE BOOSTER (``is_boosted``), never a filter — an artist can sit
    anywhere in the line-up.
  * ``channel`` is ALWAYS emitted as a candidate (source ``"channel"``): it is the
    single best proxy for "the DJ", even though it is sometimes a label/media.

Convention learned on the corpus (see ``scripts/local/trackid_titles/data/
samples.md``): a set title is overwhelmingly "Artist[ & Artist…] - Track/Context",
DJ-first, so a spaced " - " separates the artist region (left) from the track /
description (right); the connectors then split the artist region into individual
names.
"""

import re
from typing import NamedTuple

from workers.artist_names import (
    _SPLIT_PUNCT,
    _SPLIT_WORDS,
    fold_base,
    is_placeholder_artist,
    punct_fold_key,
    strip_artist_noise,
)

# ── Candidate ────────────────────────────────────────────────────────────────


class Candidate(NamedTuple):
    """One proposed artist string, with its provenance.

    ``name``       — the cleaned candidate string (original casing/accents kept;
                     downstream matching folds it, so it is NOT a fold key).
    ``source``     — ``"title"`` (extracted from the set title) or ``"channel"``
                     (the source-platform account name).
    ``is_boosted`` — True when the candidate comes from the LEADING region of the
                     title (a confidence hint, never a hard signal).
    """

    name: str
    source: str
    is_boosted: bool


# ── ported brick vocabularies / recognisers (aligned with bricks.py) ─────────

# Month names (full + common 3-letter abbreviations), for the textual date forms.
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)

# FORMAT words/phrases — the non-artist "what kind of recording" noise. Multi-word
# phrases first (regex alternation is leftmost-first, so sort longest-first when
# compiled). No bare "set"/"mix": those belong to the EP marker ("Set 5"/"Mix 5").
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

# DATE — all forms C13.b enumerates, most-specific first; numeric-only forms guarded
# by (?<!\d)/(?!\d) so they don't bite a chunk out of a longer number.
_DATE = re.compile(
    r"(?<!\w)(?:"
    r"\d{1,4}[-./]\d{1,2}[-./]\d{1,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:" + _MONTHS + r")\.?(?:\s+\d{2,4})?"
    r"|(?:" + _MONTHS + r")\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?\d{2,4}"
    r"|\d{8}|\d{6}"
    r"|(?:19|20)\d{2}"
    r")(?!\w)",
    re.IGNORECASE,
)

# EP — episode/volume/part markers + a bare 3+ digit run. Runs AFTER date so years
# are already gone.
_EP = re.compile(
    r"(?<!\w)(?:"
    r"s\d{1,3}e\d{1,3}"
    r"|(?:ep|episode|vol|volume|part|pt|set|mix|chapter|ch|day|week|night|"
    r"edition|edt|no|nr)\.?\s*#?\s*\d{1,4}"
    r"|#\s*\d{1,4}"
    r"|\d{3,}"
    r")(?!\w)",
    re.IGNORECASE,
)

_FORMAT = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(t) for t in sorted(_FORMAT_TERMS, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)

# Applied IN THIS ORDER (parity with bricks.py): DATE first (a year must be a DATE,
# not EP's bare \d{3,}), then FORMAT phrases before EP ("Guest Mix #128" → the
# phrase is claimed before EP's "mix #128" could steal it), EP last. Each match is
# swapped for a boundary sentinel so it BREAKS the surrounding name region.
_NOISE_PASSES = (_DATE, _FORMAT, _EP)

_BOUNDARY = "\x00"

# ── connectors that STRUCTURE the line-up (split into several candidates) ─────

# DJ-set line-up connectors NOT already covered by artist_names._SPLIT_WORDS: the
# back-to-back / face-to-face joins and a standalone "x". feat/ft/vs/versus/presents/
# pres/with come from artist_names (single source of truth for those). Word-bounded
# so "vs" in "Elvis" and "x" in "Max" never fire; "&", ",", "|", … stay to the
# punctuation split. An optional trailing dot swallows "feat."/"pres.".
_CONNECTOR_WORDS = ["b2b", "b3b", "b4b", "f2f", "versus", "vs", "x"]

# Word connectors sourced from artist_names._SPLIT_WORDS, reduced to bare tokens
# (drop the surrounding spaces/dots/parens of that constant — they are match
# fragments there, whole words here).
_SPLIT_WORD_TOKENS = sorted(
    {w.strip(" .(").rstrip(".") for w in _SPLIT_WORDS if w.strip(" .(")},
    key=len,
    reverse=True,
)

# One alternation over every word connector, word-bounded, optional trailing dot,
# case-insensitive. Punctuation separators (artist_names._SPLIT_PUNCT) are added as
# a bare character class.
_CONNECTOR = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(w)
        for w in sorted(
            set(_CONNECTOR_WORDS) | set(_SPLIT_WORD_TOKENS), key=len, reverse=True
        )
    )
    + r")\.?(?!\w)"
    + r"|[" + re.escape(_SPLIT_PUNCT) + r"]",
    re.IGNORECASE,
)

# Structural region separators: venue/label/field boundaries where the artist could
# be on either side (all regions are emitted, the first one boosted). The venue "@"
# is handled separately (its tail is dropped). "//" collapses to one boundary.
_STRUCTURAL = re.compile(r"//+|[|~·•⤀⬴／⁄\n\r\t" + _BOUNDARY + r"]")

# A spaced dash ( - / – / — with a space on BOTH sides) = the "Artist - Track"
# boundary. Space-bounded so intra-name hyphens survive ("Cro-Magnon", "JAY-Z").
_SPACED_DASH = re.compile(r"\s[-–—]\s")

# Leading hosting/curator prefix on a region ("by Miss Monique", "w/ DJ Rae"): the
# name follows, so drop the prefix. Conservative, anchored at the region start.
_HOST_PREFIX = re.compile(
    r"^(?:by|w/|hosted\s+by|presented\s+by|host)\s+", re.IGNORECASE
)

_RE_SPACES = re.compile(r"\s+")

# Characters trimmed off a candidate's edges (residual quotes/brackets/punctuation).
_EDGE_TRIM = " \t\"'`.:;!?/\\-–—([{)]}<>*"

# A candidate must carry at least one Unicode letter — drops pure-number / pure-
# symbol residue ("123", "#", "-") while keeping non-Latin names (Japanese, …).
_HAS_LETTER = re.compile(r"[^\W\d_]")


# ── internal helpers ─────────────────────────────────────────────────────────


def strip_title_noise(title):
    """Replace every recognised noise brick (DATE/FORMAT/EP) by a boundary sentinel.

    Returns the sentinel-tagged string (exposed for tests). Passes run in
    ``_NOISE_PASSES`` order so a year is claimed by DATE before EP's bare
    ``\\d{3,}`` could grab it, and a FORMAT phrase before EP's "mix N" could.
    """
    s = title or ""
    for pattern in _NOISE_PASSES:
        s = pattern.sub(f" {_BOUNDARY} ", s)
    return s


def _classify_brackets(text):
    """Resolve ``(...)`` / ``[...]`` spans by content.

    A bracket whose content reduces to pure noise (date/format/episode) is dropped;
    otherwise the content is kept INLINE but fenced by a boundary, so a bracketed
    name ("(Live Set)" → dropped, "(Kaytranada)" → its own region) never glues onto
    the neighbouring text.
    """
    def repl(m):
        inner = m.group(1)
        if not _residue(inner):
            return " "  # pure noise → drop the whole bracket
        return f" {_BOUNDARY} {inner} {_BOUNDARY} "

    prev = None
    out = text or ""
    # Repeat to unwrap nested/adjacent brackets; bounded by convergence.
    while prev != out:
        prev = out
        out = re.sub(r"\(([^()]*)\)", repl, out)
        out = re.sub(r"\[([^\[\]]*)\]", repl, out)
    return out


def _residue(text):
    """True when ``text`` still holds a non-noise word once the bricks are peeled.

    Used to decide whether a bracket / region carries any candidate material at all.
    """
    peeled = strip_title_noise(text)
    for chunk in _STRUCTURAL.split(peeled):
        if _HAS_LETTER.search(chunk or ""):
            return True
    # a bare number is noise; a letter run anywhere is residue
    return bool(_HAS_LETTER.search(peeled or ""))


def _cut_venue(text):
    """Drop the venue tail introduced by ``@`` ("Artist @ Club, City 2026").

    Keeps the head (the artist region); if the title STARTS with ``@`` (an empty
    head, e.g. "@channel …") the tail is kept instead so nothing is lost.
    """
    if "@" not in (text or ""):
        return text
    head, _, tail = text.partition("@")
    return head if head.strip() else tail


def _first_dash_region(region):
    """Collapse an "Artist - Track" region to its LEADING (artist) segment.

    Splits on the spaced dash and returns the first NON-EMPTY segment — the DJ-first
    convention. "Ley Moore - Songs of Spring" → "Ley Moore"; a region with no spaced
    dash is returned unchanged.
    """
    parts = _SPACED_DASH.split(region)
    for part in parts:
        if part.strip():
            return part
    return ""


def split_artists(text):
    """Split one artist region into individual names on every connector.

    Uses the combined :data:`_CONNECTOR` alternation — the DJ line-up joins
    (B2B/B3B/F2F/VS/X) plus the ``artist_names`` word connectors (feat/ft/vs/
    presents/pres/with) and punctuation separators (``&/|;,+``). Returns the raw
    (untrimmed, un-cleaned) fragments in order; empty fragments are dropped.
    """
    return [p for p in _CONNECTOR.split(text or "") if p and p.strip()]


def _clean_candidate(raw):
    """Turn a raw fragment into a clean candidate name, or ``None`` to reject it.

    Trims edge punctuation, strips the leading hosting prefix, applies
    ``artist_names.strip_artist_noise``, compacts whitespace, and rejects: an empty
    string, a compilation/unknown PLACEHOLDER (``is_placeholder_artist``), and a
    fragment with no letter (pure number/symbol residue).
    """
    name = (raw or "").strip()
    name = _HOST_PREFIX.sub("", name)
    name = name.strip(_EDGE_TRIM)
    name = strip_artist_noise(name)
    name = _RE_SPACES.sub(" ", name).strip(_EDGE_TRIM).strip()
    if not name:
        return None
    if is_placeholder_artist(name):
        return None
    if not _HAS_LETTER.search(name):
        return None
    return name


def _dedup_key(name):
    """Fold key for de-duplication: the punctuation-insensitive key, or (when it
    folds to blank — a fully non-Latin name) the case-folded string itself."""
    return punct_fold_key(name) or fold_base(name) or name.casefold()


# ── public API ───────────────────────────────────────────────────────────────


def extract_artist_candidates(title, channel):
    """Extract ordered, de-duplicated artist CANDIDATES from a set ``(title, channel)``.

    Returns a ``list[Candidate]``. The pipeline is subtractive:

      1. Peel brackets by content, drop the ``@`` venue tail, replace DATE/FORMAT/EP
         bricks with region boundaries.
      2. Split the title into structural regions (venue/label/field boundaries);
         collapse each "Artist - Track" region to its leading segment; split each
         region on the line-up connectors into individual names.
      3. Clean every name (``artist_names`` hygiene, placeholder rejection); the
         leading region's names are flagged ``is_boosted``.
      4. ALWAYS add ``channel`` (split the same way, source ``"channel"``).
      5. De-duplicate by fold key, first occurrence wins, order preserved (title
         candidates before channel, boosted first by construction).

    NO existence/Deezer check here — a later lot verifies; this only proposes.
    """
    out = []
    seen = set()

    def _emit(raw, source, boosted):
        name = _clean_candidate(raw)
        if name is None:
            return
        key = _dedup_key(name)
        if key in seen:
            return
        seen.add(key)
        out.append(Candidate(name=name, source=source, is_boosted=boosted))

    # ── title ──
    prepared = _classify_brackets(title or "")
    prepared = _cut_venue(prepared)
    prepared = strip_title_noise(prepared)
    for idx, region in enumerate(_STRUCTURAL.split(prepared)):
        region = _first_dash_region(region or "")
        if not region.strip():
            continue
        for part in split_artists(region):
            _emit(part, "title", idx == 0)

    # ── channel (always) ──
    for part in split_artists(channel or ""):
        _emit(part, "channel", False)

    return out


def extract_candidate_names(title, channel):
    """Convenience wrapper: just the ordered, de-duplicated candidate NAMES."""
    return [c.name for c in extract_artist_candidates(title, channel)]
