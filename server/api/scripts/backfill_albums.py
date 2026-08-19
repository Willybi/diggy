#!/usr/bin/env python
"""One-shot OPS backfill: link existing catalog rows to their Deezer album (Album chantier, lot L3).

The Album entity (``albums`` + ``catalog_albums`` M2M, lot L1) is populated
fil-de-l'eau by enrichment (lot L2) from that point ON. But every track enriched
BEFORE the deploy carries NO album link. This script backfills the pre-existing
rows, WITHOUT touching the model, the migration, or the fil-de-l'eau enrichment.

It reuses the SINGLE source of the album upsert rule — ``apply_album_release_metadata``
/ ``link_catalog_album_from_hit`` / ``_resolve_or_create_album`` from L2 — so a
backfilled album/link is indistinguishable from an enrichment-built one and can
never diverge from the fil-de-l'eau definition. Invariant #4: an album is NEVER
created without a reliable ``deezer_album_id`` (both sources enforce it).

Three selectable sources (``--source payload|deezer|covers|both``, default ``payload``):

  * ``payload`` (FREE, network-free, run by default): walks ``artist_activity`` of
    type ``release`` carrying BOTH a ``payload.album_id`` and a non-null
    ``catalog_id`` (the C6.c release-crawl already stored the album id/title/
    record_type/release_date in the activity payload). For each it upserts the
    Album by ``deezer_album_id`` (title + conservative record_type/release_date
    top-up via ``apply_album_release_metadata``) and links ``CatalogAlbum``
    (catalog_id, album_id). No Deezer call.

  * ``deezer`` (OPTIONAL, rate-limited DRAIN — a MULTI-DAY job): for every
    ``catalog`` row with a real ``deezer_id`` (not the NOT_FOUND sentinel) and NO
    ``catalog_albums`` link, fetches ``/track/{deezer_id}`` (shared worker
    ``HttpPool`` + Redis rate limiter), reads ``hit["album"]`` and upserts + links
    + uploads the cover via ``link_catalog_album_from_hit``. Bounded by ``--limit``
    (default budget ``DEEZER_BUDGET_DEFAULT`` when unset); re-run to continue —
    linked rows drop out of the selection. Only ``--apply`` performs Deezer calls
    (a dry-run just counts the eligible rows, never burning the rate window).

  * ``covers`` (OPTIONAL, rate-limited DRAIN — a MULTI-DAY job): catch-up for the
    albums ALREADY created (fil-de-l'eau or the ``deezer`` source) but still
    lacking artwork or ``record_type`` — the batch funnel reads ``hit["album"]``
    (no record_type) and, while the ``album-artworks`` bucket was missing, every
    cover upload failed silently. For each ``albums`` row with a real
    ``deezer_album_id`` and (``has_artwork = false`` OR ``record_type IS NULL``)
    it fetches ``/album/{deezer_album_id}`` (the only hit carrying record_type/
    release_date/label + a cover), tops up the metadata conservatively via
    ``apply_album_release_metadata`` and uploads the cover to ``BUCKET_ALBUM``.
    Neither the fil-de-l'eau path nor the ``deezer`` source revisit these (the
    ``deezer`` source only targets catalog rows with NO album link). Bounded by
    ``--limit``; re-run to continue (a row drops out once covered + typed). Only
    ``--apply`` performs Deezer calls.

Convention (mirrors the other OPS scripts): DRY-RUN by default (reads only, prints
what WOULD change), ``--apply`` to write, ``--limit N`` to cap rows processed per
source. Idempotent: a second run (any source) converges to 0 creations — an already
linked catalog row / an already upserted album falls out of the work.

>>> ``--apply`` mutates rows (and, on the deezer source, calls Deezer). DUMP PROD
    FIRST (see docs/restore.md). <<<
A crash mid-run is safe (each batch is committed and the operation is idempotent —
a re-run finds the still-unlinked rows).

Usage (from the VPS):
    docker compose exec api python scripts/backfill_albums.py                        # dry-run, payload
    docker compose exec api python scripts/backfill_albums.py --apply                # write, payload
    docker compose exec api python scripts/backfill_albums.py --source deezer --limit 2000 --apply
    docker compose exec api python scripts/backfill_albums.py --source covers --limit 2000 --apply
    docker compose exec api python scripts/backfill_albums.py --source both --apply
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)  # server/ -> workers

from models import Album, ArtistActivity, CatalogAlbum, CatalogEntry
from services.image_service import BUCKET_ALBUM, ImageService
from sqlalchemy import create_engine, exists, func, or_, select
from sqlalchemy.orm import Session

# Reuse the EXACT L2 album helpers so a backfilled album/link is indistinguishable
# from an enrichment-built one (get-or-create by deezer_album_id, conservative
# metadata top-up, idempotent link + cover upload). Never re-implement the rule.
from workers.deezer_enrich import (
    apply_album_release_metadata,
    link_catalog_album_from_hit,
)

logger = logging.getLogger("backfill_albums")

# Rows scanned per DB round-trip and rows mutated per committed transaction.
_BATCH = 500
_COMMIT_EVERY = 200
# Default cap for the deezer drain when --limit is unset (it is a multi-day job;
# re-run to continue). Mirrors the budget-capped artist backfills.
DEEZER_BUDGET_DEFAULT = 2000

_engine = None


def _get_engine():
    """Lazy sync engine (mirrors the other OPS scripts: strip the +asyncpg driver)."""
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


# ── source: payload (network-free) ────────────────────────────────────────────


def backfill_from_payload(
    session, *, apply=False, batch_size=_BATCH, commit_every=_COMMIT_EVERY, limit=None,
    max_examples=5,
):
    """Upsert + link the Album recorded in every release ``artist_activity`` payload.

    Selects ``activity_type == 'release'`` rows with a non-null ``catalog_id`` and
    (in Python) a ``payload.album_id``; iterates by keyset (``id`` ascending) so the
    table is never loaded at once. For each candidate it get-or-creates the Album by
    ``deezer_album_id`` (via L2's ``apply_album_release_metadata`` — same title +
    conservative record_type/release_date top-up) and adds the ``CatalogAlbum`` link
    if absent.

    Counts are driven by read-only existence checks shared by both modes, so a
    dry-run reports the SAME numbers ``--apply`` would produce while writing nothing.
    ``apply`` writes and commits every ``commit_every`` mutated rows. A within-run
    duplicate ``(catalog_id, album)`` pair is handled once (counted ``already``) so
    the counts stay mode-independent and no PK clash occurs.

    Returns ``{"scanned", "no_album_id", "albums_created", "links_created",
    "already", "errors", "examples"}`` where ``albums_created`` counts DISTINCT new
    ``deezer_album_id`` values and ``examples`` is a list of
    ``(activity_id, catalog_id, deezer_album_id)``.
    """
    scanned = no_album_id = albums_created = links_created = already = errors = 0
    created_ids = set()  # deezer_album_ids newly created (or would-be) this run
    handled_pairs = set()  # (catalog_id, dz_album_id) already processed this run
    examples = []
    pending = 0
    last_id = 0

    while True:
        if limit is not None and scanned >= limit:
            break
        rows = session.execute(
            select(
                ArtistActivity.id,
                ArtistActivity.artist_id,
                ArtistActivity.catalog_id,
                ArtistActivity.payload,
            )
            .where(
                ArtistActivity.activity_type == "release",
                ArtistActivity.catalog_id.isnot(None),
                ArtistActivity.id > last_id,
            )
            .order_by(ArtistActivity.id.asc())
            .limit(batch_size)
        ).all()
        if not rows:
            break

        for act_id, artist_id, catalog_id, payload in rows:
            last_id = act_id
            if limit is not None and scanned >= limit:
                break
            scanned += 1

            data = payload or {}
            raw_album_id = data.get("album_id")
            if not raw_album_id:
                no_album_id += 1
                continue
            dz_id = str(raw_album_id)

            pair = (catalog_id, dz_id)
            if pair in handled_pairs:
                already += 1
                continue
            handled_pairs.add(pair)

            try:
                # Was the album already in the DB (before this run)? Drives the
                # created-vs-existing count identically in dry-run and --apply.
                prior = session.execute(
                    select(Album.id).where(Album.deezer_album_id == dz_id)
                ).scalar_one_or_none()
                album_pre_existing = prior is not None
                if not album_pre_existing and dz_id not in created_ids:
                    albums_created += 1
                    created_ids.add(dz_id)

                if apply:
                    album_obj = {
                        "id": raw_album_id,
                        "title": data.get("album_title"),
                        "record_type": data.get("record_type"),
                        "release_date": data.get("release_date"),
                    }
                    album = apply_album_release_metadata(
                        session, album_obj, artist_id=artist_id
                    )
                    link_exists = (
                        session.execute(
                            select(CatalogAlbum.catalog_id).where(
                                CatalogAlbum.catalog_id == catalog_id,
                                CatalogAlbum.album_id == album.id,
                            )
                        ).first()
                        is not None
                    )
                    if link_exists:
                        already += album_pre_existing
                    else:
                        session.add(
                            CatalogAlbum(catalog_id=catalog_id, album_id=album.id)
                        )
                        session.flush()
                        links_created += 1
                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0
                else:
                    # Dry-run: a brand-new album implies a new link; an existing
                    # album still needs its link checked.
                    if album_pre_existing:
                        link_exists = (
                            session.execute(
                                select(CatalogAlbum.catalog_id).where(
                                    CatalogAlbum.catalog_id == catalog_id,
                                    CatalogAlbum.album_id == prior,
                                )
                            ).first()
                            is not None
                        )
                        if link_exists:
                            already += 1
                        else:
                            links_created += 1
                    else:
                        links_created += 1

                if len(examples) < max_examples:
                    examples.append((act_id, catalog_id, dz_id))
            except Exception as exc:  # noqa: BLE001 — count + skip one bad row
                errors += 1
                logger.warning("payload backfill failed for activity %s: %s", act_id, exc)
                if apply:
                    session.rollback()
                    pending = 0

    if apply and pending:
        session.commit()

    return {
        "scanned": scanned,
        "no_album_id": no_album_id,
        "albums_created": albums_created,
        "links_created": links_created,
        "already": already,
        "errors": errors,
        "examples": examples,
    }


# ── source: deezer (rate-limited drain) ───────────────────────────────────────


def _deezer_candidates(session, last_id, take):
    """Catalog rows with a real deezer_id and NO catalog_albums link, id-keyset."""
    link_exists = exists().where(CatalogAlbum.catalog_id == CatalogEntry.id)
    return session.execute(
        select(CatalogEntry.id, CatalogEntry.deezer_id)
        .where(
            CatalogEntry.deezer_id.isnot(None),
            CatalogEntry.deezer_id != "NOT_FOUND",
            CatalogEntry.id > last_id,
            ~link_exists,
        )
        .order_by(CatalogEntry.id.asc())
        .limit(take)
    ).all()


def count_deezer_eligible(session):
    """Read-only: number of catalog rows the deezer drain WOULD fetch."""
    link_exists = exists().where(CatalogAlbum.catalog_id == CatalogEntry.id)
    return session.execute(
        select(func.count())
        .select_from(CatalogEntry)
        .where(
            CatalogEntry.deezer_id.isnot(None),
            CatalogEntry.deezer_id != "NOT_FOUND",
            ~link_exists,
        )
    ).scalar_one()


async def drain_deezer(
    engine, *, limit, batch_size=_BATCH, commit_every=_COMMIT_EVERY, max_examples=5,
):
    """Fetch each eligible catalog row's Deezer track and link its album (--apply only).

    For each candidate (deezer_id set, no link), fetches ``/track/{deezer_id}`` and
    hands the hit to L2's ``link_catalog_album_from_hit`` (upsert album by
    ``deezer_album_id`` + link + cover upload). A Deezer HTTP error or a track with
    no album is counted and skipped, never fatal. Bounded by ``limit`` (the drain
    budget). Async pool + sync Session, mirroring ``_check_releases``.

    Returns ``{"scanned", "albums_created", "links_created", "no_album", "errors",
    "examples"}``.
    """
    from workers.async_http import DeezerHTTPError, HttpPool
    from workers.rate_limiter import RateLimiter

    scanned = albums_created = links_created = no_album = errors = 0
    examples = []
    pending = 0
    last_id = 0

    ImageService.ensure_bucket(BUCKET_ALBUM)  # once per --apply run (covers upload)
    limiter = RateLimiter()
    async with HttpPool(limiter) as pool:
        with Session(engine) as session:
            while scanned < limit:
                take = min(batch_size, limit - scanned)
                rows = _deezer_candidates(session, last_id, take)
                if not rows:
                    break

                for cat_id, dz_id in rows:
                    last_id = cat_id
                    if scanned >= limit:
                        break
                    scanned += 1

                    try:
                        hit = await pool.deezer_get(f"/track/{dz_id}")
                    except DeezerHTTPError as exc:
                        errors += 1
                        logger.warning(
                            "deezer drain: /track/%s failed: %s", dz_id, exc
                        )
                        continue

                    if not isinstance(hit, dict) or hit.get("error"):
                        errors += 1
                        continue
                    album_obj = hit.get("album") or {}
                    if not album_obj.get("id"):
                        no_album += 1
                        continue

                    dz_album_id = str(album_obj["id"])
                    album_pre = session.execute(
                        select(Album.id).where(Album.deezer_album_id == dz_album_id)
                    ).scalar_one_or_none()

                    try:
                        link_catalog_album_from_hit(session, cat_id, hit)
                        session.flush()
                    except Exception as exc:  # noqa: BLE001 — count + skip
                        errors += 1
                        session.rollback()
                        pending = 0
                        logger.warning(
                            "deezer drain: link failed for catalog %s: %s", cat_id, exc
                        )
                        continue

                    if album_pre is None:
                        albums_created += 1
                    links_created += 1  # selection guarantees the row had no link
                    if len(examples) < max_examples:
                        examples.append((cat_id, dz_album_id))

                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0

            if pending:
                session.commit()

    return {
        "scanned": scanned,
        "albums_created": albums_created,
        "links_created": links_created,
        "no_album": no_album,
        "errors": errors,
        "examples": examples,
    }


# ── source: covers (rate-limited catch-up on already-created albums) ──────────


def _covers_candidates(session, last_id, take):
    """Existing albums with a real deezer_album_id but missing artwork OR
    record_type, id-keyset. Neither the fil-de-l'eau enrichment nor the deezer
    drain revisit these — the deezer drain only targets catalog rows with NO
    album link, whereas these albums are already linked but were never covered/
    metadata-topped (the batch funnel reads ``hit["album"]`` which carries no
    record_type, and the cover upload silently failed while the bucket was
    absent)."""
    return session.execute(
        select(Album.id, Album.deezer_album_id)
        .where(
            Album.deezer_album_id.isnot(None),
            or_(Album.has_artwork.is_(False), Album.record_type.is_(None)),
            Album.id > last_id,
        )
        .order_by(Album.id.asc())
        .limit(take)
    ).all()


def count_covers_eligible(session):
    """Read-only: number of existing albums the covers drain WOULD re-fetch."""
    return session.execute(
        select(func.count())
        .select_from(Album)
        .where(
            Album.deezer_album_id.isnot(None),
            or_(Album.has_artwork.is_(False), Album.record_type.is_(None)),
        )
    ).scalar_one()


def topup_album_from_data(session, album, data):
    """Top up ONE existing album from its ``/album/{id}`` payload: conservative
    release metadata (record_type/release_date/label via L2's
    ``apply_album_release_metadata``, artist_id=None so the already-set artist is
    untouched) + a one-shot cover upload. Returns ``(metadata_updated,
    cover_uploaded)``. Sync core, factored out so tests drive it without network.
    """
    meta_was_missing = album.record_type is None
    cover_was_missing = not album.has_artwork
    apply_album_release_metadata(session, data, artist_id=None)
    metadata_updated = meta_was_missing and album.record_type is not None

    cover_uploaded = False
    if cover_was_missing:
        cover_url = data.get("cover_medium") or data.get("cover_big")
        if cover_url and ImageService.upload_from_url(
            cover_url, BUCKET_ALBUM, f"{album.id}.jpg"
        ):
            album.has_artwork = True
            cover_uploaded = True
    return metadata_updated, cover_uploaded


async def drain_covers(
    engine, *, limit, batch_size=_BATCH, commit_every=_COMMIT_EVERY, max_examples=5,
):
    """Fetch each eligible album's Deezer record and top up metadata + cover (--apply only).

    For each candidate (deezer_album_id set, missing artwork or record_type),
    fetches ``/album/{deezer_album_id}`` (the ONLY hit that carries record_type/
    release_date/label + a cover) and hands it to ``topup_album_from_data``. A
    Deezer HTTP error or an errored payload is counted and skipped, never fatal.
    Bounded by ``limit`` (the drain budget). Async pool + sync Session, mirroring
    ``drain_deezer``.

    Returns ``{"scanned", "metadata_updated", "covers_uploaded", "errors",
    "examples"}``.
    """
    from workers.async_http import DeezerHTTPError, HttpPool
    from workers.rate_limiter import RateLimiter

    scanned = metadata_updated = covers_uploaded = errors = 0
    examples = []
    pending = 0
    last_id = 0

    ImageService.ensure_bucket(BUCKET_ALBUM)  # once per --apply run
    limiter = RateLimiter()
    async with HttpPool(limiter) as pool:
        with Session(engine) as session:
            while scanned < limit:
                take = min(batch_size, limit - scanned)
                rows = _covers_candidates(session, last_id, take)
                if not rows:
                    break

                for album_id, dz_album_id in rows:
                    last_id = album_id
                    if scanned >= limit:
                        break
                    scanned += 1

                    try:
                        data = await pool.deezer_get(f"/album/{dz_album_id}")
                    except DeezerHTTPError as exc:
                        errors += 1
                        logger.warning(
                            "covers drain: /album/%s failed: %s", dz_album_id, exc
                        )
                        continue

                    if not isinstance(data, dict) or data.get("error"):
                        errors += 1
                        continue

                    album = session.get(Album, album_id)
                    if album is None:  # deleted between selection and now
                        errors += 1
                        continue

                    try:
                        meta_up, cover_up = topup_album_from_data(session, album, data)
                        session.flush()
                    except Exception as exc:  # noqa: BLE001 — count + skip
                        errors += 1
                        session.rollback()
                        pending = 0
                        logger.warning(
                            "covers drain: top-up failed for album %s: %s",
                            album_id,
                            exc,
                        )
                        continue

                    metadata_updated += int(meta_up)
                    covers_uploaded += int(cover_up)
                    if len(examples) < max_examples:
                        examples.append((album_id, dz_album_id))

                    pending += 1
                    if pending >= commit_every:
                        session.commit()
                        pending = 0

            if pending:
                session.commit()

    return {
        "scanned": scanned,
        "metadata_updated": metadata_updated,
        "covers_uploaded": covers_uploaded,
        "errors": errors,
        "examples": examples,
    }


# ── reporting ─────────────────────────────────────────────────────────────────


def _print_payload(stats, apply):
    verb = "linked" if apply else "would link"
    create_verb = "created" if apply else "would create"
    print(
        f"\n[payload] scanned {stats['scanned']} release activity(ies) "
        f"({stats['no_album_id']} without an album_id, skipped): "
        f"{create_verb} {stats['albums_created']} album(s), {verb} "
        f"{stats['links_created']} catalog_album link(s), {stats['already']} already "
        f"up to date, {stats['errors']} error(s)."
    )
    for act_id, cat_id, dz_id in stats["examples"]:
        print(f"    activity #{act_id} catalog #{cat_id} -> album deezer:{dz_id}")


def _print_deezer(stats, apply):
    if not apply:
        print(
            f"\n[deezer] {stats['eligible']} catalog row(s) eligible (real deezer_id, "
            f"no album link). The drain fetches /track/{{id}} for each — RATE-LIMITED, "
            f"a multi-day job — ONLY under --apply (bounded by --limit; re-run to "
            f"continue)."
        )
        return
    print(
        f"\n[deezer] drained {stats['scanned']} catalog row(s): created "
        f"{stats['albums_created']} album(s), linked {stats['links_created']}, "
        f"{stats['no_album']} track(s) had no album, {stats['errors']} error(s)."
    )
    for cat_id, dz_id in stats["examples"]:
        print(f"    catalog #{cat_id} -> album deezer:{dz_id}")


def _print_covers(stats, apply):
    if not apply:
        print(
            f"\n[covers] {stats['eligible']} existing album(s) eligible (real "
            f"deezer_album_id, missing artwork or record_type). The drain fetches "
            f"/album/{{id}} for each — RATE-LIMITED, a multi-day job — ONLY under "
            f"--apply (bounded by --limit; re-run to continue)."
        )
        return
    print(
        f"\n[covers] drained {stats['scanned']} album(s): topped up "
        f"{stats['metadata_updated']} record_type(s), uploaded "
        f"{stats['covers_uploaded']} cover(s), {stats['errors']} error(s)."
    )
    for album_id, dz_id in stats["examples"]:
        print(f"    album #{album_id} -> deezer:{dz_id}")


def main(apply, source, limit):
    engine = _get_engine()
    # Same budget default backs both network drains (deezer + covers).
    deezer_limit = limit if limit is not None else DEEZER_BUDGET_DEFAULT
    try:
        head = "APPLY" if apply else "DRY-RUN — nothing will be modified (use --apply)"
        print(f"=== {head} (source={source}) ===")

        if source in ("payload", "both"):
            with Session(engine) as session:
                stats = backfill_from_payload(session, apply=apply, limit=limit)
                _print_payload(stats, apply)
                if apply:
                    conv = backfill_from_payload(session, apply=False, limit=limit)
                    print(
                        f"    convergence re-check (expected 0/0): "
                        f"albums={conv['albums_created']}, links={conv['links_created']}."
                    )
                else:
                    session.rollback()

        if source in ("deezer", "both"):
            if not apply:
                with Session(engine) as session:
                    eligible = count_deezer_eligible(session)
                _print_deezer({"eligible": eligible}, apply=False)
            else:
                stats = asyncio.run(drain_deezer(engine, limit=deezer_limit))
                _print_deezer(stats, apply=True)

        if source == "covers":
            if not apply:
                with Session(engine) as session:
                    eligible = count_covers_eligible(session)
                _print_covers({"eligible": eligible}, apply=False)
            else:
                stats = asyncio.run(drain_covers(engine, limit=deezer_limit))
                _print_covers(stats, apply=True)

        if not apply:
            print(
                "\nDry-run only. Re-run with --apply to write — DUMP PROD FIRST (see "
                "docs/restore.md). The payload source is network-free; the deezer and "
                "covers sources are rate-limited multi-day drains (bound with --limit)."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill album links for pre-existing catalog rows (payload = "
        "free, from release activity payloads; deezer = rate-limited drain; covers = "
        "rate-limited catch-up of already-created albums missing artwork/record_type). "
        "Dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write albums/links (default: dry-run, no changes)",
    )
    parser.add_argument(
        "--source",
        choices=("payload", "deezer", "covers", "both"),
        default="payload",
        help="which source to backfill from (default: payload, network-free; "
        "covers = rate-limited catch-up of already-created albums missing "
        "artwork/record_type)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap rows processed per source (deezer drain budget; validate a sample "
        "first). Default deezer budget when unset: %d" % DEEZER_BUDGET_DEFAULT,
    )
    args = parser.parse_args()
    main(apply=args.apply, source=args.source, limit=args.limit)
