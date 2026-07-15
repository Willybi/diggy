"""
Sync artists from catalog.artist strings into the artists table.

Idempotent — safe to re-run. New catalog entries are processed, already-known
artist strings are skipped.

Classification rules (in priority order):
  1. feat / featuring / ft. / vs  → split → create
  2. comma:
       - if any token already in DB → split → create
       - else check Deezer per token → if all found → split → create
       - else → flag(comma_unresolved)
  3. ampersand ( & ):
       - if any token already in DB → split → create
       - else check Deezer for full string AND tokens:
           full found, tokens not → duo → create (no split)
           tokens found, full not → collab → create (split)
           both found             → flag(ampersand_ambiguous)
           neither found          → flag(ampersand_unknown)
  4. no separator → create as-is
"""

import asyncio
import re
import sys
import time
from datetime import datetime, timezone

import requests
from sqlalchemy import select

# Allow running as a script inside the api container
sys.path.insert(0, "/app")

from database import SessionLocal
from models import Artist, ArtistAlias, ArtistFlag, CatalogEntry
from trackid.importer import get_or_create_artist
from utils import normalize

DEEZER_API = "https://api.deezer.com"
RATE_LIMIT = 0.12  # seconds between Deezer calls

# Regex separators — order matters
FEAT_RE = re.compile(
    r"\s+(?:feat\.?|featuring|ft\.?|vs\.?)\s+",
    flags=re.IGNORECASE,
)


def _deezer_artist_id(name: str) -> str | None:
    """Return Deezer artist id if an exact-name match exists, else None."""
    try:
        resp = requests.get(
            f"{DEEZER_API}/search/artist",
            params={"q": name, "limit": 10},
            timeout=5,
        )
        for hit in resp.json().get("data", []):
            if hit.get("name", "").lower() == name.lower():
                return str(hit["id"])
    except Exception:
        pass
    return None


def _name_in_db_sync(name: str, known_norms: set[str]) -> bool:
    """Check if normalized name exists in our in-memory set of known normalized names."""
    return normalize(name) in known_norms


def _split_feat(raw: str) -> list[str]:
    parts = FEAT_RE.split(raw)
    return [p.strip() for p in parts if p.strip()]


def _split_comma(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def _split_ampersand(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(" & ") if p.strip()]


def _split_pipe(raw: str) -> list[str]:
    # Bare "|" (spaces optional): source strings use both "A | B" and "A|B".
    return [p.strip() for p in raw.split("|") if p.strip()]


async def run_sync(db) -> dict:
    """
    Main sync logic. Returns {"created": N, "flagged": M, "skipped": K}.
    Safe to call from FastAPI endpoint or CLI.
    """
    # 1. Load all distinct catalog.artist strings
    rows = await db.execute(
        select(CatalogEntry.artist).distinct().where(CatalogEntry.artist.isnot(None))
    )
    all_artist_strings: list[str] = [r[0] for r in rows.all()]

    # 2. Load known normalized names (artists + aliases) into memory
    art_rows = await db.execute(select(Artist.normalized_name))
    alias_rows = await db.execute(select(ArtistAlias.normalized_alias))
    known_norms: set[str] = set(r[0] for r in art_rows.all()) | set(
        r[0] for r in alias_rows.all()
    )

    # 3. Load already-flagged strings to skip re-processing
    flag_rows = await db.execute(select(ArtistFlag.raw_artist_string))
    already_flagged: set[str] = set(r[0] for r in flag_rows.all())

    created = 0
    flagged = 0
    skipped = 0

    for raw in all_artist_strings:
        raw = raw.strip()
        if not raw:
            continue

        norm = normalize(raw)

        # Skip if already in DB as an artist or alias
        if norm in known_norms:
            skipped += 1
            continue

        # Skip if already flagged (pending or resolved)
        if raw in already_flagged:
            skipped += 1
            continue

        # --- Rule 1: feat / featuring / ft / vs ---
        if FEAT_RE.search(raw):
            tokens = _split_feat(raw)
            for name in tokens:
                artist = await get_or_create_artist(db, name)
                known_norms.add(artist.normalized_name)
                created += 1
            await db.commit()
            continue

        # --- Rule 2: comma ---
        if "," in raw:
            tokens = _split_comma(raw)
            if any(_name_in_db_sync(t, known_norms) for t in tokens):
                # At least one token known → split
                for name in tokens:
                    artist = await get_or_create_artist(db, name)
                    known_norms.add(artist.normalized_name)
                    created += 1
                await db.commit()
            else:
                # Check Deezer for each token
                deezer_ids: dict[str, str | None] = {}
                for t in tokens:
                    deezer_ids[t] = _deezer_artist_id(t)
                    time.sleep(RATE_LIMIT)

                if all(deezer_ids[t] is not None for t in tokens):
                    for name in tokens:
                        artist = await get_or_create_artist(db, name)
                        if not artist.deezer_id and deezer_ids.get(name):
                            artist.deezer_id = deezer_ids[name]
                        known_norms.add(artist.normalized_name)
                        created += 1
                    await db.commit()
                else:
                    flag = ArtistFlag(
                        raw_artist_string=raw,
                        reason="comma_unresolved",
                        tokens=tokens,
                        deezer_ids=deezer_ids,
                        status="pending",
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(flag)
                    already_flagged.add(raw)
                    await db.commit()
                    flagged += 1
            continue

        # --- Rule 3: ampersand ---
        if " & " in raw:
            tokens = _split_ampersand(raw)
            if any(_name_in_db_sync(t, known_norms) for t in tokens):
                # At least one token known → it's a collab, split
                for name in tokens:
                    artist = await get_or_create_artist(db, name)
                    known_norms.add(artist.normalized_name)
                    created += 1
                await db.commit()
                continue

            # Check Deezer for full string + each token
            deezer_full = _deezer_artist_id(raw)
            time.sleep(RATE_LIMIT)
            deezer_ids = {raw: deezer_full}
            for t in tokens:
                deezer_ids[t] = _deezer_artist_id(t)
                time.sleep(RATE_LIMIT)

            full_found = deezer_full is not None
            tokens_found = all(deezer_ids[t] is not None for t in tokens)

            if full_found and not tokens_found:
                # Established duo (e.g. "Polo & Pan")
                artist = await get_or_create_artist(db, raw)
                if not artist.deezer_id:
                    artist.deezer_id = deezer_full
                known_norms.add(artist.normalized_name)
                await db.commit()
                created += 1
            elif tokens_found and not full_found:
                # Collab, split
                for name in tokens:
                    artist = await get_or_create_artist(db, name)
                    if not artist.deezer_id and deezer_ids.get(name):
                        artist.deezer_id = deezer_ids[name]
                    known_norms.add(artist.normalized_name)
                    created += 1
                await db.commit()
            else:
                reason = (
                    "ampersand_ambiguous"
                    if (full_found and tokens_found)
                    else "ampersand_unknown"
                )
                flag = ArtistFlag(
                    raw_artist_string=raw,
                    reason=reason,
                    tokens=tokens,
                    deezer_ids=deezer_ids,
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(flag)
                already_flagged.add(raw)
                await db.commit()
                flagged += 1
            continue

        # --- Rule 3b: pipe (mirror of ampersand — "|" reads like a duo/collab) ---
        if "|" in raw:
            tokens = _split_pipe(raw)
            if any(_name_in_db_sync(t, known_norms) for t in tokens):
                # At least one token known → it's a collab, split
                for name in tokens:
                    artist = await get_or_create_artist(db, name)
                    known_norms.add(artist.normalized_name)
                    created += 1
                await db.commit()
                continue

            # Check Deezer for full string + each token
            deezer_full = _deezer_artist_id(raw)
            time.sleep(RATE_LIMIT)
            deezer_ids = {raw: deezer_full}
            for t in tokens:
                deezer_ids[t] = _deezer_artist_id(t)
                time.sleep(RATE_LIMIT)

            full_found = deezer_full is not None
            tokens_found = all(deezer_ids[t] is not None for t in tokens)

            if full_found and not tokens_found:
                # Established duo
                artist = await get_or_create_artist(db, raw)
                if not artist.deezer_id:
                    artist.deezer_id = deezer_full
                known_norms.add(artist.normalized_name)
                await db.commit()
                created += 1
            elif tokens_found and not full_found:
                # Collab, split
                for name in tokens:
                    artist = await get_or_create_artist(db, name)
                    if not artist.deezer_id and deezer_ids.get(name):
                        artist.deezer_id = deezer_ids[name]
                    known_norms.add(artist.normalized_name)
                    created += 1
                await db.commit()
            else:
                reason = (
                    "ampersand_ambiguous"
                    if (full_found and tokens_found)
                    else "ampersand_unknown"
                )
                flag = ArtistFlag(
                    raw_artist_string=raw,
                    reason=reason,
                    tokens=tokens,
                    deezer_ids=deezer_ids,
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(flag)
                already_flagged.add(raw)
                await db.commit()
                flagged += 1
            continue

        # --- Rule 4: no separator → create as-is ---
        artist = await get_or_create_artist(db, raw)
        known_norms.add(artist.normalized_name)
        await db.commit()
        created += 1

    return {"created": created, "flagged": flagged, "skipped": skipped}


# ---------- CLI entry point ----------


async def _main():
    async with SessionLocal() as db:
        result = await run_sync(db)
    print(f"✅ {result['created']} artistes créés")
    print(f"⚠️  {result['flagged']} flags générés")
    print(f"⏭️  {result['skipped']} skippés (déjà connus)")


if __name__ == "__main__":
    asyncio.run(_main())
