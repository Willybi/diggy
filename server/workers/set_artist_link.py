"""Pure name→artist resolution helpers for the set-artist linker (no I/O, no session).

C2c-1 — the set-title extractor (:mod:`workers.set_artist_extract`) PROPOSES artist
CANDIDATES from a set's ``(title, channel)``; this module turns a candidate name
into a REAL artist by resolving it FIRST against our own artist base. It ships the
three PURE, testable building blocks that resolution needs — nothing else:

  * :func:`build_artist_lookup` — fold a ``(name, artist_id)`` corpus into a
    fold-key → id map (placeholders and blank folds excluded).
  * :func:`resolve_name_to_id` — lookup-only name → id (no creation).
  * :func:`scan_known_artists` — find KNOWN multi-token artists buried in a title.

It is DELIBERATELY the same acabit as :mod:`workers.set_artist_extract` /
:mod:`workers.artist_names`: PURE, stdlib + ``workers`` siblings only, importable
from the worker, the API and the ops scripts alike (no celery/redis/DB/Deezer). The
DB loader that builds the ``(name, artist_id)`` corpus (artist main names + aliases)
and the actual linking (``resolve → verify Deezer → link_set_artists``) live in the
NEXT lot (C2c-2) — this one wires nothing.

The fold key is the extractor's :func:`~workers.set_artist_extract._dedup_key`
(``punct_fold_key`` with a ``fold_base`` / casefold fallback), reused verbatim so a
name resolves under the SAME key the extractor de-duplicates candidates by — hence
"St. Germain" == "St Germain", "Mr. Oizo" == "Mr Oizo", etc. (invariant #4: the
lookup only matches spellings that fold identically, never a fuzzy guess).
"""

import re

from workers.artist_names import is_placeholder_artist, punct_fold_key
from workers.set_artist_extract import _dedup_key

# Junk artist keys inherited in the base: an OLD matcher created rows like "Part 2"
# (real id 131031), "Vol 3", "Mix 5" — an episode/volume MARKER followed by a NUMBER
# — as if they were artists. They are NOT cleaned from prod (no migration); instead
# the free-text scan NEUTRALISES them here so they are never dug out of a title's
# "… (Part 2)" tail (which produced a spurious source=base link). A folded lookup key
# that is EXACTLY a known marker word + a number is excluded from the scan. Only the
# marker words fire: a real artist that carries a number but NO marker ("Aux 88",
# "Front 242", "Sunset 102" — "aux"/"front"/"sunset" are not markers) stays scannable.
# resolve_name_to_id (an ISOLATED candidate) is deliberately NOT affected — only the
# free-text scan unearths this junk.
_JUNK_MARKER_KEY = re.compile(
    r"^(?:part|pt|vol|volume|mix|set|ep|episode|chapter|ch|no|nr|"
    r"day|week|night|edition|session|show|podcast)\s+\d+$"
)

# ── fold key (aligned with the extractor's _dedup_key) ────────────────────────


def _fold_key(name: str) -> str:
    """The extractor's de-dup fold key, stripped. Empty ⇒ "no signal" (blank names,
    or a fully non-Latin name that folds away)."""
    return _dedup_key(name).strip() if name else ""


# ── build_artist_lookup ───────────────────────────────────────────────────────


def build_artist_lookup(pairs):
    """Build a ``fold_key → artist_id`` map from ``(name, artist_id)`` pairs.

    ``pairs`` is any iterable of ``(name, artist_id)`` (typically an artist's main
    name AND its aliases, both pointing at the same id — supplied by the C2c-2 DB
    loader). Each name is folded through :func:`_fold_key`; a name that is a
    compilation/unknown PLACEHOLDER (:func:`~workers.artist_names.is_placeholder_artist`)
    or whose fold is EMPTY is skipped. On a fold-key COLLISION (two spellings folding
    the same) the FIRST pair wins, so the result is deterministic given a stable input
    order.
    """
    lookup: dict[str, int] = {}
    for name, artist_id in pairs:
        if not name or is_placeholder_artist(name):
            continue
        key = _fold_key(name)
        if not key:
            continue
        lookup.setdefault(key, artist_id)
    return lookup


# ── resolve_name_to_id ─────────────────────────────────────────────────────────


def resolve_name_to_id(name, lookup):
    """Return the ``artist_id`` whose fold key matches ``name``, or ``None``.

    Lookup-only — NEVER creates an artist (that is the DB caller's job in C2c-2).
    Folds ``name`` with the SAME :func:`_fold_key` used to build ``lookup``; a blank
    fold (empty / fully non-Latin name) returns ``None`` ("no signal, do not match").
    """
    key = _fold_key(name)
    if not key:
        return None
    return lookup.get(key)


# ── scan_known_artists ─────────────────────────────────────────────────────────

# Edge characters trimmed off each raw title token before folding — structural
# wrappers a name is never really made of (brackets, quotes, pipes, slashes, …).
# Intra-name punctuation (``.'-,``) is DELIBERATELY left to the folder, and a lone
# spaced dash "-" survives the trim then folds to "" — so it acts as a run boundary
# between the "Artist - Track" halves.
_SCAN_EDGE = "()[]{}<>|/\\\"'`“”*!?:;~"


def _scan_tokens(title):
    """Whitespace-tokenise ``title`` into ``(folded, original)`` token pairs.

    Each raw token is edge-trimmed (:data:`_SCAN_EDGE`) then folded with
    :func:`~workers.artist_names.punct_fold_key`. A token that folds to "" (a lone
    dash, a pure-symbol chunk, a fully non-Latin word) keeps an empty ``folded`` and
    acts as a contiguity BREAK during the scan.
    """
    tokens = []
    for raw in (title or "").split():
        cleaned = raw.strip(_SCAN_EDGE)
        tokens.append((punct_fold_key(cleaned), cleaned))
    return tokens


def scan_known_artists(title, lookup):
    """Find KNOWN artists buried in ``title`` as contiguous token runs.

    Scans the folded title for any ``lookup`` fold key of **≥ 2 tokens** appearing as
    a run of contiguous title tokens, and returns ``[(matched_name, artist_id), …]``
    in order of appearance (the matched name is reconstructed from the ORIGINAL title
    tokens, casing preserved). Matches are NON-OVERLAPPING and LONGEST-FIRST: at each
    position the longest key that matches wins, then the scan advances past it — so
    "Deep Space Orchestra …" prefers "Deep Space Orchestra" over "Deep Space".

    CRITICAL PRECISION GUARD: only keys of ≥ 2 tokens are ever scanned. A single-word
    artist key ("Live", "Move", "Fabric") is far too collision-prone for a free-text
    scan — it would match an unrelated artist at random — so mono-token keys are
    excluded here (they are still resolvable by :func:`resolve_name_to_id` on an
    isolated candidate). This is what recovers "Ricardo Villalobos" out of "Ricardo
    Villalobos Recorded Live from …" WITHOUT any mono-word false positive.
    """
    if not title or not lookup:
        return []
    scannable = {
        k
        for k in lookup
        if len(k.split()) >= 2 and not _JUNK_MARKER_KEY.match(k)
    }
    if not scannable:
        return []
    max_len = max(len(k.split()) for k in scannable)

    tokens = _scan_tokens(title)
    n = len(tokens)
    out = []
    i = 0
    while i < n:
        if not tokens[i][0]:
            i += 1
            continue
        matched = False
        upper = min(max_len, n - i)
        for length in range(upper, 1, -1):
            run = tokens[i : i + length]
            if any(not folded for folded, _ in run):
                continue  # a blank token breaks contiguity → this length can't match
            key = " ".join(folded for folded, _ in run)
            if key in scannable:
                name = " ".join(original for _, original in run)
                out.append((name, lookup[key]))
                i += length
                matched = True
                break
        if not matched:
            i += 1
    return out
