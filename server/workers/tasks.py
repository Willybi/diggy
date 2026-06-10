"""
Celery tasks for Diggy.
Main task: import a Rekordbox database into PostgreSQL.
"""
import os
import json
import sys
import requests
from workers.celery_app import celery_app

API_BASE = os.environ.get("DIGGY_API_URL", "http://api:8000")
DEEZER_API = "https://api.deezer.com"


@celery_app.task(name="workers.tasks.crawl_radar")
def crawl_radar():
    """
    Crawl toutes les playlists Deezer surveillées (watched_playlists).
    - Skip si Deezer ne signale pas de modification depuis le dernier crawl.
    - Skip les tracks déjà présents (déduplication par contrainte unique).
    """
    from datetime import datetime, timezone

    playlists = requests.get(f"{API_BASE}/api/watchlist/", timeout=10).json()
    inserted = 0
    skipped = 0
    errors = 0

    for pl in playlists:
        if pl["source"] != "deezer":
            continue

        # Vérifie si la playlist a été modifiée depuis le dernier crawl
        dz_meta = requests.get(f"{DEEZER_API}/playlist/{pl['external_id']}", timeout=10).json()
        dz_modification_date = dz_meta.get("time_mod") or dz_meta.get("creation_date")

        if dz_modification_date and pl.get("last_crawled_at"):
            last_crawled = datetime.fromisoformat(pl["last_crawled_at"]).replace(tzinfo=timezone.utc)
            dz_mod = datetime.fromtimestamp(int(dz_modification_date), tz=timezone.utc)
            if dz_mod <= last_crawled:
                skipped += 1
                continue

        tracks = []
        url = f"{DEEZER_API}/playlist/{pl['external_id']}/tracks?limit=100&index=0"
        while url:
            resp = requests.get(url, timeout=10).json()
            tracks.extend(resp.get("data", []))
            url = resp.get("next")

        for t in tracks:
            artist = t.get("artist", {}).get("name") if isinstance(t.get("artist"), dict) else None
            payload = {
                "watched_playlist_id": pl["id"],
                "external_track_id": str(t["id"]),
                "source": "deezer",
                "title": t.get("title", ""),
                "artist": artist,
                "isrc": t.get("isrc") or None,
            }
            r = requests.post(f"{API_BASE}/api/radar/", json=payload, timeout=10)
            if r.status_code == 201:
                inserted += 1

        # Marque la playlist comme crawlée
        requests.patch(f"{API_BASE}/api/watchlist/{pl['id']}/crawled", timeout=10)

    return {"inserted": inserted, "skipped_playlists": skipped, "errors": errors}


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
    from models import LibLibTrack, Base
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
