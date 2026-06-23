"""
Celery tasks for Diggy.
Pipeline tasks for crawling playlists, enriching catalog, syncing artists, etc.
"""
import asyncio
import os
import sys
import time
import logging
import requests
from workers.celery_app import celery_app

API_BASE = os.environ.get("DIGGY_API_URL", "http://api:8000")
DEEZER_API = "https://api.deezer.com"

logger = logging.getLogger(__name__)


@celery_app.task(name="workers.tasks.crawl_radar", bind=True)
def crawl_radar(self):
    """
    Crawl toutes les playlists surveillées (Deezer, TIDAL, Spotify).
    Fan-out: lance crawl_single_playlist en parallèle via Celery.
    """
    from workers.source_clients import get_fetchers
    from workers.db import get_engine
    from sqlalchemy.orm import Session

    engine = get_engine()
    playlists = requests.get(f"{API_BASE}/api/watchlist/", timeout=10).json()

    with Session(engine) as log_session:
        from workers.crawl_logger import CrawlLogger
        with CrawlLogger(log_session, task_type="crawl_radar",
                         target_label=f"{len(playlists)} playlists",
                         celery_task_id=self.request.id) as clog:
            dispatched = 0
            skipped = 0
            errors = 0

            for pl in playlists:
                source = pl.get("source")
                try:
                    _, _, has_changed = get_fetchers(source)
                except ValueError:
                    logger.warning("Unknown source %s for playlist %s, skipping", source, pl["id"])
                    continue

                try:
                    if not has_changed(pl["external_id"], pl.get("last_crawled_at")):
                        skipped += 1
                        continue
                except Exception as e:
                    logger.warning("has_changed check failed for %s/%s: %s", source, pl["id"], e)

                try:
                    crawl_single_playlist.delay(pl["id"])
                    dispatched += 1
                except Exception as e:
                    logger.error("Failed to dispatch crawl for %s/%s: %s", source, pl["id"], e)
                    errors += 1

            clog.set_stats({"dispatched": dispatched, "skipped": skipped, "errors": errors})

    return {"dispatched": dispatched, "skipped_playlists": skipped, "errors": errors}


@celery_app.task(name="workers.tasks.crawl_single_playlist", bind=True)
def crawl_single_playlist(self, playlist_id: int):
    """
    Crawl une seule playlist (Deezer, TIDAL, ou Spotify) par son watched_entity ID.
    Uses direct DB access (bulk ops) + concurrent async enrichment.
    """
    from sqlalchemy import select, delete as sa_delete
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry, RadarTrack, WatchedEntity, UserFollow
    from deezer_enrich import _get_s3, _ensure_bucket, upload_image_to_bucket
    from workers.source_clients import get_fetchers
    from workers.db import get_engine, bulk_get_or_create_catalog, bulk_insert_radar_tracks

    engine = get_engine()

    # Load playlist info from DB directly
    with Session(engine) as session:
        entity = session.get(WatchedEntity, playlist_id)
        if not entity:
            return {"error": "playlist not found"}
        source = entity.source
        external_id = entity.external_id
        entity_title = entity.title

    try:
        fetch_meta, fetch_tracks, _ = get_fetchers(source)
    except ValueError:
        return {"error": f"unknown source: {source}"}

    s3 = _get_s3()
    _ensure_bucket(s3)

    # 0. Fetch playlist metadata + update entity
    try:
        meta = fetch_meta(external_id)
    except Exception as e:
        err_str = str(e).lower()
        if "not found" in err_str or "404" in err_str:
            logger.warning("Playlist %s (%s) no longer exists on %s — removing", playlist_id, entity_title, source)
            with Session(engine) as session:
                session.execute(sa_delete(RadarTrack).where(RadarTrack.watched_entity_id == playlist_id))
                session.execute(sa_delete(UserFollow).where(UserFollow.entity_id == playlist_id))
                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    session.delete(entity)
                session.commit()
            return {"deleted": True, "playlist_id": playlist_id, "source": source, "reason": "not_found_on_source"}
        raise

    # CrawlLogger wraps the main work
    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(log_session, task_type="crawl_playlist",
                         target_id=playlist_id, target_label=entity_title,
                         source=source, celery_task_id=self.request.id) as clog:

            with Session(engine) as session:
                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    if meta.track_count is not None:
                        entity.track_count = meta.track_count
                    if meta.description:
                        entity.description = meta.description
                    if meta.owner:
                        entity.owner = meta.owner
                    if meta.title and not entity.title:
                        entity.title = meta.title
                    if not entity.has_artwork and meta.cover_url:
                        _ensure_bucket(s3, "playlist-artworks")
                        if upload_image_to_bucket(s3, meta.cover_url, f"{playlist_id}.jpg", "playlist-artworks"):
                            entity.has_artwork = True
                    session.commit()

            # 1. Fetch all tracks from source
            source_tracks = fetch_tracks(external_id)

            # 2. Bulk insert radar tracks (direct DB, replaces per-track HTTP POST)
            with Session(engine) as session:
                track_dicts = [
                    {"title": st.title, "artist": st.artist, "isrc": st.isrc, "duration_ms": st.duration_ms}
                    for st in source_tracks
                ]
                catalog_map = bulk_get_or_create_catalog(session, track_dicts)
                inserted = bulk_insert_radar_tracks(session, playlist_id, source, source_tracks, catalog_map)
                session.commit()

            # 3 & 4. Async enrichment (Deezer + Beatport) — concurrent
            async def _async_enrich():
                from workers.rate_limiter import RateLimiter
                from workers.async_http import HttpPool
                from workers.enrichment import enrich_deezer_batch, enrich_beatport_batch

                limiter = RateLimiter()
                dz_stats = {"enriched": 0, "errors": 0}
                bp_stats = {"enriched": 0, "not_found": 0, "errors": 0}

                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        # Preload ISRCs
                        existing_isrcs = {r[0] for r in session.execute(
                            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
                        ).all()}

                        # Get catalog IDs from radar tracks for this playlist
                        radar_rows = session.execute(
                            select(RadarTrack.external_track_id, RadarTrack.catalog_id)
                            .where(RadarTrack.watched_entity_id == playlist_id)
                        ).all()
                        catalog_ids = {row.catalog_id for row in radar_rows if row.catalog_id}

                        # Deezer enrichment — entries missing deezer_id
                        dz_entries = session.execute(
                            select(CatalogEntry).where(
                                CatalogEntry.id.in_(catalog_ids),
                                CatalogEntry.deezer_id.is_(None),
                            )
                        ).scalars().all()

                        if dz_entries:
                            ext_id_map = None
                            if source == "deezer":
                                ext_to_catalog = {row.external_track_id: row.catalog_id for row in radar_rows}
                                ext_id_map = {}
                                for ext_id, cat_id in ext_to_catalog.items():
                                    if cat_id:
                                        ext_id_map[cat_id] = ext_id

                            dz_stats = await enrich_deezer_batch(
                                session, dz_entries, pool, s3, existing_isrcs,
                                source=source if source == "deezer" else "cross-search",
                                ext_id_map=ext_id_map,
                            )

                        session.commit()

                        # Beatport enrichment — entries missing beatport_id
                        bp_entries = session.execute(
                            select(CatalogEntry).where(
                                CatalogEntry.id.in_(catalog_ids),
                                CatalogEntry.beatport_id.is_(None),
                            )
                        ).scalars().all()

                        if bp_entries:
                            bp_stats = await enrich_beatport_batch(session, bp_entries, pool, s3)

                        session.commit()

                return dz_stats, bp_stats

            try:
                dz_stats, bp_stats = asyncio.run(_async_enrich())
            except Exception as e:
                logger.error("Async enrichment failed for playlist %s: %s", playlist_id, e)
                dz_stats = {"enriched": 0, "errors": 1}
                bp_stats = {"enriched": 0, "not_found": 0, "errors": 1}

            # 5. Mark playlist as crawled
            with Session(engine) as session:
                from datetime import datetime, timezone
                entity = session.get(WatchedEntity, playlist_id)
                if entity:
                    entity.last_crawled_at = datetime.now(timezone.utc)
                    session.commit()

            clog.set_stats({
                "inserted": inserted,
                "enriched": dz_stats.get("enriched", 0),
                "bp_enriched": bp_stats.get("enriched", 0),
                "total_tracks": len(source_tracks),
            })

    return {
        "playlist_id": playlist_id,
        "source": source,
        "title": entity_title or (meta.title if meta else None),
        "inserted": inserted,
        "enriched": dz_stats.get("enriched", 0),
        "bp_enriched": bp_stats.get("enriched", 0),
        "total_tracks": len(source_tracks),
    }


@celery_app.task(name="workers.tasks.check_previews")
def check_previews():
    """
    Vérifie chaque semaine si les tracks catalog ont une preview Deezer dispo.
    Met à jour has_preview dans les deux sens (True/False).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry, RadarTrack
    from workers.db import get_engine

    engine = get_engine()

    updated = 0
    with Session(engine) as session:
        entries = session.execute(select(CatalogEntry)).scalars().all()
        for entry in entries:
            row = session.execute(
                select(RadarTrack.external_track_id)
                .where(RadarTrack.catalog_id == entry.id)
                .where(RadarTrack.source == "deezer")
                .limit(1)
            ).first()
            if not row:
                continue
            try:
                r = requests.get(f"{DEEZER_API}/track/{row[0]}", timeout=10)
                has = bool(r.json().get("preview", "").strip())
            except Exception:
                continue
            if entry.has_preview != has:
                entry.has_preview = has
                updated += 1
            time.sleep(0.15)
        session.commit()

    return {"updated": updated}


@celery_app.task(name="workers.tasks.resolve_set_tracks", bind=True)
def resolve_set_tracks(self):
    """
    Résout les set_tracks sans catalog_id.
    Uses bulk catalog operations + concurrent async enrichment.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import SetTrack, CatalogEntry
    from deezer_enrich import _get_s3, _ensure_bucket
    from workers.db import get_engine, bulk_get_or_create_catalog
    from workers.crawl_logger import CrawlLogger

    engine = get_engine()
    s3 = _get_s3()
    _ensure_bucket(s3)

    with Session(engine) as log_session:
        with CrawlLogger(log_session, task_type="resolve_set_tracks",
                         celery_task_id=self.request.id) as clog:
            resolved = 0

            with Session(engine) as session:
                tracks = session.execute(
                    select(SetTrack).where(
                        SetTrack.catalog_id.is_(None),
                        SetTrack.is_id == False,  # noqa: E712
                        SetTrack.raw_title.isnot(None),
                    )
                ).scalars().all()

                if not tracks:
                    clog.set_stats({"resolved": 0, "enriched": 0, "bp_enriched": 0})
                    return {"resolved": 0, "enriched": 0, "bp_enriched": 0}

                # Bulk catalog lookup/create
                track_dicts = [
                    {"title": st.raw_title, "artist": st.raw_artist}
                    for st in tracks
                ]
                catalog_map = bulk_get_or_create_catalog(session, track_dicts)

                from utils import make_normalized_key
                for st in tracks:
                    nk = make_normalized_key(st.raw_title, st.raw_artist)
                    entry = catalog_map.get(nk)
                    if entry:
                        st.catalog_id = entry.id
                        resolved += 1

                session.commit()

            # Async enrichment for entries missing deezer_id or beatport_id
            async def _async_enrich():
                from workers.rate_limiter import RateLimiter
                from workers.async_http import HttpPool
                from workers.enrichment import enrich_deezer_batch, enrich_beatport_batch

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        existing_isrcs = {r[0] for r in session.execute(
                            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
                        ).all()}

                        resolved_ids = {st.catalog_id for st in tracks if st.catalog_id}
                        dz_entries = session.execute(
                            select(CatalogEntry).where(
                                CatalogEntry.id.in_(resolved_ids),
                                CatalogEntry.deezer_id.is_(None),
                            )
                        ).scalars().all()

                        dz_stats = {"enriched": 0}
                        if dz_entries:
                            dz_stats = await enrich_deezer_batch(session, dz_entries, pool, s3, existing_isrcs)
                        session.commit()

                        bp_entries = session.execute(
                            select(CatalogEntry).where(
                                CatalogEntry.id.in_(resolved_ids),
                                CatalogEntry.beatport_id.is_(None),
                            )
                        ).scalars().all()

                        bp_stats = {"enriched": 0}
                        if bp_entries:
                            bp_stats = await enrich_beatport_batch(session, bp_entries, pool, s3)
                        session.commit()

                return dz_stats, bp_stats

            try:
                dz_stats, bp_stats = asyncio.run(_async_enrich())
            except Exception as e:
                logger.error("Async enrichment failed in resolve_set_tracks: %s", e)
                dz_stats = {"enriched": 0}
                bp_stats = {"enriched": 0}

            result = {
                "resolved": resolved,
                "enriched": dz_stats.get("enriched", 0),
                "bp_enriched": bp_stats.get("enriched", 0),
            }
            clog.set_stats(result)

    return result


@celery_app.task(name="workers.tasks.enrich_catalog", bind=True)
def enrich_catalog(self):
    """
    Enrichit les entrées catalog sans deezer_id via Deezer.
    Concurrent async enrichment (5 parallel requests).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from deezer_enrich import _get_s3, _ensure_bucket
    from workers.db import get_engine

    engine = get_engine()
    s3 = _get_s3()
    _ensure_bucket(s3)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(log_session, task_type="enrich_catalog",
                         source="deezer", celery_task_id=self.request.id) as clog:

            async def _async_enrich():
                from workers.rate_limiter import RateLimiter
                from workers.async_http import HttpPool
                from workers.enrichment import enrich_deezer_batch

                limiter = RateLimiter()
                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        existing_isrcs = {r[0] for r in session.execute(
                            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
                        ).all()}

                        entries = session.execute(
                            select(CatalogEntry).where(
                                CatalogEntry.deezer_id.is_(None),
                                CatalogEntry.deezer_searched_at.is_(None),
                            ).order_by(CatalogEntry.id)
                        ).scalars().all()

                        if not entries:
                            return {"enriched": 0, "errors": 0}

                        total_enriched = 0
                        total_errors = 0
                        for i in range(0, len(entries), 100):
                            batch = entries[i:i + 100]
                            stats = await enrich_deezer_batch(session, batch, pool, s3, existing_isrcs)
                            total_enriched += stats.get("enriched", 0)
                            total_errors += stats.get("errors", 0)
                            session.commit()
                            logger.info("Deezer enrich progress: %d/%d", min(i + 100, len(entries)), len(entries))

                        return {"enriched": total_enriched, "errors": total_errors}

            try:
                stats = asyncio.run(_async_enrich())
            except Exception as e:
                logger.error("enrich_catalog failed: %s", e)
                stats = {"enriched": 0, "errors": 1}

            clog.set_stats(stats)

    return stats


@celery_app.task(name="workers.tasks.sync_artists", bind=True)
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
    from workers.db import get_engine

    from workers.crawl_logger import CrawlLogger

    FEAT_RE = re.compile(r"\s+(?:feat\.?|featuring|ft\.?|vs\.?)\s+", flags=re.IGNORECASE)
    engine = get_engine()

    # Start crawl log (running) — manual enter/exit to avoid re-indenting the entire body
    _log_session = Session(engine)
    _clog = CrawlLogger(_log_session, task_type="sync_artists", celery_task_id=self.request.id)
    _clog.__enter__()
    _clog_exc = None

    created = 0
    flagged = 0
    skipped = 0

    # Collect names needing Deezer disambiguation
    needs_deezer = []  # list of (raw_string, tokens, rule_type)

    try:
      with Session(engine) as session:
        all_strings = [r[0] for r in session.execute(
            select(CatalogEntry.artist).distinct().where(CatalogEntry.artist.isnot(None))
        ).all()]

        known_norms = set(r[0] for r in session.execute(select(Artist.normalized_name)).all())
        known_norms |= set(r[0] for r in session.execute(select(ArtistAlias.normalized_alias)).all())
        already_flagged = set(r[0] for r in session.execute(select(ArtistFlag.raw_artist_string)).all())

        def _get_or_create(name):
            nonlocal created
            norm = normalize(name)
            if norm in known_norms:
                artist = session.execute(select(Artist).where(Artist.normalized_name == norm)).scalar_one_or_none()
                if artist and name.strip() != artist.name:
                    _ensure_alias(artist, name.strip())
                return artist
            alias = session.execute(select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)).scalar_one_or_none()
            if alias:
                return session.get(Artist, alias.artist_id)
            artist = Artist(name=name, normalized_name=norm, created_at=datetime.now(timezone.utc))
            session.add(artist)
            session.flush()
            known_norms.add(norm)
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
            session.add(ArtistAlias(artist_id=artist.id, alias=alias_name, normalized_alias=norm))
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

            # Rule 1: feat / featuring / ft / vs — always split locally
            if FEAT_RE.search(raw):
                for name in [p.strip() for p in FEAT_RE.split(raw) if p.strip()]:
                    _get_or_create(name)
                    created += 1
                batch_count += 1
                if batch_count % 50 == 0:
                    session.commit()
                continue

            # Rule 2: comma — if any token known, resolve locally
            if "," in raw:
                tokens = [p.strip() for p in raw.split(",") if p.strip()]
                if any(normalize(t) in known_norms for t in tokens):
                    for name in tokens:
                        _get_or_create(name)
                        created += 1
                    batch_count += 1
                    if batch_count % 50 == 0:
                        session.commit()
                else:
                    needs_deezer.append((raw, tokens, "comma"))
                continue

            # Rule 3: ampersand — if any token known, resolve locally
            if " & " in raw:
                tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
                if any(normalize(t) in known_norms for t in tokens):
                    for name in tokens:
                        _get_or_create(name)
                        created += 1
                    batch_count += 1
                    if batch_count % 50 == 0:
                        session.commit()
                    continue
                needs_deezer.append((raw, tokens, "ampersand"))
                continue

            # Rule 4: no separator — create directly
            _get_or_create(raw)
            created += 1
            batch_count += 1
            if batch_count % 50 == 0:
                session.commit()

        session.commit()

    # Phase B: Deezer disambiguation (concurrent)
    if needs_deezer:
        async def _deezer_resolve():
            nonlocal created, flagged
            import unicodedata
            from workers.rate_limiter import RateLimiter
            from workers.async_http import HttpPool

            def _norm(s):
                s = unicodedata.normalize("NFKD", s.lower().strip())
                return s.encode("ascii", "ignore").decode()

            async def _deezer_artist_id(pool, name):
                data = await pool.deezer_get("/search/artist", params={"q": name, "limit": 10})
                name_norm = _norm(name)
                for hit in data.get("data", []):
                    dz_name = hit.get("name", "")
                    if dz_name.lower() == name.lower() or _norm(dz_name) == name_norm:
                        return str(hit["id"])
                return None

            limiter = RateLimiter()
            async with HttpPool(limiter) as pool:
                with Session(engine) as session:
                    # Re-load known_norms
                    known = set(r[0] for r in session.execute(select(Artist.normalized_name)).all())
                    known |= set(r[0] for r in session.execute(select(ArtistAlias.normalized_alias)).all())

                    for raw, tokens, rule_type in needs_deezer:
                        # Concurrent Deezer lookups for all tokens
                        deezer_ids = {}
                        tasks_list = []
                        names_to_search = list(tokens)
                        if rule_type == "ampersand":
                            names_to_search = [raw] + list(tokens)

                        for name in names_to_search:
                            tasks_list.append(_deezer_artist_id(pool, name))
                        results = await asyncio.gather(*tasks_list)

                        for name, dz_id in zip(names_to_search, results):
                            deezer_ids[name] = dz_id

                        if rule_type == "comma":
                            if all(deezer_ids.get(t) is not None for t in tokens):
                                for name in tokens:
                                    norm = normalize(name)
                                    if norm not in known:
                                        a = Artist(name=name, normalized_name=norm, created_at=datetime.now(timezone.utc))
                                        session.add(a)
                                        session.flush()
                                        known.add(norm)
                                        if deezer_ids.get(name):
                                            a.deezer_id = deezer_ids[name]
                                    created += 1
                            else:
                                session.add(ArtistFlag(
                                    raw_artist_string=raw, reason="comma_unresolved",
                                    tokens=tokens, deezer_ids=deezer_ids, status="pending",
                                    created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                                ))
                                flagged += 1

                        elif rule_type == "ampersand":
                            deezer_full = deezer_ids.get(raw)
                            full_found = deezer_full is not None
                            tokens_found = all(deezer_ids.get(t) is not None for t in tokens)

                            if full_found and not tokens_found:
                                norm = normalize(raw)
                                if norm not in known:
                                    a = Artist(name=raw, normalized_name=norm, created_at=datetime.now(timezone.utc))
                                    a.deezer_id = deezer_full
                                    session.add(a)
                                    session.flush()
                                    known.add(norm)
                                created += 1
                            elif tokens_found and not full_found:
                                for name in tokens:
                                    norm = normalize(name)
                                    if norm not in known:
                                        a = Artist(name=name, normalized_name=norm, created_at=datetime.now(timezone.utc))
                                        if deezer_ids.get(name):
                                            a.deezer_id = deezer_ids[name]
                                        session.add(a)
                                        session.flush()
                                        known.add(norm)
                                    created += 1
                            else:
                                reason = "ampersand_ambiguous" if (full_found and tokens_found) else "ampersand_unknown"
                                session.add(ArtistFlag(
                                    raw_artist_string=raw, reason=reason,
                                    tokens=tokens, deezer_ids=deezer_ids, status="pending",
                                    created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                                ))
                                flagged += 1

                        session.commit()

        try:
            asyncio.run(_deezer_resolve())
        except Exception as e:
            logger.error("Deezer artist disambiguation failed: %s", e)

    except Exception as exc:
        _clog_exc = exc
        raise
    finally:
        result = {"created": created, "flagged": flagged, "skipped": skipped}
        _clog.set_stats(result)
        if _clog_exc:
            _clog.__exit__(type(_clog_exc), _clog_exc, _clog_exc.__traceback__)
        else:
            _clog.__exit__(None, None, None)
        _log_session.close()

    return result


@celery_app.task(name="workers.tasks.fetch_artist_artworks", bind=True)
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
    from deezer_enrich import _get_s3, _ensure_bucket
    from workers.db import get_engine

    from workers.crawl_logger import CrawlLogger

    ARTIST_BUCKET = "artist-artworks"
    engine = get_engine()
    s3 = _get_s3()
    _ensure_bucket(s3, ARTIST_BUCKET)

    _log_session = Session(engine)
    _clog = CrawlLogger(_log_session, task_type="fetch_artworks", celery_task_id=self.request.id)
    _clog.__enter__()

    async def _async_fetch():
        from workers.rate_limiter import RateLimiter
        from workers.async_http import HttpPool

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
                no_id_artists = session.execute(
                    select(Artist).where(Artist.deezer_id.is_(None))
                ).scalars().all()

                used_ids = set(
                    row[0] for row in session.execute(
                        select(Artist.deezer_id).where(Artist.deezer_id.isnot(None))
                    ).all()
                )

                async def _link_one(artist):
                    nonlocal linked, skipped
                    data = await pool.deezer_get("/search/artist", params={"q": artist.name, "limit": 10})
                    name_norm = _norm(artist.name)
                    for hit in data.get("data", []):
                        dz_name = hit.get("name", "")
                        if dz_name.lower() == artist.name.lower() or _norm(dz_name) == name_norm:
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
                artists_needing_art = session.execute(
                    select(Artist).where(
                        Artist.deezer_id.isnot(None),
                        Artist.deezer_id != "NOT_FOUND",
                        Artist.has_artwork == False,  # noqa: E712
                    )
                ).scalars().all()

                async def _fetch_one(artist):
                    nonlocal fetched, skipped
                    data = await pool.deezer_get(f"/artist/{artist.deezer_id}")
                    pic_url = data.get("picture_xl") or data.get("picture_big") or data.get("picture")
                    if not pic_url:
                        skipped += 1
                        return
                    img_data = await pool.download_image(pic_url)
                    if img_data:
                        import tempfile
                        try:
                            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                                f.write(img_data)
                                tmp = f.name
                            s3.upload_file(tmp, ARTIST_BUCKET, f"{artist.id}.jpg", ExtraArgs={"ContentType": "image/jpeg"})
                            artist.has_artwork = True
                            fetched += 1
                        except Exception:
                            skipped += 1
                        finally:
                            try:
                                os.unlink(tmp)
                            except Exception:
                                pass
                    else:
                        skipped += 1

                await asyncio.gather(*[_fetch_one(a) for a in artists_needing_art])
                session.commit()

        return {"linked": linked, "fetched": fetched, "skipped": skipped}

    try:
        result = asyncio.run(_async_fetch())
    except Exception as e:
        logger.error("fetch_artist_artworks failed: %s", e)
        result = {"linked": 0, "fetched": 0, "skipped": 0, "error": str(e)}

    _clog.set_stats(result)
    if "error" in result:
        exc = Exception(result["error"])
        _clog.__exit__(type(exc), exc, None)
    else:
        _clog.__exit__(None, None, None)
    _log_session.close()

    return result


@celery_app.task(name="workers.tasks.link_set_artists")
def link_set_artists():
    """
    Parse set titles to extract artist names and link them to the artists table.
    Matches against known artists (by name and aliases). Idempotent.
    """
    import re as _re
    from sqlalchemy import select, func
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
                r[0] for r in session.execute(
                    select(SetArtist.artist_id).where(SetArtist.set_id == dj_set.id)
                ).all()
            }

            for aid in matched_ids:
                if aid in existing:
                    skipped += 1
                    continue
                role = "b2b" if is_b2b else "dj"
                session.add(SetArtist(
                    set_id=dj_set.id,
                    artist_id=aid,
                    role=role,
                    position=0,
                ))
                linked += 1

            session.commit()

    return {"linked": linked, "skipped": skipped}


@celery_app.task(name="workers.tasks.crawl_followed_sets")
def crawl_followed_sets():
    """
    Re-crawl followed sets whose tracklist is not 100% identified.
    Skips sets crawled < 12h ago.
    After re-import, resolves unlinked tracks via catalog matching + Deezer enrichment.
    """
    import asyncio
    from datetime import datetime, timezone
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import DJSet, SetTrack, UserSetFollow
    from workers.db import get_engine

    engine = get_engine()

    sets_to_crawl = []
    skipped_complete = 0
    skipped_recent = 0

    with Session(engine) as session:
        followed_ids = {
            r[0] for r in session.execute(
                select(UserSetFollow.set_id).distinct()
            ).all()
        }

        if not followed_ids:
            return {"crawled": 0, "skipped_complete": 0, "skipped_recent": 0}

        for sid in followed_ids:
            dj_set = session.get(DJSet, sid)
            if not dj_set or dj_set.source != "trackid":
                continue

            total = session.execute(
                select(func.count(SetTrack.id)).where(SetTrack.set_id == sid)
            ).scalar() or 0
            identified = session.execute(
                select(func.count(SetTrack.id)).where(
                    SetTrack.set_id == sid,
                    SetTrack.is_id.is_(False),
                    SetTrack.catalog_id.isnot(None),
                )
            ).scalar() or 0

            if total > 0 and identified >= total:
                skipped_complete += 1
                continue

            if dj_set.last_crawled_at:
                age_h = (datetime.now(timezone.utc) - dj_set.last_crawled_at).total_seconds() / 3600
                if age_h < 12:
                    skipped_recent += 1
                    continue

            sets_to_crawl.append({"ext_id": dj_set.external_id, "slug": dj_set.external_slug})

    if not sets_to_crawl:
        return {"crawled": 0, "skipped_complete": skipped_complete, "skipped_recent": skipped_recent}

    async def _crawl_all():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker as async_sessionmaker
        from trackid.client import TrackIDClient
        from trackid.importer import import_audiostream

        async_engine = create_async_engine(os.environ["DATABASE_URL"])
        AsyncS = async_sessionmaker(async_engine, class_=AsyncSession)
        crawled = 0

        async with TrackIDClient() as client:
            for info in sets_to_crawl:
                if not info["slug"]:
                    continue
                try:
                    async with AsyncS() as db:
                        audiostream = {"id": info["ext_id"], "slug": info["slug"]}
                        result, track_count = await import_audiostream(
                            db, client, audiostream, min_age_hours=0
                        )
                        if result and track_count > 0:
                            crawled += 1
                        await db.commit()
                    await asyncio.sleep(1.5)
                except Exception:
                    pass

        await async_engine.dispose()
        return crawled

    crawled = asyncio.run(_crawl_all())

    # Trigger track resolution for updated sets
    resolve_set_tracks.delay()

    return {
        "crawled": crawled,
        "skipped_complete": skipped_complete,
        "skipped_recent": skipped_recent,
    }


@celery_app.task(name="workers.tasks.enrich_catalog_beatport", bind=True)
def enrich_catalog_beatport(self, batch_size: int = 0):
    """
    Enrichit les entrées catalog via Beatport (concurrent async scraping).
    Uses 2 concurrent scrapers with Redis caching.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from deezer_enrich import _get_s3, _ensure_bucket
    from workers.db import get_engine

    engine = get_engine()
    s3 = _get_s3()
    _ensure_bucket(s3)

    from workers.crawl_logger import CrawlLogger

    with Session(engine) as log_session:
        with CrawlLogger(log_session, task_type="enrich_beatport",
                         source="beatport", celery_task_id=self.request.id) as clog:

            async def _async_enrich():
                from workers.rate_limiter import RateLimiter
                from workers.async_http import HttpPool
                from workers.enrichment import enrich_beatport_batch

                limiter = RateLimiter()
                total_enriched = 0
                total_not_found = 0
                total_errors = 0

                async with HttpPool(limiter) as pool:
                    with Session(engine) as session:
                        query = (
                            select(CatalogEntry).where(
                                CatalogEntry.beatport_id.is_(None),
                                CatalogEntry.beatport_searched_at.is_(None),
                            ).order_by(CatalogEntry.id)
                        )
                        if batch_size > 0:
                            query = query.limit(batch_size)
                        entries = session.execute(query).scalars().all()
                        total = len(entries)

                        if not entries:
                            return {"enriched": 0, "not_found": 0, "errors": 0, "total": 0}

                        for i in range(0, len(entries), 50):
                            batch = entries[i:i + 50]
                            stats = await enrich_beatport_batch(session, batch, pool, s3)
                            total_enriched += stats.get("enriched", 0)
                            total_not_found += stats.get("not_found", 0)
                            total_errors += stats.get("errors", 0)
                            session.commit()
                            logger.info("Beatport enrich progress: %d/%d", min(i + 50, total), total)

                        return {"enriched": total_enriched, "not_found": total_not_found, "errors": total_errors, "total": total}

            try:
                result = asyncio.run(_async_enrich())
            except Exception as e:
                logger.error("enrich_catalog_beatport failed: %s", e)
                result = {"enriched": 0, "not_found": 0, "errors": 1, "total": 0}

            clog.set_stats(result)

    return result


