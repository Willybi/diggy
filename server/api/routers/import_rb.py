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

    lock_key = f"import:lock:{user.id}"
    if await redis.exists(lock_key):
        raise HTTPException(
            status_code=409, detail="Un import est déjà en cours pour ce compte"
        )

    task_id = str(uuid4())

    # Upload XML to MinIO (bucket import-jobs)
    ImageService.ensure_bucket(BUCKET_IMPORT)
    s3 = ImageService._get_s3()
    s3.upload_fileobj(
        io.BytesIO(content),
        BUCKET_IMPORT,
        f"{user.id}/{task_id}.xml",
        ExtraArgs={"ContentType": "application/xml"},
    )

    # Redis lock (TTL 600s) + progress init (TTL 3600s)
    await redis.set(lock_key, task_id, ex=600)
    progress = {"status": "queued", "total": 0, "inserted": 0, "updated": 0, "errors": [], "user_id": user.id}
    await redis.set(f"import:{task_id}", json.dumps(progress), ex=3600)

    celery.send_task("workers.tasks.import_rekordbox_xml", args=[task_id, user.id])

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
