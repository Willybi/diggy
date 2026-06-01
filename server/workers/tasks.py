"""
Celery tasks for Diggy.
Main task: import a Rekordbox database into PostgreSQL.
"""
import os
import json
import sys
from workers.celery_app import celery_app


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
