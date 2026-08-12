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

The BEATPORT pass ALSO clears bpm/key when — and ONLY when — they are
beatport-sourced (``bpm_source`` / ``key_source`` == "beatport"):

    row.bpm = row.bpm_source = NULL   (iff bpm_source == "beatport")
    row.key = row.key_source = NULL   (iff key_source == "beatport")

because ``beatport/enrich.enrich_from_beatport`` writes bpm/key ONLY when the
source is not already "beatport". A suspect row still carrying the WRONG match's
``bpm_source="beatport"`` would otherwise keep its wrong bpm/key forever — the
corrected match re-finds the right value but DROPS it at that guard. Nulling the
value AND its source re-opens the guard so the re-scan re-derives it. A bpm/key
from any OTHER source ("rekordbox", "deezer", or unset) did NOT come from the
suspect Beatport match and may be authoritative, so it is NEVER blanked
(data-authority invariant #2). The DEEZER pass has no bpm/key to clear (Deezer
enrichment never stamps a bpm/key provenance) but DOES reset ``has_preview`` to
False when it clears the id:

    row.has_preview = False   (iff no ``deezer`` radar source backs the row)

because ``has_preview`` is a Deezer-only signal (only a Deezer hit sets it True;
TIDAL/Spotify ingestion stores ``preview=None``) and ``get_preview_url`` resolves a
preview ONLY via Deezer — a ``deezer`` radar source, else ``catalog.deezer_id``. A
row left ``has_preview=True`` with neither can never serve a preview, so the
frontend (which gates Play on ``has_preview``) offers a Play button that 404s. A row
that keeps a ``deezer`` radar source still serves a preview from its
``external_track_id`` and is therefore left untouched.

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

TWO OPERATING MODES (X4.c adds the second):

  * DEFAULT (shared ids) — the detection above: reset only ids SHARED across
    distinct recordings. Precise but NARROW — it never sees a WRONG id that is
    UNIQUE to a single row (a mismatch that stamped an id belonging to no OTHER
    catalog row), which is the MAJORITY of the pre-X3 mistakes: ~73767 beatport /
    ~106116 deezer rows were id-stamped by the UNGUARDED matcher BEFORE the X3 fix
    (2026-07-22) and most of those wrong ids are unique to their row, so the
    shared-id pass never touches them.

  * --pre-x3 (opt-in) — bulk re-verification: reset EVERY row that carries a
    platform id AND whose last search predates the X3 fix
    (``*_searched_at < X3_FIX_DATE``), whether or not the id is shared. Any such
    row was stamped by the unguarded matcher and may hold a wrong id. The reset
    SEMANTICS are IDENTICAL to the default mode (id + search state + conditional
    beatport-sourced bpm/key + stale has_preview) — only the SELECTION differs.
    Because this can touch tens of thousands of rows, the operator bounds the
    churn (an ops decision):
      --only-divergent  restrict to rows whose flat ``catalog.artist`` FRANKLY
                        diverges (fold + non-containment) from the row's FIRST
                        linked artist (``catalog_artists`` at the lowest
                        ``position``) — the rows most likely to hold a wrong id.
                        A row with no linked artist has no reference to diverge
                        from and is skipped by this filter.
      --limit N         sample only the N OLDEST rows (by ``*_searched_at``) per
                        column, so a first run can be validated before the full
                        drain.
    EDGE (both bounds): a row with an id but ``*_searched_at IS NULL`` (never
    stamped — legacy) is NOT in the measured pre-X3 population, so by default it
    is NOT reset; it is only COUNTED and reported as a separate edge for the
    operator to decide on.

Idempotent in both modes: a reset row has a NULL id, so it leaves the selection
(default: no longer shared; --pre-x3: ``column IS NULL`` fails the filter).

>>> DESTRUCTIVE (mutates rows). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
operation is idempotent — a re-run finds the remaining groups), but a bad dump is
not recoverable.

RESIDUAL (assumed): the platform id + its search state are reset on both passes;
the beatport pass additionally nulls beatport-sourced bpm/key and the deezer pass
resets stale ``has_preview``. The OTHER metadata a wrong match may have written
(cover, duration, label, release_date, ...) is NOT blanked — that is deliberately
too risky to null blind. Such a mis-derived
field can survive until a natural overwrite (the re-scan fills only NULL fields; an
already-populated wrong value may persist). The report calls this out; deciding
whether that residual is acceptable is the team's call before running --apply.

The run is DRY-RUN by default: it prints how many id-groups are suspect (shared
across distinct recordings), how many are true-duplicate groups left to
``dedup_catalog``, how many rows would be reset, and a few examples, WITHOUT
modifying anything. Pass --apply to clear the ids. A second --apply run is
idempotent (the cleared ids are NULL, so no group is shared any more → 0 suspect).

Usage (from the VPS):
    # DEFAULT — shared ids across distinct recordings
    docker compose exec api python scripts/reverify_platform_ids.py           # dry-run
    docker compose exec api python scripts/reverify_platform_ids.py --apply   # clear ids
    # --pre-x3 — every id stamped before the X3 fix (bulk re-verification)
    docker compose exec api python scripts/reverify_platform_ids.py --pre-x3               # dry-run
    docker compose exec api python scripts/reverify_platform_ids.py --pre-x3 --only-divergent --limit 5000
    docker compose exec api python scripts/reverify_platform_ids.py --pre-x3 --apply       # full drain
"""

import argparse
import os
import sys
import unicodedata
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Artist, CatalogArtist, CatalogEntry

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
# Per-column metadata whose value must be re-derived on re-enrichment, cleared
# ONLY when its provenance proves it came from THIS platform's (suspect) match.
# Each entry is (value_col, source_col, expected_source): when
# ``row.<source_col> == expected_source`` the pair is nulled so the enrich guard
# re-opens (``enrich_from_beatport`` writes bpm/key only when the source is not
# already "beatport" — a wrong bpm_source="beatport" would otherwise pin the wrong
# value forever). A bpm/key from another source ("rekordbox"/"deezer"/unset) did
# NOT come from this match and may be authoritative → NEVER touched (data-authority
# invariant #2). Deezer has no bpm/key provenance write, so its pass stays id-only.
_CONDITIONAL_METADATA = {
    "deezer_id": (),
    "beatport_id": (
        ("bpm", "bpm_source", "beatport"),
        ("key", "key_source", "beatport"),
    ),
}
# ``has_preview`` is a DEEZER-only signal: only a Deezer hit ever sets it True
# (``enrich_entry``); TIDAL/Spotify ingestion stores ``preview=None``. Clearing a
# suspect ``deezer_id`` therefore invalidates ``has_preview`` — ``get_preview_url``
# resolves previews ONLY via Deezer (a ``deezer`` radar source, else
# ``catalog.deezer_id``), so a row left ``has_preview=True`` with NEITHER can never
# serve a preview: the frontend offers Play (gated on ``has_preview``) and it 404s.
# The DEEZER pass thus also resets ``has_preview=False`` — but ONLY for a row with
# no ``deezer`` radar source (a row that keeps one still serves a preview from its
# ``external_track_id`` and must stay True). The BEATPORT pass never touches it
# (Beatport never sets ``has_preview``). This closes the residual that shipped dead
# Play buttons on ~2.3k remixes after the first prod run (see git history).
_CLEAR_HAS_PREVIEW = {"deezer_id": True, "beatport_id": False}
# Groups per committed transaction in --apply mode (mirrors dedup_catalog).
_COMMIT_EVERY = 50
# Cut-off of the X3 matcher fix (lots A/B, 2026-07-22): any platform id whose
# ``*_searched_at`` is STRICTLY before this instant was stamped by the UNGUARDED
# matcher (Deezer hits[0] unchecked, Beatport EP-wide beatport_id) and is a
# --pre-x3 re-verification candidate. Aware UTC to compare against the
# TIMESTAMPTZ (UTC) ``*_searched_at`` columns; a naive comparison would be
# ambiguous. On SQLite (test harness) the tz is dropped in the stored string but
# the format is identical on both sides, so the ``<`` comparison still holds.
X3_FIX_DATE = datetime(2026, 7, 22, tzinfo=timezone.utc)

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _has_deezer_radar_source(session, catalog_id):
    """True if a ``deezer`` radar_tracks row backs this catalog id.

    ``get_preview_url`` can still resolve a preview from that source's
    ``external_track_id`` even after ``catalog.deezer_id`` is cleared, so such a
    row's ``has_preview`` must be left True (clearing it would hide a working Play
    button). Rows with no deezer radar source are the ones that 404.
    """
    from sqlalchemy import text

    return (
        session.execute(
            text(
                "SELECT 1 FROM radar_tracks "
                "WHERE catalog_id = :cid AND source = 'deezer' LIMIT 1"
            ),
            {"cid": catalog_id},
        ).first()
        is not None
    )


def _fold(s):
    """Lowercase + strip diacritics for accent-insensitive comparison.

    Mirrors ``workers.deezer_enrich._fold`` / ``beatport.client._fold`` so the
    divergence check folds names the same way the enrichment matcher does.
    """
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _artist_diverges(flat_artist, m2m_artist):
    """True when the flat ``catalog.artist`` FRANKLY diverges from the M2M artist.

    "Frank" divergence = non-containment after folding: neither folded name is a
    substring of the other. Containment (either way) is treated as agreement so a
    concatenated flat string ("Artist A, Artist B") still matches its first
    linked artist ("Artist A") and a "feat."-suffixed variant matches its base.

    A missing name on either side gives NO basis to claim a mismatch, so it
    returns False (the row stays out of the --only-divergent scope). This is a
    deliberately SIMPLE, conservative heuristic to bound churn — it errs toward
    NOT resetting when unsure (invariant #4: separation over a risky action).
    """
    if not flat_artist or not m2m_artist:
        return False
    a = _fold(flat_artist).strip()
    b = _fold(m2m_artist).strip()
    if not a or not b:
        return False
    return not (a in b or b in a)


def _first_m2m_artist_name(session, catalog_id):
    """Name of the FIRST linked artist (lowest ``catalog_artists.position``).

    ``position`` orders the credits; NULL positions sort last, then artist_id as
    a deterministic tie-break. Returns None when the row has NO artist link (the
    X4 volet-3 gap of ~29k rows) — such a row has no reference to diverge from, so
    the --only-divergent filter skips it.
    """
    return session.execute(
        select(Artist.name)
        .join(CatalogArtist, CatalogArtist.artist_id == Artist.id)
        .where(CatalogArtist.catalog_id == catalog_id)
        .order_by(
            CatalogArtist.position.asc().nulls_last(), CatalogArtist.artist_id.asc()
        )
        .limit(1)
    ).scalar_one_or_none()


def _reset_row(session, row, column, *, apply, conditional, clear_preview):
    """Reset ONE catalog row to a tier-1 E1 re-scan candidate for ``column``.

    The single source of truth for the reset SEMANTICS, shared by both the
    default (shared-ids) and the --pre-x3 modes so they can never diverge. In
    ``apply`` mode it mutates the row; in dry-run it mutates nothing but still
    counts what WOULD change. Returns ``(meta_cleared, preview_cleared)`` — the
    number of beatport-sourced bpm/key fields and stale has_preview flags this row
    contributes.

    Mutations (apply only):
      - ``column`` → NULL, ``*_searched_at`` → NULL, ``*_search_attempts`` → 0
        (tier-1 re-scan candidate for ``select_enrich_candidates``);
      - each conditional (value_col, source_col) pair nulled IFF ``source_col``
        proves the value came from THIS platform's suspect match — a bpm/key from
        rekordbox/deezer/unset is authoritative and NEVER touched (invariant #2);
      - ``has_preview`` → False IFF it is Deezer-derived (``clear_preview``) and no
        ``deezer`` radar source still backs the row (else the frontend keeps
        offering a Play that 404s).
    """
    searched_name, attempts_name = _SEARCH_STATE[column]
    meta_cleared = preview_cleared = 0

    # Null each metadata field only when its *_source proves it came from THIS
    # platform's suspect match — invariant #2 guards a rekordbox/deezer/unset value.
    for value_col, source_col, expected_source in conditional:
        if getattr(row, source_col) == expected_source:
            meta_cleared += 1
            if apply:
                setattr(row, value_col, None)
                setattr(row, source_col, None)
    # has_preview is Deezer-derived: reset it when the suspect deezer_id is cleared
    # AND no deezer radar source can still serve a preview, so the frontend stops
    # offering a Play that 404s (invariant restored).
    if clear_preview and row.has_preview and not _has_deezer_radar_source(
        session, row.id
    ):
        preview_cleared += 1
        if apply:
            row.has_preview = False
    if apply:
        setattr(row, column, None)
        setattr(row, searched_name, None)
        setattr(row, attempts_name, 0)
    return meta_cleared, preview_cleared


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

    On the BEATPORT column each suspect row ALSO has its bpm/key nulled when — and
    only when — the value is beatport-sourced (``_CONDITIONAL_METADATA``): a
    ``bpm_source``/``key_source`` still equal to "beatport" pins the wrong value at
    the ``enrich_from_beatport`` guard, so both value and source are cleared to let
    the re-scan re-derive them. A bpm/key from any other source is authoritative
    and NEVER touched (invariant #2).

    On the DEEZER column each suspect row ALSO has ``has_preview`` reset to False
    (``_CLEAR_HAS_PREVIEW``) — but only when no ``deezer`` radar source still backs
    it: ``has_preview`` is a Deezer-only signal and, once the id is cleared, an
    orphaned True makes the frontend offer a Play button that 404s. A row keeping a
    deezer radar source still serves a preview and is left True.

    apply=False (default) is read-only: nothing is committed and the returned
    counts describe what WOULD happen (``meta_cleared`` / ``preview_cleared``
    included). In --apply mode the work is committed every ``commit_every`` suspect
    groups (plus a trailing commit).

    Returns ``{"suspect_groups", "clean_groups", "suspect_rows", "reset",
    "meta_cleared", "preview_cleared", "examples"}`` where ``suspect_groups`` counts
    id-groups spanning distinct recordings, ``clean_groups`` counts true-duplicate
    groups left intact, ``meta_cleared`` counts individual beatport-sourced bpm/key
    fields cleared, ``preview_cleared`` counts stale has_preview flags reset (both,
    in dry-run, describe what WOULD happen), and ``examples`` is a list of
    ``(value, [(row_id, title), ...])`` per suspect group.
    """
    col = getattr(CatalogEntry, column)
    conditional = _CONDITIONAL_METADATA[column]
    clear_preview = _CLEAR_HAS_PREVIEW[column]
    dup_values = _duplicate_values(session, column)

    suspect_groups = clean_groups = suspect_rows = reset = meta_cleared = 0
    preview_cleared = 0
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

        for r in rows:
            # Count (dry-run included) and, in --apply, reset the row through the
            # shared semantics helper (id + search state + conditional bpm/key +
            # stale has_preview). reset stays apply-only by design (dry-run == 0).
            mc, pc = _reset_row(
                session,
                r,
                column,
                apply=apply,
                conditional=conditional,
                clear_preview=clear_preview,
            )
            meta_cleared += mc
            preview_cleared += pc
            if apply:
                reset += 1

        if apply:
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
        "meta_cleared": meta_cleared,
        "preview_cleared": preview_cleared,
        "examples": examples,
    }


def reverify_pre_x3_by_column(
    session,
    column,
    *,
    apply=False,
    only_divergent=False,
    limit=None,
    commit_every=_COMMIT_EVERY,
    max_examples=5,
):
    """Reset every row whose platform ``column`` id predates the X3 fix (--pre-x3).

    Unlike ``reverify_by_column`` (which only touches ids SHARED across distinct
    recordings), this bulk pass selects EVERY row that carries a non-NULL
    ``column`` AND whose ``*_searched_at`` is strictly before ``X3_FIX_DATE`` — the
    ids stamped by the UNGUARDED pre-X3 matcher, most of which are UNIQUE to their
    row and thus invisible to the shared-id pass. Each selected row is reset via
    the SAME ``_reset_row`` semantics (id + search state + conditional
    beatport-sourced bpm/key + stale has_preview), so the two modes never diverge.

    Scope bounds (an ops decision to cap the ~73k/~106k churn):
      - ``only_divergent`` restricts to rows whose flat ``catalog.artist`` FRANKLY
        diverges (``_artist_diverges``: fold + non-containment) from the row's
        first linked artist. A non-divergent row (or one with no linked artist) is
        counted in ``skipped_non_divergent`` and left intact.
      - ``limit`` caps the selection to the N OLDEST rows (by ``*_searched_at``),
        applied at the SQL level BEFORE the divergence filter — a first run can be
        validated on a small, oldest sample before the full drain.

    EDGE: a row with a non-NULL ``column`` but ``*_searched_at IS NULL`` (an id
    never stamped a search timestamp — legacy) is NOT in the measured pre-X3
    population, so it is NOT reset; it is only counted in ``stale_null_searched``
    and surfaced in the report for the operator to decide on.

    apply=False (default) is read-only: nothing is committed and the counts
    describe what WOULD happen. In --apply mode work is committed every
    ``commit_every`` reset rows (plus a trailing commit). Idempotent: a reset row's
    ``column`` is NULL, so it drops out of the selection on a re-run.

    Returns ``{"candidates", "matched", "skipped_non_divergent",
    "stale_null_searched", "reset", "meta_cleared", "preview_cleared",
    "examples"}`` where ``candidates`` counts selected pre-X3 rows, ``matched`` the
    subset actually reset (== candidates unless ``only_divergent``), and
    ``examples`` is a list of ``(row_id, artist, id_value)`` per reset row.
    """
    col = getattr(CatalogEntry, column)
    searched_name, _attempts_name = _SEARCH_STATE[column]
    searched_col = getattr(CatalogEntry, searched_name)
    conditional = _CONDITIONAL_METADATA[column]
    clear_preview = _CLEAR_HAS_PREVIEW[column]

    # EDGE tally: an id present but never search-stamped is outside the pre-X3
    # measurement — reported apart, never reset by default.
    stale_null_searched = session.execute(
        select(func.count())
        .select_from(CatalogEntry)
        .where(col.isnot(None), searched_col.is_(None))
    ).scalar_one()

    stmt = (
        select(CatalogEntry)
        .where(col.isnot(None), searched_col.isnot(None), searched_col < X3_FIX_DATE)
        .order_by(searched_col.asc(), CatalogEntry.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).scalars().all()

    candidates = matched = reset = meta_cleared = preview_cleared = 0
    skipped_non_divergent = 0
    examples = []
    pending = 0

    for r in rows:
        candidates += 1
        if only_divergent and not _artist_diverges(
            r.artist, _first_m2m_artist_name(session, r.id)
        ):
            skipped_non_divergent += 1
            continue

        matched += 1
        if len(examples) < max_examples:
            examples.append((r.id, r.artist, getattr(r, column)))

        mc, pc = _reset_row(
            session,
            r,
            column,
            apply=apply,
            conditional=conditional,
            clear_preview=clear_preview,
        )
        meta_cleared += mc
        preview_cleared += pc
        if apply:
            reset += 1
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "candidates": candidates,
        "matched": matched,
        "skipped_non_divergent": skipped_non_divergent,
        "stale_null_searched": stale_null_searched,
        "reset": reset,
        "meta_cleared": meta_cleared,
        "preview_cleared": preview_cleared,
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
    if stats["meta_cleared"]:
        meta_verb = "cleared" if apply else "would clear"
        print(
            f"    (+ {meta_verb} {stats['meta_cleared']} beatport-sourced bpm/key "
            f"field(s) so the re-scan re-derives them)"
        )
    if stats.get("preview_cleared"):
        prev_verb = "reset" if apply else "would reset"
        print(
            f"    (+ {prev_verb} {stats['preview_cleared']} stale has_preview flag(s) "
            f"to False — Deezer-derived, unresolvable once the id is cleared)"
        )
    for value, rows in stats["examples"]:
        titles = ", ".join(f"#{rid} {title!r}" for rid, title in rows)
        print(f"    {column}={value!r}: {titles}")


def _print_pre_x3_report(column, stats, apply, only_divergent):
    verb = "reset" if apply else "would reset"
    print(
        f"\n[{column}] {stats['candidates']} pre-X3 row(s) carrying an id searched "
        f"before {X3_FIX_DATE.date()}, {verb} {stats['matched']} row(s)."
    )
    if only_divergent:
        print(
            f"    (--only-divergent: skipped {stats['skipped_non_divergent']} "
            f"non-divergent / unlinked row(s))"
        )
    if stats["meta_cleared"]:
        meta_verb = "cleared" if apply else "would clear"
        print(
            f"    (+ {meta_verb} {stats['meta_cleared']} beatport-sourced bpm/key "
            f"field(s) so the re-scan re-derives them)"
        )
    if stats.get("preview_cleared"):
        prev_verb = "reset" if apply else "would reset"
        print(
            f"    (+ {prev_verb} {stats['preview_cleared']} stale has_preview flag(s) "
            f"to False — Deezer-derived, unresolvable once the id is cleared)"
        )
    if stats["stale_null_searched"]:
        print(
            f"    EDGE: {stats['stale_null_searched']} row(s) carry a {column} but "
            f"NO {column.replace('_id', '')}_searched_at (never stamped — legacy). "
            f"Outside the measured pre-X3 population → NOT reset. Decide separately."
        )
    for row_id, artist, id_value in stats["examples"]:
        print(f"    #{row_id} {column}={id_value!r} artist={artist!r}")


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
                    "job. The deezer pass resets the id and stale has_preview (a "
                    "Deezer-only signal, unresolvable once the id is cleared, unless "
                    "a deezer radar source still backs the row); the beatport pass "
                    "ALSO clears bpm/key when they are beatport-sourced "
                    "(bpm_source/key_source == 'beatport') so the re-scan re-derives "
                    "them — a rekordbox/deezer/unset bpm/key is authoritative and "
                    "left untouched (invariant #2). The OTHER metadata a wrong match "
                    "may have written (cover/duration/label/release_date) is still "
                    "left as-is (too risky to blank blind) and can survive until a "
                    "natural overwrite — an assumed residual."
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
                "enrich_catalog_beatport). The platform id + its search state were "
                "cleared on both passes; the beatport pass ALSO nulled beatport-"
                "sourced bpm/key and the deezer pass reset stale has_preview so the "
                "corrected match re-derives them. Other mis-derived non-id fields "
                "(cover/duration/label/release_date) may persist until a natural "
                "overwrite — the assumed X3.c residual."
            )
    finally:
        engine.dispose()


def main_pre_x3(apply, only_divergent=False, limit=None):
    """--pre-x3 bulk re-verification (see the module docstring for the rationale).

    Resets EVERY row carrying a platform id last searched before ``X3_FIX_DATE``
    (not only the shared-id groups), through the same ``_reset_row`` semantics.
    ``only_divergent`` / ``limit`` bound the churn; a searched_at-NULL id is an
    edge reported apart, never reset.
    """
    engine = _get_engine()
    try:
        with Session(engine) as session:
            print(f"Catalog rows: {_total_rows(session)}")
            scope = []
            if only_divergent:
                scope.append("only rows whose flat artist FRANKLY diverges from the "
                             "first linked artist")
            if limit is not None:
                scope.append(f"the {limit} oldest row(s) per column")
            scope_note = ("  [scope: " + "; ".join(scope) + "]") if scope else ""

            head = (
                "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
            )
            print(f"\n=== PRE-X3 MODE — {head} ==={scope_note}")
            for column in _REVERIFY_COLUMNS:
                stats = reverify_pre_x3_by_column(
                    session,
                    column,
                    apply=apply,
                    only_divergent=only_divergent,
                    limit=limit,
                )
                _print_pre_x3_report(column, stats, apply, only_divergent)

            if not apply:
                session.rollback()
                print(
                    "\nDry-run only. --pre-x3 resets EVERY id searched before the X3 "
                    "fix (2026-07-22), not only shared ids — the reset SEMANTICS are "
                    "identical to the default mode (id + search state; the beatport "
                    "pass ALSO clears beatport-sourced bpm/key, the deezer pass ALSO "
                    "resets stale has_preview; a rekordbox/deezer/unset bpm/key stays "
                    "untouched, invariant #2). A searched_at-NULL id is an edge (NOT "
                    "reset). Bound the churn with --only-divergent and/or --limit N "
                    "before the full drain."
                )
                print(
                    "Re-run with --pre-x3 --apply to clear them so the E1 re-scan "
                    "(now matcher-guarded) re-enriches them — DUMP PROD FIRST (see "
                    "docs/restore.md)."
                )
                return

            session.commit()
            print(
                "\nThe reset rows are now tier-1 E1 re-scan candidates and will be "
                "re-enriched on the next nightly run (enrich_catalog / "
                "enrich_catalog_beatport) with the corrected matcher. Other "
                "mis-derived non-id fields (cover/duration/label/release_date) may "
                "persist until a natural overwrite — the assumed X3.c residual. Re-run "
                "to drain the rest (idempotent) or drop --limit for the full sweep."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clear suspect platform ids so the E1 re-scan re-enriches them "
        "with the corrected matcher. DEFAULT: only ids SHARED across distinct "
        "recordings (true duplicates are left to dedup_catalog). --pre-x3: bulk "
        "re-verification of EVERY id searched before the X3 fix (2026-07-22)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually clear the suspect ids (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--pre-x3",
        dest="pre_x3",
        action="store_true",
        help="bulk mode: reset EVERY row whose platform id was searched before the "
        "X3 fix (2026-07-22), not only shared ids (see --only-divergent / --limit "
        "to bound the churn)",
    )
    parser.add_argument(
        "--only-divergent",
        dest="only_divergent",
        action="store_true",
        help="(--pre-x3 only) restrict to rows whose flat catalog.artist frankly "
        "diverges from the first linked artist (fold + non-containment)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="(--pre-x3 only) reset at most N rows per column, the oldest first "
        "(by *_searched_at) — sample a run before the full drain",
    )
    args = parser.parse_args()
    if args.pre_x3:
        main_pre_x3(
            apply=args.apply,
            only_divergent=args.only_divergent,
            limit=args.limit,
        )
    else:
        if args.only_divergent or args.limit is not None:
            parser.error("--only-divergent and --limit require --pre-x3")
        main(apply=args.apply)
