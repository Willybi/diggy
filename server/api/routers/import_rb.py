"""Router for Rekordbox XML web import."""

import io
import json
import logging
from uuid import uuid4

from celery_client import celery
from dependencies import get_current_user, get_redis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from models import User
from schemas import ImportQueuedResponse, ImportStatusResponse

logger = logging.getLogger("diggy")

BUCKET_IMPORT = "import-jobs"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Lock TTL must cover the task's effective time_limit (global CELERY_TIME_LIMIT,
# 3600s) so the lock cannot expire while a legitimate import is still running
IMPORT_LOCK_TTL = 3700

router = APIRouter(tags=["import"])


@router.post("/rekordbox-xml", response_model=ImportQueuedResponse)
async def upload_rekordbox_xml(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    from services.image_service import ImageService
    from services.rekordbox_xml import validate_rekordbox_xml

    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=422, detail="Le fichier doit avoir l'extension .xml")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 10 Mo)")

    if not validate_rekordbox_xml(content):
        raise HTTPException(
            status_code=422,
            detail="Fichier invalide : ce n'est pas un export XML Rekordbox valide",
        )

    task_id = str(uuid4())

    # Atomic lock acquisition (SET NX) before any side effect: a concurrent
    # upload for the same user must lose the race, not slip between check and set
    lock_key = f"import:lock:{user.id}"
    if not await redis.set(lock_key, task_id, nx=True, ex=IMPORT_LOCK_TTL):
        raise HTTPException(
            status_code=409, detail="Un import est déjà en cours pour ce compte"
        )

    try:
        # Upload XML to MinIO (bucket import-jobs)
        ImageService.ensure_bucket(BUCKET_IMPORT)
        s3 = ImageService._get_s3()
        s3.upload_fileobj(
            io.BytesIO(content),
            BUCKET_IMPORT,
            f"{user.id}/{task_id}.xml",
            ExtraArgs={"ContentType": "application/xml"},
        )

        # Progress init (TTL 3600s)
        progress = {"status": "queued", "total": 0, "inserted": 0, "updated": 0, "errors": [], "user_id": user.id}
        await redis.set(f"import:{task_id}", json.dumps(progress), ex=3600)

        celery.send_task("workers.tasks.import_rekordbox_xml", args=[task_id, user.id])
    except Exception:
        # The task will never run, so nothing else can release the lock:
        # free it now (only if still ours) instead of blocking the user's
        # imports for the full TTL
        if await redis.get(lock_key) == task_id:
            await redis.delete(lock_key)
        raise

    return {"task_id": task_id, "status": "queued"}


@router.get("/status/{task_id}", response_model=ImportStatusResponse)
async def get_import_status(
    task_id: str,
    user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    raw = await redis.get(f"import:{task_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Import inconnu ou expiré")

    data = json.loads(raw)
    if data.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Import inconnu ou expiré")

    data.pop("user_id", None)
    return data
