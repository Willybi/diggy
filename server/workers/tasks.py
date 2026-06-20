"""
Celery tasks for Diggy.
Main task: import a Rekordbox database into PostgreSQL.
"""
import os
import sys
import time
import requests
from workers.celery_app import celery_app

API_BASE = os.environ.get("DIGGY_API_URL", "http://api:8000")
DEEZER_API = "https://api.deezer.com"


@celery_app.task(name="workers.tasks.crawl_radar")
def crawl_radar():
    """
    Crawl toutes les playlists surveillées (Deezer, TIDAL, Spotify).
    Délègue chaque playlist à crawl_single_playlist pour enrichissement inline.
    """
    import logging
    from workers.source_clients import get_fetchers

    logger = logging.getLogger(__name__)
    playlists = requests.get(f"{API_BASE}/api/watchlist/", timeout=10).json()
    crawled = 0
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
            crawl_single_playlist(pl["id"])
            crawled += 1
        except Exception as e:
            logger.error("crawl_single_playlist failed for %s/%s: %s", source, pl["id"], e)
            errors += 1

    return {"crawled": crawled, "skipped_playlists": skipped, "errors": errors}


@celery_app.task(name="workers.tasks.crawl_single_playlist")
def crawl_single_playlist(playlist_id: int):
    """
    Crawl une seule playlist (Deezer, TIDAL, ou Spotify) par son watched_entity ID.
    Insere les tracks via l'API, puis enrichit les nouvelles entrees catalog
    via Deezer cross-search (deezer_id, artwork, preview, duration).
    """
    import logging
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry, RadarTrack, WatchedEntity
    from deezer_enrich import enrich_entry, search_deezer, upload_cover_from_url, _get_s3, _ensure_bucket
    from workers.source_clients import get_fetchers

    logger = logging.getLogger(__name__)

    pl = requests.get(f"{API_BASE}/api/watchlist/browse", timeout=10).json()
    target = next((p for p in pl if p["id"] == playlist_id), None)
    if not target:
        return {"error": "playlist not found"}

    source = target["source"]
    try:
        fetch_meta, fetch_tracks, _ = get_fetchers(source)
    except ValueError:
        return {"error": f"unknown source: {source}"}

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)
    s3 = _get_s3()
    _ensure_bucket(s3)

    # 0. Fetch playlist metadata + update entity
    meta = fetch_meta(target["external_id"])

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
                if upload_cover_from_url(s3, meta.cover_url, f"playlist-{playlist_id}"):
                    entity.has_artwork = True
            session.commit()

    # 1. Fetch all tracks from source
    source_tracks = fetch_tracks(target["external_id"])

    # 2. Insert radar tracks via API (handles dedup + catalog creation)
    inserted = 0
    for st in source_tracks:
        payload = {
            "watched_playlist_id": target["id"],
            "external_track_id": st.external_id,
            "source": source,
            "title": st.title,
            "artist": st.artist,
            "isrc": st.isrc,
        }
        r = requests.post(f"{API_BASE}/api/radar/", json=payload, timeout=10)
        if r.status_code == 201:
            inserted += 1

    # 3. Enrich catalog entries that lack deezer_id
    enriched = 0
    with Session(engine) as session:
        existing_isrcs = {r[0] for r in session.execute(
            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
        ).all()}

        radar_rows = session.execute(
            select(RadarTrack.external_track_id, RadarTrack.catalog_id)
            .where(RadarTrack.watched_entity_id == playlist_id)
        ).all()

        catalog_ids = {row.catalog_id for row in radar_rows if row.catalog_id}

        entries = session.execute(
            select(CatalogEntry).where(
                CatalogEntry.id.in_(catalog_ids),
                CatalogEntry.deezer_id.is_(None),
            )
        ).scalars().all()

        if source == "deezer":
            # For Deezer: we have the external_track_id which IS the deezer track id
            ext_to_catalog = {row.external_track_id: row.catalog_id for row in radar_rows}
            catalog_to_ext = {}
            for ext_id, cat_id in ext_to_catalog.items():
                if cat_id:
                    catalog_to_ext[cat_id] = ext_id

            for entry in entries:
                ext_id = catalog_to_ext.get(entry.id)
                if not ext_id:
                    continue
                dz_resp = requests.get(f"{DEEZER_API}/track/{ext_id}", timeout=10).json()
                if dz_resp.get("id") and enrich_entry(entry, dz_resp, s3=s3, _known_isrcs=existing_isrcs):
                    enriched += 1
                time.sleep(0.12)
        else:
            # For TIDAL/Spotify: cross-search via Deezer by artist+title
            for entry in entries:
                dz_hit = search_deezer(entry.artist, entry.title)
                if dz_hit and enrich_entry(entry, dz_hit, s3=s3, _known_isrcs=existing_isrcs):
                    enriched += 1
                time.sleep(0.15)

        session.commit()

    # 4. Enrich via Beatport (BPM, key, label) for entries still missing beatport_id
    bp_enriched = 0
    try:
        from beatport.client import BeatportClient
        from beatport.enrich import enrich_from_beatport

        bp_client = BeatportClient()
        with Session(engine) as session:
            bp_entries = session.execute(
                select(CatalogEntry).where(
                    CatalogEntry.id.in_(catalog_ids),
                    CatalogEntry.beatport_id.is_(None),
                )
            ).scalars().all()
            for entry in bp_entries:
                try:
                    bp_track = None
                    if entry.isrc:
                        bp_track = bp_client.search_track_by_isrc(entry.isrc)
                    if not bp_track:
                        bp_track_list = bp_client.search_track(entry.title, entry.artist)
                        if bp_track_list:
                            bp_track = bp_track_list[0]
                    if bp_track and enrich_from_beatport(entry, bp_track, s3=s3):
                        bp_enriched += 1
                except Exception as e:
                    logger.warning("Beatport enrich failed for catalog %s: %s", entry.id, e)
            session.commit()
    except Exception as e:
        logger.warning("Beatport enrichment step skipped: %s", e)

    requests.patch(f"{API_BASE}/api/watchlist/{target['id']}/crawled", timeout=10)
    return {
        "playlist_id": playlist_id,
        "source": source,
        "title": target.get("title") or meta.title,
        "inserted": inserted,
        "enriched": enriched,
        "bp_enriched": bp_enriched,
        "total_tracks": len(source_tracks),
    }


@celery_app.task(name="workers.tasks.check_previews")
def check_previews():
    """
    Vérifie chaque semaine si les tracks catalog ont une preview Deezer dispo.
    Met à jour has_preview dans les deux sens (True/False).
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry, RadarTrack

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

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


@celery_app.task(name="workers.tasks.resolve_set_tracks")
def resolve_set_tracks():
    """
    Résout les set_tracks sans catalog_id.
    Pour chaque set_track non-ID avec raw_title :
    1. Cherche dans catalog par normalized_key
    2. Si absent, crée une entrée catalog
    3. Lie le set_track au catalog
    4. Enrichit via Deezer (deezer_id, isrc, duration, preview, cover)
    Idempotent : ne touche pas les tracks déjà résolus.
    """
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import SetTrack, CatalogEntry
    from utils import make_normalized_key
    from deezer_enrich import search_deezer, enrich_entry, _get_s3, _ensure_bucket

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

    s3 = _get_s3()
    _ensure_bucket(s3)

    resolved = 0
    created = 0
    enriched = 0
    with Session(engine) as session:
        # Preload ISRCs to avoid unique constraint violations
        existing_isrcs = {r[0] for r in session.execute(
            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
        ).all()}

        tracks = session.execute(
            select(SetTrack).where(
                SetTrack.catalog_id.is_(None),
                SetTrack.is_id == False,  # noqa: E712
                SetTrack.raw_title.isnot(None),
            )
        ).scalars().all()

        for st in tracks:
            norm_key = make_normalized_key(st.raw_title, st.raw_artist)

            entry = session.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
            ).scalar_one_or_none()

            is_new = False
            if not entry:
                entry = CatalogEntry(
                    title=st.raw_title,
                    artist=st.raw_artist,
                    normalized_key=norm_key,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(entry)
                session.flush()
                created += 1
                is_new = True

            st.catalog_id = entry.id
            resolved += 1

            # Enrich new entries or entries missing deezer_id
            if is_new or not entry.deezer_id:
                hit = search_deezer(st.raw_artist, st.raw_title)
                if hit and enrich_entry(entry, hit, s3=s3, _known_isrcs=existing_isrcs):
                    enriched += 1
                time.sleep(0.12)

        session.commit()

    # Beatport enrichment for entries still missing beatport_id
    bp_enriched = 0
    try:
        from beatport.client import BeatportClient
        from beatport.enrich import enrich_from_beatport

        bp_client = BeatportClient()
        with Session(engine) as session:
            bp_entries = session.execute(
                select(CatalogEntry).where(
                    CatalogEntry.beatport_id.is_(None),
                    CatalogEntry.id.in_(
                        select(SetTrack.catalog_id).where(SetTrack.catalog_id.isnot(None))
                    ),
                )
            ).scalars().all()
            for entry in bp_entries:
                try:
                    bp_track = None
                    if entry.isrc:
                        bp_track = bp_client.search_track_by_isrc(entry.isrc)
                    if not bp_track:
                        bp_track_list = bp_client.search_track(entry.title, entry.artist)
                        if bp_track_list:
                            bp_track = bp_track_list[0]
                    if bp_track and enrich_from_beatport(entry, bp_track, s3=s3):
                        bp_enriched += 1
                except Exception as e:
                    logger.warning("Beatport enrich failed for catalog %s: %s", entry.id, e)
            session.commit()
    except Exception as e:
        logger.warning("Beatport enrichment step skipped: %s", e)

    return {"resolved": resolved, "catalog_created": created, "enriched": enriched, "bp_enriched": bp_enriched}


@celery_app.task(name="workers.tasks.enrich_catalog")
def enrich_catalog():
    """
    Enrichit les entrées catalog sans deezer_id via l'API Deezer.
    Remplit : deezer_id, isrc, duration_ms, has_preview, has_artwork (+ cover).
    Hebdomadaire, rate-limited.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from deezer_enrich import search_deezer, enrich_entry, _get_s3, _ensure_bucket

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

    s3 = _get_s3()
    _ensure_bucket(s3)

    enriched = 0
    not_found = 0
    with Session(engine) as session:
        # Preload ISRCs to avoid unique constraint violations
        existing_isrcs = {r[0] for r in session.execute(
            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
        ).all()}

        entries = session.execute(
            select(CatalogEntry).where(CatalogEntry.deezer_id.is_(None))
            .order_by(CatalogEntry.id)
        ).scalars().all()

        for i, entry in enumerate(entries):
            try:
                hit = search_deezer(entry.artist, entry.title)
            except Exception:
                time.sleep(0.5)
                continue

            if hit and enrich_entry(entry, hit, s3=s3, _known_isrcs=existing_isrcs):
                enriched += 1
            else:
                not_found += 1

            time.sleep(0.12)

            if (i + 1) % 100 == 0:
                session.commit()

        session.commit()

    return {"enriched": enriched, "not_found": not_found}


@celery_app.task(name="workers.tasks.sync_artists")
def sync_artists():
    """
    Sync artists from catalog.artist strings into the artists table.
    Idempotent — safe to re-run.
    """
    import re
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, ArtistFlag, CatalogEntry
    from utils import normalize
    from deezer_enrich import _get_s3, upload_image_to_bucket

    FEAT_RE = re.compile(r"\s+(?:feat\.?|featuring|ft\.?|vs\.?)\s+", flags=re.IGNORECASE)
    RATE_LIMIT = 0.12
    ARTIST_BUCKET = "artist-artworks"

    s3 = _get_s3()
    existing_buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if ARTIST_BUCKET not in existing_buckets:
        s3.create_bucket(Bucket=ARTIST_BUCKET)
        s3.put_bucket_policy(
            Bucket=ARTIST_BUCKET,
            Policy=(
                f'{{"Version":"2012-10-17","Statement":[{{"Effect":"Allow",'
                f'"Principal":"*","Action":"s3:GetObject",'
                f'"Resource":"arn:aws:s3:::{ARTIST_BUCKET}/*"}}]}}'
            ),
        )

    def _norm(s):
        import unicodedata
        s = unicodedata.normalize("NFKD", s.lower().strip())
        return s.encode("ascii", "ignore").decode()

    def _deezer_artist_id(name):
        try:
            resp = requests.get(
                "https://api.deezer.com/search/artist",
                params={"q": name, "limit": 10},
                timeout=5,
            )
            name_norm = _norm(name)
            for hit in resp.json().get("data", []):
                dz_name = hit.get("name", "")
                if dz_name.lower() == name.lower() or _norm(dz_name) == name_norm:
                    return str(hit["id"])
        except Exception:
            pass
        return None

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

    created = 0
    flagged = 0
    skipped = 0

    with Session(engine) as session:
        # Load all distinct catalog artist strings
        all_strings = [r[0] for r in session.execute(
            select(CatalogEntry.artist).distinct().where(CatalogEntry.artist.isnot(None))
        ).all()]

        # Build known normalized names set
        known_norms = set(r[0] for r in session.execute(select(Artist.normalized_name)).all())
        known_norms |= set(r[0] for r in session.execute(select(ArtistAlias.normalized_alias)).all())

        # Load already-flagged strings
        already_flagged = set(r[0] for r in session.execute(select(ArtistFlag.raw_artist_string)).all())

        def _get_or_create(name):
            norm = normalize(name)
            if norm in known_norms:
                artist = session.execute(select(Artist).where(Artist.normalized_name == norm)).scalar_one_or_none()
                # If found but name differs, ensure alias for this variant
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

        def _fetch_artwork(artist):
            """Fetch and store Deezer artist image if deezer_id is set and artwork missing."""
            if not artist or not artist.deezer_id or artist.has_artwork:
                return
            try:
                resp = requests.get(f"https://api.deezer.com/artist/{artist.deezer_id}", timeout=5)
                data = resp.json()
                pic_url = data.get("picture_xl") or data.get("picture_big") or data.get("picture")
                if pic_url and upload_image_to_bucket(s3, pic_url, f"{artist.id}.jpg", ARTIST_BUCKET):
                    artist.has_artwork = True
            except Exception:
                pass
            time.sleep(RATE_LIMIT)

        def _ensure_alias(artist, alias_name):
            """Create alias if normalized forms differ and alias doesn't exist yet."""
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

        def _flag(raw, reason, tokens, deezer_ids):
            flag = ArtistFlag(
                raw_artist_string=raw,
                reason=reason,
                tokens=tokens,
                deezer_ids=deezer_ids,
                status="pending",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(flag)
            already_flagged.add(raw)
            session.flush()

        for raw in all_strings:
            raw = raw.strip()
            if not raw:
                continue
            norm = normalize(raw)
            if norm in known_norms or raw in already_flagged:
                skipped += 1
                continue

            # Rule 1: feat / featuring / ft / vs
            if FEAT_RE.search(raw):
                for name in [p.strip() for p in FEAT_RE.split(raw) if p.strip()]:
                    _get_or_create(name)
                    created += 1
                session.commit()
                continue

            # Rule 2: comma
            if "," in raw:
                tokens = [p.strip() for p in raw.split(",") if p.strip()]
                if any(normalize(t) in known_norms for t in tokens):
                    for name in tokens:
                        _get_or_create(name)
                        created += 1
                    session.commit()
                else:
                    deezer_ids = {}
                    for t in tokens:
                        deezer_ids[t] = _deezer_artist_id(t)
                        time.sleep(RATE_LIMIT)
                    if all(deezer_ids[t] is not None for t in tokens):
                        for name in tokens:
                            a = _get_or_create(name)
                            if a and not a.deezer_id and deezer_ids.get(name):
                                a.deezer_id = deezer_ids[name]
                                _fetch_artwork(a)
                            created += 1
                        session.commit()
                    else:
                        _flag(raw, "comma_unresolved", tokens, deezer_ids)
                        session.commit()
                        flagged += 1
                continue

            # Rule 3: ampersand
            if " & " in raw:
                tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
                if any(normalize(t) in known_norms for t in tokens):
                    for name in tokens:
                        _get_or_create(name)
                        created += 1
                    session.commit()
                    continue
                deezer_full = _deezer_artist_id(raw)
                time.sleep(RATE_LIMIT)
                deezer_ids = {raw: deezer_full}
                for t in tokens:
                    deezer_ids[t] = _deezer_artist_id(t)
                    time.sleep(RATE_LIMIT)
                full_found = deezer_full is not None
                tokens_found = all(deezer_ids[t] is not None for t in tokens)
                if full_found and not tokens_found:
                    a = _get_or_create(raw)
                    if a and not a.deezer_id:
                        a.deezer_id = deezer_full
                        _fetch_artwork(a)
                    session.commit()
                    created += 1
                elif tokens_found and not full_found:
                    for name in tokens:
                        a = _get_or_create(name)
                        if a and not a.deezer_id and deezer_ids.get(name):
                            a.deezer_id = deezer_ids[name]
                            _fetch_artwork(a)
                        created += 1
                    session.commit()
                else:
                    reason = "ampersand_ambiguous" if (full_found and tokens_found) else "ampersand_unknown"
                    _flag(raw, reason, tokens, deezer_ids)
                    session.commit()
                    flagged += 1
                continue

            # Rule 4: no separator
            _get_or_create(raw)
            session.commit()
            created += 1

    return {"created": created, "flagged": flagged, "skipped": skipped}


@celery_app.task(name="workers.tasks.fetch_artist_artworks")
def fetch_artist_artworks():
    """
    One-shot + idempotent: fetch Deezer artist images for all artists with a deezer_id.
    Uploads to MinIO bucket 'artist-artworks' as {artist_id}.jpg.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist
    from deezer_enrich import _get_s3, upload_image_to_bucket

    ARTIST_BUCKET = "artist-artworks"

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)
    s3 = _get_s3()

    # Ensure bucket exists and is public
    existing_buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if ARTIST_BUCKET not in existing_buckets:
        s3.create_bucket(Bucket=ARTIST_BUCKET)
        s3.put_bucket_policy(
            Bucket=ARTIST_BUCKET,
            Policy=(
                f'{{"Version":"2012-10-17","Statement":[{{"Effect":"Allow",'
                f'"Principal":"*","Action":"s3:GetObject",'
                f'"Resource":"arn:aws:s3:::{ARTIST_BUCKET}/*"}}]}}'
            ),
        )

    fetched = 0
    linked = 0
    skipped = 0

    def _norm(s):
        import unicodedata
        s = unicodedata.normalize("NFKD", s.lower().strip())
        return s.encode("ascii", "ignore").decode()

    def _search_deezer_artist(name):
        try:
            resp = requests.get(
                "https://api.deezer.com/search/artist",
                params={"q": name, "limit": 10},
                timeout=5,
            )
            name_norm = _norm(name)
            for hit in resp.json().get("data", []):
                dz_name = hit.get("name", "")
                if dz_name.lower() == name.lower() or _norm(dz_name) == name_norm:
                    return str(hit["id"])
        except Exception:
            pass
        return None

    def _fetch_pic(deezer_id):
        try:
            resp = requests.get(f"https://api.deezer.com/artist/{deezer_id}", timeout=5)
            data = resp.json()
            return data.get("picture_xl") or data.get("picture_big") or data.get("picture")
        except Exception:
            return None

    with Session(engine) as session:
        # Pass 1: artists without deezer_id → search Deezer
        no_id_artists = session.execute(
            select(Artist).where(Artist.deezer_id.is_(None))
        ).scalars().all()

        for artist in no_id_artists:
            deezer_id = _search_deezer_artist(artist.name)
            time.sleep(0.12)
            if deezer_id:
                artist.deezer_id = deezer_id
                linked += 1
            else:
                skipped += 1

        session.commit()

        # Pass 2: all artists with a real deezer_id but no artwork
        artists_needing_art = session.execute(
            select(Artist).where(
                Artist.deezer_id.isnot(None),
                Artist.deezer_id != "NOT_FOUND",
                Artist.has_artwork == False,  # noqa: E712
            )
        ).scalars().all()

        for artist in artists_needing_art:
            pic_url = _fetch_pic(artist.deezer_id)
            time.sleep(0.12)
            if pic_url and upload_image_to_bucket(s3, pic_url, f"{artist.id}.jpg", ARTIST_BUCKET):
                artist.has_artwork = True
                fetched += 1
            else:
                skipped += 1

        session.commit()

    return {"linked": linked, "fetched": fetched, "skipped": skipped}


@celery_app.task(name="workers.tasks.link_set_artists")
def link_set_artists():
    """
    Parse set titles to extract artist names and link them to the artists table.
    Matches against known artists (by name and aliases). Idempotent.
    """
    import re as _re
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, DJSet, SetArtist
    from utils import normalize

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

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


@celery_app.task(name="workers.tasks.populate_artist_genres")
def populate_artist_genres():
    """
    Infer artist genres from their catalog tracks' genres.
    For each artist, find catalog entries matching name/aliases,
    aggregate catalog_genres, and assign genres appearing in >=20% of tracks.
    Idempotent (clears and repopulates).
    """
    from sqlalchemy import create_engine, select, func, delete as sa_delete
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import Artist, ArtistAlias, CatalogEntry, Genre, artist_genres, catalog_genres
    from utils import normalize

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

    with Session(engine) as session:
        # Load all genres
        genres_by_id = {g.id: g.name for g in session.execute(select(Genre)).scalars().all()}
        if not genres_by_id:
            return {"updated": 0}

        # Load all artists + aliases
        artists = session.execute(select(Artist)).scalars().all()
        aliases = session.execute(select(ArtistAlias)).scalars().all()

        # Build artist_id → set of lowercase names
        artist_names: dict[int, set[str]] = {}
        for a in artists:
            artist_names.setdefault(a.id, set()).add(a.name.lower())
        for al in aliases:
            artist_names.setdefault(al.artist_id, set()).add(al.alias.lower())

        # Build catalog.artist (lower) → list of catalog_ids
        cat_result = session.execute(select(CatalogEntry.id, CatalogEntry.artist))
        cat_by_artist: dict[str, list[int]] = {}
        for cid, cart in cat_result.all():
            if cart:
                cat_by_artist.setdefault(cart.lower(), []).append(cid)

        # Load catalog_genres as catalog_id → set of genre_ids
        cg_result = session.execute(select(catalog_genres))
        cat_genre_map: dict[int, set[int]] = {}
        for row in cg_result.all():
            cat_genre_map.setdefault(row[0], set()).add(row[1])

        # Clear existing artist_genres
        session.execute(sa_delete(artist_genres))

        updated = 0
        for a in artists:
            names = artist_names.get(a.id, set())
            # Collect all catalog_ids for this artist
            cat_ids = []
            for n in names:
                cat_ids.extend(cat_by_artist.get(n, []))
            if not cat_ids:
                continue

            # Count genre occurrences
            genre_counts: dict[int, int] = {}
            for cid in cat_ids:
                for gid in cat_genre_map.get(cid, set()):
                    genre_counts[gid] = genre_counts.get(gid, 0) + 1

            total = len(cat_ids)
            threshold = max(1, int(total * 0.2))  # >=20% of tracks

            assigned = []
            for gid, count in genre_counts.items():
                if count >= threshold:
                    session.execute(artist_genres.insert().values(artist_id=a.id, genre_id=gid))
                    assigned.append(gid)

            if assigned:
                updated += 1

        session.commit()

    return {"updated": updated}


@celery_app.task(name="workers.tasks.crawl_followed_sets")
def crawl_followed_sets():
    """
    Re-crawl followed sets whose tracklist is not 100% identified.
    Skips sets crawled < 12h ago.
    After re-import, resolves unlinked tracks via catalog matching + Deezer enrichment.
    """
    import asyncio
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import DJSet, SetTrack, UserSetFollow

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

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


@celery_app.task(name="workers.tasks.enrich_catalog_beatport")
def enrich_catalog_beatport():
    """
    Enrichit les entrées catalog via Beatport API v4.
    Priorité 1: lookup par ISRC (fiable).
    Priorité 2: search par artist+title (fallback).
    Remplit: bpm, key, bpm_source, key_source, beatport_id, label, genre, release_date, artwork.
    """
    import logging
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import CatalogEntry
    from beatport.client import BeatportClient
    from beatport.enrich import enrich_from_beatport
    from deezer_enrich import _get_s3, _ensure_bucket

    logger = logging.getLogger(__name__)

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)

    s3 = _get_s3()
    _ensure_bucket(s3)

    client = BeatportClient()
    enriched = 0
    not_found = 0
    errors = 0

    with Session(engine) as session:
        entries = session.execute(
            select(CatalogEntry).where(CatalogEntry.beatport_id.is_(None))
            .order_by(CatalogEntry.id)
        ).scalars().all()

        for i, entry in enumerate(entries):
            try:
                bp_track = None

                # Strategy 1: ISRC search (most reliable)
                if entry.isrc:
                    bp_track = client.search_track_by_isrc(entry.isrc)

                # Strategy 2: title+artist search
                if not bp_track and entry.title:
                    results = client.search_track(entry.title, entry.artist)
                    if results:
                        bp_track = results[0]

                if bp_track and enrich_from_beatport(entry, bp_track, s3=s3):
                    enriched += 1
                else:
                    not_found += 1

            except Exception as e:
                logger.warning("Beatport enrich failed for catalog %s: %s", entry.id, e)
                errors += 1
                time.sleep(2)

            if (i + 1) % 100 == 0:
                session.commit()

        session.commit()

    return {"enriched": enriched, "not_found": not_found, "errors": errors}


