"""User track schemas (Rekordbox library)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Cap the artwork payload to guard against memory-DoS when importing a Rekordbox
# library (an image per track). base64 inflates ~33 %, so ~3 MiB of base64 caps a
# ~2.2 MiB source image — well above any real Rekordbox embedded artwork
# (typically a few hundred KB).
MAX_IMAGE_BASE64_LEN = 3 * 1024 * 1024


class TrackImport(BaseModel):
    id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration: Optional[int] = None
    rating: Optional[int] = None
    file_path: Optional[str] = None
    date_added: Optional[datetime] = None
    tags: list[str] = []
    image_base64: Optional[str] = Field(default=None, max_length=MAX_IMAGE_BASE64_LEN)
