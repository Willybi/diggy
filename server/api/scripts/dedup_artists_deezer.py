#!/usr/bin/env python
"""One-shot cleanup: merge accent/Unicode-variant ARTIST duplicates onto their Deezer twin.

``artists.normalized_name`` (the identity key, UNIQUE) is accent-SENSITIVE
(``utils.normalize`` only lowercases / trims / folds a couple of quote+feat forms),
while the Deezer matcher folds accents (NFKD + ASCII,
``workers.tasks.artists._norm_artist_name``). So two spellings of ONE artist that
differ only by an accent or Unicode form ("Nick León" / "Nick Leon", an NFD vs NFC
"Zoë") land as TWO ``artists`` rows: the first searched links the Deezer id, and
its twin is then blocked FOREVER by the partial-unique index ``uq_artists_deezer_id``
(it can never take the same id). In prod ~205 of the ~965 ``deezer_id IS NULL``
artists are such orphans.

This script finds each orphan (``deezer_id IS NULL``) whose accent-folded name
matches EXACTLY ONE linked holder (``deezer_id`` set, ``<> 'NOT_FOUND'``) and folds
the orphan INTO that holder via ``workers.artist_merge.merge_artist_into`` (which
reassigns every ``set_artists`` / ``catalog_artists`` link, moves the aliases and
keeps the orphan spelling as an alias before deleting the orphan row). The linked
holder survives; the orphan disappears. A fold that matches 0 or 2+ holders is
AMBIGUOUS and left untouched (reported separately) — merge asymmetry (invariant
#4): a missed dup is cheap, a bad merge is corruption.

Deezer confirmation (ON by default, ``--no-verify`` to skip): before merging, the
orphan name is searched on Deezer and the first hit whose folded name equals the
orphan's fold MUST carry the holder's ``deezer_id``. This guards against two
locally-similar-but-actually-distinct artists (the fold is lossy). ``--no-verify``
trusts the offline fold alone (faster, no network) — only for a hand-reviewed run.

After each merge the survivor's ``normalized_name`` is canonicalised to NFC (safe:
the orphan is already deleted, so no unique collision remains) so a future NFC-form
import dedups against it instead of creating yet another twin.

>>> DESTRUCTIVE (deletes the orphan rows). DUMP PROD FIRST. <<<
Take a fresh encrypted PG dump and keep ``docs/restore.md`` within reach BEFORE
running with --apply. A crash mid-run is safe (each batch is committed and the
operation is idempotent — a re-run finds the remaining orphans), but a bad dump is
not recoverable.

The run is DRY-RUN by default: it prints the full table of candidate pairs
(orphan → holder, Deezer id), the counters (candidates / confirmed / ambiguous /
unconfirmed) and modifies NOTHING. Pass --apply to merge the confirmed pairs. A
second --apply run is idempotent (the merged orphans are gone → 0 candidates).

Usage (from the VPS):
    docker compose exec api python scripts/dedup_artists_deezer.py             # dry-run + verify
    docker compose exec api python scripts/dedup_artists_deezer.py --no-verify # dry-run, offline
    docker compose exec api python scripts/dedup_artists_deezer.py --apply     # merge confirmed
"""

import argparse
import os
import sys
import time
import unicodedata
from collections import defaultdict, namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

import requests
from models import Artist
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from workers.artist_merge import merge_artist_into

# Reuse the EXACT accent-folding used by the Deezer link matcher so pairing and
# confirmation agree with how the twin was matched in the first place — never a
# second, divergent fold.
from workers.tasks.artists import _norm_artist_name

# Deezer sentinel for "confirmed absent" — such a row is neither an orphan
# (deezer_id is NOT NULL) nor a holder, and is left entirely alone.
_NOT_FOUND = "NOT_FOUND"
DEEZER_SEARCH = "https://api.deezer.com/search/artist"
# Seconds between Deezer calls (mirrors populate_artists.RATE_LIMIT) + request
# timeout. Deezer's public search is rate-limited; a one-shot over ~200 orphans
# at this cadence stays well within the window.
_RATE_LIMIT = 0.12
_TIMEOUT = 8
# Pairs per committed transaction in --apply mode (mirrors dedup_catalog).
_COMMIT_EVERY = 50

# A vetted orphan→holder pair. ``orphan_fold`` is carried so the Deezer
# confirmation reuses the exact fold that paired them (no recompute).
Candidate = namedtuple(
    "Candidate",
    ["orphan_id", "orphan_name", "orphan_fold", "holder_id", "holder_deezer_id"],
)
# An orphan whose fold matched 0 or 2+ holders — reported, never merged.
Ambiguous = namedtuple("Ambiguous", ["orphan_id", "orphan_name", "holder_ids"])

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def find_candidate_pairs(artists):
    """Split ``artists`` into orphan→holder candidates and ambiguous orphans.

    Pure (no I/O): ``artists`` is any iterable of rows exposing ``.id``, ``.name``
    and ``.deezer_id``. Holders (``deezer_id`` set and ``<> 'NOT_FOUND'``) are
    grouped by their accent-folded name; each orphan (``deezer_id`` NULL) is folded
    the same way and:

      - fold matches EXACTLY ONE holder  → a ``Candidate`` (safe to merge, pending
        the optional Deezer confirmation);
      - fold matches 0 holders           → ignored (no twin to merge into);
      - fold matches 2+ distinct holders → an ``Ambiguous`` (cannot tell which is
        the real twin offline → never merged).

    Returns ``(candidates, ambiguous)`` — two lists of the named tuples above.
    ``_norm_artist_name`` folds a NULL/empty name to ``""``; such rows never pair
    (an empty fold is skipped on both sides).
    """
    holders_by_fold = defaultdict(list)
    orphans = []
    for a in artists:
        deezer_id = a.deezer_id
        if deezer_id is None:
            orphans.append(a)
        elif deezer_id != _NOT_FOUND:
            fold = _norm_artist_name(a.name or "")
            if fold:
                holders_by_fold[fold].append((a.id, deezer_id))

    candidates = []
    ambiguous = []
    for orphan in orphans:
        fold = _norm_artist_name(orphan.name or "")
        if not fold:
            continue
        holders = holders_by_fold.get(fold, [])
        if len(holders) == 1:
            holder_id, holder_deezer_id = holders[0]
            candidates.append(
                Candidate(
                    orphan.id, orphan.name, fold, holder_id, holder_deezer_id
                )
            )
        elif len(holders) >= 2:
            ambiguous.append(
                Ambiguous(orphan.id, orphan.name, [h[0] for h in holders])
            )
        # 0 holders → no twin, nothing to do
    return candidates, ambiguous


def _deezer_confirms(candidate):
    """True if Deezer's own search backs the orphan→holder pairing.

    Searches the orphan name on Deezer; the FIRST hit whose folded name equals the
    orphan's fold must carry ``candidate.holder_deezer_id``. Any mismatch — a
    different id, no folding hit, or a network/parse failure — returns False so the
    pair is NOT merged (better a missed merge than a wrong one, invariant #4).
    """
    try:
        resp = requests.get(
            DEEZER_SEARCH,
            params={"q": candidate.orphan_name, "limit": 10},
            timeout=_TIMEOUT,
        )
        hits = resp.json().get("data", [])
    except Exception:
        return False
    for hit in hits:
        if _norm_artist_name(hit.get("name") or "") == candidate.orphan_fold:
            return str(hit.get("id")) == str(candidate.holder_deezer_id)
    return False


def _load_artists(session):
    """All artists as lightweight rows (id, name, deezer_id) for the detection."""
    return session.execute(
        select(Artist.id, Artist.name, Artist.deezer_id)
    ).all()


def _counts(session):
    total = session.execute(select(func.count()).select_from(Artist)).scalar_one()
    orphans = session.execute(
        select(func.count()).select_from(Artist).where(Artist.deezer_id.is_(None))
    ).scalar_one()
    return total, orphans


def _partition_confirmed(candidates, verify):
    """Return (confirmed, unconfirmed): with verify, hit Deezer per candidate.

    ``--no-verify`` trusts the offline fold and confirms every candidate. With
    verification each candidate is checked against Deezer at ``_RATE_LIMIT`` cadence
    (a live outage/mismatch drops it to ``unconfirmed`` — reported, never merged).
    """
    if not verify:
        return list(candidates), []
    confirmed, unconfirmed = [], []
    for cand in candidates:
        time.sleep(_RATE_LIMIT)
        (confirmed if _deezer_confirms(cand) else unconfirmed).append(cand)
    return confirmed, unconfirmed


def _print_pairs(title, pairs):
    print(f"\n{title}: {len(pairs)}")
    for c in pairs:
        print(
            f"    #{c.orphan_id} {c.orphan_name!r} -> #{c.holder_id} "
            f"(deezer_id {c.holder_deezer_id})"
        )


def _print_ambiguous(ambiguous):
    print(f"\nAmbiguous (fold matches 2+ holders, left intact): {len(ambiguous)}")
    for a in ambiguous:
        print(f"    #{a.orphan_id} {a.orphan_name!r} -> holders {a.holder_ids}")


def _apply_merges(session, confirmed, commit_every=_COMMIT_EVERY):
    """Merge every confirmed orphan into its holder, committing per batch.

    After each merge the survivor's ``normalized_name`` is canonicalised to NFC —
    safe because the orphan (the only row that could have shared the folded key) is
    already deleted, so no UNIQUE collision remains. Returns the number merged.
    """
    merged = pending = 0
    for c in confirmed:
        merge_artist_into(session, c.orphan_id, c.holder_id)
        holder = session.get(Artist, c.holder_id)
        holder.normalized_name = unicodedata.normalize("NFC", holder.normalized_name)
        merged += 1
        pending += 1
        if pending >= commit_every:
            session.commit()
            pending = 0
    if pending:
        session.commit()
    return merged


def main(apply, verify):
    engine = _get_engine()
    try:
        with Session(engine) as session:
            total, orphan_count = _counts(session)
            print(f"Artists: {total} total, {orphan_count} with deezer_id NULL")

            candidates, ambiguous = find_candidate_pairs(_load_artists(session))
            if verify and candidates:
                print(
                    f"\nVerifying {len(candidates)} candidate(s) against Deezer "
                    f"(~{len(candidates) * _RATE_LIMIT:.0f}s)..."
                )
            confirmed, unconfirmed = _partition_confirmed(candidates, verify)

            verb = "verified" if verify else "trusted offline (no verify)"
            print(
                f"\nCandidates: {len(candidates)} "
                f"({len(confirmed)} confirmed [{verb}], "
                f"{len(unconfirmed)} unconfirmed, {len(ambiguous)} ambiguous)"
            )
            _print_pairs("Confirmed pairs (orphan -> holder)", confirmed)
            if unconfirmed:
                _print_pairs("Unconfirmed pairs (NOT merged)", unconfirmed)
            if ambiguous:
                _print_ambiguous(ambiguous)

            if not apply:
                session.rollback()
                print("\n=== DRY-RUN — nothing was modified (use --apply) ===")
                print(
                    "Only the CONFIRMED pairs above would be merged: each orphan "
                    "is folded into its linked twin via merge_artist_into (links + "
                    "aliases reassigned, orphan deleted) and the survivor's "
                    "normalized_name is canonicalised to NFC. Ambiguous orphans "
                    "(fold matches 2+ holders) and unconfirmed pairs are left "
                    "untouched — merge asymmetry (invariant #4)."
                )
                print(
                    "Re-run with --apply to merge — DUMP PROD FIRST (see "
                    "docs/restore.md)."
                )
                return

            print("\n=== APPLY — merging confirmed pairs ===")
            merged = _apply_merges(session, confirmed)
            total_after, orphan_after = _counts(session)
            print(
                f"\nMerged {merged} orphan(s) into their twin. Artists: "
                f"{total_after} total (removed {total - total_after}), "
                f"{orphan_after} with deezer_id NULL."
            )
            print(
                "Ambiguous / unconfirmed orphans were left as-is. A re-run finds 0 "
                "confirmed candidates (the merged orphans are gone)."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge accent/Unicode-variant artist duplicates into their "
        "linked Deezer twin (ambiguous / Deezer-unconfirmed pairs are left intact)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually merge the confirmed pairs (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        help="skip the Deezer confirmation and trust the offline fold alone "
        "(faster, no network — only for a hand-reviewed run)",
    )
    args = parser.parse_args()
    main(apply=args.apply, verify=args.verify)
