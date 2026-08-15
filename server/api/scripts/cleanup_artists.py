#!/usr/bin/env python
"""One-shot OPS cleanup: scrub noise + fold punctuation-variant duplicates in the ARTIST graph (lot L4).

The "artist string hygiene" chantier left two kinds of debt in the ``artists``
table, both only worth acting on for ATTACHED artists (a row with at least one
``catalog_artists`` OR ``set_artists`` link — an orphan artist row nobody points at
is harmless clutter and out of scope):

  1. NOISE — an artist whose name carries unambiguous junk: a trailing
     performing-rights-organisation suffix ("Ioannis Siopis (GEMA)") or a leading
     marketplace bullet ("Vinyl • Harvey Mason"). The whitelist-driven
     ``workers.artist_names.strip_artist_noise`` is the ONLY authority on what counts
     as noise (a Discogs "(4)", a "(Sofa Beats)" label, an "AC/DC" slash all pass
     through untouched).

  2. DUPES — several attached rows that are the SAME artist spelled with different
     punctuation ("St. Germain" / "St Germain", "Mr. Oizo" / "Mr Oizo"): the
     accent-SENSITIVE identity key ``artists.normalized_name`` keeps them apart, so
     the links scatter across duplicate rows. They are clustered by the
     punctuation-insensitive ``workers.artist_names.punct_fold_key``.

Two INDEPENDENT passes, selected by ``--noise`` / ``--dupes`` (BOTH run when neither
flag is given). Each is idempotent and dry-run by default.

NOISE pass — for every attached artist where ``strip_artist_noise(name) != name``:
  * ``clean = strip_artist_noise(name)``, resolved by ``normalize(clean)``.
  * if ANOTHER artist already carries ``normalize(clean)`` → fold the noisy row into
    that clean twin via ``workers.artist_merge.merge_artist_into`` (links + aliases
    reassigned, noisy row deleted).
  * else → rename the noisy row in place (``name`` / ``normalized_name`` ← clean). If
    the rename would collide on the UNIQUE ``normalized_name`` (a twin appeared —
    e.g. two noisy rows cleaning to the same name in one run), merge instead.
  * ALWAYS rewrite the flat ``catalog.artist`` of every catalog row whose flat string
    == the noisy name (→ clean). Additive; nothing else is touched.

DUPES pass — cluster attached artists by ``punct_fold_key(name)`` (non-empty key);
for each cluster of >= 2 distinct rows the decision is PURE (``decide_cluster``):
  * SAFE, auto-merged: EXACTLY one Deezer-linked row (``deezer_id`` set and
    ``<> 'NOT_FOUND'``) + one/more ``deezer_id``-NULL rows and NOTHING else, and NO
    row is ``looks_acronym`` → the NULL rows are unlinked twins → fold them into the
    linked canonical.
  * EVERYTHING else → FLAG only, no action: 0 linked rows, >= 2 linked rows with
    distinct ids, or any ``looks_acronym`` member (an "N.E.R.D." folds to a short
    letter run that could collide with an unrelated word). Merge asymmetry
    (invariant #4): a missed dup is cheap, a bad merge is corruption — never guess.

    STRETCH (pure, NOT wired to the network here by design): ``decide_cluster``
    accepts an optional ``fans`` map so a >= 2-linked cluster CAN be auto-merged into
    the confidently most-fanned row (``dominant_by_fans``). The orchestration passes
    no fan data — resolving fan counts means a live Deezer round-trip per row, which
    a fully offline, dry-runnable cleanup deliberately avoids — so in practice every
    >= 2-linked cluster is flagged for a human call.

>>> DESTRUCTIVE (renames / deletes artist rows, rewrites catalog.artist). DUMP PROD
    FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
operation is idempotent — a re-run finds the still-dirty rows), but a bad dump is
not recoverable.

The run is DRY-RUN by default and READ-ONLY: it prints per-pass counters (noise:
renamed / merged / flat_updated; dupes: merged / link_recovered / flagged), a few
examples and the full flag list, WITHOUT writing anything. Pass --apply to act. A
second --apply run is idempotent (cleaned rows leave the selection; flagged clusters
are never mutated).

Usage (from the VPS):
    docker compose exec api python scripts/cleanup_artists.py             # dry-run, both passes
    docker compose exec api python scripts/cleanup_artists.py --noise     # dry-run, noise only
    docker compose exec api python scripts/cleanup_artists.py --apply      # act on both passes
"""

import argparse
import os
import sys
from collections import defaultdict, namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Artist, CatalogArtist, CatalogEntry, SetArtist
from sqlalchemy import create_engine, exists, func, or_, select, update
from sqlalchemy.orm import Session
from utils import normalize

# FK-safe merge primitive (reused verbatim: reassigns catalog_artists / set_artists
# links + aliases, keeps the source spelling as an alias, deletes the source; the
# caller owns the transaction — it never commits).
from workers.artist_merge import merge_artist_into

# Pure name-hygiene helpers shipped by lot L1 (no I/O, no session).
from workers.artist_names import (
    dominant_by_fans,
    looks_acronym,
    punct_fold_key,
    strip_artist_noise,
)

# Deezer sentinel for "confirmed absent": such a row is neither Deezer-linked nor a
# NULL orphan, so it never anchors a merge and its presence makes a cluster mixed.
_NOT_FOUND = "NOT_FOUND"

# Rows/clusters per committed transaction in --apply mode (mirrors the sibling
# scripts' batching).
_COMMIT_EVERY = 500
# How many worked examples to keep per bucket for the report.
_MAX_EXAMPLES = 5
# How many flagged clusters to print in full (the rest are summarised as a count).
_MAX_FLAGS_PRINTED = 50

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


# A lightweight attached-artist row (no ORM identity-map bloat across per-batch
# commits). ``deezer_id`` is the raw column value (None / a real id / 'NOT_FOUND').
Member = namedtuple("Member", ["id", "name", "deezer_id"])

# The outcome of examining one dupe cluster. ``action`` is "merge" or "flag";
# ``source_ids`` are the rows folded into ``canonical_id`` (empty on a flag).
ClusterDecision = namedtuple(
    "ClusterDecision",
    ["action", "canonical_id", "source_ids", "reason", "key", "names"],
)


# ── pure decision logic (network- and DB-free, importable, unit-tested) ───────


def decide_cluster(members, key, *, fans=None):
    """Decide what to do with one punct-fold cluster of >= 2 attached artist rows.

    Pure: ``members`` is an iterable of :data:`Member` (or anything exposing
    ``.id`` / ``.name`` / ``.deezer_id``). Returns a :data:`ClusterDecision`.

    Rules (err toward separation, invariant #4):

      * ANY member ``looks_acronym`` → FLAG ("acronym"): a dotted/spaced initialism
        folds to a short letter run that could spuriously match an unrelated word.
      * EXACTLY one Deezer-linked row + one/more ``deezer_id``-NULL rows and NOTHING
        else → MERGE the NULLs into the linked canonical ("one_linked_nulls"): the
        NULL rows are unlinked twins the unique index kept from taking the same id.
      * 0 linked rows → FLAG ("no_linked"): no anchor to pick a canonical.
      * >= 2 linked rows → FLAG ("multi_linked") UNLESS ``fans`` is supplied AND one
        row confidently dominates (``dominant_by_fans``), in which case MERGE the
        rest into it ("fan_dominant"). The orchestration never supplies ``fans`` (a
        fully offline cleanup avoids the live Deezer round-trip), so this branch is
        the documented, test-covered STRETCH extension, not prod behaviour.
      * exactly one linked but a ``NOT_FOUND`` (or other non-NULL) row is mixed in →
        FLAG ("one_linked_mixed").
    """
    members = list(members)
    names = [m.name for m in members]
    if any(looks_acronym(m.name or "") for m in members):
        return ClusterDecision("flag", None, [], "acronym", key, names)

    linked = [m for m in members if m.deezer_id and m.deezer_id != _NOT_FOUND]
    nulls = [m for m in members if m.deezer_id is None]

    # SAFE case: one linked canonical + only NULL twins (no second linked row, no
    # NOT_FOUND sentinel) → fold the twins in.
    if len(linked) == 1 and nulls and len(linked) + len(nulls) == len(members):
        return ClusterDecision(
            "merge", linked[0].id, [m.id for m in nulls], "one_linked_nulls", key, names
        )

    if not linked:
        return ClusterDecision("flag", None, [], "no_linked", key, names)

    if len(linked) >= 2:
        # STRETCH (fans supplied only in tests): auto-merge into the dominant row.
        if fans is not None:
            ranked = sorted(
                linked, key=lambda m: fans.get(m.deezer_id, 0), reverse=True
            )
            if dominant_by_fans(
                fans.get(ranked[0].deezer_id, 0), fans.get(ranked[1].deezer_id, 0)
            ):
                sources = [m.id for m in members if m.id != ranked[0].id]
                return ClusterDecision(
                    "merge", ranked[0].id, sources, "fan_dominant", key, names
                )
        return ClusterDecision("flag", None, [], "multi_linked", key, names)

    # Exactly one linked, but the rest are not all NULL (a NOT_FOUND is mixed in).
    return ClusterDecision("flag", None, [], "one_linked_mixed", key, names)


# ── engine helpers ────────────────────────────────────────────────────────────


def _select_attached_artists(session):
    """Every artist with >= 1 ``catalog_artists`` OR ``set_artists`` link.

    Returned as a materialised list of :data:`Member` (id, name, deezer_id), ordered
    by id — a stable snapshot the loops iterate while the DB is mutated underneath
    (each merge deletes a source row; the snapshot itself is untouched).
    """
    cat_link = exists().where(CatalogArtist.artist_id == Artist.id)
    set_link = exists().where(SetArtist.artist_id == Artist.id)
    rows = session.execute(
        select(Artist.id, Artist.name, Artist.deezer_id)
        .where(or_(cat_link, set_link))
        .order_by(Artist.id)
    ).all()
    return [Member(r.id, r.name, r.deezer_id) for r in rows]


def _find_artist_by_norm(session, norm, *, exclude_id):
    """The (single) OTHER artist holding ``normalized_name == norm``, or None.

    ``normalized_name`` is UNIQUE, so this is at most one row. A live query — in
    --apply it sees rows renamed earlier in this run (they are flushed), which is how
    an intra-run collision resolves to a merge instead of a duplicate.
    """
    return (
        session.execute(
            select(Artist).where(
                Artist.normalized_name == norm, Artist.id != exclude_id
            )
        )
        .scalars()
        .first()
    )


def _count_flat_rows(session, name):
    """Read-only count of catalog rows whose flat ``artist`` exactly equals ``name``."""
    return session.execute(
        select(func.count())
        .select_from(CatalogEntry)
        .where(CatalogEntry.artist == name)
    ).scalar_one()


def _apply_flat_rename(session, old_name, new_name):
    """Rewrite the flat ``catalog.artist`` from ``old_name`` to ``new_name``.

    Exact-string match (bulk UPDATE, ``synchronize_session=False`` — the rows are
    not read back in this unit of work). Returns the number of rows rewritten.
    """
    result = session.execute(
        update(CatalogEntry)
        .where(CatalogEntry.artist == old_name)
        .values(artist=new_name)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def _rename_artist(session, artist_id, clean, clean_norm):
    """Rename an artist in place and flush (so a later holder query sees it)."""
    artist = session.get(Artist, artist_id)
    artist.name = clean
    artist.normalized_name = clean_norm
    session.flush()


# ── passes ────────────────────────────────────────────────────────────────────


def run_noise_pass(
    session, *, apply=False, commit_every=_COMMIT_EVERY, max_examples=_MAX_EXAMPLES
):
    """Scrub PRO-suffix / marketplace-bullet noise from attached artist names.

    For each attached artist whose ``strip_artist_noise(name)`` differs from its
    name, the noisy row is folded into a pre-existing clean twin (if one holds
    ``normalize(clean)``) or renamed in place, and every catalog row whose flat
    ``artist`` equals the noisy name has its flat rewritten to ``clean``.

    In dry-run nothing is written: the merge-vs-rename choice and the flat count come
    from read-only queries, and an intra-run collision (two noisy rows cleaning to
    the same name) is tracked in ``would_rename_norms`` so the dry-run counts match
    what --apply would do. Returns ``{"renamed", "merged", "flat_updated",
    "rename_examples", "merge_examples"}``.
    """
    renamed = merged = flat_updated = 0
    rename_examples = []
    merge_examples = []
    would_rename_norms = set()
    pending = 0

    for member in _select_attached_artists(session):
        name = member.name or ""
        clean = strip_artist_noise(name)
        if clean == name:
            continue
        clean_norm = normalize(clean)

        holder = _find_artist_by_norm(session, clean_norm, exclude_id=member.id)
        # In dry-run a name already slated to rename to clean_norm acts as a holder
        # for the next one (mirrors --apply, where the first rename is flushed and
        # found by the holder query) — keeps dry-run counts equal to --apply.
        collides = holder is not None or (not apply and clean_norm in would_rename_norms)

        # Flat rewrite is unconditional (additive); counted read-only in dry-run.
        if apply:
            flat_updated += _apply_flat_rename(session, name, clean)
        else:
            flat_updated += _count_flat_rows(session, name)

        if collides:
            merged += 1
            if len(merge_examples) < max_examples:
                merge_examples.append((name, clean))
            if apply:
                merge_artist_into(session, member.id, holder.id)
        else:
            renamed += 1
            if len(rename_examples) < max_examples:
                rename_examples.append((name, clean))
            if apply:
                _rename_artist(session, member.id, clean, clean_norm)
            else:
                would_rename_norms.add(clean_norm)

        if apply:
            pending += 1
            if pending >= commit_every:
                session.commit()
                pending = 0

    if apply and pending:
        session.commit()

    return {
        "renamed": renamed,
        "merged": merged,
        "flat_updated": flat_updated,
        "rename_examples": rename_examples,
        "merge_examples": merge_examples,
    }


def run_dupes_pass(
    session,
    *,
    apply=False,
    commit_every=_COMMIT_EVERY,
    max_examples=_MAX_EXAMPLES,
    fans_lookup=None,
):
    """Fold punctuation-variant duplicate artists into their linked canonical.

    Attached artists are clustered by ``punct_fold_key(name)`` (empty keys skipped —
    a fully non-Latin name folds to "" and must not match every other one). Each
    cluster of >= 2 rows is decided by :func:`decide_cluster`; a "merge" folds the
    source rows into the canonical, a "flag" is recorded untouched.

    ``fans_lookup`` (default None) is forwarded to ``decide_cluster`` — see the
    STRETCH note there; the CLI never supplies it, so >= 2-linked clusters flag.
    Returns ``{"merged", "link_recovered", "flagged", "merge_examples", "flags"}``
    where ``merged`` counts folded source rows and ``link_recovered`` counts the
    clusters auto-merged (canonicals that recovered links).
    """
    clusters = defaultdict(list)
    for member in _select_attached_artists(session):
        key = punct_fold_key(member.name or "")
        if key:
            clusters[key].append(member)

    merged = link_recovered = flagged = 0
    merge_examples = []
    flags = []
    pending = 0

    for key, group in clusters.items():
        if len(group) < 2:
            continue
        decision = decide_cluster(group, key, fans=fans_lookup)
        if decision.action == "merge":
            link_recovered += 1
            merged += len(decision.source_ids)
            if len(merge_examples) < max_examples:
                merge_examples.append(decision)
            if apply:
                for source_id in decision.source_ids:
                    merge_artist_into(session, source_id, decision.canonical_id)
                pending += 1
                if pending >= commit_every:
                    session.commit()
                    pending = 0
        else:
            flagged += 1
            flags.append(decision)

    if apply and pending:
        session.commit()

    return {
        "merged": merged,
        "link_recovered": link_recovered,
        "flagged": flagged,
        "merge_examples": merge_examples,
        "flags": flags,
    }


# ── report ────────────────────────────────────────────────────────────────────


def _print_noise_report(stats, apply):
    rename_verb = "renamed" if apply else "would rename"
    merge_verb = "merged" if apply else "would merge"
    flat_verb = "rewrote" if apply else "would rewrite"
    print("\n── NOISE pass (PRO suffix / marketplace bullet) ──")
    print(f"    {rename_verb} in place:                 {stats['renamed']}")
    print(f"    {merge_verb} into existing clean twin:  {stats['merged']}")
    print(f"    flat catalog.artist {flat_verb}:        {stats['flat_updated']}")
    for old, clean in stats["rename_examples"]:
        print(f"    rename  {old!r} -> {clean!r}")
    for old, clean in stats["merge_examples"]:
        print(f"    merge   {old!r} -> existing {clean!r}")


def _print_dupes_report(stats, apply, max_flags=_MAX_FLAGS_PRINTED):
    merge_verb = "merged" if apply else "would merge"
    print("\n── DUPES pass (punctuation-fold clusters) ──")
    print(f"    {merge_verb} source rows into a canonical: {stats['merged']}")
    print(f"    clusters auto-merged (links recovered):    {stats['link_recovered']}")
    print(f"    clusters flagged for review (no action):   {stats['flagged']}")
    for d in stats["merge_examples"]:
        print(f"    merge   {d.key!r}: {d.names} -> canonical #{d.canonical_id}")
    if stats["flags"]:
        print(f"    flags ({len(stats['flags'])}, needing a human call):")
        for d in stats["flags"][:max_flags]:
            print(f"        [{d.reason}] {d.key!r}: {d.names}")
        if len(stats["flags"]) > max_flags:
            print(f"        ... and {len(stats['flags']) - max_flags} more")


def main(apply, do_noise, do_dupes):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total = session.execute(
                select(func.count()).select_from(Artist)
            ).scalar_one()
            print(f"Artists: {total}")
            mode = (
                "APPLY — writing changes"
                if apply
                else "DRY-RUN — nothing will be written (use --apply)"
            )
            print(f"\n=== {mode} ===")

            if do_noise:
                _print_noise_report(run_noise_pass(session, apply=apply), apply)
            if do_dupes:
                _print_dupes_report(run_dupes_pass(session, apply=apply), apply)

            if not apply:
                session.rollback()  # read-only anyway; belt-and-braces
                print(
                    "\nDry-run only. Re-run with --apply to act — DUMP PROD FIRST "
                    "(see docs/restore.md). Flagged dupe clusters are NEVER "
                    "auto-merged (invariant #4 — err toward separation)."
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrub noise + fold punctuation-variant duplicates in the artist "
        "graph (dry-run by default; flagged dupe clusters are never auto-merged)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the changes (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--noise",
        action="store_true",
        help="run ONLY the noise pass (default: both passes)",
    )
    parser.add_argument(
        "--dupes",
        action="store_true",
        help="run ONLY the dupes pass (default: both passes)",
    )
    args = parser.parse_args()
    run_both = not (args.noise or args.dupes)
    main(
        apply=args.apply,
        do_noise=args.noise or run_both,
        do_dupes=args.dupes or run_both,
    )
