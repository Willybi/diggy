"""
Celery tasks for artist sync, artwork fetching, and set artist linking.
"""

import asyncio
import logging
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Artist-string separators — one canonical source, shared by sync_artists
# Phase A (classify_artist_string) and Phase C (split_artist_parts). Keep the
# order feat → comma → ampersand → pipe: it is significant (a "A feat B & C"
# name resolves on feat first). "|" reads like "&" (duo / collab). This regex is
# scoped to the sync task only — do NOT unify it with deezer_enrich._first_artist,
# beatport._ARTIST_SEPARATORS or migration 0023 (different jobs).
FEAT_RE = re.compile(r"\s+(?:feat\.?|featuring|ft\.?|vs\.?)\s+", flags=re.IGNORECASE)

# " presents " family — a stage/alias notation ("Larry Heard presents Mr. White",
# "Antoine Clamaran pres. D-Plac"). Like feat it is a LOCAL split (no Deezer round
# trip), but every token is a PRIMARY artist, not a featured contributor. Kept
# separate from FEAT_RE (different role) and — like FEAT_RE — deliberately NOT
# unified with deezer_enrich._first_artist / beatport._ARTIST_SEPARATORS /
# migration 0023 (different jobs). "presents"/"présente" precede "pres\.?" in the
# alternation so the long forms win; "pres\.?" covers both "pres." and bare "pres".
PRESENTS_RE = re.compile(r"\s+(?:presents|présente|pres\.?)\s+", flags=re.IGNORECASE)

# Space-bounded, case-insensitive "&"-family separators, routed through the SAME
# "ampersand" rule as " & " / " + " / "|" (Deezer disambiguation unless a token is
# already known). Bounded by \s+ like FEAT_RE. Unlike "&"/"+"/"|", each of these
# can legitimately occur INSIDE a real artist name, so two pure guards protect
# them: _is_stylized_name (a letter-by-letter name like "A X L") and
# _article_after_separator (a group name like "Amyl and the Sniffers").
#   " x "   — collab notation          " and " — EN "and"
#   " y "   — ES "and"                  " e "   — PT / IT "and"
X_RE = re.compile(r"\s+x\s+", flags=re.IGNORECASE)
AND_RE = re.compile(r"\s+and\s+", flags=re.IGNORECASE)
Y_RE = re.compile(r"\s+y\s+", flags=re.IGNORECASE)
E_RE = re.compile(r"\s+e\s+", flags=re.IGNORECASE)

# Right-hand articles that mark a group-name continuation after " and " / " y "
# ("Amyl and the Sniffers", "Cortijo Y Su Maquina Del Tiempo") rather than a
# two-artist collab. Multilingual: EN the/a/an, FR la/le/les, ES el/los/las/su/sus,
# PT/IT os/as/o/il/i. Compared lower-cased against the FIRST word of the token that
# follows the separator (see _article_after_separator).
_ARTICLES = frozenset(
    {
        "the", "a", "an",
        "la", "le", "les",
        "el", "los", "las", "su", "sus",
        "os", "as", "o", "il", "i",
    }
)


def _is_stylized_name(raw):
    """True when a name is a single artist spelled letter-by-letter — the MAJORITY
    of its whitespace-separated tokens are one character long ("A X L",
    "t e s t p r e s s", "J A Y E L E C T R O N I C A").

    Such a name must never be split on a space-bounded separator (" x ", " and ",
    " y ", " e "): the spacing is stylistic, not a collab. The guard therefore sits
    AFTER the unambiguous delimiters (comma / & / + / |) and BEFORE the
    space-bounded ones in both classify_artist_string and split_artist_parts, so
    "A X L, SH.AH" still splits on the comma while a bare "A X L" stays single.
    """
    tokens = raw.split()
    if not tokens:
        return False
    single = sum(1 for t in tokens if len(t) == 1)
    return single > len(tokens) / 2


def _article_after_separator(tokens):
    """True when a token AFTER the first begins with an article (see _ARTICLES).

    For " and " / " y " an article on the right-hand side signals a group-name
    continuation ("Amyl and the Sniffers", "Cortijo Y Su Maquina Del Tiempo")
    rather than a collab, so the raw string must stay a single artist instead of
    being split. ``tokens`` is the already-split, stripped, non-empty token list.
    """
    for token in tokens[1:]:
        words = token.split()
        if words and words[0].lower() in _ARTICLES:
            return True
    return False


def classify_artist_string(raw, known_norms):
    """Pure Phase A dispatch for a catalog `artist` string — no I/O, no session.

    Mirrors sync_artists Phase A exactly. Precedence (a string splits on the FIRST
    separator matched, so the order is significant):
      1.  feat / ft / vs (FEAT_RE)       → split, contributors after the first 'featured'
      2.  presents / pres. (PRESENTS_RE) → split LOCALLY, every token 'primary'
      3.  ","                            → known-check → split | needs_deezer('comma')
      4.  " & "   5. " + "   6. "|"      → known-check → split | needs_deezer('ampersand')
      7.  stylized-name guard            → single (letter-by-letter name, never split)
      8.  " x "                          → known-check → split | needs_deezer('ampersand')
      9.  " and "  10. " y "             → article-after → single ; else known-check → …
      11. " e "                          → known-check → split | needs_deezer('ampersand')
      12. otherwise                      → single
    Returns one of:
      ("split", tokens)               — resolve locally, create each token
      ("needs_deezer", tokens, rule)  — defer to Deezer (rule 'comma'/'ampersand')
      ("single", [raw])               — no actionable separator, create the string as-is
    `known_norms` is the live set of normalized artist/alias names; a comma/
    ampersand-family pair with at least one already-known token is treated as a
    collab and split locally, otherwise it is deferred to Deezer. Steps 7/9-10 are
    anti false-positive guards; feat/presents (steps 1-2) split with no Deezer call.
    """
    from utils import normalize

    raw = raw.strip()
    if FEAT_RE.search(raw):
        return ("split", [p.strip() for p in FEAT_RE.split(raw) if p.strip()])
    if PRESENTS_RE.search(raw):
        # Alias notation — a purely LOCAL split (no Deezer), every token primary.
        return ("split", [p.strip() for p in PRESENTS_RE.split(raw) if p.strip()])
    if "," in raw:
        tokens = [p.strip() for p in raw.split(",") if p.strip()]
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "comma")
    if " & " in raw:
        tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "ampersand")
    if " + " in raw:
        # "+" reads like "&": same ampersand rule. A space-bounded " + " is never
        # part of a real artist name, so a direct split is safe (no guard needed).
        tokens = [p.strip() for p in raw.split(" + ") if p.strip()]
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "ampersand")
    if "|" in raw:
        # Bare "|" — no surrounding spaces required: source strings use both
        # "A | B" and "A|B". Unlike "&"/","/space, a pipe is never part of a real
        # artist name, so splitting on it directly is safe.
        tokens = [p.strip() for p in raw.split("|") if p.strip()]
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        # "|" reads like "&": route it through the same rule_type so Phase B
        # disambiguates it full-string-vs-tokens instead of dropping it.
        return ("needs_deezer", tokens, "ampersand")
    if _is_stylized_name(raw):
        # Letter-by-letter stylized name ("A X L") — never split on a space-bounded
        # separator. Placed AFTER comma/&/+/| (so "A X L, SH.AH" still splits on the
        # comma) and BEFORE " x "/" and "/" y "/" e ".
        return ("single", [raw])
    if X_RE.search(raw):
        tokens = [p.strip() for p in X_RE.split(raw) if p.strip()]
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "ampersand")
    if AND_RE.search(raw):
        tokens = [p.strip() for p in AND_RE.split(raw) if p.strip()]
        if _article_after_separator(tokens):
            # "Amyl and the Sniffers" — article after " and " = group name, not a collab.
            return ("single", [raw])
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "ampersand")
    if Y_RE.search(raw):
        tokens = [p.strip() for p in Y_RE.split(raw) if p.strip()]
        if _article_after_separator(tokens):
            # "Cortijo Y Su Maquina Del Tiempo" — article after " y " = group name.
            return ("single", [raw])
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "ampersand")
    if E_RE.search(raw):
        tokens = [p.strip() for p in E_RE.split(raw) if p.strip()]
        if any(normalize(t) in known_norms for t in tokens):
            return ("split", tokens)
        return ("needs_deezer", tokens, "ampersand")
    return ("single", [raw])


def split_artist_parts(raw):
    """Pure Phase C part-building — no I/O, no session.

    Mirrors sync_artists Phase C AND classify_artist_string exactly: the SAME
    precedence and the SAME two guards (stylized name, article after " and "/
    " y "). If it diverged, Phase C would try to link tokens Phase A never created.
    Returns [(token, role, position), ...] with role 'featured' for feat
    contributors after the first, 'primary' otherwise (presents / comma /
    ampersand-family / no-separator are all 'primary').
    """
    raw = raw.strip()
    parts = []
    if FEAT_RE.search(raw):
        tokens = [p.strip() for p in FEAT_RE.split(raw) if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary" if i == 0 else "featured", i))
    elif PRESENTS_RE.search(raw):
        tokens = [p.strip() for p in PRESENTS_RE.split(raw) if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    elif "," in raw:
        tokens = [p.strip() for p in raw.split(",") if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    elif " & " in raw:
        tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    elif " + " in raw:
        tokens = [p.strip() for p in raw.split(" + ") if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    elif "|" in raw:
        tokens = [p.strip() for p in raw.split("|") if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    elif _is_stylized_name(raw):
        parts.append((raw, "primary", 0))
    elif X_RE.search(raw):
        tokens = [p.strip() for p in X_RE.split(raw) if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    elif AND_RE.search(raw):
        tokens = [p.strip() for p in AND_RE.split(raw) if p.strip()]
        if _article_after_separator(tokens):
            parts.append((raw, "primary", 0))
        else:
            for i, token in enumerate(tokens):
                parts.append((token, "primary", i))
    elif Y_RE.search(raw):
        tokens = [p.strip() for p in Y_RE.split(raw) if p.strip()]
        if _article_after_separator(tokens):
            parts.append((raw, "primary", 0))
        else:
            for i, token in enumerate(tokens):
                parts.append((token, "primary", i))
    elif E_RE.search(raw):
        tokens = [p.strip() for p in E_RE.split(raw) if p.strip()]
        for i, token in enumerate(tokens):
            parts.append((token, "primary", i))
    else:
        parts.append((raw, "primary", 0))
    return parts


# ── Artist Deezer link backlog (loop-safe, mirror of the catalog enrich pattern)
# The 2026-07-13 incident: the old fetch_artist_artworks selected every
# linked-without-artwork artist in one asyncio.gather with a single final
# commit, blew past the 30-min soft limit, and — being decorated with
# autoretry_for=(Exception,) — retried the SoftTimeLimitExceeded forever,
# re-downloading everything and committing nothing. The link and artwork passes
# are now two separate budget-capped, batch-committing, Redis-locked tasks with
# NO autoretry_for=(Exception,) (that decorator is what made the timeout loop).

# E1-style re-scan backoff for artist Deezer link searches (mirror of the
# catalog tiers in workers/enrichment.py): a no-match artist is retried after 30
# then 90 days, then abandoned for good after 3 attempts.
ARTIST_RESCAN_TIER2_DAYS = 30
ARTIST_RESCAN_TIER3_DAYS = 90
ARTIST_MAX_SEARCH_ATTEMPTS = 3

# Max artist link searches per run. Code-defaulted (not in .env), env-overridable
# like ENRICH_NIGHTLY_BUDGET. The cap is the PRIMARY loop guard: dimensioned well
# under soft_time_limit (1500 searches ÷ 10 req/s ≈ 150s) so the run finishes in
# minutes and the timeout that triggered the retry storm never fires.
ARTIST_LINK_DEFAULT_BUDGET = 1500
# Max artist artwork downloads per nightly run — same loop-guard role. Sized to
# drain the linked-without-artwork backlog in ~2 nights (~10 req/s Deezer →
# ~1000s for 10000), then trivial in steady state (only new artists remain).
# Overridable per call (budget arg) for an ad-hoc bigger drain.
ARTIST_ARTWORK_DEFAULT_BUDGET = 10000

# Single-instance locks: TTL strictly above each task's time_limit so the lock
# cannot expire while a legitimate run is still in progress.
LINK_ARTISTS_LOCK_TTL = 1800  # > link time_limit (1500)
FETCH_ARTIST_ARTWORKS_LOCK_TTL = 3600  # > artwork time_limit (3300)
SYNC_ARTISTS_LOCK_TTL = 4800  # > sync_artists time_limit (4500)
# link_set_artists has no explicit time_limit → the global CELERY_TIME_LIMIT (3600)
LINK_SET_ARTISTS_LOCK_TTL = 4200  # > global time_limit (3600)
BACKFILL_MULTI_ARTISTS_LOCK_TTL = 9300  # > backfill time_limit (9000)

# Batch commit size: a kill after any chunk keeps the committed chunks (the old
# single final commit lost everything on a timeout).
ARTIST_BACKLOG_BATCH = 100

# C6.c — activity feed for followed artists.
# A Deezer release counts as fresh activity when it was published within this
# many days (one albums page is enough: we only keep recent releases).
ARTIST_ACTIVITY_RELEASE_HORIZON_DAYS = 30
# New imported sets are picked up within this window. It is wider than the daily
# cadence on purpose so a late/skipped run still catches the previous day's
# imports; the unique constraint on artist_activity dedups the overlap.
ARTIST_ACTIVITY_SET_WINDOW_HOURS = 48
# C6.c v2 — a detected release is now fully crawled into the catalog (one catalog
# track per Deezer track), so the "Nouveautés" feed renders it like any other
# track (cover, title, preview) instead of a bare external link. A Deezer release
# is an *album*: it is expanded into its tracklist and each track becomes its own
# feed card linked to a catalog entry. Safety cap so a pathological compilation
# cannot fan out unbounded (logged when hit — never silently truncated).
ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE = 40
# Single-instance lock: TTL must stay strictly above the task time_limit (3900s)
# so the lock cannot expire while a legitimate run is still in progress (same
# rule as resolve_set_tracks / recrawl_incomplete_sets).
CHECK_FOLLOWED_ARTISTS_LOCK_TTL = 4200


def _norm_artist_name(s):
    # Trailing .strip() is load-bearing: a fully non-ASCII name (Japanese
    # "桜井　哲夫", Hebrew "נוער שוליים"…) collapses to a blank string after
    # NFKD+ascii-fold — the ideographs are dropped and separators like U+3000
    # become a plain space, leaving NO identity signal. Folding to "" (rather than
    # " ") lets callers treat the empty result as "do not match": any other
    # non-latin name would fold to the same blank, so a match on it is spurious.
    s = unicodedata.normalize("NFKD", s.lower().strip())
    return s.encode("ascii", "ignore").decode().strip()


def _link_budget():
    return int(
        os.environ.get("ARTIST_LINK_NIGHTLY_BUDGET", str(ARTIST_LINK_DEFAULT_BUDGET))
    )


def _artwork_budget():
    return int(
        os.environ.get(
            "ARTIST_ARTWORK_NIGHTLY_BUDGET", str(ARTIST_ARTWORK_DEFAULT_BUDGET)
        )
    )


def _link_tiers(now):
    """SQLAlchemy predicates for artist Deezer link selection (mirror of the
    catalog tiers in workers.enrichment.select_enrich_candidates).

    Returns (tier1, retry):
      - tier1: unlinked AND never searched.
      - retry: unlinked AND E1 backoff — 1 attempt searched >30d ago, or
        2 attempts searched >90d ago.
    ``deezer_search_attempts >= ARTIST_MAX_SEARCH_ATTEMPTS`` matches neither, so
    an artist is abandoned after 3 attempts. The NOT_FOUND sentinel keeps
    deezer_id non-NULL, so confirmed-absent artists are excluded from both tiers
    (a human decision, never auto-retried).
    """
    from models import Artist
    from sqlalchemy import and_, or_

    tier1 = and_(Artist.deezer_id.is_(None), Artist.deezer_searched_at.is_(None))
    retry = and_(
        Artist.deezer_id.is_(None),
        or_(
            and_(
                Artist.deezer_search_attempts == 1,
                Artist.deezer_searched_at
                < now - timedelta(days=ARTIST_RESCAN_TIER2_DAYS),
            ),
            and_(
                Artist.deezer_search_attempts == 2,
                Artist.deezer_searched_at
                < now - timedelta(days=ARTIST_RESCAN_TIER3_DAYS),
            ),
        ),
    )
    return tier1, retry


def select_link_candidates(session, budget, now):
    """Pick artists missing a deezer_id to Deezer-search, under a budget.

    Tier 1 (never searched) drains OLDEST id first: an id-DESC order would
    starve the long backlog tail under the constant influx of freshly created
    artists. Retries (tiers 2/3, oldest search first) only consume the budget
    tier 1 leaves; the total never exceeds ``budget``.
    """
    from models import Artist
    from sqlalchemy import select

    if budget <= 0:
        return []

    tier1, retry = _link_tiers(now)

    fresh = (
        session.execute(
            select(Artist).where(tier1).order_by(Artist.id.asc()).limit(budget)
        )
        .scalars()
        .all()
    )

    remaining = budget - len(fresh)
    if remaining <= 0:
        return list(fresh)

    retries = (
        session.execute(
            select(Artist)
            .where(retry)
            .order_by(Artist.deezer_searched_at.asc())
            .limit(remaining)
        )
        .scalars()
        .all()
    )

    return list(fresh) + list(retries)


def count_link_candidates(session, now):
    """Total artists eligible for a link search (all tiers), ignoring the budget.
    Drives the dropped_by_budget stat so a capped run never reads as complete."""
    from models import Artist
    from sqlalchemy import func, or_, select

    tier1, retry = _link_tiers(now)
    return session.execute(
        select(func.count(Artist.id)).where(or_(tier1, retry))
    ).scalar_one()


def _mark_link_searched(artist, now):
    """Record a completed Deezer link search (matched or not): stamp the time and
    bump the attempt counter together. Never called on a DeezerHTTPError — an
    outage is not an attempt (E1 invariant / catalog A3-04), the artist stays
    eligible for the next run. Mirror of workers.enrichment._mark_searched."""
    artist.deezer_searched_at = now
    artist.deezer_search_attempts = (artist.deezer_search_attempts or 0) + 1


def _matching_deezer_hits(hits, name):
    """Deezer hits matching ``name``, ordered by descending fan count.

    Three match signals, tried per hit (the pre-L3 pair — raw exact + accent fold
    — PLUS the new punctuation fold), each returning the hit unchanged when it
    fires:
      (a) raw exact name equality (case-insensitive) — valid for ANY name,
          non-latin included: an exact echo is a valid identity (a Deezer hit
          spelling 桜井　哲夫 verbatim must still match).
      (b) accent fold equality (``_norm_artist_name``) — gated on a NON-EMPTY
          fold: a fully non-ASCII name folds to "" (no ASCII signal) and would
          otherwise "match" any other blank-folding name (invariant #4).
      (c) NEW punctuation fold (``punct_fold_key``): "St. Germain" == "St
          Germain", "Mr. Oizo" == "Mr Oizo". A WEAK signal, so it is refused when
          the fold key is blank, when EITHER side looks like an acronym
          ("L.I.L.Y" must NOT fold-match "Lily"), or when the hit's fan count is
          below ``FAN_FLOOR`` (a 12-fan parasite entry must not be linked). Only
          this fold is floor-gated; exact and accent matches are not.

    Sorted by ``nb_fan`` DESC so a caller preferring the most popular homonym
    picks the dominant artist. The sort is STABLE and ``reverse=True`` keeps
    stability, so hits with equal or absent fan counts retain Deezer's original
    order — i.e. the pre-L3 "first matching hit" pick is preserved when there is
    no fan signal (retro-compat).
    """
    from workers.artist_names import FAN_FLOOR, looks_acronym, punct_fold_key

    name_lower = name.lower()
    name_norm = _norm_artist_name(name)
    name_key = punct_fold_key(name)
    name_is_acronym = looks_acronym(name)

    matched = []
    for hit in hits:
        dz_name = hit.get("name", "")
        if dz_name.lower() == name_lower:
            matched.append(hit)
            continue
        if name_norm and _norm_artist_name(dz_name) == name_norm:
            matched.append(hit)
            continue
        if (
            name_key
            and not name_is_acronym
            and not looks_acronym(dz_name)
            and punct_fold_key(dz_name) == name_key
            and (hit.get("nb_fan", 0) or 0) >= FAN_FLOOR
        ):
            matched.append(hit)

    matched.sort(key=lambda h: h.get("nb_fan", 0) or 0, reverse=True)
    return matched


async def _link_artist_deezer(pool, artist, holder_map, now):
    """Search Deezer for one artist and link (or fold) it on an exact name match.

    Returns a ``(status, holder_id)`` tuple:
      - ("linked", None):   a FREE Deezer id was matched and assigned. ``holder_map``
                            is updated (dz_id → this artist's id) so a same-run
                            sibling matching the same id folds into this row.
      - ("merge", holder_id): a matching id is ALREADY held by ANOTHER artist row.
                            A held id is NOT a collision to skip — it means the SAME
                            real artist was written twice under two spellings
                            ("Nick León"/"Nick Leon": the matcher folds accents, the
                            identity key ``normalized_name`` does not). We return the
                            holder so the orchestrator folds this orphan INTO it. The
                            merge itself (DELETE/UPDATE/flush) is deferred OUT of the
                            concurrent gather — see _run_link_artists_deezer.
      - ("searched", None): the search completed but no hit matched at all. Marked.
      - ("error", None):    a Deezer outage (DeezerHTTPError). NOT marked, so the
                            artist stays eligible next run (an outage is not an
                            attempt).

    A completed search (linked / merge / searched) stamps deezer_searched_at and
    bumps deezer_search_attempts together via _mark_link_searched.

    ``holder_map`` maps every claimed deezer_id → its holder artist id (the
    NOT_FOUND sentinel excluded); both the free-id membership test and the merge
    target are read from it.
    """
    from workers.async_http import DeezerHTTPError

    try:
        data = await pool.deezer_get(
            "/search/artist", params={"q": artist.name, "limit": 10}
        )
    except DeezerHTTPError as e:
        logger.warning("Deezer artist search failed for %s: %s", artist.name, e)
        return "error", None

    _mark_link_searched(artist, now)
    # Rank the qualifying hits by fan count (most popular homonym first — L3) and
    # KEEP the free-id-over-merge preference: scan the ranked matches, link on the
    # first hit exposing a FREE id, and only fall back to merging into the top held
    # homonym when no matching hit offers a free id. This preserves the old "skip a
    # taken id, keep looking" preference — it just turns the terminal no-op
    # ("searched", orphan left NULL) into a merge into the row that already owns the
    # artist. All match signals (exact / accent fold / guarded punctuation fold) and
    # the blank-fold non-latin guard live in _matching_deezer_hits.
    merge_target = None
    for hit in _matching_deezer_hits(data.get("data", []), artist.name):
        dz_id = str(hit["id"])
        holder_id = holder_map.get(dz_id)
        if holder_id is None:
            artist.deezer_id = dz_id
            # Publish the fresh holder so a same-run duplicate processed later in
            # this batch merges into this row instead of orphaning.
            holder_map[dz_id] = artist.id
            return "linked", None
        # Held by another row → remember it as a merge fallback but keep scanning
        # for a free id. holder_id is never this orphan: an orphan has no deezer_id,
        # so it is never a value in holder_map (guarded anyway).
        if merge_target is None and holder_id != artist.id:
            merge_target = holder_id
    if merge_target is not None:
        return "merge", merge_target
    return "searched", None


@celery_app.task(
    name="workers.tasks.link_artists_deezer",
    bind=True,
    soft_time_limit=1200,
    time_limit=1500,
)
def link_artists_deezer(self):
    """Link artists with no deezer_id to Deezer, loop-safe by construction.

    Extracted from the old fetch_artist_artworks Pass 1. Single-instance: a Redis
    lock (SET NX EX, conditional release) makes overlapping runs (beat vs admin,
    or broker re-delivery) a no-op. NO autoretry_for=(Exception,) — that decorator
    is exactly what turned the 2026-07-13 soft timeout into an infinite loop
    (SoftTimeLimitExceeded IS an Exception, impossible to exclude). We rely on the
    budget cap + batch commits instead.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:link_artists"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=LINK_ARTISTS_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning(
            "link_artists_deezer already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_link_artists_deezer(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_link_artists_deezer(task):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist
    from workers.artist_merge import merge_artist_into
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()
    budget = _link_budget()

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="link_artists",
            source="deezer",
            celery_task_id=task.request.id,
        ) as clog:

            async def _async_link():
                from workers.async_http import HttpPool
                from workers.rate_limiter import RateLimiter

                now = datetime.now(timezone.utc)
                stats = {
                    "linked": 0,
                    "merged": 0,
                    "searched": 0,
                    "abandoned": 0,
                    "errors": 0,
                    "dropped_by_budget": 0,
                }

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        candidates = select_link_candidates(session, budget, now)
                        stats["dropped_by_budget"] = max(
                            0, count_link_candidates(session, now) - len(candidates)
                        )
                        if not candidates:
                            return stats

                        # Map every claimed deezer_id → its holder artist id. Two
                        # jobs: (1) the free-id membership test (an id in the map is
                        # taken) and (2) the merge target — a match on a held id
                        # means the orphan is the SAME artist as the holder (an
                        # accent/Unicode spelling twin), so it is folded INTO it.
                        # NOT_FOUND is excluded: it is not a real Deezer id, is
                        # shared by many artists, and must never be a merge target
                        # (a real hit id is always numeric, so it is never looked up
                        # anyway — excluding it just keeps the map honest).
                        holder_map = {
                            row[0]: row[1]
                            for row in session.execute(
                                select(Artist.deezer_id, Artist.id).where(
                                    Artist.deezer_id.isnot(None),
                                    Artist.deezer_id != "NOT_FOUND",
                                )
                            ).all()
                        }

                        # merge_pairs holds (orphan_id, holder_id) couples DETECTED
                        # during the concurrent gather. The merge itself is NEVER run
                        # inside the gather: the whole batch shares ONE sync Session,
                        # and merge_artist_into issues DELETE/UPDATE + flush — a
                        # coroutine mutating/flushing the session while a sibling
                        # coroutine reads it would corrupt it (same hazard as
                        # asyncio.gather-ing db.execute on one session). So the
                        # concurrent phase only COLLECTS; the merges run
                        # SEQUENTIALLY after the gather (see the post-gather loop).
                        merge_pairs = []

                        async def _link_one(artist):
                            status, holder_id = await _link_artist_deezer(
                                pool, artist, holder_map, now
                            )
                            if status == "error":
                                stats["errors"] += 1
                                return
                            stats["searched"] += 1
                            if status == "linked":
                                stats["linked"] += 1
                            elif status == "merge":
                                # Detect only — defer the DELETE/UPDATE + flush out
                                # of the gather (see merge_pairs above). Recorded by
                                # id so a later session.commit() expiring the ORM
                                # object cannot break the merge.
                                merge_pairs.append((artist.id, holder_id))
                            elif (
                                artist.deezer_search_attempts
                                >= ARTIST_MAX_SEARCH_ATTEMPTS
                            ):
                                # This no-match search hit the abandonment cap:
                                # the artist will never be re-selected.
                                stats["abandoned"] += 1

                        for i in range(0, len(candidates), ARTIST_BACKLOG_BATCH):
                            batch = candidates[i : i + ARTIST_BACKLOG_BATCH]
                            merge_pairs = []
                            await asyncio.gather(*[_link_one(a) for a in batch])
                            # Persist this batch's stampings + fresh links FIRST:
                            # each merge below runs in its OWN unit of work and a
                            # failed one is rolled back — committing here guarantees
                            # that rollback can never discard the batch's search
                            # progress.
                            session.commit()
                            # Fold each detected duplicate into its holder,
                            # SEQUENTIALLY and outside the gather. Each merge is
                            # isolated (own commit): a failure — an IntegrityError on
                            # an alias/link collision, or a holder that vanished — is
                            # rolled back and skipped, the run continues, and the
                            # orphan keeps its NULL deezer_id (E1-eligible for a later
                            # run). Merge asymmetry (invariant #4): a bad merge costs
                            # far more than a retried orphan.
                            for orphan_id, holder_id in merge_pairs:
                                try:
                                    merge_artist_into(
                                        session,
                                        source_id=orphan_id,
                                        target_id=holder_id,
                                    )
                                    session.commit()
                                    stats["merged"] += 1
                                except Exception:
                                    session.rollback()
                                    logger.warning(
                                        "link_artists_deezer: merge of artist %s "
                                        "into %s failed — rolled back, orphan left "
                                        "for a later run",
                                        orphan_id,
                                        holder_id,
                                        exc_info=True,
                                    )
                            logger.info(
                                "link_artists_deezer progress: %d/%d "
                                "(linked=%d merged=%d)",
                                min(i + ARTIST_BACKLOG_BATCH, len(candidates)),
                                len(candidates),
                                stats["linked"],
                                stats["merged"],
                            )

                        return stats

            try:
                stats = asyncio.run(_async_link())
            except Exception:
                logger.exception("link_artists_deezer failed")
                raise

            clog.set_stats(stats)

    return stats


def _assign_deezer_id(artist, dz_id, used_deezer_ids):
    """Assign dz_id to artist only if it is still free.

    Two distinct raw names can resolve to the same Deezer artist — e.g. the
    diacritic pair "Åskar"/"Askar": the Deezer search strips accents (_norm)
    while utils.normalize() keeps them, so both pass the local dedup check yet
    map to the same Deezer id. Assigning blindly would violate the partial
    unique index uq_artists_deezer_id. Err toward separation (project invariant):
    on a collision the artist is left at deezer_id=NULL rather than merged.

    Returns True when assigned, False when a truthy id was refused (collision),
    None when there was no id to assign.
    """
    if not dz_id:
        return None
    if dz_id in used_deezer_ids:
        logger.warning(
            "sync_artists: refusing deezer_id %s for artist '%s' (id=%s) — "
            "already held by another row; leaving deezer_id NULL",
            dz_id,
            artist.name,
            artist.id,
        )
        return False
    artist.deezer_id = dz_id
    used_deezer_ids.add(dz_id)
    return True


@celery_app.task(
    name="workers.tasks.sync_artists",
    bind=True,
    soft_time_limit=3600,
    time_limit=4500,
)
def sync_artists(self):
    """
    Sync artists from catalog.artist strings into the artists table.
    Phase A: local resolution (CPU-only, fast).
    Phase B: Deezer disambiguation for ambiguous names (concurrent).
    Artwork deferred to fetch_artist_artworks task.

    Single-instance: a Redis lock (SET NX EX, conditional release) makes
    overlapping runs (beat vs admin, or broker re-delivery) a no-op — the same
    pattern as link_artists_deezer / check_followed_artists. NO
    autoretry_for=(Exception,): SoftTimeLimitExceeded IS an Exception, so that
    decorator would turn a soft timeout into an infinite retry loop.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:sync_artists"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=SYNC_ARTISTS_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning("sync_artists already running (task %s), skipping", holder)
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_sync_artists(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_sync_artists(task):
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, ArtistFlag, CatalogEntry
    from utils import normalize
    from workers.artist_names import strip_artist_noise
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    # Phase A / Phase C separator logic lives in the module-level pure helpers
    # classify_artist_string() / split_artist_parts() (single source of truth,
    # unit-tested directly). FEAT_RE is now module-level too.
    engine = get_engine()

    # Start crawl log (running) — manual enter/exit to avoid re-indenting the entire body
    _log_session = Session(engine)
    _clog = CrawlLogger(
        _log_session, task_type="sync_artists", celery_task_id=task.request.id
    )
    _clog.__enter__()
    _clog_exc = None

    created = 0
    flagged = 0
    skipped = 0
    linked = 0
    dz_id_skipped = 0

    # Collect names needing Deezer disambiguation
    needs_deezer = []  # list of (raw_string, tokens, rule_type)

    try:
        with Session(engine) as session:
            all_strings = [
                r[0]
                for r in session.execute(
                    select(CatalogEntry.artist)
                    .distinct()
                    .where(CatalogEntry.artist.isnot(None))
                ).all()
            ]

            known_norms = set(
                r[0] for r in session.execute(select(Artist.normalized_name)).all()
            )
            known_norms |= set(
                r[0]
                for r in session.execute(select(ArtistAlias.normalized_alias)).all()
            )
            already_flagged = set(
                r[0]
                for r in session.execute(select(ArtistFlag.raw_artist_string)).all()
            )

            def _get_or_create(name):
                nonlocal created
                name = strip_artist_noise(name)
                norm = normalize(name)
                if norm in known_norms:
                    artist = session.execute(
                        select(Artist).where(Artist.normalized_name == norm)
                    ).scalar_one_or_none()
                    if artist and name.strip() != artist.name:
                        _ensure_alias(artist, name.strip())
                    return artist
                alias = session.execute(
                    select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
                ).scalar_one_or_none()
                if alias:
                    return session.get(Artist, alias.artist_id)
                artist = Artist(
                    name=name,
                    normalized_name=norm,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(artist)
                session.flush()
                known_norms.add(norm)
                created += 1
                return artist

            def _ensure_alias(artist, alias_name):
                if not artist or not alias_name:
                    return
                norm = normalize(alias_name)
                if norm == artist.normalized_name or norm in known_norms:
                    return
                existing = session.execute(
                    select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
                ).scalar_one_or_none()
                if existing:
                    return
                session.add(
                    ArtistAlias(
                        artist_id=artist.id, alias=alias_name, normalized_alias=norm
                    )
                )
                known_norms.add(norm)

            # Phase A: local resolution
            batch_count = 0
            for raw in all_strings:
                raw = raw.strip()
                if not raw:
                    continue
                norm = normalize(raw)
                if norm in known_norms or raw in already_flagged:
                    skipped += 1
                    continue

                decision = classify_artist_string(raw, known_norms)
                if decision[0] == "needs_deezer":
                    # Deferred to Phase B — no local creation, no commit cadence.
                    needs_deezer.append((raw, decision[1], decision[2]))
                    continue

                # "split" (create each token) or "single" (create the string):
                # both create locally and share the same batch-commit cadence.
                for name in decision[1]:
                    _get_or_create(name)
                batch_count += 1
                if batch_count % 50 == 0:
                    session.commit()

            session.commit()

        # Phase B: Deezer disambiguation (concurrent)
        if needs_deezer:

            async def _deezer_resolve():
                nonlocal created, flagged, dz_id_skipped

                from sqlalchemy.exc import IntegrityError
                from workers.async_http import DeezerHTTPError, HttpPool
                from workers.rate_limiter import RateLimiter

                async def _deezer_artist_id(pool, name):
                    try:
                        data = await pool.deezer_get(
                            "/search/artist", params={"q": name, "limit": 10}
                        )
                    except DeezerHTTPError as e:
                        logger.warning("Deezer artist search failed for %s: %s", name, e)
                        return None
                    # All match signals (raw exact / accent fold / guarded
                    # punctuation fold) and the blank-fold non-latin guard live in
                    # _matching_deezer_hits; it returns the qualifying hits ordered
                    # by fan count, so the most popular homonym wins instead of
                    # Deezer's first hit (L3). "St. Germain" now resolves "St
                    # Germain"; "L.I.L.Y" still refuses "Lily".
                    matches = _matching_deezer_hits(data.get("data", []), name)
                    return str(matches[0]["id"]) if matches else None

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        known = set(
                            r[0]
                            for r in session.execute(
                                select(Artist.normalized_name)
                            ).all()
                        )
                        known |= set(
                            r[0]
                            for r in session.execute(
                                select(ArtistAlias.normalized_alias)
                            ).all()
                        )
                        # Deezer ids already assigned in the DB. Guards against
                        # two distinct names resolving to the same Deezer artist
                        # (e.g. "Åskar"/"Askar" — _norm strips diacritics but
                        # normalize() keeps them), which would violate the partial
                        # unique index uq_artists_deezer_id.
                        used_deezer_ids = set(
                            r[0]
                            for r in session.execute(
                                select(Artist.deezer_id).where(
                                    Artist.deezer_id.isnot(None)
                                )
                            ).all()
                        )

                        for raw, tokens, rule_type in needs_deezer:
                            deezer_ids = {}
                            names_to_search = list(tokens)
                            # "|"-separated names are routed with rule_type
                            # "ampersand" (Phase A), so they resolve here too:
                            # search the full string AND the tokens.
                            if rule_type == "ampersand":
                                names_to_search = [raw] + list(tokens)

                            results = await asyncio.gather(
                                *[_deezer_artist_id(pool, n) for n in names_to_search]
                            )

                            for name, dz_id in zip(names_to_search, results):
                                deezer_ids[name] = dz_id

                            if rule_type == "comma":
                                if all(deezer_ids.get(t) is not None for t in tokens):
                                    for name in tokens:
                                        norm = normalize(name)
                                        if norm not in known:
                                            a = Artist(
                                                name=name,
                                                normalized_name=norm,
                                                created_at=datetime.now(timezone.utc),
                                            )
                                            session.add(a)
                                            session.flush()
                                            known.add(norm)
                                            if (
                                                _assign_deezer_id(
                                                    a,
                                                    deezer_ids.get(name),
                                                    used_deezer_ids,
                                                )
                                                is False
                                            ):
                                                dz_id_skipped += 1
                                            created += 1
                                else:
                                    session.add(
                                        ArtistFlag(
                                            raw_artist_string=raw,
                                            reason="comma_unresolved",
                                            tokens=tokens,
                                            deezer_ids=deezer_ids,
                                            status="pending",
                                            created_at=datetime.now(timezone.utc),
                                            updated_at=datetime.now(timezone.utc),
                                        )
                                    )
                                    flagged += 1

                            elif rule_type == "ampersand":
                                deezer_full = deezer_ids.get(raw)
                                full_found = deezer_full is not None
                                tokens_found = all(
                                    deezer_ids.get(t) is not None for t in tokens
                                )

                                if full_found and not tokens_found:
                                    norm = normalize(raw)
                                    if norm not in known:
                                        a = Artist(
                                            name=raw,
                                            normalized_name=norm,
                                            created_at=datetime.now(timezone.utc),
                                        )
                                        session.add(a)
                                        session.flush()
                                        known.add(norm)
                                        if (
                                            _assign_deezer_id(
                                                a, deezer_full, used_deezer_ids
                                            )
                                            is False
                                        ):
                                            dz_id_skipped += 1
                                        created += 1
                                elif tokens_found and not full_found:
                                    for name in tokens:
                                        norm = normalize(name)
                                        if norm not in known:
                                            a = Artist(
                                                name=name,
                                                normalized_name=norm,
                                                created_at=datetime.now(timezone.utc),
                                            )
                                            session.add(a)
                                            session.flush()
                                            known.add(norm)
                                            if (
                                                _assign_deezer_id(
                                                    a,
                                                    deezer_ids.get(name),
                                                    used_deezer_ids,
                                                )
                                                is False
                                            ):
                                                dz_id_skipped += 1
                                            created += 1
                                else:
                                    reason = (
                                        "ampersand_ambiguous"
                                        if (full_found and tokens_found)
                                        else "ampersand_unknown"
                                    )
                                    session.add(
                                        ArtistFlag(
                                            raw_artist_string=raw,
                                            reason=reason,
                                            tokens=tokens,
                                            deezer_ids=deezer_ids,
                                            status="pending",
                                            created_at=datetime.now(timezone.utc),
                                            updated_at=datetime.now(timezone.utc),
                                        )
                                    )
                                    flagged += 1

                            try:
                                session.commit()
                            except IntegrityError:
                                # The guard above is not atomic across processes:
                                # a concurrent run may have claimed a deezer_id
                                # between our in-memory check and this commit.
                                # Roll back this batch and let the next run
                                # reconcile — the task survives.
                                session.rollback()
                                logger.warning(
                                    "sync_artists: Phase B commit hit "
                                    "IntegrityError for '%s' — rolled back, "
                                    "will retry next run",
                                    raw,
                                )

            try:
                asyncio.run(_deezer_resolve())
            except Exception:
                logger.exception("Deezer artist disambiguation failed")
                raise

        # Phase C: link catalog entries to artists via catalog_artists
        from models import CatalogArtist

        linked = 0
        with Session(engine) as session:
            # Reload known artists + aliases
            known_artists = {
                r[0]: r[1]
                for r in session.execute(
                    select(Artist.normalized_name, Artist.id)
                ).all()
            }
            alias_map = {
                r[0]: r[1]
                for r in session.execute(
                    select(ArtistAlias.normalized_alias, ArtistAlias.artist_id)
                ).all()
            }
            # Merge: alias -> artist_id (artists take priority)
            lookup = {**alias_map, **{n: aid for n, aid in known_artists.items()}}

            # Find catalog entries without any catalog_artists link
            from sqlalchemy import exists as sa_exists

            unlinked = session.execute(
                select(CatalogEntry.id, CatalogEntry.artist)
                .where(CatalogEntry.artist.isnot(None))
                .where(
                    ~sa_exists(
                        select(CatalogArtist.catalog_id).where(
                            CatalogArtist.catalog_id == CatalogEntry.id
                        )
                    )
                )
            ).all()

            seen = set()
            batch = 0
            for cat_id, raw in unlinked:
                if not raw or not raw.strip():
                    continue
                raw = raw.strip()
                parts = split_artist_parts(raw)

                for name, role, position in parts:
                    artist_id = lookup.get(normalize(name))
                    if artist_id and (cat_id, artist_id) not in seen:
                        session.add(
                            CatalogArtist(
                                catalog_id=cat_id,
                                artist_id=artist_id,
                                role=role,
                                position=position,
                            )
                        )
                        seen.add((cat_id, artist_id))
                        linked += 1
                        batch += 1
                        if batch % 100 == 0:
                            session.commit()

            session.commit()
        logger.info("Phase C: linked %d catalog-artist pairs", linked)

    except Exception as exc:
        _clog_exc = exc
        raise
    finally:
        result = {
            "created": created,
            "flagged": flagged,
            "skipped": skipped,
            "linked": linked,
            "dz_id_skipped": dz_id_skipped,
        }
        _clog.set_stats(result)
        if _clog_exc:
            _clog.__exit__(type(_clog_exc), _clog_exc, _clog_exc.__traceback__)
        else:
            _clog.__exit__(None, None, None)
        _log_session.close()

    return result


@celery_app.task(
    name="workers.tasks.fetch_artist_artworks",
    bind=True,
    soft_time_limit=3000,
    time_limit=3300,
)
def fetch_artist_artworks(self, budget=None):
    """Download Deezer artist images for linked artists missing artwork.

    Artwork-only since the backlog loop-safe chantier: the Deezer *linking* pass
    moved to link_artists_deezer. Loop-safe by construction (the 2026-07-13
    incident) — a per-run budget (ARTIST_ARTWORK_NIGHTLY_BUDGET, default 10000),
    batch commits, a Redis single-instance lock, and NO autoretry_for=(Exception,)
    (the decorator that turned the old soft timeout into an infinite re-download
    loop). Runs nightly at 05:20 (Paris); ``budget`` overrides the default for an
    ad-hoc bigger drain. The limits (soft 3000 / time 3300) stay well above the
    budget runtime (10000 ÷ 10 req/s ≈ 1000s), so the timeout never fires — the
    budget is the primary guard.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:fetch_artist_artworks"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=FETCH_ARTIST_ARTWORKS_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "fetch_artist_artworks already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_fetch_artist_artworks(self, budget)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_fetch_artist_artworks(task, budget=None):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist
    from services.image_service import BUCKET_ARTIST, ImageService
    from workers.db import get_engine

    engine = get_engine()
    ImageService.ensure_bucket(BUCKET_ARTIST)
    budget = _artwork_budget() if budget is None else int(budget)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="fetch_artworks",
            source="deezer",
            celery_task_id=task.request.id,
        ) as clog:

            async def _async_fetch():
                from workers.async_http import DeezerHTTPError, HttpPool
                from workers.rate_limiter import RateLimiter

                stats = {
                    "fetched": 0,
                    "skipped": 0,
                    "errors": 0,
                    "dropped_by_budget": 0,
                }

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        # has_artwork is nullable with no server_default, so use
                        # IS NOT TRUE (not == False): three-valued logic keeps the
                        # NULL rows in, which == False would silently drop.
                        base = (
                            Artist.deezer_id.isnot(None),
                            Artist.deezer_id != "NOT_FOUND",
                            Artist.has_artwork.isnot(True),
                        )
                        total_missing = session.execute(
                            select(func.count(Artist.id)).where(*base)
                        ).scalar_one()
                        artists = (
                            session.execute(
                                select(Artist)
                                .where(*base)
                                .order_by(Artist.id.asc())
                                .limit(budget)
                            )
                            .scalars()
                            .all()
                        )
                        stats["dropped_by_budget"] = max(
                            0, total_missing - len(artists)
                        )
                        if not artists:
                            return stats

                        async def _fetch_one(artist):
                            try:
                                data = await pool.deezer_get(
                                    f"/artist/{artist.deezer_id}"
                                )
                            except DeezerHTTPError as e:
                                logger.warning(
                                    "Deezer artist fetch failed for %s: %s",
                                    artist.deezer_id,
                                    e,
                                )
                                stats["errors"] += 1
                                return
                            pic_url = (
                                data.get("picture_xl")
                                or data.get("picture_big")
                                or data.get("picture")
                            )
                            if not pic_url:
                                stats["skipped"] += 1
                                return
                            img_data = await pool.download_image(pic_url)
                            if img_data and ImageService.upload_bytes(
                                img_data, BUCKET_ARTIST, f"{artist.id}.jpg"
                            ):
                                artist.has_artwork = True
                                stats["fetched"] += 1
                            else:
                                stats["skipped"] += 1

                        for i in range(0, len(artists), ARTIST_BACKLOG_BATCH):
                            batch = artists[i : i + ARTIST_BACKLOG_BATCH]
                            await asyncio.gather(*[_fetch_one(a) for a in batch])
                            session.commit()
                            logger.info(
                                "fetch_artist_artworks progress: %d/%d (fetched=%d)",
                                min(i + ARTIST_BACKLOG_BATCH, len(artists)),
                                len(artists),
                                stats["fetched"],
                            )

                        return stats

            try:
                result = asyncio.run(_async_fetch())
            except Exception:
                logger.exception("fetch_artist_artworks failed")
                raise

            clog.set_stats(result)

    return result


@celery_app.task(
    name="workers.tasks.link_set_artists",
    bind=True,
)
def link_set_artists(self):
    """
    Parse set titles to extract artist names and link them to the artists table.
    Matches against known artists (by name and aliases). Idempotent.

    Single-instance: a Redis lock (SET NX EX, conditional release) makes
    overlapping runs a no-op — the same pattern as link_artists_deezer /
    check_followed_artists. NO autoretry_for=(Exception,): SoftTimeLimitExceeded
    IS an Exception, so that decorator would turn a soft timeout into an
    infinite retry loop.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:link_set_artists"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(lock_key, self.request.id, nx=True, ex=LINK_SET_ARTISTS_LOCK_TTL):
        holder = r.get(lock_key)
        logger.warning("link_set_artists already running (task %s), skipping", holder)
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_link_set_artists(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_link_set_artists(task):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, DJSet, SetArtist
    from utils import normalize
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session, task_type="link_set_artists", celery_task_id=task.request.id
        ) as clog:
            # Build lookup: normalized name/alias → artist_id
            with Session(engine) as session:
                norm_to_id = {}
                for a in session.execute(select(Artist)).scalars().all():
                    norm_to_id[normalize(a.name)] = a.id
                for al in session.execute(select(ArtistAlias)).scalars().all():
                    if al.normalized_alias not in norm_to_id:
                        norm_to_id[al.normalized_alias] = al.artist_id

                # Sort by name length DESC so "Fred again.." matches before "Fred"
                sorted_names = sorted(norm_to_id.keys(), key=len, reverse=True)

                sets = session.execute(select(DJSet)).scalars().all()
                linked = 0
                skipped = 0

                for dj_set in sets:
                    title = dj_set.title or ""
                    title_lower = title.lower()

                    # Detect B2B
                    is_b2b = (
                        "b2b" in title_lower
                        or "b2b" in title_lower.replace("_", " ")
                    )

                    # Find all artist names present in the title
                    matched_ids = set()
                    title_norm = normalize(title)
                    # Also normalize underscores (e.g. Busy_P_b2b_Erol_Alkan)
                    title_norm_clean = title_norm.replace("_", " ")

                    for norm_name in sorted_names:
                        if len(norm_name) < 3:
                            continue  # skip very short names to avoid false positives
                        if norm_name in title_norm or norm_name in title_norm_clean:
                            aid = norm_to_id[norm_name]
                            if aid not in matched_ids:
                                matched_ids.add(aid)

                    # Insert set_artists (skip existing)
                    existing = {
                        r[0]
                        for r in session.execute(
                            select(SetArtist.artist_id).where(
                                SetArtist.set_id == dj_set.id
                            )
                        ).all()
                    }

                    for aid in matched_ids:
                        if aid in existing:
                            skipped += 1
                            continue
                        role = "b2b" if is_b2b else "dj"
                        session.add(
                            SetArtist(
                                set_id=dj_set.id,
                                artist_id=aid,
                                role=role,
                                position=0,
                            )
                        )
                        linked += 1

                    session.commit()

            result = {"linked": linked, "skipped": skipped}
            clog.set_stats(result)

    return result


@celery_app.task(
    name="workers.tasks.backfill_multi_artists",
    bind=True,
    soft_time_limit=7200,
    time_limit=9000,
)
def backfill_multi_artists(self):
    """Re-fetch Deezer track data for catalog entries with only 1 artist linked.

    Uses the /track/{deezer_id} endpoint which returns a ``contributors`` array,
    then calls link_catalog_artist_from_hit to add missing artist links.

    Single-instance: a Redis lock (SET NX EX, conditional release) makes
    overlapping runs a no-op — the same pattern as link_artists_deezer /
    check_followed_artists. NO autoretry_for=(Exception,): SoftTimeLimitExceeded
    IS an Exception, so that decorator would turn a soft timeout into an
    infinite retry loop.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:backfill_multi_artists"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=BACKFILL_MULTI_ARTISTS_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "backfill_multi_artists already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_backfill_multi_artists(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_backfill_multi_artists(task):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogArtist, CatalogEntry
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    _log_session = Session(engine)
    _clog = CrawlLogger(
        _log_session,
        task_type="backfill_multi_artists",
        celery_task_id=task.request.id,
    )
    _clog.__enter__()

    async def _async_backfill():
        from workers.async_http import HttpPool
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        enriched = 0
        errors = 0

        async with HttpPool(limiter) as pool:
            with Session(engine) as session:
                # Entries with a deezer_id and exactly 1 catalog_artist link
                link_count = (
                    select(
                        CatalogArtist.catalog_id,
                        func.count().label("cnt"),
                    )
                    .group_by(CatalogArtist.catalog_id)
                    .subquery()
                )
                entries = (
                    session.execute(
                        select(CatalogEntry)
                        .join(
                            link_count,
                            CatalogEntry.id == link_count.c.catalog_id,
                        )
                        .where(
                            CatalogEntry.deezer_id.isnot(None),
                            CatalogEntry.deezer_id != "",
                            link_count.c.cnt == 1,
                        )
                    )
                    .scalars()
                    .all()
                )

                logger.info(
                    "backfill_multi_artists: %d entries with 1 artist link",
                    len(entries),
                )

                async def _process_one(entry):
                    # Fetch + link ONLY — never commit here (A3-12). Committing a
                    # shared session from inside asyncio.gather flushes the other
                    # coroutines' partial work at an arbitrary point (project
                    # pitfall); the orchestrator commits BETWEEN chunks instead.
                    nonlocal enriched, errors
                    try:
                        hit = await pool.deezer_get(f"/track/{entry.deezer_id}")
                        if not hit.get("id"):
                            return
                        contributors = hit.get("contributors") or []
                        if len(contributors) <= 1:
                            return
                        from workers.deezer_enrich import link_catalog_artist_from_hit

                        link_catalog_artist_from_hit(session, entry.id, hit)
                        enriched += 1
                    except Exception as e:
                        errors += 1
                        logger.warning(
                            "backfill_multi_artists failed for catalog %s: %s",
                            entry.id,
                            e,
                        )

                # Process in bounded chunks and commit AFTER each chunk, in the
                # orchestrating coroutine — never inside the gather. A kill after
                # any chunk keeps the committed chunks (pattern:
                # fetch_artist_artworks).
                for i in range(0, len(entries), ARTIST_BACKLOG_BATCH):
                    chunk = entries[i : i + ARTIST_BACKLOG_BATCH]
                    await asyncio.gather(*[_process_one(e) for e in chunk])
                    session.commit()
                    logger.info(
                        "backfill_multi_artists progress: %d/%d (enriched=%d)",
                        min(i + ARTIST_BACKLOG_BATCH, len(entries)),
                        len(entries),
                        enriched,
                    )

        return {"enriched": enriched, "errors": errors, "total": len(entries)}

    try:
        result = asyncio.run(_async_backfill())
    except Exception:
        logger.exception("backfill_multi_artists failed")
        _clog.set_stats({"enriched": 0, "errors": 0})
        import sys as _sys

        _clog.__exit__(*_sys.exc_info())
        _log_session.close()
        raise

    _clog.set_stats(result)
    _clog.__exit__(None, None, None)
    _log_session.close()

    return result


# ── C6.c: daily activity check for followed artists ──────────────────────────


async def _fetch_artist_releases(pool, deezer_id):
    """Fetch one page of an artist's Deezer albums (id, title, link, release_date,
    record_type). A single page (limit 100, newest first) is enough — we only
    keep recent releases. Raises DeezerHTTPError on an API failure so the caller
    can count it and move on (an outage must not abort the whole run).
    """
    data = await pool.deezer_get(
        f"/artist/{deezer_id}/albums", params={"limit": 100}
    )
    return data.get("data", []) or []


def _activity_exists(session, artist_id, activity_type, source, external_id):
    """True if an artist_activity row already matches the unique key
    (artist_id, activity_type, source, external_id). The lock guarantees a
    single instance, so a plain existence check is enough — no dialect-specific
    ON CONFLICT needed (tests run on SQLite)."""
    from models import ArtistActivity
    from sqlalchemy import select

    return (
        session.execute(
            select(ArtistActivity.id).where(
                ArtistActivity.artist_id == artist_id,
                ArtistActivity.activity_type == activity_type,
                ArtistActivity.source == source,
                ArtistActivity.external_id == external_id,
            )
        ).first()
        is not None
    )


def _release_in_horizon(release_date, threshold):
    """True if a Deezer release_date string ('YYYY-MM-DD') is on/after threshold.
    Missing or malformed dates are treated as out of horizon (skipped)."""
    if not release_date:
        return False
    try:
        rel = date.fromisoformat(str(release_date)[:10])
    except ValueError:
        return False
    return rel >= threshold


def _parse_release_date(value):
    """Parse a Deezer 'YYYY-MM-DD' release_date into a date, or None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


async def _fetch_album_tracks(pool, album_id):
    """Fetch a Deezer album's tracklist (track summaries: id, title, link).
    Raises DeezerHTTPError on an API failure so the caller can count it and move
    on (an outage on one album must not abort the whole run)."""
    data = await pool.deezer_get(f"/album/{album_id}")
    if not isinstance(data, dict) or data.get("error"):
        return []
    return (data.get("tracks") or {}).get("data") or []


def _crawl_track(session, hit):
    """Create/enrich a catalog entry from a Deezer /track/{id} hit and link its
    artists. Returns (entry, created).

    Reuses the shared sync enrichment helpers (deezer_id, isrc, duration,
    has_preview, cover upload + multi-artist linking) so a crawled release track
    is indistinguishable from any other catalog track. New entries default to
    scope='shared' (model default) — visible to everyone, as with
    radar/enrichment tracks. Raises IntegrityError (norm_key race or the
    partial-unique artist deezer_id guard) so the caller can roll back and fall
    back to a link-only activity card.
    """
    from models import CatalogEntry
    from sqlalchemy import select as sa_select
    from utils import make_normalized_key
    from workers.deezer_enrich import enrich_entry, link_catalog_artist_from_hit

    title = (hit.get("title") or "").strip()
    if not title:
        return None, False
    artist_obj = hit.get("artist") if isinstance(hit.get("artist"), dict) else {}
    artist_name = artist_obj.get("name")
    isrc = hit.get("isrc") or None
    norm_key = make_normalized_key(title, artist_name)

    entry = None
    if isrc:
        entry = session.execute(
            sa_select(CatalogEntry).where(CatalogEntry.isrc == isrc)
        ).scalar_one_or_none()
    if entry is None:
        entry = session.execute(
            sa_select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
        ).scalar_one_or_none()

    created = False
    if entry is None:
        entry = CatalogEntry(
            title=title,
            artist=artist_name,
            normalized_key=norm_key,
            isrc=isrc,
            release_date=_parse_release_date(hit.get("release_date")),
            created_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        session.flush()
        created = True

    # X1/L2 deferral: this crawler references entry.id right after (artist link +
    # the caller attaches an artist_activity to entry.id) and its caller wraps the
    # call in a broad `except Exception: session.rollback()` that would UNDO a
    # merge. Folding a duplicate here would leave entry pointing at a deleted row
    # and roll the merge back — so merge-on-collision is disabled until the flow
    # is reworked to adopt the survivor (deferred, tracked X1).
    enrich_entry(entry, hit, session=session, merge_on_collision=False)
    if entry.release_date is None:
        entry.release_date = _parse_release_date(hit.get("release_date"))
    link_catalog_artist_from_hit(session, entry.id, hit)
    return entry, created


async def _check_releases(engine, followed_ids, now):
    """Releases volet: for each followed artist with a valid Deezer id, fetch its
    recent albums, expand every in-horizon album into its tracklist, and CRAWL
    each new track into the catalog (cover, preview, artists) — recording one
    artist_activity per track, linked to its catalog entry. A Deezer HTTP error
    on one artist / album / track is logged and counted, never fatal; a track
    that fails to crawl still gets a link-only activity card (external Deezer
    URL, catalog_id NULL) so the release is never lost."""
    from models import Artist, ArtistActivity
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session
    from workers.async_http import DeezerHTTPError, HttpPool
    from workers.rate_limiter import RateLimiter

    stats = {
        "artists_checked": 0,
        "artists_skipped_no_deezer": 0,
        "releases_found": 0,
        "catalog_created": 0,
        "crawl_errors": 0,
        "errors": 0,
    }
    threshold = (now - timedelta(days=ARTIST_ACTIVITY_RELEASE_HORIZON_DAYS)).date()

    limiter = RateLimiter()
    async with HttpPool(limiter) as pool:
        with Session(engine) as session:
            artists = (
                session.execute(
                    select(Artist).where(Artist.id.in_(followed_ids))
                )
                .scalars()
                .all()
            )

            for artist in artists:
                dz_id = artist.deezer_id
                if not dz_id or dz_id == "NOT_FOUND":
                    stats["artists_skipped_no_deezer"] += 1
                    continue
                stats["artists_checked"] += 1

                try:
                    albums = await _fetch_artist_releases(pool, dz_id)
                except DeezerHTTPError as e:
                    stats["errors"] += 1
                    logger.warning(
                        "check_followed_artists: Deezer albums fetch failed for "
                        "artist %s (deezer_id=%s): %s",
                        artist.id,
                        dz_id,
                        e,
                    )
                    continue

                for album in albums:
                    album_id = album.get("id")
                    if album_id is None:
                        continue
                    if not _release_in_horizon(album.get("release_date"), threshold):
                        continue

                    try:
                        tracks = await _fetch_album_tracks(pool, album_id)
                    except DeezerHTTPError as e:
                        stats["errors"] += 1
                        logger.warning(
                            "check_followed_artists: Deezer album fetch failed for "
                            "album %s (artist %s): %s",
                            album_id,
                            artist.id,
                            e,
                        )
                        continue

                    if not tracks:
                        continue

                    if len(tracks) > ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE:
                        logger.warning(
                            "check_followed_artists: album %s has %d tracks > cap "
                            "%d — only the first %d are crawled",
                            album_id,
                            len(tracks),
                            ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE,
                            ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE,
                        )
                        tracks = tracks[:ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE]

                    # Supersede any legacy album-level release card (external_id =
                    # album id, from the pre-crawl behaviour) now that we record
                    # per-track cards. Scoped + self-healing: only the album being
                    # reprocessed is touched; committed before the track loop so a
                    # later per-track rollback can't resurrect it.
                    superseded = session.execute(
                        sa_delete(ArtistActivity).where(
                            ArtistActivity.artist_id == artist.id,
                            ArtistActivity.activity_type == "release",
                            ArtistActivity.source == "deezer",
                            ArtistActivity.external_id == str(album_id),
                        )
                    )
                    if superseded.rowcount:
                        session.commit()

                    record_type = album.get("record_type")
                    for track in tracks:
                        track_id = track.get("id")
                        if track_id is None:
                            continue
                        ext_id = str(track_id)
                        if _activity_exists(
                            session, artist.id, "release", "deezer", ext_id
                        ):
                            continue

                        # Fetch the full track detail, then crawl it into the
                        # catalog. Async HTTP first, sync DB work second.
                        entry = None
                        created = False
                        hit = None
                        try:
                            hit = await pool.deezer_get(f"/track/{track_id}")
                        except DeezerHTTPError as e:
                            stats["errors"] += 1
                            logger.warning(
                                "check_followed_artists: Deezer track fetch failed "
                                "for track %s (album %s): %s",
                                track_id,
                                album_id,
                                e,
                            )

                        if isinstance(hit, dict) and not hit.get("error"):
                            try:
                                entry, created = _crawl_track(session, hit)
                                session.flush()
                            except IntegrityError:
                                session.rollback()
                                entry, created = None, False
                                stats["crawl_errors"] += 1
                                logger.warning(
                                    "check_followed_artists: crawl IntegrityError "
                                    "for track %s — recording link-only card",
                                    track_id,
                                )
                            except Exception:
                                session.rollback()
                                entry, created = None, False
                                stats["crawl_errors"] += 1
                                logger.warning(
                                    "check_followed_artists: crawl failed for track "
                                    "%s — recording link-only card",
                                    track_id,
                                    exc_info=True,
                                )

                        # INVARIANT: never store an external image URL — artwork
                        # lives in MinIO (has_artwork on the catalog entry).
                        session.add(
                            ArtistActivity(
                                artist_id=artist.id,
                                activity_type="release",
                                source="deezer",
                                external_id=ext_id,
                                title=(
                                    hit.get("title")
                                    if isinstance(hit, dict)
                                    else None
                                )
                                or track.get("title"),
                                external_url=(
                                    hit.get("link")
                                    if isinstance(hit, dict)
                                    else None
                                )
                                or track.get("link"),
                                catalog_id=entry.id if entry else None,
                                payload={
                                    "release_date": album.get("release_date"),
                                    "record_type": record_type,
                                    "album_id": str(album_id),
                                    "album_title": album.get("title"),
                                },
                            )
                        )
                        # Commit per track so the catalog entry, its artist links
                        # and the activity land atomically; a mid-run failure keeps
                        # all prior progress.
                        try:
                            session.commit()
                            stats["releases_found"] += 1
                            if created:
                                stats["catalog_created"] += 1
                        except IntegrityError:
                            # Rare activity-unique race under the single-instance
                            # lock — discard this track and move on.
                            session.rollback()
                            stats["crawl_errors"] += 1

    return stats


def _check_new_sets(engine, followed_ids, now):
    """Sets volet (DB only, no external call): record an activity for every
    recently-imported set that features a followed artist. The 48h window is
    wider than the daily cadence; the unique constraint dedups the overlap."""
    from datetime import timedelta

    from models import DJSet, SetArtist
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from trackid.reliability import set_reliable

    window_start = now - timedelta(hours=ARTIST_ACTIVITY_SET_WINDOW_HOURS)
    sets_found = 0

    with Session(engine) as session:
        rows = session.execute(
            select(SetArtist.artist_id, DJSet)
            .join(DJSet, DJSet.id == SetArtist.set_id)
            .where(
                SetArtist.artist_id.in_(followed_ids),
                DJSet.created_at.isnot(None),
                DJSet.created_at >= window_start,
                # C8: don't surface an unreliable TrackID set in the follow feed.
                set_reliable(),
            )
        ).all()

        for artist_id, dj_set in rows:
            if _activity_exists(
                session, artist_id, "set", "trackid", str(dj_set.id)
            ):
                continue
            from models import ArtistActivity

            session.add(
                ArtistActivity(
                    artist_id=artist_id,
                    activity_type="set",
                    source="trackid",
                    external_id=str(dj_set.id),
                    title=dj_set.title,
                    external_url=dj_set.source_url,
                    set_id=dj_set.id,
                )
            )
            sets_found += 1

        session.commit()

    return sets_found


@celery_app.task(
    name="workers.tasks.check_followed_artists",
    bind=True,
    soft_time_limit=3600,
    time_limit=3900,
)
def check_followed_artists(self):
    """
    Daily: detect new activity for every artist followed by ≥1 user.
    Two volets — new Deezer releases and newly imported sets that feature the
    artist. Single-instance: a Redis lock (SET NX EX, conditional release) keeps
    overlapping runs from doubling external traffic, same pattern as
    resolve_set_tracks. NO autoretry_for=(Exception,): SoftTimeLimitExceeded IS
    an Exception, so that decorator would turn a soft timeout into an infinite
    retry loop.
    """
    import redis as redis_lib

    sys.path.insert(0, "/app")
    from workers.celery_app import REDIS_URL

    lock_key = "lock:check_followed_artists"
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    if not r.set(
        lock_key, self.request.id, nx=True, ex=CHECK_FOLLOWED_ARTISTS_LOCK_TTL
    ):
        holder = r.get(lock_key)
        logger.warning(
            "check_followed_artists already running (task %s), skipping", holder
        )
        return {"skipped": "already_running", "holder": holder}

    try:
        return _run_check_followed_artists(self)
    finally:
        # Release only if we still own it (TTL may have expired mid-run)
        if r.get(lock_key) == self.request.id:
            r.delete(lock_key)


def _run_check_followed_artists(task):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import FollowedArtist
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()
    now = datetime.now(timezone.utc)

    with Session(engine) as log_session:
        with CrawlLogger(
            log_session,
            task_type="check_followed_artists",
            celery_task_id=task.request.id,
        ) as clog:
            with Session(engine) as session:
                followed_ids = [
                    r[0]
                    for r in session.execute(
                        select(FollowedArtist.artist_id).distinct()
                    ).all()
                ]

            stats = {
                "artists_checked": 0,
                "artists_skipped_no_deezer": 0,
                "releases_found": 0,
                "catalog_created": 0,
                "crawl_errors": 0,
                "sets_found": 0,
                "errors": 0,
            }

            if not followed_ids:
                clog.set_stats(stats)
                return stats

            release_stats = asyncio.run(
                _check_releases(engine, followed_ids, now)
            )
            stats["artists_checked"] = release_stats["artists_checked"]
            stats["artists_skipped_no_deezer"] = release_stats[
                "artists_skipped_no_deezer"
            ]
            stats["releases_found"] = release_stats["releases_found"]
            stats["catalog_created"] = release_stats["catalog_created"]
            stats["crawl_errors"] = release_stats["crawl_errors"]
            stats["errors"] = release_stats["errors"]

            stats["sets_found"] = _check_new_sets(engine, followed_ids, now)

            clog.set_stats(stats)

    return stats
