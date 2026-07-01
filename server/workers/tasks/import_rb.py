"""Celery task for asynchronous Rekordbox XML import."""

import json
import logging
import os
import sys

import boto3
import redis as redis_lib
from botocore.client import Config
from workers.celery_app import celery_app

sys.path.insert(0, "/app")

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
BUCKET_IMPORT = "import-jobs"


def _get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("MINIO_URL", "http://minio:9000"),
        aws_access_key_id=os.environ.get("MINIO_USER", ""),
        aws_secret_access_key=os.environ.get("MINIO_PASSWORD", ""),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _set_progress(r, task_id: str, data: dict):
    r.set(f"import:{task_id}", json.dumps(data), ex=3600)


def _get_progress(r, task_id: str) -> dict:
    raw = r.get(f"import:{task_id}")
    return json.loads(raw) if raw else {}


def _batches(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


@celery_app.task(
    name="workers.tasks.import_rekordbox_xml",
    bind=True,
    max_retries=0,
)
def import_rekordbox_xml(self, task_id: str, user_id: int):
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    s3 = _get_s3()

    try:
        _set_progress(r, task_id, {
            "status": "running", "total": 0, "inserted": 0, "updated": 0, "errors": [], "user_id": user_id
        })

        # Download XML from MinIO
        response = s3.get_object(Bucket=BUCKET_IMPORT, Key=f"{user_id}/{task_id}.xml")
        content = response["Body"].read()

        # Parse XML
        from services.rekordbox_xml import parse_rekordbox_xml
        tracks = parse_rekordbox_xml(content)
        logger.info("Parsed %d tracks for task %s user %s", len(tracks), task_id, user_id)

        _set_progress(r, task_id, {
            "status": "running", "total": len(tracks), "inserted": 0, "updated": 0, "errors": [], "user_id": user_id
        })

        # Import tracks via sync SQLAlchemy
        from models import CatalogEntry, UserTrack
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.orm import Session
        from utils import make_normalized_key
        from workers.db import get_engine

        engine = get_engine()

        # Snapshot of known rekordbox_ids before import (for inserted vs updated count)
        with Session(engine) as session:
            rows = session.execute(
                select(UserTrack.rekordbox_id)
                .where(UserTrack.user_id == user_id)
                .where(UserTrack.rekordbox_id.isnot(None))
            ).all()
        known_rb_ids: set[int] = {row.rekordbox_id for row in rows}

        inserted = 0
        updated = 0
        ut_table = UserTrack.__table__

        for batch in _batches(tracks, 50):
            # Phase 1 — ORM: find or create CatalogEntry for each track.
            # Committed and closed before any UserTrack write so there is
            # zero chance of ORM autoflush interfering with the upsert below.
            catalog_ids: dict[str, int] = {}
            with Session(engine) as session:
                for t in batch:
                    norm_key = make_normalized_key(t.title or "", t.artist or "")
                    cat_entry = session.execute(
                        select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
                    ).scalar_one_or_none()

                    if cat_entry is None:
                        cat_entry = CatalogEntry(
                            title=t.title or "",
                            artist=t.artist,
                            normalized_key=norm_key,
                            scope="private",
                            owner_id=user_id,
                            origin="rekordbox",
                        )
                        session.add(cat_entry)
                        session.flush()
                    elif cat_entry.scope == "private":
                        cat_entry.title = t.title or cat_entry.title
                        cat_entry.artist = t.artist or cat_entry.artist

                    catalog_ids[norm_key] = cat_entry.id

                session.commit()

            # Phase 2 — Core only: upsert UserTracks via engine.connect()
            # completely outside any ORM Session — no autoflush, no identity map.
            with engine.connect() as conn:
                for t in batch:
                    norm_key = make_normalized_key(t.title or "", t.artist or "")
                    catalog_id = catalog_ids[norm_key]
                    rb_id = t.id
                    tags = t.tags or []

                    stmt = pg_insert(ut_table).values(
                        user_id=user_id,
                        catalog_id=catalog_id,
                        rekordbox_id=rb_id,
                        date_added=t.date_added,
                        source="rekordbox_import",
                        file_path=t.file_path,
                        rb_bpm=t.bpm,
                        rb_key=t.key,
                        rb_mytags=json.dumps(tags),
                        rating=t.rating,
                        has_artwork=False,
                    ).on_conflict_do_update(
                        index_elements=["user_id", "catalog_id"],
                        set_={
                            "rekordbox_id": rb_id,
                            "date_added": t.date_added,
                            "file_path": t.file_path,
                            "rb_bpm": t.bpm,
                            "rb_key": t.key,
                            "rb_mytags": json.dumps(tags),
                            "rating": t.rating,
                        },
                    )
                    conn.execute(stmt)

                    if rb_id in known_rb_ids:
                        updated += 1
                    else:
                        inserted += 1
                        known_rb_ids.add(rb_id)

                conn.commit()

            _set_progress(r, task_id, {
                "status": "running",
                "total": len(tracks),
                "inserted": inserted,
                "updated": updated,
                "errors": [],
                "user_id": user_id,
            })

        _set_progress(r, task_id, {
            "status": "done",
            "total": len(tracks),
            "inserted": inserted,
            "updated": updated,
            "errors": [],
            "user_id": user_id,
        })
        logger.info("Import done for task %s: inserted=%d updated=%d", task_id, inserted, updated)

    except Exception as e:
        logger.error("Import failed for task %s: %s", task_id, e)
        try:
            progress = _get_progress(r, task_id)
            progress["status"] = "error"
            progress.setdefault("errors", []).append(str(e))
            _set_progress(r, task_id, progress)
        except Exception:
            pass
        raise

    finally:
        try:
            s3.delete_object(Bucket=BUCKET_IMPORT, Key=f"{user_id}/{task_id}.xml")
        except Exception:
            pass
        r.delete(f"import:lock:{user_id}")
