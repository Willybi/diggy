#!/usr/bin/env python
"""One-shot OPS repair: strip platform ids shared across DISTINCT recordings (X3.c).

Before the X3 matcher fix (lots A/B), enrichment stamped ``deezer_id`` /
``beatport_id`` that did NOT identify the recording: Deezer search returned
``hits[0]`` unchecked, so a REMIX inherited the ORIGINAL's deezer_id; the Beatport
release fallback stamped one beatport_id on EVERY track of an EP. The result is
groups of catalog rows sharing a platform id while being DISTINCT recordings —
each such row carries a suspect id and, worse, metadata (bpm/key/label/cover/...)
that may have been derived from the wrong track.

This script does NOT delete or merge anything (that is ``dedup_catalog.py``'s job
for TRUE duplicates). It only finds the suspect groups and, with ``--apply``,
resets each suspect row to a re-enrichable state:

    row.<platform>_id      = NULL
    row.<platform>_searched_at   = NULL
    row.<platform>_search_attempts = 0

which is exactly what ``workers.enrichment.select_enrich_candidates`` reads to
re-pick the row (tier 1: id NULL + searched_at NULL) — so the E1 re-scan, now
guarded by the corrected matcher (lots A/B), re-enriches it with the RIGHT id.

Detection (per column, deezer then beatport):
  1. Take every platform-id VALUE shared by 2+ rows (``_duplicate_values``).
  2. Split each group into same-recording clusters (``_cluster_by_same_track``,
     the ISRC-or-remix-aware clique from ``dedup_catalog``).
     - 1 cluster  → all rows ARE the same recording (a TRUE duplicate). NOT our
       problem — ``dedup_catalog.py`` merges those. Left untouched here.
     - 2+ clusters → the id is shared across DISTINCT recordings. It can be
       correct for AT MOST one cluster, and OFFLINE WE CANNOT KNOW WHICH, so
       EVERY row of the group is SUSPECT and has its id cleared. Design trade-off
       (assumed, see X3.c brief): clearing the id on all rows — rather than
       guessing a keeper — guarantees no row retains a possibly-wrong id; the
       cost is extra E1 re-enrichment churn (each suspect row is re-searched).

>>> DESTRUCTIVE (mutates rows). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
operation is idempotent — a re-run finds the remaining groups), but a bad dump is
not recoverable.

RESIDUAL (assumed): only the platform id and its search state are reset. The
OTHER metadata a wrong match may have written (cover, duration, bpm/key, label,
release_date, ...) is NOT blanked — that is deliberately too risky to null blind.
Such a mis-derived field can survive until a natural overwrite (the re-scan fills
only NULL fields; an already-populated wrong value may persist). The report calls
this out; deciding whether that residual is acceptable is the team's call before
running --apply.

The run is DRY-RUN by default: it prints how many id-groups are suspect (shared
across distinct recordings), how many are true-duplicate groups left to
``dedup_catalog``, how many rows would be reset, and a few examples, WITHOUT
modifying anything. Pass --apply to clear the ids. A second --apply run is
idempotent (the cleared ids are NULL, so no group is shared any more → 0 suspect).

Usage (from the VPS):
    docker compose exec api python scripts/reverify_platform_ids.py          # dry-run
    docker compose exec api python scripts/reverify_platform_ids.py --apply  # clear ids
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import CatalogEntry

# Reuse the exact detection bricks from the dedup script: the shared-value query
# and the ISRC-or-remix-aware clustering — so both scripts agree on "same
# recording" and never diverge.
from scripts.dedup_catalog import _cluster_by_same_track, _duplicate_values
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

# Platform-id columns to re-verify, deezer first (matches dedup_catalog order;
# here the passes are independent — no row is deleted — but keep the order for a
# consistent report).
_REVERIFY_COLUMNS = ("deezer_id", "beatport_id")
# For each platform-id column, the E1 search-state columns to reset so
# select_enrich_candidates re-picks the row as a tier-1 (never-searched) candidate.
_SEARCH_STATE = {
    "deezer_id": ("deezer_searched_at", "deezer_search_attempts"),
    "beatport_id": ("beatport_searched_at", "beatport_search_attempts"),
}
# Groups per committed transaction in --apply mode (mirrors dedup_catalog).
_COMMIT_EVERY = 50

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def reverify_by_column(
    session, column, *, apply=False, commit_every=_COMMIT_EVERY, max_examples=5
):
    """Clear the platform ``column`` on every row of a group shared across distinct recordings.

    Each group of rows sharing a non-NULL ``column`` is split by
    ``_cluster_by_same_track``. A group of a single cluster is a TRUE duplicate
    (same recording) and is left to ``dedup_catalog.py`` — NOT touched here. A
    group of 2+ clusters means the id spans DISTINCT recordings; the id is wrong
    for all but at most one row and offline we cannot tell which, so EVERY row of
    the group is reset: ``column`` → NULL and the source's ``*_searched_at`` /
    ``*_search_attempts`` → NULL / 0, making it a tier-1 E1 re-scan candidate.

    apply=False (default) is read-only: nothing is committed and the returned
    counts describe what WOULD happen. In --apply mode the work is committed every
    ``commit_every`` suspect groups (plus a trailing commit).

    Returns ``{"suspect_groups", "clean_groups", "suspect_rows", "reset",
    "examples"}`` where ``suspect_groups`` counts id-groups spanning distinct
    recordings, ``clean_groups`` counts true-duplicate groups left intact, and
    ``examples`` is a list of ``(value, [(row_id, title), ...])`` per suspect group.
    """
    col = getattr(CatalogEntry, column)
    searched_name, attempts_name = _SEARCH_STATE[column]
    dup_values = _duplicate_values(session, column)

    suspect_groups = clean_groups = suspect_rows = reset = 0
    examples = []
    pending = 0

    for value in dup_values:
        rows = session.execute(select(CatalogEntry).where(col == value)).scalars().all()
        if len(rows) < 2:
            continue  # defensive: this script never deletes, so it cannot shrink a group

        clusters = _cluster_by_same_track(rows)
        if len(clusters) < 2:
            clean_groups += 1  # one recording (true dup) — dedup_catalog's job, not ours
            continue

        # 2+ distinct recordings under one id → the id can be right for at most one
        # cluster and offline we cannot know which → clear it on the whole group.
        suspect_groups += 1
        suspect_rows += len(rows)
        if len(examples) < max_examples:
            examples.append((value, [(r.id, r.title) for r in rows]))

        if apply:
            for r in rows:
                setattr(r, column, None)
                setattr(r, searched_name, None)
                setattr(r, attempts_name, 0)
                reset += 1
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "suspect_groups": suspect_groups,
        "clean_groups": clean_groups,
        "suspect_rows": suspect_rows,
        "reset": reset,
        "examples": examples,
    }


def _total_rows(session):
    return session.execute(select(func.count()).select_from(CatalogEntry)).scalar_one()


def _print_report(column, stats, apply):
    verb = "reset" if apply else "would reset"
    print(
        f"\n[{column}] {stats['suspect_groups']} suspect group(s) sharing an id "
        f"across DISTINCT recordings "
        f"({stats['clean_groups']} true-duplicate group(s) left to dedup_catalog), "
        f"{verb} {stats['suspect_rows']} suspect row(s)."
    )
    for value, rows in stats["examples"]:
        titles = ", ".join(f"#{rid} {title!r}" for rid, title in rows)
        print(f"    {column}={value!r}: {titles}")


def main(apply):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            print(f"Catalog rows: {_total_rows(session)}")

            if not apply:
                print("\n=== DRY-RUN — nothing will be modified (use --apply) ===")
                for column in _REVERIFY_COLUMNS:
                    _print_report(
                        column,
                        reverify_by_column(session, column, apply=False),
                        apply=False,
                    )
                session.rollback()
                print(
                    "\nDry-run only. True-duplicate groups (a single recording "
                    "under the id) are NOT counted here — they are dedup_catalog's "
                    "job. Only the ids are reset by --apply; the OTHER metadata a "
                    "wrong match may have written (cover/duration/bpm/key/label/"
                    "release_date) is left as-is (too risky to blank blind) and can "
                    "survive until a natural overwrite — an assumed residual."
                )
                print(
                    "Re-run with --apply to clear the suspect ids so the E1 re-scan "
                    "(now matcher-guarded) re-enriches them — DUMP PROD FIRST (see "
                    "docs/restore.md)."
                )
                return

            print("\n=== APPLY — clearing suspect ids (deezer, then beatport) ===")
            for column in _REVERIFY_COLUMNS:
                _print_report(
                    column,
                    reverify_by_column(session, column, apply=True),
                    apply=True,
                )
            session.commit()

            remaining = {
                c: reverify_by_column(session, c, apply=False)["suspect_groups"]
                for c in _REVERIFY_COLUMNS
            }
            print(
                "\nRemaining suspect groups: "
                + ", ".join(f"{c}={remaining[c]}" for c in _REVERIFY_COLUMNS)
                + "  (expected 0)"
            )
            print(
                "\nThe reset rows are now tier-1 E1 re-scan candidates and will be "
                "re-enriched on the next nightly run (enrich_catalog / "
                "enrich_catalog_beatport). Only the platform id + its search state "
                "were cleared; a mis-derived non-id field may persist until a "
                "natural overwrite — the assumed X3.c residual."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clear platform ids shared across distinct recordings so the "
        "E1 re-scan re-enriches them with the corrected matcher (true duplicates "
        "are left to dedup_catalog)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually clear the suspect ids (default: dry-run, no changes)",
    )
    args = parser.parse_args()
    main(apply=args.apply)
