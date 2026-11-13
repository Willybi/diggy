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
      3. A title of the artist is masked when it is NOT corroborated AND its
         registrant is NOT anchored (a title without ISRC is never anchored), unless
         it is co-credited with ANOTHER artist holding >= ``COARTIST_MIN_CORROBORATED``
         (3) corroborated titles (§8.2). An artist that is itself in the TSV and
         subject to the rule (i.e. NOT skipped by the genre guard — even if absent
         from the DB) NEVER counts as a protecting co-artist: some TSV artists
         (homonym buckets) carry many corroborated titles through false DJ links and
         would otherwise shield farm titles. A genre-guarded TSV artist (classical/
         jazz, a real musician kept visible) and any artist outside the TSV can still
         protect. A title credited to several input artists
         is decided once for all of them: ANY protection wins (invariant #4).
      4. The artist itself is masked only when it has titles and NONE remains
         visible after step 3.
  * ``isrc_block`` — no input. Masks the titles whose ``upper(isrc)`` starts with
    one of ``workers.isrc_block.blocked_prefixes()`` (env
    ``CATALOG_ISRC_BLOCKED_PREFIXES``, default GXLE,GXLF,KRB92). Never an artist.

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
isrc" + a sample of titles protected by anchoring — READ THEM before any
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
    docker compose exec api python scripts/quarantine_undesirables.py --rule farm_fort --revert                                # revert dry-run
    docker compose exec api python scripts/quarantine_undesirables.py --rule farm_fort --revert --apply                        # revert
"""

import argparse
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.orm import Session
from workers.isrc_block import blocked_prefixes

RULES = ("farm_fort", "isrc_block")

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
        "titles_already_same_rule": 0,
        "titles_already_other_rule": 0,
        "artists_to_mask": 0,
        "artists_to_mask_tier1": 0,
        "artists_already_same_rule": 0,
        "artists_already_other_rule": 0,
        "artists_kept_visible": 0,
        "artists_without_titles": 0,
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


# --------------------------------------------------------------------------- plan


def plan_farm_fort(session, tsv_rows, rule="farm_fort"):
    """Compute the farm_fort plan (read-only). Returns ``(plan, stats)``.

    ``plan`` = {"titles": {catalog_id: info}, "to_mask": [ids], "anchored": [infos],
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
            for r in trows:
                if r.hidden_reason is not None or r.corro:
                    continue  # intrinsic status, decided below
                reg = _registrant(r.isrc)
                if reg is not None and reg in anchored:
                    verdict = "anchored"
                elif any(
                    coartist_cache.get(a, 0) >= COARTIST_MIN_CORROBORATED
                    for a in credits.get(r.id, ())
                    if a != artist_id and a not in subject_ids
                ):
                    verdict = "coartist"
                else:
                    verdict = "mask"
                verdicts.setdefault(r.id, set()).add(verdict)

    to_mask, anchored_infos = [], []
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
            v = verdicts.get(cid, {"mask"})
            if "anchored" in v:
                stats["titles_protected_anchored"] += 1
                anchored_infos.append(info)
            elif "coartist" in v:
                stats["titles_protected_coartist"] += 1
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

    plan = {
        "titles": titles,
        "to_mask": to_mask,
        "anchored": anchored_infos,
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
    plan = {
        "titles": titles,
        "to_mask": to_mask,
        "anchored": [],
        "artists_to_mask": [],
        "prefixes": prefixes,
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
    artist_stmt = text(
        """
        UPDATE artists SET hidden_reason = :rule, hidden_at = :now
        WHERE id IN :ids AND hidden_reason IS NULL
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
    else:
        print(f"    préfixes bloqués           : {', '.join(plan.get('prefixes') or ()) or '(aucun — règle inerte)'}")
    print(f"    titres examinés            : {stats['titles_examined']}")
    print(f"    {'titres ' + verb:<27}: {stats['titles_to_mask']}")
    print(f"    protégés corroborés        : {stats['titles_protected_corroborated']}")
    if rule == "farm_fort":
        print(f"    protégés ancrés            : {stats['titles_protected_anchored']}")
        print(f"    protégés co-artiste        : {stats['titles_protected_coartist']}")
    print(f"    déjà masqués (même règle)  : {stats['titles_already_same_rule']}")
    print(f"    déjà masqués (autre règle) : {stats['titles_already_other_rule']}")
    if rule == "farm_fort":
        print(f"    {'artistes ' + verb:<27}: {stats['artists_to_mask']}  (dont tier 1 cohorte : {stats['artists_to_mask_tier1']})")
        print(f"    artistes gardés visibles   : {stats['artists_kept_visible']}")
        print(f"    artistes sans titre        : {stats['artists_without_titles']}  (jamais masqués)")
        print(f"    artistes déjà masqués      : {stats['artists_already_same_rule']} même règle / {stats['artists_already_other_rule']} autre règle")
    if apply:
        print(f"    ÉCRIT : {stats['titles_masked']} titre(s), {stats['artists_masked']} artiste(s)")

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
