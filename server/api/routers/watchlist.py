import requests
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import WatchedPlaylist
from schemas import WatchedPlaylistIn, WatchedPlaylistOut

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DEEZER_API = "https://api.deezer.com"


def _fetch_deezer_playlist_title(deezer_playlist_id: str) -> str | None:
    try:
        resp = requests.get(f"{DEEZER_API}/playlist/{deezer_playlist_id}", timeout=5)
        data = resp.json()
        return data.get("title")
    except Exception:
        return None


@router.get("/", response_model=list[WatchedPlaylistOut])
async def list_watched(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WatchedPlaylist))
    return result.scalars().all()


@router.post("/", response_model=WatchedPlaylistOut, status_code=201)
async def add_watched(body: WatchedPlaylistIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(WatchedPlaylist).where(WatchedPlaylist.deezer_playlist_id == body.deezer_playlist_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Playlist already watched")

    title = _fetch_deezer_playlist_title(body.deezer_playlist_id)

    entry = WatchedPlaylist(
        deezer_playlist_id=body.deezer_playlist_id,
        title=title,
        description=body.description,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_watched(entry_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WatchedPlaylist).where(WatchedPlaylist.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(entry)
    await db.commit()
