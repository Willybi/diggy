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
  * ``channel`` is emitted as a candidate (source ``"channel"``) — the single best
    proxy for "the DJ" — UNLESS it is a KNOWN media/label channel (C2c-3,
    ``set_title_meta.is_known_channel``): Boiler Room / NTS / RA host countless DJs
    and are never the artist, so emitting them was a systematic false positive.

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
    space_fold_key,
    strip_artist_noise,
)
from workers.set_artist_media_denylist import MEDIA_TITLE_KEYS
from workers.set_title_meta import is_known_channel

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

# Roman numeral (non-empty, well-formed 1–4999), matched ONLY as the count AFTER an
# episode marker — never on its own — so a lone "X"/"V"/"I" (a connector or a real
# name) is never stripped. The leading lookahead forces at least one roman letter
# (the standard bounded pattern otherwise also matches the empty string).
_ROMAN = r"(?=[mdclxvi])m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"

# EP — episode/volume/part markers + a count (arabic digits OR a roman numeral) + a
# bare 3+ digit run. Runs AFTER date so years are already gone. The count after a
# marker accepts arabic (existing behaviour, unchanged) AND roman ("Part II", "Vol.
# III", "Pt IV", "Chapter V"); a bare "#N" and a lone 3+ digit run stay arabic-only.
_EP = re.compile(
    r"(?<!\w)(?:"
    r"s\d{1,3}e\d{1,3}"
    r"|(?:ep|episode|vol|volume|part|pt|set|mix|chapter|ch|day|week|night|"
    r"edition|edt|no|nr)\.?\s*#?\s*(?:\d{1,4}|" + _ROMAN + r")"
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
#
# C2a — VERBAL line-up connectors introduce a guest ("X invites Y", "X meets Y",
# "X avec Y") the same way B2B does, plus "by" as an INTERNAL host separator
# ("… by Ladaeg" mid-region, generalising _HOST_PREFIX which only caught it at the
# region start). All word-bounded, so "invite" never fires inside a longer word and
# "by" never inside "Baby". ("with"/"w" already come from artist_names._SPLIT_WORDS,
# so "w/" is already split via the "w" token + the "/" punctuation separator.)
_CONNECTOR_WORDS = [
    "b2b", "b3b", "b4b", "f2f", "versus", "vs", "x",
    "invites", "invite", "invita", "meets", "avec", "by",
]

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
#
# C2a — added: the colon ":", directional ARROWS (→ ⟶ ➤, plus the pre-existing ⤀ ⬴)
# and BOX-DRAWING glyphs (═ ╚ ╗ ║ ┃ │) used as ornamental separators in some
# channels' titles.
# C2b — the colon is a boundary ONLY when followed by a space (`:(?=\s)`, zero-width
# lookahead): "Show: Guest" / "The Beat Mix: Nelly" still split, but a colon glued
# INSIDE a token no longer cuts it — "Blond:ish" stays one region and a bare time
# "21:00" is inert (all corpus split targets carry ": " with a space).
_STRUCTURAL = re.compile(
    r"//+|:(?=\s)|[|~·•⤀⬴／⁄→⟶➤═╚╗║┃│\n\r\t" + _BOUNDARY + r"]"
)

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

# C2c-3 — NON-ARTIST denylist: bare tokens that match a Deezer/base artist by
# accident but are music GENRES, residual FORMAT words, or very common CITY names —
# a systematic false positive of the extractor (a set titled "Boiler Room Athens" or
# "… - House" would otherwise propose "Athens" / "House" as a DJ). A candidate whose
# key is in here is rejected. DELIBERATELY CONSERVATIVE (invariant #4): only
# UNAMBIGUOUS non-artist tokens — a word that is ALSO a real artist/band is left OUT
# (e.g. "Jungle", "Chicago" are famous bands; it costs precision on that lone word,
# never recall on a real DJ). Matched on ``space_fold_key`` (punctuation AND spaces
# dropped) so every spelling of a multi-word genre collapses to one key: "Tech House"
# == "Tech-House" == "techhouse", "DnB" == "dnb", "Drum and Bass" == "drumandbass".
_NOT_ARTIST_TERMS = [
    # music genres
    "house", "tech house", "deep house", "afro house", "melodic house",
    "melodic techno", "progressive house", "techno", "minimal", "disco",
    "nu disco", "trance", "psytrance", "electro", "electronica", "dnb",
    "drum and bass", "drum n bass", "dubstep", "ambient", "downtempo",
    "breakbeat", "uk garage", "hardgroove", "afrobeat", "amapiano",
    "reggaeton", "dancehall",
    # residual format words not already stripped as noise bricks
    "radio", "fm", "records", "recordings", "soundsystem", "collective",
    # very common city names (never the DJ when they appear alone)
    "athens", "berlin", "london", "brooklyn", "paris", "amsterdam", "sydney",
    "ibiza", "detroit",
]
# The hand-written terms above (genres/cities/format words) UNIONED with the
# curated media/non-artist denylist (radios, magazines, labels, festivals, mix
# series, uploader handles — see :mod:`workers.set_artist_media_denylist`), both
# keyed on ``space_fold_key`` so a title candidate whose space-fold matches either
# source is rejected. Frozenset dedups the overlap naturally.
_NOT_ARTIST = frozenset(
    k for k in (space_fold_key(t) for t in _NOT_ARTIST_TERMS) if k
) | MEDIA_TITLE_KEYS


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


def _dash_segments(region):
    """Split an "Artist - Track" region on the spaced dash, returning EVERY
    non-empty segment in order (DJ-first segment kept first).

    C2a — the old behaviour collapsed the region to its leading segment only
    ("Ley Moore - Songs of Spring" → "Ley Moore"), which lost a buried artist sitting
    AFTER the dash ("Krossfingers Podcast - Suzanne Kraft", "344 - The Boom Room -
    Dennis Quin"). Now both/all sides are emitted; the caller boosts only the first
    segment of the leading region, and the extra track-title candidates are filtered
    downstream by the Deezer verification (invariant #4: over-propose, never mis-link).
    A region with no spaced dash yields a single segment (itself).
    """
    return [p for p in _SPACED_DASH.split(region) if p and p.strip()]


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
    string, a compilation/unknown PLACEHOLDER (``is_placeholder_artist``), a fragment
    with no letter (pure number/symbol residue), and a NON-ARTIST token (genre /
    residual format word / common city, :data:`_NOT_ARTIST`, C2c-3).
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
    if space_fold_key(name) in _NOT_ARTIST:
        return None
    return name


def _dedup_key(name):
    """Fold key for de-duplication: the punctuation-insensitive key, or (when it
    folds to blank — a fully non-Latin name) the case-folded string itself."""
    return punct_fold_key(name) or fold_base(name) or name.casefold()


def _emit_regions(text, source, emit, boost_leading):
    """Run one text through the shared SUBTRACTIVE pipeline and emit its candidates.

    strip DATE/FORMAT/EP noise (``strip_title_noise``) → split into structural
    regions (``_STRUCTURAL``) → split each region on the spaced dash into segments
    (``_dash_segments``, BOTH sides) → split each segment on the line-up connectors
    (``split_artists``) → ``emit`` every surviving fragment.

    C2b — factored out of the title path so the ``channel`` goes through the SAME
    region/dash/strip-noise/connector treatment instead of the old raw connector
    split, recovering artists that live ONLY in the channel ("Wilson Frisk -
    HouseBound Radio Show" → "Wilson Frisk", "Antony Daly 586" → "Antony Daly").
    ``boost_leading`` flags the first segment of the first region ``is_boosted``
    (title only); the channel passes ``False``.
    """
    prepared = strip_title_noise(text or "")
    for idx, region in enumerate(_STRUCTURAL.split(prepared)):
        if not (region or "").strip():
            continue
        for seg_idx, segment in enumerate(_dash_segments(region)):
            boosted = boost_leading and idx == 0 and seg_idx == 0
            for part in split_artists(segment):
                emit(part, source, boosted)


# ── public API ───────────────────────────────────────────────────────────────


def extract_artist_candidates(title, channel):
    """Extract ordered, de-duplicated artist CANDIDATES from a set ``(title, channel)``.

    Returns a ``list[Candidate]``. The pipeline is subtractive:

      1. Peel brackets by content, drop the ``@`` venue tail (title-specific
         pre-steps).
      2. Run the title through the shared subtractive pipeline (``_emit_regions``):
         strip DATE/FORMAT/EP bricks, split into structural regions (venue/label/
         field boundaries), split each "Artist - Track" region on the spaced dash
         into segments (BOTH sides emitted, C2a), split each segment on the line-up
         connectors into names. The FIRST segment of the leading region is boosted.
      3. Clean every name (``artist_names`` hygiene, placeholder rejection).
      4. Add ``channel`` UNLESS it is a KNOWN media/label channel (C2c-3), run through
         the SAME pipeline (C2b — region/dash/strip-noise/connectors, not just a raw
         connector split), source ``"channel"``, never boosted.
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

    # ── title (bracket-classify + venue-cut, then the shared pipeline) ──
    prepared = _classify_brackets(title or "")
    prepared = _cut_venue(prepared)
    _emit_regions(prepared, "title", _emit, boost_leading=True)

    # ── channel — SAME pipeline as the title (C2b), never boosted. C2c-3: a KNOWN
    #    media/label channel (Boiler Room, NTS, RA, …) is the host, not the DJ, so it
    #    is NOT emitted as a candidate; an out-of-gazetteer channel (an artist's own
    #    account, "Fred again..") is still emitted. ──
    if channel and not is_known_channel(channel):
        _emit_regions(channel, "channel", _emit, boost_leading=False)

    return out


def extract_candidate_names(title, channel):
    """Convenience wrapper: just the ordered, de-duplicated candidate NAMES."""
    return [c.name for c in extract_artist_candidates(title, channel)]
