#!/usr/bin/env python
"""OPS: apply (or revert) a reversible masking rule on undesirable catalog rows.

WHY — the 2026-11 audit (``docs/audits/2026-11/donnees-indesirables.md`` §7-§9)
measured that AI "farms", distributor ISRC blocks, functional music and Deezer
homonym catch-alls flood the catalog through the uncorroborated Deezer entry points
(release watch + discography backfill). The chosen remedy is NOT a deletion but a
reversible flag: ``catalog.hidden_reason`` / ``artists.hidden_reason`` (NULL =
visible, else the id of the rule that hid the row) + ``hidden_at``. The read paths
already exclude flagged rows (``catalog_visible`` & co.). This script is the only
writer of those flags: it APPLIES one rule, or REVERTS it, rule by rule.

RULES (``--rule``, mandatory):

  * ``farm_fort`` — input = ``filtre-fort-966.tsv`` (no header; columns: id, name,
    deezer_id, titles, corroborated, watch, backfill, cohort tier, fans/album,
    majority Deezer genre, genre share), on stdin or ``--file``.
      1. Artists whose majority Deezer genre is classical (98) or jazz (129) are
         SKIPPED (``GENRE_GUARD_IDS`` — "garde-fou genre", §8.1). An id absent from
         the DB is counted and skipped, never an error.
      2. For each remaining artist, computed LIVE: its titles (``catalog_artists``),
         its corroborated titles, and its ANCHORED registrants = the set of
         ``upper(left(isrc, 5))`` of its corroborated titles that carry an ISRC
         (§7.2 — the real artist hiding under a polluted Deezer id).
      3. Each (title, TSV artist) pair is decided TITLE BY TITLE (v2, 2026-11 — the
         v1 rule would have hidden ~25 % of REAL music in the prod dry-run, mostly
         through "homonym buckets": one Deezer id aggregating dozens of real
         same-name artists — Mamba, Futura, Elle, Vega…). The FIRST true condition
         wins:
           a. corroborated                                  → protected "corroboré"
           b. registrant anchored (a title without ISRC is
              never anchored)                               → protected "ancré"
           c. co-credited with ANOTHER artist holding >=
              ``COARTIST_MIN_CORROBORATED`` (3) corroborated
              titles (§8.2)                                 → protected "co-artiste"
           d. classical marker in the title (``CLASSICAL_TITLE_RE``: "Op. 37",
              "BWV 1007", "Act II:") AND NOT junk           → protected "classique"
           e. the artist is a homonym bucket (top-3 registrant share <
              ``HOMONYM_TOP3_MAX``) AND NOT junk AND the title's registrant is
              NOT a Brazilian funk one (``BR_FUNK_REGISTRANT_PREFIXES``)
                                                            → protected "seau homonymes"
           f. ISRC year <= ``ISRC_OLD_MAX_YEAR`` (2019) AND NOT junk
                                                            → protected "ISRC ancien"
           g. otherwise                                     → masked.
         "junk" = the TITLE matches ``JUNK_TITLE_RE`` (slowed/sped up/lo-fi/sleep…)
         OR the row's flat ``catalog.artist`` matches ``FUNCTIONAL_ARTIST_RE``
         (relax/meditation/lounge/phonk… functional-music labels): those are the
         farm signatures, they never benefit from d/e/f. The artist's REGISTRANT
         PROFILE (for e) is built from ALL its titles not masked by ANOTHER rule
         (corroborated ones included; titles already hidden by THIS rule are kept so
         a re-run sees the same profile — idempotence), grouped by
         ``upper(isrc[:5])``, titles without ISRC in one "no ISRC" group. All the
         regex/year/profile tests run in Python on the loaded rows (PG + SQLite).
         An artist that is itself in the TSV and
         subject to the rule (i.e. NOT skipped by the genre guard — even if absent
         from the DB) NEVER counts as a protecting co-artist: some TSV artists
         (homonym buckets) carry many corroborated titles through false DJ links and
         would otherwise shield farm titles. A genre-guarded TSV artist (classical/
         jazz, a real musician kept visible) and any artist outside the TSV can still
         protect. A title credited to several input artists
         is decided once for all of them: ANY protection wins (invariant #4).
      4. The artist itself is masked only when it has titles and NONE remains
         visible after step 3. Artists OUTSIDE the TSV go through the shared
         empty-artist step below (counted apart: "co-crédités hors liste").
  * ``isrc_block`` — no input. Masks the titles whose ``upper(isrc)`` starts with
    one of ``workers.isrc_block.blocked_prefixes()`` (env
    ``CATALOG_ISRC_BLOCKED_PREFIXES``, default GXLE,GXLF,KRB92).
  * ``episode`` — no input. Radio-show / podcast episodes published on Deezer as
    albums (audit §2.1 / §7.3: e.g. 1,478 of Armin van Buuren's 2,277 titles are "A
    State Of Trance" episode tracks). An episode mixes spoken segments ("Coming Up",
    "Shout Outs") with "show versions" of the played tracks — not the original
    recordings — so PRODUCT DECISION: the WHOLE episode is masked, segments AND
    played tracks. A title is a candidate when EITHER:
      a. it is linked (``catalog_albums``) to an album of a SERIES = >=
         ``EPISODE_SERIES_MIN_ALBUMS`` (3) distinct albums sharing the same
         ``series_key`` (unaccented lowercase, numbers → "#", punctuation folded),
         WHATEVER their ``albums.artist_id`` (NULL on ~87 % of the albums and on
         ~90 % of the known episode albums in prod), AND that key carries
         broadcast vocabulary ("radio edit/mix/version" phrases removed first):
         a named show of the audit (``EPISODE_NAMED_SHOW_RE``: ASOT, FSOE,
         Toolroom Radio, Group Therapy, Defected Radio…), or a generic word
         (``EPISODE_GENERIC_VOCAB_RE``: radio/podcast/episode) plus at least
         ``EPISODE_KEY_MIN_EXTRA_WORDS`` (2) other words — "radio #" never forms a
         series. Recurrence AND vocabulary are both required: recurrence alone
         catches real label series (Speicher, Klockworks…), vocabulary alone
         catches one-off albums ("The Next Episode", "Episode 8 EP");
      b. its own title carries the ASOT marker ``(ASOT <n>)`` (episode titles
         without a linked album).
    "Other album" guard: a title found through (a) only that is ALSO linked to an
    album outside every retained series is protected — it is the original
    recording merged by ISRC with its show version (prod: 69 / 5,719 titles;
    invariant #4). A (b) marker hit is never shielded (it names the show version).
    The dry-run lists every retained series (key, most-credited artist, albums,
    titles) by volume — the anti-false-positive review vector — plus a sample of
    the titles protected by the "other album" guard.

EMPTY ARTISTS (every rule, after the title plan): an artist is masked with the
rule's reason when it is not already masked, has >= 1 title, NONE of its titles
stays visible once the plan is applied (masked by any rule) and at least one of
them is masked by THIS rule (planned or already). An artist with 0 title is never
masked. farm_fort keeps its own TSV-artist step (4.) and applies this one to the
co-credited artists outside the TSV. The artist UPDATE re-checks, after the titles
are written, that no title of the artist is still visible.

SYSTEMATIC PROTECTION (every rule): a title is NEVER masked when it is corroborated
— present in ``set_tracks``, ``user_tracks``, a ``user_opinions`` row with
``entity_type='track'`` or a ``collection_items`` row with ``item_type='track'``.
A row already masked by ANOTHER rule is never rewritten (one never changes another
rule's reason); the UPDATE itself is guarded by ``hidden_reason IS NULL`` and
re-checks corroboration, so a row corroborated between plan and write stays visible.

``--revert --rule <r>`` sets ``hidden_reason``/``hidden_at`` back to NULL on the
catalog AND artists rows whose ``hidden_reason = <r>`` — nothing else is touched.

DRY-RUN by default (no ``--apply``): read-only, NOTHING is committed; prints the
counters + a stable random sample (fixed seed) of masked titles "artist — title —
isrc" + a sample of titles protected by anchoring, and (farm_fort v2) one sample per
new protection: classical, homonym bucket, old ISRC — READ THEM before any
``--apply``. ``--apply`` writes in bulk UPDATEs (5000 titles / 1000 artists per
committed transaction — no ORM object per row). Idempotent: a second ``--apply``
changes nothing (already-masked rows are counted, not rewritten). No network I/O
(the TSV was computed off the VPS).

>>> ``--apply`` MUTATES ``catalog`` / ``artists``. DUMP PROD FIRST (docs/restore.md). <<<

OPS SEQUENCE: deploy (push → CI → image) → dry-run → read the samples → ENCRYPTED
DUMP → ``--apply`` → re-dry-run (expect 0 "à masquer"). Start with ``farm_fort``.

Usage (from the VPS — ships in the image under api/):
    cat filtre-fort-966.tsv | docker compose exec -T api python scripts/quarantine_undesirables.py --rule farm_fort            # dry-run
    cat filtre-fort-966.tsv | docker compose exec -T api python scripts/quarantine_undesirables.py --rule farm_fort --apply    # write
    docker compose exec api python scripts/quarantine_undesirables.py --rule isrc_block                                        # dry-run
    docker compose exec api python scripts/quarantine_undesirables.py --rule isrc_block --apply
    docker compose exec api python scripts/quarantine_undesirables.py --rule episode                                           # dry-run
    docker compose exec api python scripts/quarantine_undesirables.py --rule episode --apply
    docker compose exec api python scripts/quarantine_undesirables.py --rule farm_fort --revert                                # revert dry-run
    docker compose exec api python scripts/quarantine_undesirables.py --rule farm_fort --revert --apply                        # revert
"""

import argparse
import os
import random
import re
import sys
import unicodedata
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.orm import Session
from workers.isrc_block import blocked_prefixes

RULES = ("farm_fort", "isrc_block", "episode")

# Majority Deezer genre ids excluded from farm_fort (§8.1 garde-fou): classical
# performers and jazz musicians have few Deezer fans per album without being farms.
GENRE_GUARD_IDS = frozenset({"98", "129"})

# A title co-credited with another artist holding at least this many corroborated
# titles is protected (§8.2 — e.g. King Tubby). Artists of the TSV subject to the
# rule (not genre-guarded, present in the DB or not) are NEVER protecting
# co-artists — their corroborated titles may come from false DJ links.
COARTIST_MIN_CORROBORATED = 3

# Registrant = the first 5 chars of an ISRC (country + registrant code).
REGISTRANT_LEN = 5

# ---- farm_fort v2 per-title protections (prod SQL simulation, 2026-11) ----------
# Homonym bucket: share of an artist's titles held by its 3 biggest registrant
# groups. Measured in prod: farms sit between 85 and 100 % (one or two distributor
# registrants), homonym buckets between 13 and 52 % (dozens of real artists, each
# with its own label). A share strictly below this bound = bucket → protected.
HOMONYM_TOP3_MAX = 0.6
_HOMONYM_TOP_GROUPS = 3

# ISRC year (chars 5-6) at or before this year → protected: AI farms only appear
# after 2023, a title registered in 2019 or earlier predates them.
ISRC_OLD_MAX_YEAR = 2019
# Two-digit ISRC year >= this pivot is 19xx, else 20xx.
_ISRC_CENTURY_PIVOT = 50

# Junk title: slowed/sped-up edits, montagens, type beats, lo-fi/sleep/relaxation
# filler — the farm signatures measured in the audit. A junk title never benefits
# from the classical / homonym / old-ISRC protections.
JUNK_TITLE_RE = re.compile(
    r"(slowed|speed ?up|sped up|reverb|montagem|mtg |type beat|lo-?fi|sleep|relax"
    r"|meditat|asmr|rain |ocean|white noise|bgm|study|yoga|spa |calm|healing"
    r"|binaural|lullab|8d)",
    re.IGNORECASE,
)

# Functional artist name (on the flat ``catalog.artist`` of the row): functional
# music / genre-label pseudo-artists, same effect as a junk title.
FUNCTIONAL_ARTIST_RE = re.compile(
    r"(chill ?out|relax|meditat|sleep|spa |spa$|lounge|café|cafe|yoga|zen|nature"
    r"|rain|study|focus|piano relax|instrumental|background|music for|worship"
    r"|lullab|baby|asmr|white noise|ambient|calm|healing|dynamic music"
    r"|tribal house|house music|deep house|dance music|happy hardcore|phonk|фонк"
    r"|synthwave|sound lab|reimagined)",
    re.IGNORECASE,
)

# Classical marker in the title (opus / BWV / opera act). Deliberately NARROW: a
# broader try ("aria", "symphony"…) caught "putaria" or "Hot Symphony".
CLASSICAL_TITLE_RE = re.compile(r"\bop\. ?[0-9]|\bbwv ?[0-9]|\bact [ivx]+:", re.IGNORECASE)

# Recent Brazilian registrant codes hosting the funk "montagens" the product chose
# to hide: such a registrant only LOSES the homonym-bucket protection (e).
BR_FUNK_REGISTRANT_PREFIXES = ("BC", "BX", "BK")
_ISRC_YEAR_RE = re.compile(r"[0-9]{2}")

# ---- episode rule (audit §2.1 / §7.3, prod read-only measurement 2026-11-11) -----
# A radio show / podcast episode is published on Deezer as an album. A SERIES = at
# least this many distinct albums sharing one series key, WHATEVER their
# ``albums.artist_id`` (prod 2026-11: artist_id is NULL on 345,669 / 397,767 albums
# and on ~90 % of the known episode albums — 51 / 531 — so requiring it missed most
# episodes). Measured: series + vocabulary at >= 3 albums = ~40 series, ~7,600
# titles, no false positive once ONE-album series are excluded ("The Next Episode",
# "Episode 8 EP", "Live at Radio City Music Hall", HBO soundtracks were the ~25 %
# false positives of the vocabulary-only try).
EPISODE_SERIES_MIN_ALBUMS = 3

# Broadcast vocabulary the series key must contain. Recurrence ALONE caught real
# label series to protect (Speicher, Little Helpers, Whities, Klockworks, Compost
# Black Label — no vocabulary), vocabulary ALONE caught one-off albums: both
# conditions are mandatory. Matched on the series key (lowercase, unaccented,
# punctuation folded, numbers = "#"). Two kinds:
#   * NAMED shows measured in the audit (§2.1 table) — specific by themselves;
#   * GENERIC broadcast words (radio / podcast / episode) — only with
#     ``EPISODE_KEY_MIN_EXTRA_WORDS`` other words (see below).
EPISODE_NAMED_SHOW_RE = re.compile(
    r"\b(state of trance|asot|fsoe|future sound of egypt|toolroom radio"
    r"|group therapy|interplay radio|glitterbox radio|get physical radio"
    r"|uncharted worlds|defected radio|defected in the house|fyh|find your harmony)\b"
)
EPISODE_GENERIC_VOCAB_RE = re.compile(r"\b(radio|podcast|episode)\b")
# Since a series no longer needs a common album artist, a key made of a generic
# word alone ("radio #" ← "Radio 1/2/3", "episode #") would fuse unrelated albums:
# a generic-vocabulary key must carry at least this many OTHER alphabetic words
# ("club night radio show #" qualifies, "radio show #" does not). The named shows
# are exempt — the ASOT key "asot # a state of trance episode #" has a single word
# ("a") outside its vocabulary.
EPISODE_KEY_MIN_EXTRA_WORDS = 2
# "Radio Edit(s)" / "Radio Mix" / "Radio Version" are track versions, not shows:
# removed from the key before the vocabulary test (a "Remixes Vol. 1/2/3 (Radio
# Edits)" label series must not qualify). Anticipated, not a measured case.
EPISODE_VOCAB_EXCLUDE_RE = re.compile(r"\bradio (edit|mix|version|cut)s?\b")

# Track-title marker of an ASOT episode track ("Que Pasa (ASOT 977) [Tune Of The
# Week]", "A State Of Trance (ASOT 974) (Coming Up, Pt. 1)") — catches the episode
# titles without a linked album. Measured ~100 % precision (§7.3).
EPISODE_TITLE_MARKER_RE = re.compile(r"\(asot ?[0-9]+\)", re.IGNORECASE)
# Portable SQL pre-filter for the marker (the regex itself runs in Python).
_EPISODE_MARKER_LIKE = "%(asot%"

_SERIES_NUMBER_RE = re.compile(r"[0-9]+")
_SERIES_FOLD_RE = re.compile(r"[^a-z#]+")

TITLES_PER_TX = 5000
ARTISTS_PER_TX = 1000
# Artists per read batch while planning farm_fort, and ids per IN (...) chunk.
_ARTIST_READ_BATCH = 200
_IN_CHUNK = 5000

_SAMPLE_SEED = 20261111
DEFAULT_SAMPLE = 30

# Corroboration predicate on a catalog alias — portable SQL (PG + SQLite).
_CORROBORATED_SQL = """(
    EXISTS (SELECT 1 FROM set_tracks st WHERE st.catalog_id = {c}.id)
    OR EXISTS (SELECT 1 FROM user_tracks ut WHERE ut.catalog_id = {c}.id)
    OR EXISTS (SELECT 1 FROM user_opinions uo
               WHERE uo.entity_type = 'track'
                 AND uo.entity_key = CAST({c}.id AS VARCHAR(255)))
    OR EXISTS (SELECT 1 FROM collection_items ci
               WHERE ci.item_type = 'track' AND ci.item_id = {c}.id)
)"""


def corroborated_sql(alias="c"):
    return _CORROBORATED_SQL.format(c=alias)


_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _chunks(seq, size):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _registrant(isrc):
    if not isinstance(isrc, str):
        return None
    value = isrc.strip().upper()
    if len(value) < REGISTRANT_LEN:
        return None
    return value[:REGISTRANT_LEN]


def isrc_year(isrc):
    """4-digit year from ISRC chars 5-6 (``>= 50`` → 19xx, else 20xx), or None."""
    if not isinstance(isrc, str):
        return None
    yy = isrc.strip()[5:7]
    if not _ISRC_YEAR_RE.fullmatch(yy):
        return None
    n = int(yy)
    return (1900 if n >= _ISRC_CENTURY_PIVOT else 2000) + n


def is_junk(title, flat_artist):
    """Junk title OR functional flat artist name (farm signatures)."""
    return bool(
        (title and JUNK_TITLE_RE.search(title))
        or (flat_artist and FUNCTIONAL_ARTIST_RE.search(flat_artist))
    )


def has_classical_marker(title):
    return bool(title and CLASSICAL_TITLE_RE.search(title))


def is_br_funk_registrant(registrant):
    return bool(registrant) and registrant.startswith(BR_FUNK_REGISTRANT_PREFIXES)


def top3_share(isrcs):
    """Share of titles in the 3 biggest registrant groups (no ISRC = one group)."""
    groups = {}
    for isrc in isrcs:
        key = _registrant(isrc)  # None groups the titles without (usable) ISRC
        groups[key] = groups.get(key, 0) + 1
    total = sum(groups.values())
    if not total:
        return 1.0
    top = sorted(groups.values(), reverse=True)[:_HOMONYM_TOP_GROUPS]
    return sum(top) / total


def series_key(album_title):
    """Series key of an album title: unaccented lowercase, every number → ``#``,
    punctuation and whitespace folded to single spaces.

    "ASOT 974 - A State Of Trance Episode 974" → "asot # a state of trance episode #".
    """
    if not album_title:
        return ""
    folded = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", album_title)
        if not unicodedata.combining(ch)
    ).lower()
    # A literal "#" ("Show #12") is punctuation; only numbers become the token.
    folded = _SERIES_NUMBER_RE.sub(" # ", folded.replace("#", " "))
    return " ".join(_SERIES_FOLD_RE.sub(" ", folded).split())


def is_episode_series_key(key):
    """The series key carries broadcast vocabulary (track-version phrases removed):
    a named show, or a generic word + ``EPISODE_KEY_MIN_EXTRA_WORDS`` other words."""
    if not key:
        return False
    key = EPISODE_VOCAB_EXCLUDE_RE.sub(" ", key)
    if EPISODE_NAMED_SHOW_RE.search(key):
        return True
    if not EPISODE_GENERIC_VOCAB_RE.search(key):
        return False
    extra = [w for w in EPISODE_GENERIC_VOCAB_RE.sub(" ", key).split() if w.isalpha()]
    return len(extra) >= EPISODE_KEY_MIN_EXTRA_WORDS


def has_episode_marker(title):
    return bool(title and EPISODE_TITLE_MARKER_RE.search(title))


def _new_stats():
    return {
        "artists_read": 0,
        "artists_malformed": 0,
        "artists_genre_guard": 0,
        "artists_missing": 0,
        "titles_examined": 0,
        "titles_to_mask": 0,
        "titles_protected_corroborated": 0,
        "titles_protected_anchored": 0,
        "titles_protected_coartist": 0,
        "titles_protected_classical": 0,
        "titles_protected_homonym": 0,
        "titles_protected_isrc_old": 0,
        "titles_already_same_rule": 0,
        "titles_already_other_rule": 0,
        "artists_to_mask": 0,
        "artists_to_mask_tier1": 0,
        "artists_already_same_rule": 0,
        "artists_already_other_rule": 0,
        "artists_kept_visible": 0,
        "artists_without_titles": 0,
        # farm_fort only: artists OUTSIDE the TSV left empty by the rule (point B).
        "artists_to_mask_coartists": 0,
        "artists_to_mask_coartists_tier1": 0,
        # episode only
        "albums_examined": 0,
        "series_retained": 0,
        "titles_via_series": 0,
        "titles_via_marker": 0,
        "titles_protected_other_album": 0,
        "titles_masked": 0,
        "artists_masked": 0,
    }


# --------------------------------------------------------------------------- input


def read_tsv(stream):
    """Parse the farm_fort TSV → list of dicts ``{id, name, tier, genre}``.

    A line whose first column is not an int is counted as malformed (returned
    count). Duplicate ids keep the first occurrence.
    """
    rows, seen, malformed = [], set(), 0
    for line in stream:
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        cols = line.split("\t")
        try:
            artist_id = int(cols[0].strip())
        except (ValueError, IndexError):
            malformed += 1
            continue
        if artist_id in seen:
            continue
        seen.add(artist_id)
        rows.append(
            {
                "id": artist_id,
                "name": cols[1].strip() if len(cols) > 1 else "",
                "tier": cols[7].strip() if len(cols) > 7 else "",
                "genre": cols[9].strip() if len(cols) > 9 else "",
            }
        )
    return rows, malformed


# --------------------------------------------------------------------------- reads


def _load_artists(session, ids):
    out = {}
    stmt = text("SELECT id, name, hidden_reason FROM artists WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    for chunk in _chunks(ids, _IN_CHUNK):
        for row in session.execute(stmt, {"ids": chunk}):
            out[row.id] = {"name": row.name, "hidden_reason": row.hidden_reason}
    return out


def _load_titles(session, artist_ids):
    """Titles of the given artists with their corroboration flag."""
    stmt = text(
        f"""
        SELECT ca.artist_id AS artist_id, c.id AS id, c.title AS title,
               c.artist AS artist, c.isrc AS isrc, c.hidden_reason AS hidden_reason,
               CASE WHEN {corroborated_sql("c")} THEN 1 ELSE 0 END AS corro
        FROM catalog_artists ca JOIN catalog c ON c.id = ca.catalog_id
        WHERE ca.artist_id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    return list(session.execute(stmt, {"ids": list(artist_ids)}))


def _load_credits(session, catalog_ids):
    """``{catalog_id: {artist_id, ...}}`` — every credited artist of those titles."""
    out = {}
    stmt = text(
        "SELECT catalog_id, artist_id FROM catalog_artists WHERE catalog_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(catalog_ids, _IN_CHUNK):
        for row in session.execute(stmt, {"ids": chunk}):
            out.setdefault(row.catalog_id, set()).add(row.artist_id)
    return out


def _load_corroborated_counts(session, artist_ids):
    """``{artist_id: n corroborated titles}`` (absent = 0)."""
    out = {}
    stmt = text(
        f"""
        SELECT ca.artist_id AS artist_id, COUNT(DISTINCT ca.catalog_id) AS n
        FROM catalog_artists ca JOIN catalog c ON c.id = ca.catalog_id
        WHERE ca.artist_id IN :ids AND {corroborated_sql("c")}
        GROUP BY ca.artist_id
        """
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(artist_ids, _IN_CHUNK):
        for row in session.execute(stmt, {"ids": chunk}):
            out[row.artist_id] = row.n
    return out


def _load_tier1(session, artist_ids):
    """Subset of ``artist_ids`` whose effective cohort tier is 1."""
    out = set()
    stmt = text(
        "SELECT artist_id FROM artist_cohort WHERE tier = 1 AND artist_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(artist_ids, _IN_CHUNK):
        out.update(row.artist_id for row in session.execute(stmt, {"ids": chunk}))
    return out


def _rule_artist_candidates(session, rule, to_mask):
    """Artists credited on a title masked by ``rule`` — already, or by the plan."""
    out = {
        row.artist_id
        for row in session.execute(
            text(
                """
                SELECT DISTINCT ca.artist_id AS artist_id
                FROM catalog_artists ca JOIN catalog c ON c.id = ca.catalog_id
                WHERE c.hidden_reason = :rule
                """
            ),
            {"rule": rule},
        )
    }
    stmt = text(
        "SELECT DISTINCT artist_id FROM catalog_artists WHERE catalog_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(to_mask, _IN_CHUNK):
        out.update(row.artist_id for row in session.execute(stmt, {"ids": chunk}))
    return out


def plan_empty_artists(session, rule, to_mask, exclude_ids=()):
    """Artists the plan of ``rule`` leaves without any visible title (point B).

    An artist is to mask with ``rule`` when: it is not already masked, it has >= 1
    title, NONE of its titles stays visible once the plan is applied (masked by any
    rule, this one included) and at least one of them is masked by THIS rule (in the
    plan or already). Candidates are derived from the rule's titles, so an artist
    with 0 title is never even considered. ``exclude_ids`` = artists decided
    elsewhere (farm_fort's own TSV list). Returns ``(artist_ids, counters)``.
    """
    counters = {
        "to_mask": 0,
        "tier1": 0,
        "already_same_rule": 0,
        "already_other_rule": 0,
        "kept_visible": 0,
    }
    planned = set(to_mask)
    candidates = sorted(_rule_artist_candidates(session, rule, planned) - set(exclude_ids))
    titles_stmt = text(
        """
        SELECT ca.artist_id AS artist_id, c.id AS id, c.hidden_reason AS hidden_reason
        FROM catalog_artists ca JOIN catalog c ON c.id = ca.catalog_id
        WHERE ca.artist_id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    artist_ids = []
    for batch in _chunks(candidates, _ARTIST_READ_BATCH):
        db_artists = _load_artists(session, batch)
        per_artist = {}
        for row in session.execute(titles_stmt, {"ids": batch}):
            per_artist.setdefault(row.artist_id, []).append(row)
        for aid in batch:
            if aid not in db_artists:
                continue
            current = db_artists[aid]["hidden_reason"]
            if current == rule:
                counters["already_same_rule"] += 1
                continue
            if current is not None:
                counters["already_other_rule"] += 1
                continue
            rows = per_artist.get(aid, [])
            if not rows:
                continue  # 0 title: never masked
            visible = any(r.hidden_reason is None and r.id not in planned for r in rows)
            by_rule = any(r.hidden_reason == rule or r.id in planned for r in rows)
            if visible or not by_rule:
                counters["kept_visible"] += 1
            else:
                artist_ids.append(aid)
    counters["to_mask"] = len(artist_ids)
    counters["tier1"] = len(_load_tier1(session, artist_ids))
    return artist_ids, counters


def _apply_empty_artist_counters(stats, counters):
    stats["artists_to_mask"] = counters["to_mask"]
    stats["artists_to_mask_tier1"] = counters["tier1"]
    stats["artists_already_same_rule"] = counters["already_same_rule"]
    stats["artists_already_other_rule"] = counters["already_other_rule"]
    stats["artists_kept_visible"] = counters["kept_visible"]


# --------------------------------------------------------------------------- plan


def plan_farm_fort(session, tsv_rows, rule="farm_fort"):
    """Compute the farm_fort plan (read-only). Returns ``(plan, stats)``.

    ``plan`` = {"titles": {catalog_id: info}, "to_mask": [ids], "anchored": [infos],
    "classical"/"homonym"/"isrc_old": [infos] (v2 protections, for the samples),
    "artists_to_mask": [ids]}.
    """
    stats = _new_stats()
    stats["artists_read"] = len(tsv_rows)
    kept = []
    for row in tsv_rows:
        if row["genre"] in GENRE_GUARD_IDS:
            stats["artists_genre_guard"] += 1
        else:
            kept.append(row)
    # TSV artists subject to the rule: never a protecting co-artist.
    subject_ids = {r["id"] for r in kept}

    db_artists = _load_artists(session, [r["id"] for r in kept])
    present = []
    for row in kept:
        if row["id"] in db_artists:
            present.append(row)
        else:
            stats["artists_missing"] += 1

    titles = {}  # catalog_id -> info (intrinsic fields)
    artist_titles = {}  # artist_id -> [catalog_id]
    # catalog_id -> set of verdicts from each crediting input artist
    verdicts = {}
    coartist_cache = {}

    for batch in _chunks(present, _ARTIST_READ_BATCH):
        ids = [r["id"] for r in batch]
        rows = _load_titles(session, ids)
        per_artist = {}
        for r in rows:
            per_artist.setdefault(r.artist_id, []).append(r)
            if r.id not in titles:
                titles[r.id] = {
                    "id": r.id,
                    "title": r.title,
                    "artist": r.artist,
                    "isrc": r.isrc,
                    "hidden_reason": r.hidden_reason,
                    "corro": bool(r.corro),
                }
        credits = _load_credits(session, {r.id for r in rows})
        others = set()
        for cid, artist_set in credits.items():
            others |= artist_set
        others -= subject_ids
        missing = [a for a in others if a not in coartist_cache]
        counts = _load_corroborated_counts(session, missing)
        for a in missing:
            coartist_cache[a] = counts.get(a, 0)

        for artist_id in ids:
            trows = per_artist.get(artist_id, [])
            artist_titles[artist_id] = [r.id for r in trows]
            anchored = {
                reg
                for r in trows
                if r.corro and (reg := _registrant(r.isrc)) is not None
            }
            # Registrant profile: every title not masked by ANOTHER rule (titles
            # already hidden by this rule stay in → a re-run sees the same profile).
            bucket = (
                top3_share(
                    r.isrc
                    for r in trows
                    if r.hidden_reason is None or r.hidden_reason == rule
                )
                < HOMONYM_TOP3_MAX
            )
            for r in trows:
                if r.hidden_reason is not None or r.corro:
                    continue  # intrinsic status, decided below
                reg = _registrant(r.isrc)
                junk = is_junk(r.title, r.artist)
                year = isrc_year(r.isrc)
                if reg is not None and reg in anchored:
                    verdict = "anchored"
                elif any(
                    coartist_cache.get(a, 0) >= COARTIST_MIN_CORROBORATED
                    for a in credits.get(r.id, ())
                    if a != artist_id and a not in subject_ids
                ):
                    verdict = "coartist"
                elif not junk and has_classical_marker(r.title):
                    verdict = "classical"
                elif bucket and not junk and not is_br_funk_registrant(reg):
                    verdict = "homonym"
                elif not junk and year is not None and year <= ISRC_OLD_MAX_YEAR:
                    verdict = "isrc_old"
                else:
                    verdict = "mask"
                verdicts.setdefault(r.id, set()).add(verdict)

    to_mask, anchored_infos = [], []
    protected_infos = {v: [] for v in ("classical", "homonym", "isrc_old")}
    for cid in sorted(titles):
        info = titles[cid]
        stats["titles_examined"] += 1
        if info["hidden_reason"] == rule:
            stats["titles_already_same_rule"] += 1
        elif info["hidden_reason"] is not None:
            stats["titles_already_other_rule"] += 1
        elif info["corro"]:
            stats["titles_protected_corroborated"] += 1
        else:
            # ANY protection from any crediting input artist wins; counted under
            # the first one in the rule's order.
            v = verdicts.get(cid, {"mask"})
            if "anchored" in v:
                stats["titles_protected_anchored"] += 1
                anchored_infos.append(info)
            elif "coartist" in v:
                stats["titles_protected_coartist"] += 1
            elif "classical" in v:
                stats["titles_protected_classical"] += 1
                protected_infos["classical"].append(info)
            elif "homonym" in v:
                stats["titles_protected_homonym"] += 1
                protected_infos["homonym"].append(info)
            elif "isrc_old" in v:
                stats["titles_protected_isrc_old"] += 1
                protected_infos["isrc_old"].append(info)
            else:
                to_mask.append(cid)
    stats["titles_to_mask"] = len(to_mask)

    masked = set(to_mask)
    tier_by_id = {r["id"]: r["tier"] for r in present}
    artists_to_mask = []
    for row in present:
        aid = row["id"]
        current = db_artists[aid]["hidden_reason"]
        if current == rule:
            stats["artists_already_same_rule"] += 1
            continue
        if current is not None:
            stats["artists_already_other_rule"] += 1
            continue
        tids = artist_titles.get(aid, [])
        if not tids:
            stats["artists_without_titles"] += 1
            continue
        visible = [
            t for t in tids if titles[t]["hidden_reason"] is None and t not in masked
        ]
        if visible:
            stats["artists_kept_visible"] += 1
        else:
            artists_to_mask.append(aid)
            if tier_by_id.get(aid) == "1":
                stats["artists_to_mask_tier1"] += 1
    stats["artists_to_mask"] = len(artists_to_mask)

    # Point B: artists OUTSIDE the TSV (co-credited) that the rule leaves empty.
    # Counted apart so the TSV-artist counters above stay those of v2; every TSV id
    # (genre-guarded included — "skipped" means untouched) is excluded.
    extra, extra_counters = plan_empty_artists(
        session, rule, to_mask, exclude_ids={r["id"] for r in tsv_rows}
    )
    stats["artists_to_mask_coartists"] = extra_counters["to_mask"]
    stats["artists_to_mask_coartists_tier1"] = extra_counters["tier1"]
    artists_to_mask = artists_to_mask + extra

    plan = {
        "titles": titles,
        "to_mask": to_mask,
        "anchored": anchored_infos,
        "classical": protected_infos["classical"],
        "homonym": protected_infos["homonym"],
        "isrc_old": protected_infos["isrc_old"],
        "artists_to_mask": artists_to_mask,
    }
    return plan, stats


def plan_isrc_block(session, rule="isrc_block", prefixes=None):
    """Compute the isrc_block plan (read-only). Returns ``(plan, stats)``."""
    stats = _new_stats()
    if prefixes is None:
        prefixes = blocked_prefixes()
    prefixes = tuple(p.strip().upper() for p in prefixes if p and p.strip())
    titles, to_mask = {}, []
    if prefixes:
        clauses = " OR ".join(
            f"UPPER(c.isrc) LIKE :p{i}" for i in range(len(prefixes))
        )
        params = {f"p{i}": f"{p}%" for i, p in enumerate(prefixes)}
        stmt = text(
            f"""
            SELECT c.id AS id, c.title AS title, c.artist AS artist, c.isrc AS isrc,
                   c.hidden_reason AS hidden_reason,
                   CASE WHEN {corroborated_sql("c")} THEN 1 ELSE 0 END AS corro
            FROM catalog c
            WHERE c.isrc IS NOT NULL AND ({clauses})
            ORDER BY c.id
            """
        )
        for r in session.execute(stmt, params):
            info = {
                "id": r.id,
                "title": r.title,
                "artist": r.artist,
                "isrc": r.isrc,
                "hidden_reason": r.hidden_reason,
                "corro": bool(r.corro),
            }
            titles[r.id] = info
            stats["titles_examined"] += 1
            if r.hidden_reason == rule:
                stats["titles_already_same_rule"] += 1
            elif r.hidden_reason is not None:
                stats["titles_already_other_rule"] += 1
            elif info["corro"]:
                stats["titles_protected_corroborated"] += 1
            else:
                to_mask.append(r.id)
    stats["titles_to_mask"] = len(to_mask)
    artists_to_mask, counters = plan_empty_artists(session, rule, to_mask)
    _apply_empty_artist_counters(stats, counters)
    plan = {
        "titles": titles,
        "to_mask": to_mask,
        "anchored": [],
        "artists_to_mask": artists_to_mask,
        "prefixes": prefixes,
    }
    return plan, stats


def plan_episode(session, rule="episode"):
    """Compute the episode plan (read-only). Returns ``(plan, stats)``.

    Candidates = titles linked to an album of a retained SERIES (>=
    ``EPISODE_SERIES_MIN_ALBUMS`` distinct albums sharing a series key that passes
    ``is_episode_series_key``, whatever their ``albums.artist_id``) ∪ titles
    carrying the ASOT marker. A series candidate ALSO linked to an album outside
    every retained series is protected (the original recording merged by ISRC with
    its show version); a marker hit is not. Grouped reads only; keys and regexes are
    evaluated in Python (PG + SQLite). ``plan["series"]`` = retained series, by
    title volume, with their most-credited artist (human review vector).
    """
    stats = _new_stats()

    # 1. Series: every album, artist_id NULL included (NULL on ~87 % of prod).
    groups = {}  # key -> [album_id]
    for row in session.execute(text("SELECT id, title FROM albums")):
        stats["albums_examined"] += 1
        key = series_key(row.title)
        if is_episode_series_key(key):
            groups.setdefault(key, []).append(row.id)
    series = {
        key: album_ids
        for key, album_ids in groups.items()
        if len(set(album_ids)) >= EPISODE_SERIES_MIN_ALBUMS
    }
    album_to_series = {aid: key for key, album_ids in series.items() for aid in album_ids}

    series_titles = {gk: set() for gk in series}
    via_series = set()
    link_stmt = text(
        "SELECT catalog_id, album_id FROM catalog_albums WHERE album_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(sorted(album_to_series), _IN_CHUNK):
        for row in session.execute(link_stmt, {"ids": chunk}):
            series_titles[album_to_series[row.album_id]].add(row.catalog_id)
            via_series.add(row.catalog_id)

    # 1b. "Other album" guard: series candidates also linked to a non-episode album.
    on_other_album = set()
    by_catalog_stmt = text(
        "SELECT catalog_id, album_id FROM catalog_albums WHERE catalog_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(sorted(via_series), _IN_CHUNK):
        for row in session.execute(by_catalog_stmt, {"ids": chunk}):
            if row.album_id not in album_to_series:
                on_other_album.add(row.catalog_id)

    # 2. Title marker (SQL LIKE pre-filter, exact regex in Python).
    via_marker = set()
    for row in session.execute(
        text("SELECT id, title FROM catalog WHERE LOWER(title) LIKE :p"),
        {"p": _EPISODE_MARKER_LIKE},
    ):
        if has_episode_marker(row.title):
            via_marker.add(row.id)

    # 3. Verdict per candidate title.
    titles, to_mask = {}, []
    title_stmt = text(
        f"""
        SELECT c.id AS id, c.title AS title, c.artist AS artist, c.isrc AS isrc,
               c.hidden_reason AS hidden_reason,
               CASE WHEN {corroborated_sql("c")} THEN 1 ELSE 0 END AS corro
        FROM catalog c WHERE c.id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    for chunk in _chunks(sorted(via_series | via_marker), _IN_CHUNK):
        for r in session.execute(title_stmt, {"ids": chunk}):
            titles[r.id] = {
                "id": r.id,
                "title": r.title,
                "artist": r.artist,
                "isrc": r.isrc,
                "hidden_reason": r.hidden_reason,
                "corro": bool(r.corro),
            }
    other_album_infos = []
    for cid in sorted(titles):
        info = titles[cid]
        stats["titles_examined"] += 1
        if info["hidden_reason"] == rule:
            stats["titles_already_same_rule"] += 1
        elif info["hidden_reason"] is not None:
            stats["titles_already_other_rule"] += 1
        elif info["corro"]:
            stats["titles_protected_corroborated"] += 1
        elif cid in on_other_album and cid not in via_marker:
            # The (ASOT nnn) marker names the show version explicitly → not shielded.
            stats["titles_protected_other_album"] += 1
            other_album_infos.append(info)
        else:
            to_mask.append(cid)
            # Counted under the series when both apply → the two sum to to_mask.
            if cid in via_series:
                stats["titles_via_series"] += 1
            else:
                stats["titles_via_marker"] += 1
    stats["titles_to_mask"] = len(to_mask)

    # Displayed artist of a series = the most credited on its titles (lowest id on
    # a tie), "?" when none — albums.artist_id is mostly NULL.
    credits = _load_credits(session, via_series)
    top_artist = {}
    for key, cids in series_titles.items():
        tally = {}
        for cid in cids:
            for aid in credits.get(cid, ()):
                tally[aid] = tally.get(aid, 0) + 1
        top_artist[key] = min(tally, key=lambda a: (-tally[a], a)) if tally else None
    names = _load_artists(session, sorted(a for a in top_artist.values() if a is not None))
    series_report = sorted(
        (
            {
                "key": key,
                "artist_id": top_artist[key],
                "artist": names.get(top_artist[key], {}).get("name") or "?",
                "albums": len(set(series[key])),
                "titles": len(series_titles[key]),
            }
            for key in series
        ),
        key=lambda s: (-s["titles"], -s["albums"], s["key"]),
    )
    stats["series_retained"] = len(series_report)

    artists_to_mask, counters = plan_empty_artists(session, rule, to_mask)
    _apply_empty_artist_counters(stats, counters)
    plan = {
        "titles": titles,
        "to_mask": to_mask,
        "anchored": [],
        "artists_to_mask": artists_to_mask,
        "series": series_report,
        "other_album": other_album_infos,
    }
    return plan, stats


# --------------------------------------------------------------------------- write


def apply_plan(session, plan, rule, now=None):
    """Write the plan in bulk UPDATEs, one committed transaction per chunk.

    Guarded by ``hidden_reason IS NULL`` (never rewrites another rule's reason, and
    a re-run is a no-op) and re-checks corroboration on titles. Returns
    ``(titles_written, artists_written)``.
    """
    now = now or datetime.now(timezone.utc)
    title_stmt = text(
        f"""
        UPDATE catalog SET hidden_reason = :rule, hidden_at = :now
        WHERE id IN :ids AND hidden_reason IS NULL
          AND NOT {corroborated_sql("catalog")}
        """
    ).bindparams(bindparam("ids", expanding=True))
    # Titles are written first, so this re-check sees the final state: an artist
    # whose title stayed visible (corroborated between plan and write) is skipped.
    artist_stmt = text(
        """
        UPDATE artists SET hidden_reason = :rule, hidden_at = :now
        WHERE id IN :ids AND hidden_reason IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM catalog_artists ca JOIN catalog c ON c.id = ca.catalog_id
              WHERE ca.artist_id = artists.id AND c.hidden_reason IS NULL
          )
        """
    ).bindparams(bindparam("ids", expanding=True))

    titles_written = 0
    for chunk in _chunks(plan["to_mask"], TITLES_PER_TX):
        res = session.execute(title_stmt, {"rule": rule, "now": now, "ids": chunk})
        titles_written += res.rowcount or 0
        session.commit()
    artists_written = 0
    for chunk in _chunks(plan["artists_to_mask"], ARTISTS_PER_TX):
        res = session.execute(artist_stmt, {"rule": rule, "now": now, "ids": chunk})
        artists_written += res.rowcount or 0
        session.commit()
    return titles_written, artists_written


def count_rule(session, rule):
    """``(catalog rows, artist rows)`` currently hidden by ``rule``."""
    n_titles = session.execute(
        text("SELECT COUNT(*) FROM catalog WHERE hidden_reason = :r"), {"r": rule}
    ).scalar()
    n_artists = session.execute(
        text("SELECT COUNT(*) FROM artists WHERE hidden_reason = :r"), {"r": rule}
    ).scalar()
    return n_titles or 0, n_artists or 0


def revert_rule(session, rule, apply=False):
    """Un-mask every catalog/artist row hidden by ``rule``. Returns the counts."""
    n_titles, n_artists = count_rule(session, rule)
    if apply:
        session.execute(
            text(
                "UPDATE catalog SET hidden_reason = NULL, hidden_at = NULL "
                "WHERE hidden_reason = :r"
            ),
            {"r": rule},
        )
        session.execute(
            text(
                "UPDATE artists SET hidden_reason = NULL, hidden_at = NULL "
                "WHERE hidden_reason = :r"
            ),
            {"r": rule},
        )
        session.commit()
    return n_titles, n_artists


def run_rule(session, rule, *, apply=False, tsv_rows=None, now=None):
    """Testable core: plan (+ write when ``apply``). Returns ``(plan, stats)``."""
    if rule == "farm_fort":
        plan, stats = plan_farm_fort(session, tsv_rows or [], rule=rule)
    elif rule == "isrc_block":
        plan, stats = plan_isrc_block(session, rule=rule)
    elif rule == "episode":
        plan, stats = plan_episode(session, rule=rule)
    else:
        raise ValueError(f"unknown rule {rule!r}")
    if apply:
        stats["titles_masked"], stats["artists_masked"] = apply_plan(
            session, plan, rule, now=now
        )
    else:
        session.rollback()
    return plan, stats


# --------------------------------------------------------------------------- report


def stable_sample(items, n, seed=_SAMPLE_SEED):
    items = list(items)
    if len(items) <= n:
        return items
    return random.Random(seed).sample(items, n)


def _fmt(info):
    return f"{info['artist'] or '?'} — {info['title']} — {info['isrc'] or '(sans ISRC)'}"


def _print_report(rule, stats, plan, apply, sample_n):
    verb = "masqués" if apply else "à masquer"
    print(f"\nRègle {rule!r} — {'APPLY' if apply else 'DRY-RUN'}")
    if rule == "farm_fort":
        print(f"    artistes lus               : {stats['artists_read']}")
        print(f"    lignes TSV invalides       : {stats['artists_malformed']}")
        print(f"    ignorés garde-fou genre    : {stats['artists_genre_guard']}  (98 classique / 129 jazz)")
        print(f"    absents en base            : {stats['artists_missing']}")
    elif rule == "isrc_block":
        print(f"    préfixes bloqués           : {', '.join(plan.get('prefixes') or ()) or '(aucun — règle inerte)'}")
    elif rule == "episode":
        print(f"    albums examinés            : {stats['albums_examined']}")
        print(f"    séries retenues            : {stats['series_retained']}  (>= {EPISODE_SERIES_MIN_ALBUMS} albums + vocabulaire d'émission)")
    print(f"    titres examinés            : {stats['titles_examined']}")
    print(f"    {'titres ' + verb:<27}: {stats['titles_to_mask']}")
    if rule == "episode":
        print(f"      dont via album de série  : {stats['titles_via_series']}")
        print(f"      dont via marqueur seul   : {stats['titles_via_marker']}  ((ASOT nnn) sans album de série)")
    print(f"    protégés corroborés        : {stats['titles_protected_corroborated']}")
    if rule == "episode":
        print(f"    protégés (aussi sur un album hors épisode) : {stats['titles_protected_other_album']}")
    if rule == "farm_fort":
        print(f"    protégés ancrés            : {stats['titles_protected_anchored']}")
        print(f"    protégés co-artiste        : {stats['titles_protected_coartist']}")
        print(f"    protégés classique         : {stats['titles_protected_classical']}")
        print(f"    protégés seau homonymes    : {stats['titles_protected_homonym']}")
        print(f"    protégés ISRC ancien       : {stats['titles_protected_isrc_old']}")
    print(f"    déjà masqués (même règle): {stats['titles_already_same_rule']}")
    print(f"    déjà masqués (autre règle) : {stats['titles_already_other_rule']}")
    print(f"    {'artistes ' + verb:<27}: {stats['artists_to_mask']}  (dont tier 1 cohorte : {stats['artists_to_mask_tier1']})")
    if rule == "farm_fort":
        print(f"    co-crédités hors liste {verb:<4}: {stats['artists_to_mask_coartists']}  (dont tier 1 cohorte : {stats['artists_to_mask_coartists_tier1']})")
    print(f"    artistes gardés visibles   : {stats['artists_kept_visible']}")
    if rule == "farm_fort":
        print(f"    artistes sans titre        : {stats['artists_without_titles']}  (jamais masqués)")
    print(f"    artistes déjà masqués      : {stats['artists_already_same_rule']} même règle / {stats['artists_already_other_rule']} autre règle")
    if apply:
        print(f"    ÉCRIT : {stats['titles_masked']} titre(s), {stats['artists_masked']} artiste(s)")

    if rule == "episode":
        print(f"\nSéries retenues ({len(plan['series'])}, par volume) — À RELIRE (anti faux positif) :")
        print("    titres | albums | artiste le plus crédité (id) | clé de série")
        for s in plan["series"]:
            print(f"    {s['titles']:>6} | {s['albums']:>6} | {s['artist']} ({s['artist_id'] or '-'}) | {s['key']}")
        other = stable_sample(plan.get("other_album", ()), sample_n)
        print(f"\nÉchantillon de {len(other)} titre(s) protégé(s) — aussi sur un album hors épisode :")
        for info in sorted(other, key=lambda i: i["id"]):
            print(f"    {_fmt(info)}")

    titles = plan["titles"]
    masked = stable_sample(plan["to_mask"], sample_n)
    print(f"\nÉchantillon de {len(masked)} titre(s) {verb} (seed fixe) — À RELIRE :")
    for cid in sorted(masked):
        print(f"    {_fmt(titles[cid])}")
    if rule == "farm_fort":
        anchored = stable_sample(plan["anchored"], sample_n)
        print(f"\nÉchantillon de {len(anchored)} titre(s) protégé(s) par ancrage :")
        for info in sorted(anchored, key=lambda i: i["id"]):
            print(f"    {_fmt(info)}")
        for key, label in (
            ("classical", "marqueur classique"),
            ("homonym", "seau homonymes"),
            ("isrc_old", "ISRC ancien"),
        ):
            sample = stable_sample(plan.get(key, ()), sample_n)
            print(f"\nÉchantillon de {len(sample)} titre(s) protégé(s) — {label} :")
            for info in sorted(sample, key=lambda i: i["id"]):
                print(f"    {_fmt(info)}")


def main(rule, apply=False, revert=False, file_path=None, sample_n=DEFAULT_SAMPLE):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            mode = "APPLY" if apply else "DRY-RUN — rien ne sera écrit (--apply)"
            print(f"=== {mode} ===")
            if revert:
                n_titles, n_artists = revert_rule(session, rule, apply=apply)
                verb = "remis visibles" if apply else "seraient remis visibles"
                print(f"Revert {rule!r} : {n_titles} titre(s), {n_artists} artiste(s) {verb}.")
                return

            tsv_rows = None
            malformed = 0
            if rule == "farm_fort":
                if file_path:
                    with open(file_path, "r", encoding="utf-8") as fh:
                        tsv_rows, malformed = read_tsv(fh)
                else:
                    tsv_rows, malformed = read_tsv(sys.stdin)
            plan, stats = run_rule(session, rule, apply=apply, tsv_rows=tsv_rows)
            stats["artists_malformed"] = malformed
            _print_report(rule, stats, plan, apply, sample_n)
            if apply:
                print("\nTerminé. Idempotent : un nouveau --apply ne change rien.")
            else:
                print(
                    "\nDry-run seulement. RELIRE les échantillons, puis DUMP CHIFFRÉ "
                    "(docs/restore.md) avant --apply."
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apply or revert a reversible masking rule (catalog/artists "
        "hidden_reason). Dry-run by default; --apply to write."
    )
    parser.add_argument("--rule", required=True, choices=RULES)
    parser.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    parser.add_argument(
        "--revert", action="store_true", help="un-mask the rows hidden by --rule"
    )
    parser.add_argument(
        "--file", dest="file_path", default=None, help="farm_fort TSV (default: stdin)"
    )
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    args = parser.parse_args()
    main(
        args.rule,
        apply=args.apply,
        revert=args.revert,
        file_path=args.file_path,
        sample_n=args.sample,
    )
