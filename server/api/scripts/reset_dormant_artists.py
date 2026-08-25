#!/usr/bin/env python
"""One-shot OPS: re-arm the Deezer link search for DORMANT abandoned artists.

A "dormant" artist is an UNLINKED row (``deezer_id IS NULL``) still ATTACHED to at
least one ``catalog_artists`` / ``set_artists`` link, that ``link_artists_deezer``
already ABANDONED after ``deezer_search_attempts >= MAX`` (3) no-match tries. Such a
row is hidden from the admin "Lier" panel and only re-searched by the worker's slow
long-term resurrection sweep (~every 180 days).

Some of them were abandoned for a reason the artist-hygiene chantiers just FIXED —
the search used to fail on a form the current matcher now handles:

  * ``suffix-n``  — a trailing Discogs disambiguator ("Praxis (2)", "Lazarus (32)").
    ``_link_artist_deezer`` used to query the literal "(2)"; since the strip-(N) fix
    it queries the bare name AND only auto-links when the bare name resolves to a
    SINGLE distinct Deezer artist (homonym guard — an ambiguous "Voices" stays
    dormant, on purpose).
  * ``punct``     — a name carrying a dot ("R.Kelly" vs "R. Kelly"): the punctuation
    fold now matches these.
  * ``non-ascii`` — a transliterable name ("Altın Gün" vs "Altin Gün"): the
    transliteration fold now matches these. NB many non-ASCII rows are genuinely
    absent from Deezer (Cyrillic/CJK) and will simply re-abandon — noisier subset.

This script RE-ARMS the chosen subset: it sets ``deezer_searched_at = NULL`` and
``deezer_search_attempts = 0`` so the rows re-enter TIER 1 of ``link_artists_deezer``
(never-searched, top priority), which then re-searches them with the current matcher.
A row that still does not match is re-abandoned cleanly (30/90/180-day E1 backoff);
the homonym guard means an ambiguous bare name is never mis-linked (invariant #4).

It links NOTHING itself — it only re-arms the search state. The actual linking is done
by the nightly ``link_artists_deezer`` (budget 1500/run) or a manual trigger.

Placeholder rows ("Various Artists (3)") are EXCLUDED: their bare form is a
placeholder (``is_placeholder_artist``) that must never become a Deezer link.

>>> WRITES to ``artists`` (resets two columns). DUMP PROD FIRST. <<<
A big reset re-eligibilises a large batch at once → extra enrich load + autovacuum
churn (the post-X4 CPU-throttle pitfall). Run it STAGED: ``--suffix-n`` first (the
cleanest subset), measure ``link_artists_deezer``'s ``linked`` count, then widen.

DRY-RUN by default (READ-ONLY: prints counters + samples, writes nothing). ``--apply``
to act. Idempotent: a reset row has ``attempts = 0`` so it leaves the selection — a
second run finds fewer.

Usage (from the VPS):
    docker compose exec api python scripts/reset_dormant_artists.py --suffix-n
    docker compose exec api python scripts/reset_dormant_artists.py --suffix-n --apply
    docker compose exec api python scripts/reset_dormant_artists.py --punct --non-ascii --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Artist, CatalogArtist, SetArtist
from sqlalchemy import create_engine, or_, select, update
from sqlalchemy.orm import Session
from workers.artist_names import is_placeholder_artist, strip_disambiguation_number

# Mirror workers.tasks.artists.ARTIST_MAX_SEARCH_ATTEMPTS (the E1 abandonment
# threshold) and the API panel's dormant definition (artist_service.list_artists).
_MAX_SEARCH_ATTEMPTS = 3
_COMMIT_EVERY = 500
_MAX_EXAMPLES = 15

# POSIX-regex subsets (PostgreSQL `~`). Each targets a form the current matcher now
# handles but the old one abandoned. Kept in parity with the sizing query.
SUBSETS = {
    "suffix-n": r"\([0-9]+\)\s*$",  # trailing Discogs "(N)"
    "punct": r"[.]",  # carries a dot (R.Kelly)
    "non-ascii": r"[^\x00-\x7F]",  # transliterable non-ASCII
}

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors workers/db.py: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _attached():
    """An artist row with at least one catalog OR set link (dead orphans excluded)."""
    return or_(
        select(CatalogArtist.artist_id)
        .where(CatalogArtist.artist_id == Artist.id)
        .exists(),
        select(SetArtist.artist_id).where(SetArtist.artist_id == Artist.id).exists(),
    )


def _select_candidates(session, patterns, limit):
    """Abandoned, attached, unlinked artists.

    ``patterns`` is a list of POSIX-regex strings the name must match ANY of, or
    None (``--all``) to take EVERY abandoned-attached-unlinked row regardless of
    form. Placeholder exclusion is applied downstream by the caller.
    """
    conds = [
        Artist.deezer_id.is_(None),
        Artist.deezer_search_attempts >= _MAX_SEARCH_ATTEMPTS,
        _attached(),
    ]
    if patterns is not None:
        conds.append(or_(*[Artist.name.op("~")(p) for p in patterns]))
    stmt = select(Artist.id, Artist.name).where(*conds).order_by(Artist.id.asc())
    if limit:
        stmt = stmt.limit(limit)
    return session.execute(stmt).all()


def _is_placeholder(name):
    """A row whose bare (strip-(N)) form is a placeholder must never be re-armed."""
    return is_placeholder_artist(strip_disambiguation_number(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suffix-n", action="store_true", help="trailing '(N)' names")
    parser.add_argument("--punct", action="store_true", help="names carrying a dot")
    parser.add_argument("--non-ascii", action="store_true", help="non-ASCII names")
    parser.add_argument(
        "--all",
        dest="all_",
        action="store_true",
        help="EVERY abandoned-attached-unlinked row (ignores the subset flags)",
    )
    parser.add_argument("--limit", type=int, default=0, help="cap the number of rows")
    parser.add_argument("--apply", action="store_true", help="write (default dry-run)")
    args = parser.parse_args()

    if args.all_:
        # --all supersedes the subset flags: re-arm the WHOLE dormant pool. Most of
        # it (names without a "(N)"/dot/non-ASCII form) is not touched by the recent
        # matcher fixes, so expect a low hit rate on that majority — the value is in
        # the fold-sensitive subsets. Drains over several nights (link budget cap).
        patterns = None
        print("Subsets: all (whole dormant pool)")
    else:
        chosen = [
            (name, SUBSETS[name])
            for name, flag in (
                ("suffix-n", args.suffix_n),
                ("punct", args.punct),
                ("non-ascii", args.non_ascii),
            )
            if flag
        ]
        if not chosen:
            parser.error("pick a subset (--suffix-n / --punct / --non-ascii) or --all")
        patterns = [p for _, p in chosen]
        print(f"Subsets: {', '.join(n for n, _ in chosen)}")

    engine = _get_engine()
    with Session(engine) as session:
        rows = _select_candidates(session, patterns, args.limit)
        kept = [(rid, name) for rid, name in rows if not _is_placeholder(name)]
        skipped = len(rows) - len(kept)

        print(f"Matched (abandoned + attached + unlinked): {len(rows)}")
        print(f"  excluded as placeholder: {skipped}")
        print(f"  to re-arm: {len(kept)}")
        for rid, name in kept[:_MAX_EXAMPLES]:
            print(f"    - [{rid}] {name}")
        if len(kept) > _MAX_EXAMPLES:
            print(f"    … +{len(kept) - _MAX_EXAMPLES} more")

        if not args.apply:
            print("\nDRY-RUN — nothing written. Re-run with --apply to re-arm.")
            return

        ids = [rid for rid, _ in kept]
        armed = 0
        for i in range(0, len(ids), _COMMIT_EVERY):
            chunk = ids[i : i + _COMMIT_EVERY]
            session.execute(
                update(Artist)
                .where(Artist.id.in_(chunk))
                .values(deezer_searched_at=None, deezer_search_attempts=0)
            )
            session.commit()
            armed += len(chunk)
        print(f"\nAPPLIED — re-armed {armed} rows (searched_at=NULL, attempts=0).")
        print(
            "They now sit in tier 1 of link_artists_deezer — the nightly run "
            "(05:10, budget 1500) re-searches them with the current matcher."
        )


if __name__ == "__main__":
    main()
