#!/usr/bin/env python
"""One-shot OPS repair: resync the flat ``catalog.artist`` string from ``catalog_artists`` (X4.b / lot L2).

A catalog row stores its artist(s) under TWO forms: the flat column
``catalog.artist`` (a free-text string) and the many-to-many ``catalog_artists``
links (what the UI renders as CLICKABLE artists). On ~3670 rows the flat column
DIVERGED franchement from the M2M: the M2M was re-resolved via Deezer without ever
rewriting the flat string, so the flat now carries a stale/wrong artist while the
M2M holds the corrected one. The flat column still matters — it backs the
``sort=artist`` ordering, the Explorer text search, and the fallback label when the
M2M is empty — so a drifted flat degrades sort/search.

This script rewrites ``catalog.artist`` from the M2M (the names concatenated in
``position`` order, joined by ", ") FOR THE FRANK-DIVERGENCE ROWS ONLY. It does NOT
create, delete or re-link any ``catalog_artists`` row (that is lot L3 /
``backfill_catalog_artists.py``), touches no application code and no migration.

Selection (per row):
  1. The row must hold >= 1 ``catalog_artists`` link AND a non-empty flat
     ``catalog.artist`` (an INNER JOIN excludes M2M-empty rows — resyncing those is
     lot X4.e's job — and blank flats are filtered out).
  2. The flat string must diverge FRANCHEMENT from the M2M concat, where
     "franche divergence" mirrors the prod measure that counted the ~3670: NEITHER
     folded string is contained in the other (``is_franche_divergence``, on the
     ``_fold`` of both, whitespace-collapsed so pure spacing differences do not
     count). A row already coherent (one string contained in the other — same
     artists, or the M2M merely more complete) is LEFT INTACT — this bounds the
     churn to the rows that actually drifted.

Classification of the frank-divergence candidates (``classify_row``):
  * "resync"    — the flat carries NO artist token the M2M keeps that would be lost
                  (same set reordered, M2M a superset, or the two are disjoint = the
                  flat is stale/unrelated junk): trust the re-resolved M2M and
                  overwrite the flat with the M2M concat.
  * "ambiguous" — the flat SHARES >= 1 artist with the M2M AND ALSO carries >= 1
                  artist the M2M drops ("M2M partiel" / partial overlap): both forms
                  are plausible and overwriting would LOSE the flat's extra artist.
                  Per data-authority invariant #4 (err toward separation) this is
                  NOT decided automatically — the row is LEFT INTACT and listed apart
                  in the report for a human call.

>>> DESTRUCTIVE (mutates ``catalog.artist``). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
operation is idempotent — a re-run finds the still-divergent rows), but a bad dump
is not recoverable.

Idempotent: after --apply a resync row's flat equals the M2M concat, so it is no
longer a frank divergence — a second --apply finds ~0 to resync (only the ambiguous
rows, intentionally left intact, still diverge).

The run is DRY-RUN by default and read-only: it prints how many rows are a frank
divergence, how many WOULD be resynced, how many are held back as ambiguous, plus a
few examples of each, WITHOUT modifying anything. Pass --apply to write the flats.

Usage (from the VPS):
    docker compose exec api python scripts/resync_catalog_artist.py          # dry-run
    docker compose exec api python scripts/resync_catalog_artist.py --apply  # rewrite flats
"""

import argparse
import os
import re
import sys
from itertools import groupby

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Artist, CatalogArtist, CatalogEntry
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

# Reuse the enrichment fold + artist-splitter so this script compares names exactly
# as enrichment/matching does (accent- and case-insensitive), and never diverges
# from the shared separator set.
from workers.deezer_enrich import _ARTIST_SPLIT, _fold

# Rows per committed transaction in --apply mode (mirrors backfill_catalog_artists).
_COMMIT_EVERY = 500
# Collapse any run of whitespace so a flat string and the ", "-joined M2M concat are
# not counted as diverging on spacing alone.
_WS = re.compile(r"\s+")

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


# ── pure comparison helpers (network- and DB-free, importable, unit-tested) ───


def build_artist_string(pairs):
    """Reconstruct the flat artist string from M2M ``(name, position)`` pairs.

    Ordered by ``position`` (NULLs last, so a legacy link with no position sorts
    after the ordered ones), ties broken by folded name for determinism; names are
    stripped, blanks dropped, and the result joined by ", " — the canonical flat
    form. Pure/testable.
    """
    cleaned = [(name.strip(), pos) for name, pos in pairs if name and name.strip()]
    cleaned.sort(
        key=lambda np: (np[1] is None, np[1] if np[1] is not None else 0, _fold(np[0]))
    )
    return ", ".join(name for name, _ in cleaned)


def _compare_key(s):
    """Fold (lowercase + strip accents) then collapse whitespace for comparison."""
    return _WS.sub(" ", _fold(s or "")).strip()


def is_franche_divergence(flat_str, m2m_str):
    """True iff the flat and the M2M concat diverge FRANCHEMENT.

    "Franche" = mirror of the prod measure that counted the ~3670: NEITHER folded
    string is contained in the other. Two forms that merely differ by containment
    (same artists, one a substring of the other — e.g. the M2M is more complete) are
    NOT a frank divergence. An empty side is never a frank divergence (there is
    nothing to resync from / to). Pure/testable.
    """
    a = _compare_key(flat_str)
    b = _compare_key(m2m_str)
    if not a or not b:
        return False
    return a not in b and b not in a


def _artist_token_set(s):
    """The set of folded artist tokens in a string (split on the enrichment separators)."""
    return {
        tok
        for tok in (_compare_key(part) for part in _ARTIST_SPLIT.split(s or ""))
        if tok
    }


def classify_row(flat_str, m2m_str):
    """Classify one row: ``"coherent"`` | ``"resync"`` | ``"ambiguous"``. Pure/testable.

    - ``coherent``  — not a frank divergence (containment or identical): leave intact.
    - ``ambiguous`` — a frank divergence where the flat SHARES >= 1 artist with the
      M2M AND ALSO carries >= 1 artist the M2M drops (partial overlap / "M2M
      partiel"): overwriting would lose the flat's extra artist and both forms are
      plausible → leave intact (invariant #4, err toward separation).
    - ``resync``    — a frank divergence that is not ambiguous (same set reordered,
      M2M a superset, or fully disjoint = the flat is stale/unrelated): trust the
      re-resolved M2M and overwrite.
    """
    if not is_franche_divergence(flat_str, m2m_str):
        return "coherent"
    flat_tokens = _artist_token_set(flat_str)
    m2m_tokens = _artist_token_set(m2m_str)
    if (flat_tokens & m2m_tokens) and (flat_tokens - m2m_tokens):
        return "ambiguous"
    return "resync"


# ── engine ─────────────────────────────────────────────────────────────────


def _iter_candidate_groups(session):
    """Yield ``(catalog_id, flat_artist, [(name, position), ...])`` for every row
    holding >= 1 ``catalog_artists`` link and a non-empty flat ``artist``.

    One JOIN query ordered by catalog_id, grouped in Python (``groupby``) — so the
    M2M-empty rows never appear (INNER JOIN) and each group is materialized lazily.
    """
    stmt = (
        select(
            CatalogEntry.id, CatalogEntry.artist, Artist.name, CatalogArtist.position
        )
        .join(CatalogArtist, CatalogArtist.catalog_id == CatalogEntry.id)
        .join(Artist, Artist.id == CatalogArtist.artist_id)
        .where(CatalogEntry.artist.isnot(None))
        .where(func.trim(CatalogEntry.artist) != "")
        .order_by(CatalogEntry.id)
    )
    for cat_id, rows in groupby(session.execute(stmt), key=lambda r: r[0]):
        rows = list(rows)
        flat = rows[0][1]
        pairs = [(r[2], r[3]) for r in rows]
        yield cat_id, flat, pairs


def resync_catalog_artist(
    session, *, apply=False, commit_every=_COMMIT_EVERY, max_examples=5
):
    """Resync ``catalog.artist`` from the M2M for every frank-divergence "resync" row.

    Each candidate group (row with links + non-empty flat) is classified by
    ``classify_row``. A "resync" row has its flat overwritten with the M2M concat
    (``build_artist_string``); a "coherent" row is skipped; an "ambiguous" row is
    LEFT INTACT and only counted/exampled (invariant #4). A group whose M2M concat is
    empty (all link names blank) is treated as coherent — there is nothing to resync
    from, and the flat must never be blanked.

    apply=False (default) is read-only: nothing is committed and the counts describe
    what WOULD happen. In --apply mode the flats are rewritten and committed every
    ``commit_every`` resync rows (plus a trailing commit).

    Returns ``{"considered", "coherent", "resync", "ambiguous", "updated",
    "examples", "ambiguous_examples"}`` where ``considered`` counts candidate rows,
    ``resync``/``ambiguous`` count the two frank-divergence buckets (their sum is the
    frank-divergence total), ``updated`` counts rows actually rewritten (0 in
    dry-run), and each ``examples`` entry is ``(catalog_id, flat, m2m)``.
    """
    considered = coherent = resync = ambiguous = updated = 0
    examples = []
    ambiguous_examples = []
    pending = 0

    for cat_id, flat, pairs in _iter_candidate_groups(session):
        considered += 1
        m2m = build_artist_string(pairs)
        if not m2m:
            coherent += 1  # no usable M2M name → nothing to resync, never blank the flat
            continue

        kind = classify_row(flat, m2m)
        if kind == "coherent":
            coherent += 1
            continue
        if kind == "ambiguous":
            ambiguous += 1
            if len(ambiguous_examples) < max_examples:
                ambiguous_examples.append((cat_id, flat, m2m))
            continue

        # resync
        resync += 1
        if len(examples) < max_examples:
            examples.append((cat_id, flat, m2m))
        if apply:
            session.execute(
                update(CatalogEntry).where(CatalogEntry.id == cat_id).values(artist=m2m)
            )
            updated += 1
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "considered": considered,
        "coherent": coherent,
        "resync": resync,
        "ambiguous": ambiguous,
        "updated": updated,
        "examples": examples,
        "ambiguous_examples": ambiguous_examples,
    }


def _total_rows(session):
    return session.execute(select(func.count()).select_from(CatalogEntry)).scalar_one()


def _print_report(stats, apply):
    verb = "resynced" if apply else "would resync"
    franche = stats["resync"] + stats["ambiguous"]
    print(
        f"\nCandidates (>= 1 catalog_artists link, non-empty flat artist): "
        f"{stats['considered']}"
    )
    print(
        f"    frank divergence: {franche} "
        f"({stats['resync']} to resync + {stats['ambiguous']} ambiguous held back), "
        f"{stats['coherent']} coherent (left intact)."
    )
    print(f"    {verb} {stats['updated'] if apply else stats['resync']} flat(s).")
    for cat_id, flat, m2m in stats["examples"]:
        print(f"    #{cat_id} {flat!r} -> {m2m!r}")
    if stats["ambiguous_examples"]:
        print("    ambiguous (partial overlap, LEFT INTACT — invariant #4):")
        for cat_id, flat, m2m in stats["ambiguous_examples"]:
            print(f"        #{cat_id} flat={flat!r} | m2m={m2m!r}")


def main(apply):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            print(f"Catalog rows: {_total_rows(session)}")

            if not apply:
                print("\n=== DRY-RUN — nothing will be modified (use --apply) ===")
                _print_report(
                    resync_catalog_artist(session, apply=False), apply=False
                )
                session.rollback()  # read-only anyway; belt-and-braces
                print(
                    "\nDry-run only. A row is resynced only when its flat "
                    "catalog.artist diverges FRANCHEMENT from the M2M concat (neither "
                    "folded string contains the other) AND overwriting would not lose "
                    "an artist the flat carries but the M2M drops. A partial overlap "
                    "('M2M partiel') is held back as ambiguous and left intact "
                    "(invariant #4). M2M-empty rows are lot X4.e's job, not this "
                    "script's."
                )
                print(
                    "Re-run with --apply to rewrite the flats — DUMP PROD FIRST (see "
                    "docs/restore.md)."
                )
                return

            print("\n=== APPLY — rewriting catalog.artist from the M2M ===")
            stats = resync_catalog_artist(session, apply=True)
            _print_report(stats, apply=True)

            after = resync_catalog_artist(session, apply=False)
            session.rollback()
            print(
                f"\nRemaining frank divergence: {after['resync'] + after['ambiguous']} "
                f"(expected {stats['ambiguous']} — the ambiguous rows intentionally "
                f"left intact; resync should be 0)."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Resync the flat catalog.artist string from catalog_artists for "
        "rows where the flat diverges frankly from the M2M (ambiguous partial "
        "overlaps are left intact, invariant #4)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually rewrite the flats (default: dry-run, no changes)",
    )
    args = parser.parse_args()
    main(apply=args.apply)
