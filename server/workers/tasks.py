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
