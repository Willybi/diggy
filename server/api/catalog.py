from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CatalogEntry
from utils import make_normalized_key


async def get_or_create_catalog(
    db: AsyncSession,
    title: str,
    artist: str | None,
    isrc: str | None = None,
    duration_ms: int | None = None,
    genres: list[str] | None = None,
    release_date=None,
    preview_url: str | None = None,
) -> CatalogEntry:
    # 1. Cherche par ISRC si dispo
    if isrc:
        result = await db.execute(select(CatalogEntry).where(CatalogEntry.isrc == isrc))
        entry = result.scalar_one_or_none()
        if entry:
            return entry

    # 2. Cherche par normalized_key
    norm_key = make_normalized_key(title, artist)
    result = await db.execute(
        select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
    )
    entry = result.scalar_one_or_none()
    if entry:
        # Met à jour l'ISRC si on l'a maintenant et qu'il manquait
        if isrc and not entry.isrc:
            entry.isrc = isrc
        return entry

    # 3. Crée une nouvelle entrée
    new = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=norm_key,
        isrc=isrc or None,
        duration_ms=duration_ms,
        genres=genres or [],
        release_date=release_date,
        preview_url=preview_url,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new)
    await db.flush()
    return new
