"""
Celery tasks for Diggy.
Main task: import a Rekordbox database into PostgreSQL.
"""
import os
import asyncio
from workers.celery_app import celery_app


@celery_app.task(bind=True, name="workers.tasks.import_rekordbox")
def import_rekordbox(self, db_path: str):
    """
    Parse a Rekordbox 6 database file and upsert tracks, cues and tags
    into the PostgreSQL database.

    Args:
        db_path: absolute path to the master.db Rekordbox file
    """
    from pyrekordbox import Rekordbox6Database
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    import sys

    sys.path.insert(0, "/app")
    from models import Track, Cue, Tag, TrackTag, Base
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
                select(Track).where(Track.rekordbox_id == rb_track.ID)
            ).scalar_one_or_none()

            if existing:
                track = existing
            else:
                track = Track(rekordbox_id=rb_track.ID)
                session.add(track)

            track.title = rb_track.Title
            track.artist = rb_track.ArtistName
            track.album = rb_track.AlbumName
            track.label = rb_track.LabelName
            track.bpm = float(rb_track.BPM) if rb_track.BPM else None
            track.key = str(rb_track.Key) if rb_track.Key else None
            track.duration = rb_track.Duration
            track.rating = rb_track.Rating
            track.play_count = rb_track.PlayCount
            track.file_path = rb_track.FolderPath
            track.date_added = rb_track.DateAdded

            # Upload artwork vers MinIO si dispo et pas déjà uploadé
            if rb_track.ImagePath and not track.artwork_url:
                try:
                    object_key = f"{rb_track.ID}.jpg"
                    track.artwork_url = upload_artwork(rb_track.ImagePath, object_key)
                except Exception:
                    pass

            session.flush()
            tracks_imported += 1

        session.commit()

    return {"imported": tracks_imported, "db_path": db_path}
