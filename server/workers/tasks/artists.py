"""
Celery tasks for artist sync, artwork fetching, and set artist linking.
"""

import asyncio
import logging
import sys

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="workers.tasks.sync_artists",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=3600,
    time_limit=4500,
)
def sync_artists(self):
    """
    Sync artists from catalog.artist strings into the artists table.
    Phase A: local resolution (CPU-only, fast).
    Phase B: Deezer disambiguation for ambiguous names (concurrent).
    Artwork deferred to fetch_artist_artworks task.
    """
    import re
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, ArtistFlag, CatalogEntry
    from utils import normalize
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    FEAT_RE = re.compile(
        r"\s+(?:feat\.?|featuring|ft\.?|vs\.?)\s+", flags=re.IGNORECASE
    )
    engine = get_engine()

    # Start crawl log (running) — manual enter/exit to avoid re-indenting the entire body
    _log_session = Session(engine)
    _clog = CrawlLogger(
        _log_session, task_type="sync_artists", celery_task_id=self.request.id
    )
    _clog.__enter__()
    _clog_exc = None

    created = 0
    flagged = 0
    skipped = 0
    linked = 0

    # Collect names needing Deezer disambiguation
    needs_deezer = []  # list of (raw_string, tokens, rule_type)

    try:
        with Session(engine) as session:
            all_strings = [
                r[0]
                for r in session.execute(
                    select(CatalogEntry.artist)
                    .distinct()
                    .where(CatalogEntry.artist.isnot(None))
                ).all()
            ]

            known_norms = set(
                r[0] for r in session.execute(select(Artist.normalized_name)).all()
            )
            known_norms |= set(
                r[0]
                for r in session.execute(select(ArtistAlias.normalized_alias)).all()
            )
            already_flagged = set(
                r[0]
                for r in session.execute(select(ArtistFlag.raw_artist_string)).all()
            )

            def _get_or_create(name):
                nonlocal created
                norm = normalize(name)
                if norm in known_norms:
                    artist = session.execute(
                        select(Artist).where(Artist.normalized_name == norm)
                    ).scalar_one_or_none()
                    if artist and name.strip() != artist.name:
                        _ensure_alias(artist, name.strip())
                    return artist
                alias = session.execute(
                    select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
                ).scalar_one_or_none()
                if alias:
                    return session.get(Artist, alias.artist_id)
                artist = Artist(
                    name=name,
                    normalized_name=norm,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(artist)
                session.flush()
                known_norms.add(norm)
                created += 1
                return artist

            def _ensure_alias(artist, alias_name):
                if not artist or not alias_name:
                    return
                norm = normalize(alias_name)
                if norm == artist.normalized_name or norm in known_norms:
                    return
                existing = session.execute(
                    select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
                ).scalar_one_or_none()
                if existing:
                    return
                session.add(
                    ArtistAlias(
                        artist_id=artist.id, alias=alias_name, normalized_alias=norm
                    )
                )
                known_norms.add(norm)

            # Phase A: local resolution
            batch_count = 0
            for raw in all_strings:
                raw = raw.strip()
                if not raw:
                    continue
                norm = normalize(raw)
                if norm in known_norms or raw in already_flagged:
                    skipped += 1
                    continue

                if FEAT_RE.search(raw):
                    for name in [p.strip() for p in FEAT_RE.split(raw) if p.strip()]:
                        _get_or_create(name)
                    batch_count += 1
                    if batch_count % 50 == 0:
                        session.commit()
                    continue

                if "," in raw:
                    tokens = [p.strip() for p in raw.split(",") if p.strip()]
                    if any(normalize(t) in known_norms for t in tokens):
                        for name in tokens:
                            _get_or_create(name)
                        batch_count += 1
                        if batch_count % 50 == 0:
                            session.commit()
                    else:
                        needs_deezer.append((raw, tokens, "comma"))
                    continue

                if " & " in raw:
                    tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
                    if any(normalize(t) in known_norms for t in tokens):
                        for name in tokens:
                            _get_or_create(name)
                        batch_count += 1
                        if batch_count % 50 == 0:
                            session.commit()
                        continue
                    needs_deezer.append((raw, tokens, "ampersand"))
                    continue

                _get_or_create(raw)
                batch_count += 1
                if batch_count % 50 == 0:
                    session.commit()

            session.commit()

        # Phase B: Deezer disambiguation (concurrent)
        if needs_deezer:

            async def _deezer_resolve():
                nonlocal created, flagged
                import unicodedata

                from workers.async_http import DeezerHTTPError, HttpPool
                from workers.rate_limiter import RateLimiter

                def _norm(s):
                    s = unicodedata.normalize("NFKD", s.lower().strip())
                    return s.encode("ascii", "ignore").decode()

                async def _deezer_artist_id(pool, name):
                    try:
                        data = await pool.deezer_get(
                            "/search/artist", params={"q": name, "limit": 10}
                        )
                    except DeezerHTTPError as e:
                        logger.warning("Deezer artist search failed for %s: %s", name, e)
                        return None
                    name_norm = _norm(name)
                    for hit in data.get("data", []):
                        dz_name = hit.get("name", "")
                        if (
                            dz_name.lower() == name.lower()
                            or _norm(dz_name) == name_norm
                        ):
                            return str(hit["id"])
                    return None

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        known = set(
                            r[0]
                            for r in session.execute(
                                select(Artist.normalized_name)
                            ).all()
                        )
                        known |= set(
                            r[0]
                            for r in session.execute(
                                select(ArtistAlias.normalized_alias)
                            ).all()
                        )

                        for raw, tokens, rule_type in needs_deezer:
                            deezer_ids = {}
                            names_to_search = list(tokens)
                            if rule_type == "ampersand":
                                names_to_search = [raw] + list(tokens)

                            results = await asyncio.gather(
                                *[_deezer_artist_id(pool, n) for n in names_to_search]
                            )

                            for name, dz_id in zip(names_to_search, results):
                                deezer_ids[name] = dz_id

                            if rule_type == "comma":
                                if all(deezer_ids.get(t) is not None for t in tokens):
                                    for name in tokens:
                                        norm = normalize(name)
                                        if norm not in known:
                                            a = Artist(
                                                name=name,
                                                normalized_name=norm,
                                                created_at=datetime.now(timezone.utc),
                                            )
                                            session.add(a)
                                            session.flush()
                                            known.add(norm)
                                            if deezer_ids.get(name):
                                                a.deezer_id = deezer_ids[name]
                                            created += 1
                                else:
                                    session.add(
                                        ArtistFlag(
                                            raw_artist_string=raw,
                                            reason="comma_unresolved",
                                            tokens=tokens,
                                            deezer_ids=deezer_ids,
                                            status="pending",
                                            created_at=datetime.now(timezone.utc),
                                            updated_at=datetime.now(timezone.utc),
                                        )
                                    )
                                    flagged += 1

                            elif rule_type == "ampersand":
                                deezer_full = deezer_ids.get(raw)
                                full_found = deezer_full is not None
                                tokens_found = all(
                                    deezer_ids.get(t) is not None for t in tokens
                                )

                                if full_found and not tokens_found:
                                    norm = normalize(raw)
                                    if norm not in known:
                                        a = Artist(
                                            name=raw,
                                            normalized_name=norm,
                                            created_at=datetime.now(timezone.utc),
                                        )
                                        a.deezer_id = deezer_full
                                        session.add(a)
                                        session.flush()
                                        known.add(norm)
                                        created += 1
                                elif tokens_found and not full_found:
                                    for name in tokens:
                                        norm = normalize(name)
                                        if norm not in known:
                                            a = Artist(
                                                name=name,
                                                normalized_name=norm,
                                                created_at=datetime.now(timezone.utc),
                                            )
                                            if deezer_ids.get(name):
                                                a.deezer_id = deezer_ids[name]
                                            session.add(a)
                                            session.flush()
                                            known.add(norm)
                                            created += 1
                                else:
                                    reason = (
                                        "ampersand_ambiguous"
                                        if (full_found and tokens_found)
                                        else "ampersand_unknown"
                                    )
                                    session.add(
                                        ArtistFlag(
                                            raw_artist_string=raw,
                                            reason=reason,
                                            tokens=tokens,
                                            deezer_ids=deezer_ids,
                                            status="pending",
                                            created_at=datetime.now(timezone.utc),
                                            updated_at=datetime.now(timezone.utc),
                                        )
                                    )
                                    flagged += 1

                            session.commit()

            try:
                asyncio.run(_deezer_resolve())
            except Exception:
                logger.exception("Deezer artist disambiguation failed")
                raise

        # Phase C: link catalog entries to artists via catalog_artists
        from models import CatalogArtist

        linked = 0
        with Session(engine) as session:
            # Reload known artists + aliases
            known_artists = {
                r[0]: r[1]
                for r in session.execute(
                    select(Artist.normalized_name, Artist.id)
                ).all()
            }
            alias_map = {
                r[0]: r[1]
                for r in session.execute(
                    select(ArtistAlias.normalized_alias, ArtistAlias.artist_id)
                ).all()
            }
            # Merge: alias -> artist_id (artists take priority)
            lookup = {**alias_map, **{n: aid for n, aid in known_artists.items()}}

            # Find catalog entries without any catalog_artists link
            from sqlalchemy import exists as sa_exists

            unlinked = session.execute(
                select(CatalogEntry.id, CatalogEntry.artist)
                .where(CatalogEntry.artist.isnot(None))
                .where(
                    ~sa_exists(
                        select(CatalogArtist.catalog_id).where(
                            CatalogArtist.catalog_id == CatalogEntry.id
                        )
                    )
                )
            ).all()

            seen = set()
            batch = 0
            for cat_id, raw in unlinked:
                if not raw or not raw.strip():
                    continue
                raw = raw.strip()
                parts = []
                if FEAT_RE.search(raw):
                    tokens = [p.strip() for p in FEAT_RE.split(raw) if p.strip()]
                    for i, token in enumerate(tokens):
                        parts.append((token, "primary" if i == 0 else "featured", i))
                elif "," in raw:
                    tokens = [p.strip() for p in raw.split(",") if p.strip()]
                    for i, token in enumerate(tokens):
                        parts.append((token, "primary", i))
                elif " & " in raw:
                    tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
                    for i, token in enumerate(tokens):
                        parts.append((token, "primary", i))
                else:
                    parts.append((raw, "primary", 0))

                for name, role, position in parts:
                    artist_id = lookup.get(normalize(name))
                    if artist_id and (cat_id, artist_id) not in seen:
                        session.add(
                            CatalogArtist(
                                catalog_id=cat_id,
                                artist_id=artist_id,
                                role=role,
                                position=position,
                            )
                        )
                        seen.add((cat_id, artist_id))
                        linked += 1
                        batch += 1
                        if batch % 100 == 0:
                            session.commit()

            session.commit()
        logger.info("Phase C: linked %d catalog-artist pairs", linked)

    except Exception as exc:
        _clog_exc = exc
        raise
    finally:
        result = {
            "created": created,
            "flagged": flagged,
            "skipped": skipped,
            "linked": linked,
        }
        _clog.set_stats(result)
        if _clog_exc:
            _clog.__exit__(type(_clog_exc), _clog_exc, _clog_exc.__traceback__)
        else:
            _clog.__exit__(None, None, None)
        _log_session.close()

    return result


@celery_app.task(
    name="workers.tasks.fetch_artist_artworks",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def fetch_artist_artworks(self):
    """
    Fetch Deezer artist images concurrently.
    Pass 1: link artists to Deezer (5 concurrent searches).
    Pass 2: download artworks (5 concurrent downloads).
    """
    import unicodedata

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist
    from services.image_service import BUCKET_ARTIST, ImageService
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    ARTIST_BUCKET = BUCKET_ARTIST
    engine = get_engine()
    ImageService.ensure_bucket(ARTIST_BUCKET)

    _log_session = Session(engine)
    _clog = CrawlLogger(
        _log_session, task_type="fetch_artworks", celery_task_id=self.request.id
    )
    _clog.__enter__()

    async def _async_fetch():
        from workers.async_http import DeezerHTTPError, HttpPool
        from workers.rate_limiter import RateLimiter

        def _norm(s):
            s = unicodedata.normalize("NFKD", s.lower().strip())
            return s.encode("ascii", "ignore").decode()

        limiter = RateLimiter()
        linked = 0
        fetched = 0
        skipped = 0

        async with HttpPool(limiter) as pool:
            with Session(engine) as session:
                # Pass 1: link artists to Deezer
                no_id_artists = (
                    session.execute(select(Artist).where(Artist.deezer_id.is_(None)))
                    .scalars()
                    .all()
                )

                used_ids = set(
                    row[0]
                    for row in session.execute(
                        select(Artist.deezer_id).where(Artist.deezer_id.isnot(None))
                    ).all()
                )

                async def _link_one(artist):
                    nonlocal linked, skipped
                    try:
                        data = await pool.deezer_get(
                            "/search/artist", params={"q": artist.name, "limit": 10}
                        )
                    except DeezerHTTPError as e:
                        logger.warning(
                            "Deezer artist search failed for %s: %s", artist.name, e
                        )
                        skipped += 1
                        return
                    name_norm = _norm(artist.name)
                    for hit in data.get("data", []):
                        dz_name = hit.get("name", "")
                        if (
                            dz_name.lower() == artist.name.lower()
                            or _norm(dz_name) == name_norm
                        ):
                            dz_id = str(hit["id"])
                            if dz_id not in used_ids:
                                artist.deezer_id = dz_id
                                used_ids.add(dz_id)
                                linked += 1
                                return
                    skipped += 1

                await asyncio.gather(*[_link_one(a) for a in no_id_artists])
                session.commit()

                # Pass 2: download artworks
                artists_needing_art = (
                    session.execute(
                        select(Artist).where(
                            Artist.deezer_id.isnot(None),
                            Artist.deezer_id != "NOT_FOUND",
                            Artist.has_artwork == False,  # noqa: E712
                        )
                    )
                    .scalars()
                    .all()
                )

                async def _fetch_one(artist):
                    nonlocal fetched, skipped
                    try:
                        data = await pool.deezer_get(f"/artist/{artist.deezer_id}")
                    except DeezerHTTPError as e:
                        logger.warning(
                            "Deezer artist fetch failed for %s: %s", artist.deezer_id, e
                        )
                        skipped += 1
                        return
                    pic_url = (
                        data.get("picture_xl")
                        or data.get("picture_big")
                        or data.get("picture")
                    )
                    if not pic_url:
                        skipped += 1
                        return
                    img_data = await pool.download_image(pic_url)
                    if img_data:
                        if ImageService.upload_bytes(
                            img_data, ARTIST_BUCKET, f"{artist.id}.jpg"
                        ):
                            artist.has_artwork = True
                            fetched += 1
                        else:
                            skipped += 1
                    else:
                        skipped += 1

                await asyncio.gather(*[_fetch_one(a) for a in artists_needing_art])
                session.commit()

        return {"linked": linked, "fetched": fetched, "skipped": skipped}

    try:
        result = asyncio.run(_async_fetch())
    except Exception:
        logger.exception("fetch_artist_artworks failed")
        _clog.set_stats({"linked": 0, "fetched": 0, "skipped": 0})
        import sys as _sys

        _clog.__exit__(*_sys.exc_info())
        _log_session.close()
        raise

    _clog.set_stats(result)
    _clog.__exit__(None, None, None)
    _log_session.close()

    return result


@celery_app.task(
    name="workers.tasks.link_set_artists",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def link_set_artists(self):
    """
    Parse set titles to extract artist names and link them to the artists table.
    Matches against known artists (by name and aliases). Idempotent.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, DJSet, SetArtist
    from utils import normalize
    from workers.db import get_engine

    engine = get_engine()

    # Build lookup: normalized name/alias → artist_id
    with Session(engine) as session:
        norm_to_id = {}
        for a in session.execute(select(Artist)).scalars().all():
            norm_to_id[normalize(a.name)] = a.id
        for al in session.execute(select(ArtistAlias)).scalars().all():
            if al.normalized_alias not in norm_to_id:
                norm_to_id[al.normalized_alias] = al.artist_id

        # Sort by name length DESC so "Fred again.." matches before "Fred"
        sorted_names = sorted(norm_to_id.keys(), key=len, reverse=True)

        sets = session.execute(select(DJSet)).scalars().all()
        linked = 0
        skipped = 0

        for dj_set in sets:
            title = dj_set.title or ""
            title_lower = title.lower()

            # Detect B2B
            is_b2b = "b2b" in title_lower or "b2b" in title_lower.replace("_", " ")

            # Find all artist names present in the title
            matched_ids = set()
            title_norm = normalize(title)
            # Also normalize underscores (e.g. Busy_P_b2b_Erol_Alkan)
            title_norm_clean = title_norm.replace("_", " ")

            for norm_name in sorted_names:
                if len(norm_name) < 3:
                    continue  # skip very short names to avoid false positives
                if norm_name in title_norm or norm_name in title_norm_clean:
                    aid = norm_to_id[norm_name]
                    if aid not in matched_ids:
                        matched_ids.add(aid)

            # Insert set_artists (skip existing)
            existing = {
                r[0]
                for r in session.execute(
                    select(SetArtist.artist_id).where(SetArtist.set_id == dj_set.id)
                ).all()
            }

            for aid in matched_ids:
                if aid in existing:
                    skipped += 1
                    continue
                role = "b2b" if is_b2b else "dj"
                session.add(
                    SetArtist(
                        set_id=dj_set.id,
                        artist_id=aid,
                        role=role,
                        position=0,
                    )
                )
                linked += 1

            session.commit()

    return {"linked": linked, "skipped": skipped}


@celery_app.task(
    name="workers.tasks.backfill_multi_artists",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    soft_time_limit=7200,
    time_limit=9000,
)
def backfill_multi_artists(self):
    """Re-fetch Deezer track data for catalog entries with only 1 artist linked.

    Uses the /track/{deezer_id} endpoint which returns a ``contributors`` array,
    then calls link_catalog_artist_from_hit to add missing artist links.
    """
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogArtist, CatalogEntry
    from workers.crawl_logger import CrawlLogger
    from workers.db import get_engine

    engine = get_engine()

    _log_session = Session(engine)
    _clog = CrawlLogger(
        _log_session,
        task_type="backfill_multi_artists",
        celery_task_id=self.request.id,
    )
    _clog.__enter__()

    async def _async_backfill():
        from workers.async_http import HttpPool
        from workers.rate_limiter import RateLimiter

        limiter = RateLimiter()
        enriched = 0
        errors = 0

        async with HttpPool(limiter) as pool:
            with Session(engine) as session:
                # Entries with a deezer_id and exactly 1 catalog_artist link
                link_count = (
                    select(
                        CatalogArtist.catalog_id,
                        func.count().label("cnt"),
                    )
                    .group_by(CatalogArtist.catalog_id)
                    .subquery()
                )
                entries = (
                    session.execute(
                        select(CatalogEntry)
                        .join(
                            link_count,
                            CatalogEntry.id == link_count.c.catalog_id,
                        )
                        .where(
                            CatalogEntry.deezer_id.isnot(None),
                            CatalogEntry.deezer_id != "",
                            link_count.c.cnt == 1,
                        )
                    )
                    .scalars()
                    .all()
                )

                logger.info(
                    "backfill_multi_artists: %d entries with 1 artist link",
                    len(entries),
                )

                batch = 0

                async def _process_one(entry):
                    nonlocal enriched, errors, batch
                    try:
                        hit = await pool.deezer_get(f"/track/{entry.deezer_id}")
                        if not hit.get("id"):
                            return
                        contributors = hit.get("contributors") or []
                        if len(contributors) <= 1:
                            return
                        from workers.deezer_enrich import link_catalog_artist_from_hit

                        link_catalog_artist_from_hit(session, entry.id, hit)
                        enriched += 1
                        batch += 1
                        if batch % 50 == 0:
                            session.commit()
                            logger.info(
                                "backfill_multi_artists: committed %d", batch
                            )
                    except Exception as e:
                        errors += 1
                        logger.warning(
                            "backfill_multi_artists failed for catalog %s: %s",
                            entry.id,
                            e,
                        )

                await asyncio.gather(*[_process_one(e) for e in entries])
                session.commit()

        return {"enriched": enriched, "errors": errors, "total": len(entries)}

    try:
        result = asyncio.run(_async_backfill())
    except Exception:
        logger.exception("backfill_multi_artists failed")
        _clog.set_stats({"enriched": 0, "errors": 0})
        import sys as _sys

        _clog.__exit__(*_sys.exc_info())
        _log_session.close()
        raise

    _clog.set_stats(result)
    _clog.__exit__(None, None, None)
    _log_session.close()

    return result
