#!/usr/bin/env python
"""One-shot OPS backfill: re-populate ``catalog_artists`` from the flat ``catalog.artist`` string (X4.e / lot L3).

A catalog row links its artist(s) through the many-to-many ``catalog_artists``
table (that is what the UI renders as a CLICKABLE artist). ~29k rows (~11% of the
catalog) carry a NON-EMPTY flat ``catalog.artist`` string but hold ZERO
``catalog_artists`` link — so their artist shows as plain, non-clickable text.
This script re-derives the missing links from the flat string, FOR THE M2M-EMPTY
ROWS ONLY, by splitting on a recognized separator and resolving/creating each
artist LOCALLY (no Deezer / no network).

Selection: ``catalog.artist`` non-empty AND no ``catalog_artists`` row. A row that
already has a link is never touched (so a second run is a no-op — those rows fall
out of the selection).

Per-row decision (deterministic, conservative — invariant #4 "err toward
separation": a wrong split fabricates bad artist links, expensive corruption; a
missed link is cheap):

  * Recognized separator present → split into N names → one ``catalog_artists``
    link per name, ``role="primary"``, ``position`` = index. Separators mirror
    ``deezer_enrich._ARTIST_SPLIT`` (',', ' & ', ' feat ', ' ft ', ' x ', ' vs ')
    PLUS a bare pipe '|' (source strings use "A | B" and "A|B"; a pipe never
    occurs inside a real artist name).
  * NO recognized separator → treat as ONE artist and link it (position 0,
    primary) — the common "Carl Cox" case.
  * GUARD — a string with NO recognized separator that looks like a multi-artist
    name spelled letter-by-letter ("t e s t p r e s s Kichta", fingerprint: a run
    of >= 3 consecutive single-character tokens) is NOT guessed apart: it creates
    NO link and is listed as "delegated to N3" (a future chantier). Splitting such
    glued spellings offline is unreliable, so we defer rather than fabricate.

Artist resolution/creation reuses the enrichment helpers verbatim
(``deezer_enrich._resolve_or_create_artist`` / ``_link_one_artist``) so this
backfill agrees with how enrichment builds links — deezer_id is always passed as
None (LOCAL resolution: by normalized name, then alias, else create).
``_link_one_artist`` is idempotent (it never inserts a duplicate link).

>>> DESTRUCTIVE (creates catalog_artists rows, and new artists rows for names not
    already present). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
operation is idempotent — a re-run finds the still-unlinked rows), but a bad dump
is not recoverable.

The run is DRY-RUN by default and READ-ONLY: it counts the rows that WOULD be
linked, how many artists would be created vs reused, and how many rows are
delegated to N3, WITHOUT writing anything (the created/reused counts come from a
read-only existence check, so a dry-run touches no row). Pass --apply to write the
links. A second --apply run is idempotent (the linked rows leave the selection).

Usage (from the VPS):
    docker compose exec api python scripts/backfill_catalog_artists.py          # dry-run
    docker compose exec api python scripts/backfill_catalog_artists.py --apply  # write links
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Artist, ArtistAlias, CatalogArtist, CatalogEntry
from sqlalchemy import create_engine, exists, func, select
from sqlalchemy.orm import Session
from utils import normalize

# Reuse the EXACT enrichment helpers so a backfilled link is indistinguishable
# from an enrichment-built one (resolve by name/alias then create; idempotent
# link insert). The split separator set is DERIVED from the same regex so the two
# never silently diverge.
from workers.deezer_enrich import (
    _ARTIST_SPLIT,
    _link_one_artist,
    _resolve_or_create_artist,
)

# Recognized multi-artist separators = deezer_enrich._ARTIST_SPLIT (',', ' & ',
# ' feat '/' ft ', ' x ', ' vs ') PLUS a bare pipe '|'. Built from the shared
# pattern (not re-typed) so the separator set stays aligned with enrichment; the
# pipe branch is the only addition — "A | B" and "A|B" both occur in the source
# strings and a pipe is never part of a real artist name (same rationale as
# workers.tasks.artists.classify_artist_string).
_SPLIT_RE = re.compile("(?:" + _ARTIST_SPLIT.pattern + r"|\s*\|\s*)", re.IGNORECASE)

# GUARD threshold: a run of at least this many consecutive single-character tokens
# marks a letter-by-letter spelled multi-artist name ("t e s t p r e s s Kichta").
_MIN_SPACED_RUN = 3

# Rows per committed transaction in --apply mode (mirrors reverify/dedup scripts).
_COMMIT_EVERY = 500

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


# ── pure decision helpers (network-free, importable, unit-tested) ────────────


def split_artist_names(raw):
    """Split ``raw`` on a recognized separator into stripped, non-empty names."""
    return [p.strip() for p in _SPLIT_RE.split(raw) if p.strip()]


def has_recognized_separator(raw):
    """True if ``raw`` contains one of the recognized multi-artist separators."""
    return bool(_SPLIT_RE.search(raw))


def looks_spaced_multi_artist(raw):
    """True when ``raw`` holds a run of >= ``_MIN_SPACED_RUN`` consecutive
    single-character tokens ("t e s t p r e s s Kichta") — the fingerprint of a
    multi-artist name glued together with the letters spaced out and NO recognized
    separator. Such a string must NOT be guessed apart (a wrong split fabricates
    bad artist links, invariant #4); it is delegated to the N3 chantier. Pure."""
    run = 0
    for token in raw.split():
        if len(token) == 1:
            run += 1
            if run >= _MIN_SPACED_RUN:
                return True
        else:
            run = 0
    return False


def plan_artist_links(raw):
    """Decide what to do with one ``catalog.artist`` string. Pure/testable.

    Returns one of:
      ("split", [name, ...])  — 2+ recognized-separator tokens, each a primary artist
      ("single", [name])      — no separator (or a separator yielding one token)
      ("delegate", raw)       — spaced-letter glued multi-artist, left to N3

    The GUARD (spaced-letter fingerprint) is only consulted when NO recognized
    separator is present: a separator gives an explicit, trustworthy boundary, so
    it wins; the guard exists to stop a *separator-less* glued name from becoming a
    single wrong artist.
    """
    s = (raw or "").strip()
    if not s:
        return ("delegate", s)
    if has_recognized_separator(s):
        names = split_artist_names(s)
        if not names:
            return ("delegate", s)  # defensive: separators but no usable token
        return ("split", names) if len(names) > 1 else ("single", names)
    if looks_spaced_multi_artist(s):
        return ("delegate", s)
    return ("single", [s])


# ── engine ───────────────────────────────────────────────────────────────────


def _select_candidates(session):
    """Every catalog row with a non-empty ``artist`` and NO ``catalog_artists`` link.

    Returned as lightweight ``(id, artist)`` rows (not ORM entities) so the loop
    holds no identity-map bloat and survives the per-batch commits unaffected.
    """
    link_exists = exists().where(CatalogArtist.catalog_id == CatalogEntry.id)
    stmt = (
        select(CatalogEntry.id, CatalogEntry.artist)
        .where(CatalogEntry.artist.isnot(None))
        .where(func.trim(CatalogEntry.artist) != "")
        .where(~link_exists)
        .order_by(CatalogEntry.id)
    )
    return session.execute(stmt).all()


def _artist_exists(session, norm):
    """Read-only: True if an Artist (or alias) already carries this normalized name.

    Mirrors the deezer_id-less lookup of ``_resolve_or_create_artist`` (normalized
    name, then alias) so the created/reused counting matches what --apply would do,
    WITHOUT creating anything — that is what keeps the dry-run read-only.
    """
    if session.execute(
        select(Artist.id).where(Artist.normalized_name == norm)
    ).first():
        return True
    return (
        session.execute(
            select(ArtistAlias.artist_id).where(ArtistAlias.normalized_alias == norm)
        ).first()
        is not None
    )


def backfill_catalog_artists(
    session, *, apply=False, commit_every=_COMMIT_EVERY, max_examples=5
):
    """Link every M2M-empty catalog row's flat ``artist`` string to catalog_artists.

    For each candidate the flat string is planned by ``plan_artist_links``:
    ``split`` / ``single`` build one ``catalog_artists`` link per resolved artist
    (``role="primary"``, ``position`` = index, deezer_id None → LOCAL resolution);
    ``delegate`` (a spaced-letter glued name) creates NO link and is only counted.

    Artists are counted created-vs-reused by a read-only existence check
    (``_artist_exists``) shared by both modes — so the counts are identical whether
    or not ``apply`` is set, and a dry-run writes nothing. In --apply mode the links
    (and any new artists) are written and committed every ``commit_every`` rows.

    Returns ``{"candidates", "linked_rows", "links_created", "artists_created",
    "artists_reused", "delegated_n3", "examples", "delegated_examples"}`` where
    ``artists_created`` counts DISTINCT names that would be newly created and
    ``artists_reused`` counts links resolving to an already-existing artist.
    """
    # Names that would be newly created THIS run — so a repeat reference to a
    # just-created name is neither a fresh creation nor an existing-artist reuse.
    would_create = set()
    candidates = linked_rows = links_created = 0
    artists_reused = delegated = 0
    examples = []
    delegated_examples = []
    pending = 0

    for cat_id, raw in _select_candidates(session):
        candidates += 1
        kind, payload = plan_artist_links(raw)

        if kind == "delegate":
            delegated += 1
            if len(delegated_examples) < max_examples:
                delegated_examples.append((cat_id, raw))
            continue

        names = payload
        row_norms = set()  # dedup a name repeated within one string ("Foo, Foo")
        row_links = 0
        for position, name in enumerate(names):
            norm = normalize(name)
            if norm in row_norms:
                continue
            row_norms.add(norm)

            links_created += 1
            row_links += 1
            # would_create is checked FIRST so a name created earlier in this run
            # is not miscounted as a reuse of an existing artist (keeps the counts
            # identical between dry-run and --apply).
            if norm in would_create:
                pass
            elif _artist_exists(session, norm):
                artists_reused += 1
            else:
                would_create.add(norm)

            if apply:
                artist = _resolve_or_create_artist(session, name, None)
                _link_one_artist(session, cat_id, artist.id, "primary", position)

        if row_links:
            linked_rows += 1
            if len(examples) < max_examples:
                examples.append((cat_id, raw, list(names)))

        if apply:
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "candidates": candidates,
        "linked_rows": linked_rows,
        "links_created": links_created,
        "artists_created": len(would_create),
        "artists_reused": artists_reused,
        "delegated_n3": delegated,
        "examples": examples,
        "delegated_examples": delegated_examples,
    }


def _print_report(stats, apply):
    link_verb = "linked" if apply else "would link"
    create_verb = "created" if apply else "would create"
    print(
        f"\nCandidates (catalog.artist set, zero catalog_artists link): "
        f"{stats['candidates']}"
    )
    print(
        f"    {link_verb} {stats['linked_rows']} row(s) via {stats['links_created']} "
        f"link(s) ({create_verb} {stats['artists_created']} new artist(s), reused "
        f"{stats['artists_reused']} existing)."
    )
    print(
        f"    delegated to N3 (spaced-letter glued names, NOT split): "
        f"{stats['delegated_n3']}"
    )
    for cat_id, raw, names in stats["examples"]:
        print(f"    #{cat_id} {raw!r} -> {names}")
    if stats["delegated_examples"]:
        print("    N3 examples (left unlinked):")
        for cat_id, raw in stats["delegated_examples"]:
            print(f"        #{cat_id} {raw!r}")


def main(apply):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total = session.execute(
                select(func.count()).select_from(CatalogEntry)
            ).scalar_one()
            print(f"Catalog rows: {total}")

            if not apply:
                print("\n=== DRY-RUN — nothing will be written (use --apply) ===")
                stats = backfill_catalog_artists(session, apply=False)
                _print_report(stats, apply=False)
                session.rollback()  # read-only anyway; belt-and-braces
                print(
                    "\nDry-run only. A row with a recognized separator "
                    "(',', '&', 'feat', 'ft', 'x', 'vs', '|') is split into N "
                    "primary artists; a separator-less string is linked as ONE "
                    "artist; a separator-less spaced-letter glued name "
                    "('t e s t p r e s s Kichta') is left UNLINKED and delegated to "
                    "the N3 chantier (never guessed apart — invariant #4)."
                )
                print(
                    "Re-run with --apply to write the links — DUMP PROD FIRST (see "
                    "docs/restore.md)."
                )
                return

            print("\n=== APPLY — writing catalog_artists links ===")
            stats = backfill_catalog_artists(session, apply=True)
            _print_report(stats, apply=True)

            remaining = backfill_catalog_artists(session, apply=False)["candidates"]
            session.rollback()
            print(
                f"\nRemaining unlinked candidates: {remaining} "
                f"(expected {stats['delegated_n3']} — the N3-delegated rows, which "
                f"are intentionally left unlinked)."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-populate catalog_artists from the flat catalog.artist string "
        "for rows that have no M2M link (spaced-letter glued names are delegated to "
        "the N3 chantier, never guessed apart)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the links (default: dry-run, no changes)",
    )
    args = parser.parse_args()
    main(apply=args.apply)
