"""Import (Rekordbox) schemas."""

from pydantic import BaseModel


class ImportQueuedResponse(BaseModel):
    task_id: str
    status: str = "queued"


class ImportStatusResponse(BaseModel):
    status: str
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: list = []
