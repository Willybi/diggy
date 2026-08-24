#!/usr/bin/env python
"""One-shot OPS backfill: route splittable unlinked artists to the "Flags artistes" queue.

A multi-artist string that was created as a SINGLE ``artists`` row ("Nigel D.
Broad/Kieron Bellamy", "Oliver Lieb Presents L.S.G.") is a SPLIT candidate, not a
Deezer-link candidate — it will never link to Deezer as a combined entity. The
admin "Lier un artiste à Deezer" panel used to show these; they belong in the
"Flags artistes" review queue instead (an ``artist_flags`` pending row, exactly
what the panel's manual "Flagguer" button creates).

The sync worker flags multi-artist strings at INGESTION, but a large legacy backlog
(~227 rows measured 2026-08-24) predates it and sits unflagged. This creates a
pending ``ArtistFlag`` for each such row so it appears in the queue; the paired
service change then drops any name with a pending flag from the link panel.

SELECTION: unlinked (``deezer_id IS NULL``), still ATTACHED (catalog or set),
carrying a known separator, and NOT already flagged. Each name is tokenized by a
FRONT-PARITY splitter (the same separator list as ``frontend/utils/artistSplit.js``,
INCLUDING the '/' and ';' review hints the backend ``split_artist_parts`` omits —
here we produce a SUGGESTED split for admin review, not an autonomous backend split).
A name that does not split into >= 2 tokens is skipped (not really splittable).

Idempotent: a name that already owns an ``artist_flags`` row is skipped (the table's
``raw_artist_string`` is UNIQUE). Re-running finds only the still-unflagged rows.

DRY-RUN by default (writes nothing, prints counts + examples). Pass --apply to act.
Non-destructive (only INSERTs review rows), but take a dump first per project OPS
convention.

Usage (from the VPS):
    docker compose exec api python scripts/backfill_artist_flags.py           # dry-run
    docker compose exec api python scripts/backfill_artist_flags.py --apply    # create flags
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models

from models import Artist, ArtistFlag, CatalogArtist, SetArtist
from sqlalchemy import and_, create_engine, exists, not_, or_, select
from sqlalchemy.orm import Session

_COMMIT_EVERY = 500
_MAX_EXAMPLES = 15

# Separator list in PARITY with frontend/src/utils/artistSplit.js SEPARATORS
# (ordered, most specific first — detect picks the first match). Includes the
# FRONT-ONLY '/' and ';' hints: the flag is a suggested split for admin review.
_SEPARATORS = [
    "/", " & ", " + ", "|", ";", ", ",
    " featuring ", " feat. ", " feat ", " ft. ", " ft ",
    " vs. ", " vs ", " presents ", " présente ", " pres. ", " pres ",
    " and ", " x ", " y ", " e ",
]

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def _detect_separator(name):
    low = (name or "").lower()
    for sep in _SEPARATORS:
        if sep in low:
            return sep
    return None


def split_tokens(name):
    """Front-parity tokenization for a SUGGESTED flag split. Returns [] when the
    name does not split into >= 2 non-empty tokens (so it is not really a split)."""
    sep = _detect_separator(name)
    if not sep:
        return []
    parts = [p.strip() for p in re.split(re.escape(sep), name, flags=re.IGNORECASE) if p.strip()]
    return parts if len(parts) >= 2 else []


def _splittable_sql(col):
    """SQL narrowing to names carrying a separator (LIKE, PG + SQLite). A superset
    of what split_tokens accepts — the Python tokenizer does the final >= 2 check."""
    from sqlalchemy import func

    low = func.lower(col)
    return or_(
        col.like("%&%"), col.like("%/%"), col.like("%|%"), col.like("%;%"),
        col.like("%,%"), col.like("%+%"),
        low.like("% feat %"), low.like("% feat.%"), low.like("% ft %"), low.like("% ft.%"),
        low.like("% vs %"), low.like("% vs.%"), low.like("% featuring %"),
        low.like("% presents %"), low.like("% pres %"), low.like("% pres.%"),
    )


def select_batch(session, after_id, limit):
    attached = or_(
        exists().where(CatalogArtist.artist_id == Artist.id),
        exists().where(SetArtist.artist_id == Artist.id),
    )
    already_flagged = exists().where(ArtistFlag.raw_artist_string == Artist.name)
    rows = session.execute(
        select(Artist.id, Artist.name)
        .where(
            and_(
                Artist.deezer_id.is_(None),
                attached,
                _splittable_sql(Artist.name),
                not_(already_flagged),
                Artist.id > after_id,
            )
        )
        .order_by(Artist.id.asc())
        .limit(limit)
    ).all()
    return [tuple(r) for r in rows]


def run(apply=False, limit=None):
    engine = _get_engine()
    scanned = flagged = skipped_no_split = 0
    examples = []
    after_id = 0
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        while True:
            page = min(_COMMIT_EVERY, limit - scanned) if limit else _COMMIT_EVERY
            if page <= 0:
                break
            batch = select_batch(session, after_id, page)
            if not batch:
                break
            after_id = batch[-1][0]
            scanned += len(batch)

            for _id, name in batch:
                tokens = split_tokens(name)
                if len(tokens) < 2:
                    skipped_no_split += 1
                    continue
                flagged += 1
                if len(examples) < _MAX_EXAMPLES:
                    examples.append(f"{name!r} -> {tokens}")
                if apply:
                    session.add(
                        ArtistFlag(
                            raw_artist_string=name,
                            reason="auto_split",
                            tokens=tokens,
                            deezer_ids={},
                            status="pending",
                            created_at=now,
                            updated_at=now,
                        )
                    )
            if apply:
                session.commit()

    verb = "FLAGGED" if apply else "WOULD FLAG"
    print(f"\n=== backfill_artist_flags ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"scanned (splittable, unflagged): {scanned}")
    print(f"{verb}: {flagged}")
    print(f"skipped (separator present but < 2 tokens): {skipped_no_split}")
    print("examples:")
    for e in examples:
        print(f"  {e}")
    return {"scanned": scanned, "flagged": flagged, "skipped": skipped_no_split}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually create flags (default: dry-run)")
    parser.add_argument("--limit", type=int, default=None, help="Cap rows scanned")
    args = parser.parse_args()
    run(apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    main()
