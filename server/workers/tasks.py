"""
Celery tasks for Diggy.
Main task: import a Rekordbox database into PostgreSQL.
"""
import os
import json
import sys
import time
import requests
from workers.celery_app import celery_app

API_BASE = os.environ.get("DIGGY_API_URL", "http://api:8000")
DEEZER_API = "https://api.deezer.com"


@celery_app.task(name="workers.tasks.crawl_radar")
def crawl_radar():
    """
    Crawl toutes les playlists Deezer surveillées.
    Délègue chaque playlist à crawl_single_playlist pour enrichissement inline.
    """
    from datetime import datetime, timezone

    playlists = requests.get(f"{API_BASE}/api/watchlist/", timeout=10).json()
    crawled = 0
    skipped = 0

    for pl in playlists:
        if pl["source"] != "deezer":
            continue

        # Vérifie si la playlist a été modifiée depuis le dernier crawl
        dz_meta = requests.get(f"{DEEZER_API}/playlist/{pl['external_id']}", timeout=10).json()
        dz_modification_date = dz_meta.get("time_mod") or dz_meta.get("creation_date")

        if dz_modification_date and pl.get("last_crawled_at"):
            last_crawled = datetime.fromisoformat(pl["last_crawled_at"]).replace(tzinfo=timezone.utc)
            try:
                dz_mod = datetime.fromtimestamp(int(dz_modification_date), tz=timezone.utc)
            except (ValueError, TypeError):
                dz_mod = datetime.fromisoformat(str(dz_modification_date)).replace(tzinfo=timezone.utc)
            if dz_mod <= last_crawled:
                skipped += 1
                continue

        crawl_single_playlist(pl["id"])
        crawled += 1

    return {"crawled": crawled, "skipped_playlists": skipped}


@celery_app.task(name="workers.tasks.crawl_single_playlist")
def crawl_single_playlist(playlist_id: int):
    """
    Crawl une seule playlist Deezer par son watched_entity ID.
    Insère les tracks via l'API, puis enrichit les nouvelles entrées catalog
    (deezer_id, artwork, preview, duration) directement depuis les données Deezer.
    """
    from datetime import datetime, timezone
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    sys.path.insert(0, "/app")
    from models import CatalogEntry, RadarTrack, WatchedEntity
    from deezer_enrich import enrich_entry, upload_cover_from_url, _get_s3, _ensure_bucket

    pl = requests.get(f"{API_BASE}/api/watchlist/browse", timeout=10).json()
    target = next((p for p in pl if p["id"] == playlist_id), None)
    if not target or target["source"] != "deezer":
        return {"error": "playlist not found or not deezer"}

    # 0. Fetch playlist metadata + cover from Deezer
    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)
    s3 = _get_s3()
    _ensure_bucket(s3)

    dz_playlist = requests.get(f"{DEEZER_API}/playlist/{target['external_id']}", timeout=10).json()

    with Session(engine) as session:
        entity = session.get(WatchedEntity, playlist_id)
        if entity:
            entity.track_count = dz_playlist.get("nb_tracks") or entity.track_count
            desc = dz_playlist.get("description")
            if desc:
                entity.description = desc
            creator = dz_playlist.get("creator")
            if isinstance(creator, dict) and creator.get("name"):
                entity.owner = creator["name"]
            # Download cover if missing
            if not entity.has_artwork:
                cover_url = dz_playlist.get("picture_big") or dz_playlist.get("picture_medium")
                if cover_url:
                    from deezer_enrich import upload_cover_from_url as _upload
                    if _upload(s3, cover_url, f"playlist-{playlist_id}"):
                        entity.has_artwork = True
            session.commit()

    # 1. Fetch all tracks from Deezer playlist
    tracks = []
    url = f"{DEEZER_API}/playlist/{target['external_id']}/tracks?limit=100&index=0"
    while url:
        resp = requests.get(url, timeout=10).json()
        tracks.extend(resp.get("data", []))
        url = resp.get("next")

    # 2. Insert radar tracks via API (handles dedup + catalog creation)
    inserted = 0
    dz_by_ext_id = {}
    for t in tracks:
        artist = t.get("artist", {}).get("name") if isinstance(t.get("artist"), dict) else None
        ext_id = str(t["id"])
        dz_by_ext_id[ext_id] = t
        payload = {
            "watched_playlist_id": target["id"],
            "external_track_id": ext_id,
            "source": "deezer",
            "title": t.get("title", ""),
            "artist": artist,
            "isrc": t.get("isrc") or None,
        }
        r = requests.post(f"{API_BASE}/api/radar/", json=payload, timeout=10)
        if r.status_code == 201:
            inserted += 1

    # 3. Enrich catalog entries that lack deezer_id (newly created)
    enriched = 0
    with Session(engine) as session:
        existing_isrcs = {r[0] for r in session.execute(
            select(CatalogEntry.isrc).where(CatalogEntry.isrc.isnot(None))
        ).all()}

        # Find catalog entries linked to this playlist's radar tracks that need enrichment
        radar_rows = session.execute(
            select(RadarTrack.external_track_id, RadarTrack.catalog_id)
            .where(RadarTrack.watched_entity_id == playlist_id)
        ).all()

        catalog_ids = {row.catalog_id for row in radar_rows if row.catalog_id}
        ext_to_catalog = {row.external_track_id: row.catalog_id for row in radar_rows}

        entries = session.execute(
            select(CatalogEntry).where(
                CatalogEntry.id.in_(catalog_ids),
                CatalogEntry.deezer_id.is_(None),
            )
        ).scalars().all()

        # Build reverse map: catalog_id → deezer track data
        catalog_to_dz = {}
        for ext_id, cat_id in ext_to_catalog.items():
            if cat_id and ext_id in dz_by_ext_id:
                catalog_to_dz[cat_id] = dz_by_ext_id[ext_id]

        for entry in entries:
            dz_hit = catalog_to_dz.get(entry.id)
            if not dz_hit:
                continue
            if enrich_entry(entry, dz_hit, s3=s3, _known_isrcs=existing_isrcs):
                enriched += 1

        session.commit()

    requests.patch(f"{API_BASE}/api/watchlist/{target['id']}/crawled", timeout=10)
    return {
        "playlist_id": playlist_id,
        "title": target.get("title"),
        "inserted": inserted,
        "enriched": enriched,
        "total_tracks": len(tracks),
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

    return {"resolved": resolved, "catalog_created": created, "enriched": enriched}


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


@celery_app.task(bind=True, name="workers.tasks.import_rekordbox")
def import_rekordbox(self, db_path: str):
    """
    Parse a Rekordbox 6 database file and upsert tracks into PostgreSQL.
    Uploads artworks to MinIO.

    Args:
        db_path: absolute path to the master.db Rekordbox file
    """
    from pyrekordbox import Rekordbox6Database
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import LibTrack, Base
    from storage import upload_artwork, ensure_bucket

    DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    ensure_bucket()

    rb_db = Rekordbox6Database(db_path)
    tracks_imported = 0

    with Session(engine) as session:
        for rb_track in rb_db.get_content():
            existing = session.execute(
                select(LibTrack).where(LibTrack.id == rb_track.ID)
            ).scalar_one_or_none()

            track = existing or LibTrack(id=rb_track.ID)
            if not existing:
                session.add(track)

            track.title = rb_track.Title
            track.artist = rb_track.ArtistName
            track.bpm = float(rb_track.BPM) if rb_track.BPM else None
            track.key = str(rb_track.Key) if rb_track.Key else None
            track.duration = rb_track.Duration
            track.rating = rb_track.Rating
            track.file_path = rb_track.FolderPath
            track.date_added = rb_track.DateAdded
            track.tags = json.dumps(rb_track.MyTagNames or [])

            if rb_track.ImagePath and not track.has_artwork:
                try:
                    upload_artwork(rb_track.ImagePath, f"{rb_track.ID}.jpg")
                    track.has_artwork = True
                except Exception:
                    pass

            session.flush()
            tracks_imported += 1

        session.commit()

    return {"imported": tracks_imported, "db_path": db_path}
