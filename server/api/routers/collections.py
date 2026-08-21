from datetime import datetime, timezone
from typing import Optional

from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from models import (
    Artist,
    CatalogEntry,
    CollectionFolder,
    CollectionItem,
    DJSet,
    User,
    UserCollection,
    WatchedEntity,
)
from schemas import (
    CollectionCreateIn,
    CollectionDetailOut,
    CollectionFolderAssignIn,
    CollectionItemAddIn,
    CollectionItemOut,
    CollectionOut,
    FolderCreateIn,
    FolderOut,
    FolderUpdateIn,
)
from services.catalog_service import catalog_visible
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("/", response_model=list[CollectionOut])
async def list_collections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = (
        select(
            UserCollection.id,
            UserCollection.name,
            UserCollection.type,
            UserCollection.folder_id,
            UserCollection.created_at,
            func.count(CollectionItem.id).label("item_count"),
        )
        .outerjoin(CollectionItem, CollectionItem.collection_id == UserCollection.id)
        .where(UserCollection.user_id == user.id)
        .group_by(UserCollection.id)
        .order_by(UserCollection.created_at.desc())
    )
    result = await db.execute(q)
    return [CollectionOut.model_validate(row._mapping) for row in result]


@router.post("/", response_model=CollectionOut, status_code=201)
async def create_collection(
    body: CollectionCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    coll = UserCollection(
        user_id=user.id,
        name=body.name,
        type=body.type or "playlist",
        created_at=datetime.now(timezone.utc),
    )
    db.add(coll)
    await db.commit()
    await db.refresh(coll)
    return CollectionOut(
        id=coll.id,
        name=coll.name,
        type=coll.type,
        folder_id=coll.folder_id,
        created_at=coll.created_at,
        item_count=0,
    )


# --- Folders (C5 v2 L2) -----------------------------------------------------
# These literal `/collections/folders...` routes MUST be declared before the
# `/{collection_id}` routes below, otherwise `folders` would be captured as a
# `collection_id` path param (→ 422 on int parsing).


@router.get("/folders", response_model=list[FolderOut])
async def list_folders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = (
        select(
            CollectionFolder.id,
            CollectionFolder.name,
            CollectionFolder.position,
            CollectionFolder.created_at,
            func.count(UserCollection.id).label("collection_count"),
        )
        .outerjoin(UserCollection, UserCollection.folder_id == CollectionFolder.id)
        .where(CollectionFolder.user_id == user.id)
        .group_by(CollectionFolder.id)
        .order_by(CollectionFolder.position, CollectionFolder.created_at.desc())
    )
    result = await db.execute(q)
    return [FolderOut.model_validate(row._mapping) for row in result]


@router.post("/folders", response_model=FolderOut, status_code=201)
async def create_folder(
    body: FolderCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = CollectionFolder(
        user_id=user.id,
        name=body.name,
        position=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return FolderOut(
        id=folder.id,
        name=folder.name,
        position=folder.position or 0,
        created_at=folder.created_at,
        collection_count=0,
    )


@router.patch("/folders/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: int,
    body: FolderUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder = await _get_user_folder(db, folder_id, user.id)
    if body.name is not None:
        folder.name = body.name
    if body.position is not None:
        folder.position = body.position
    await db.commit()
    await db.refresh(folder)

    count = await db.execute(
        select(func.count(UserCollection.id)).where(
            UserCollection.folder_id == folder_id
        )
    )
    return FolderOut(
        id=folder.id,
        name=folder.name,
        position=folder.position or 0,
        created_at=folder.created_at,
        collection_count=count.scalar() or 0,
    )


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a folder. Its collections are NOT deleted — they are orphaned
    (folder_id → NULL). The FK is declared ON DELETE SET NULL, but we null the
    members explicitly so the behaviour is deterministic even on a backend that
    doesn't enforce the FK action (the SQLite test harness)."""
    folder = await _get_user_folder(db, folder_id, user.id)
    await db.execute(
        update(UserCollection)
        .where(UserCollection.folder_id == folder_id)
        .values(folder_id=None)
    )
    await db.delete(folder)
    await db.commit()


@router.get("/{collection_id}", response_model=CollectionDetailOut)
async def get_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    coll = await _get_user_collection(db, collection_id, user.id)

    rows = await db.execute(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.position)
    )
    items = await _resolve_items(db, rows.scalars().all(), user.id)

    return CollectionDetailOut(
        id=coll.id,
        name=coll.name,
        type=coll.type,
        folder_id=coll.folder_id,
        created_at=coll.created_at,
        item_count=len(items),
        items=items,
    )


@router.patch("/{collection_id}/folder", response_model=CollectionOut)
async def assign_collection_folder(
    collection_id: int,
    body: CollectionFolderAssignIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move a collection into a folder (or out of any folder with folder_id=null).

    Both the collection and the target folder must belong to the caller.
    """
    coll = await _get_user_collection(db, collection_id, user.id)
    if body.folder_id is not None:
        await _get_user_folder(db, body.folder_id, user.id)
    coll.folder_id = body.folder_id
    await db.commit()

    count = await db.execute(
        select(func.count(CollectionItem.id)).where(
            CollectionItem.collection_id == collection_id
        )
    )
    return CollectionOut(
        id=coll.id,
        name=coll.name,
        type=coll.type,
        folder_id=coll.folder_id,
        created_at=coll.created_at,
        item_count=count.scalar() or 0,
    )


@router.post(
    "/{collection_id}/items", response_model=CollectionItemOut, status_code=201
)
async def add_item(
    collection_id: int,
    body: CollectionItemAddIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_user_collection(db, collection_id, user.id)

    # Verify the referenced entity exists (a track additionally honours the
    # viewer's catalog visibility). A genre has no table — it is accepted as-is.
    await _assert_target_exists(db, body.item_type, body.item_id, user.id)

    # Application-level dedup: refuse a second identical item in the collection.
    dedup = select(CollectionItem).where(
        CollectionItem.collection_id == collection_id,
        CollectionItem.item_type == body.item_type,
    )
    if body.item_type == "genre":
        dedup = dedup.where(CollectionItem.item_name == body.item_name)
    else:
        dedup = dedup.where(CollectionItem.item_id == body.item_id)
    if (await db.execute(dedup)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Item already in collection")

    max_pos = await db.execute(
        select(func.coalesce(func.max(CollectionItem.position), 0)).where(
            CollectionItem.collection_id == collection_id
        )
    )
    next_pos = (max_pos.scalar() or 0) + 1

    item = CollectionItem(
        collection_id=collection_id,
        item_type=body.item_type,
        item_id=body.item_id,
        item_name=body.item_name,
        position=next_pos,
        added_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.commit()

    resolved = await _resolve_items(db, [item], user.id)
    return resolved[0]


@router.delete(
    "/{collection_id}/items/{item_type}/{item_id}", status_code=204
)
async def remove_item(
    collection_id: int,
    item_type: str,
    item_id: int,
    item_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a polymorphic item.

    Addressed by ``item_type`` + ``item_id`` in the path for every id-bearing
    type. A genre has a NULL ``item_id``, so it is matched by the ``item_name``
    query param instead (the path ``item_id`` is a placeholder, e.g.
    ``DELETE /{id}/items/genre/0?item_name=Techno``).
    """
    await _get_user_collection(db, collection_id, user.id)

    q = select(CollectionItem).where(
        CollectionItem.collection_id == collection_id,
        CollectionItem.item_type == item_type,
    )
    if item_type == "genre":
        if not item_name:
            raise HTTPException(
                status_code=400, detail="item_name is required for a genre item"
            )
        q = q.where(CollectionItem.item_name == item_name)
    else:
        q = q.where(CollectionItem.item_id == item_id)

    item = (await db.execute(q)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in collection")

    await db.delete(item)
    await db.commit()


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    coll = await _get_user_collection(db, collection_id, user.id)
    await db.delete(coll)
    await db.commit()


async def _get_user_collection(
    db: AsyncSession, collection_id: int, user_id: int
) -> UserCollection:
    result = await db.execute(
        select(UserCollection).where(
            UserCollection.id == collection_id,
            UserCollection.user_id == user_id,
        )
    )
    coll = result.scalar_one_or_none()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    return coll


async def _get_user_folder(
    db: AsyncSession, folder_id: int, user_id: int
) -> CollectionFolder:
    result = await db.execute(
        select(CollectionFolder).where(
            CollectionFolder.id == folder_id,
            CollectionFolder.user_id == user_id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


async def _assert_target_exists(
    db: AsyncSession, item_type: str, item_id: Optional[int], user_id: int
) -> None:
    """404 unless the referenced entity exists (track: visible to the viewer)."""
    if item_type == "genre":
        return  # no table — validated to carry item_name upstream
    if item_type == "track":
        q = select(CatalogEntry.id).where(
            CatalogEntry.id == item_id, catalog_visible(user_id)
        )
    elif item_type == "set":
        q = select(DJSet.id).where(DJSet.id == item_id)
    elif item_type == "artist":
        q = select(Artist.id).where(Artist.id == item_id)
    elif item_type == "playlist":
        q = select(WatchedEntity.id).where(WatchedEntity.id == item_id)
    else:  # pragma: no cover — schema validation blocks other types
        raise HTTPException(status_code=422, detail="Unsupported item_type")
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"{item_type} not found")


async def _resolve_items(
    db: AsyncSession, items: list, user_id: int
) -> list[CollectionItemOut]:
    """Resolve the display fields of each item by type, preserving order.

    Entities are loaded ONE query per type (never gathered — a single
    AsyncSession is not concurrency-safe). An item whose entity no longer exists
    (or, for a track, is not visible to the viewer) is marked ``missing``.
    """
    # Bucket the id-bearing items by type.
    ids_by_type: dict[str, set[int]] = {}
    for it in items:
        if it.item_type != "genre" and it.item_id is not None:
            ids_by_type.setdefault(it.item_type, set()).add(it.item_id)

    # --- track ---
    tracks: dict[int, CatalogEntry] = {}
    if ids_by_type.get("track"):
        res = await db.execute(
            select(CatalogEntry).where(
                CatalogEntry.id.in_(ids_by_type["track"]), catalog_visible(user_id)
            )
        )
        tracks = {e.id: e for e in res.scalars().all()}

    # --- set ---
    sets: dict[int, DJSet] = {}
    if ids_by_type.get("set"):
        res = await db.execute(
            select(DJSet).where(DJSet.id.in_(ids_by_type["set"]))
        )
        sets = {s.id: s for s in res.scalars().all()}

    # --- artist ---
    artists: dict[int, Artist] = {}
    if ids_by_type.get("artist"):
        res = await db.execute(
            select(Artist).where(Artist.id.in_(ids_by_type["artist"]))
        )
        artists = {a.id: a for a in res.scalars().all()}

    # --- playlist ---
    playlists: dict[int, WatchedEntity] = {}
    if ids_by_type.get("playlist"):
        res = await db.execute(
            select(WatchedEntity).where(
                WatchedEntity.id.in_(ids_by_type["playlist"])
            )
        )
        playlists = {w.id: w for w in res.scalars().all()}

    out: list[CollectionItemOut] = []
    for it in items:
        base = dict(
            item_type=it.item_type,
            item_id=it.item_id,
            item_name=it.item_name,
            position=it.position or 0,
            added_at=it.added_at,
        )
        if it.item_type == "genre":
            out.append(
                CollectionItemOut(
                    **base, title=it.item_name, has_artwork=False, missing=False
                )
            )
            continue

        if it.item_type == "track":
            entity = tracks.get(it.item_id)
            if entity is None:
                out.append(
                    CollectionItemOut(**base, title=it.item_name, missing=True)
                )
            else:
                out.append(
                    CollectionItemOut(
                        **base,
                        title=entity.title,
                        subtitle=entity.artist,
                        has_artwork=bool(entity.has_artwork),
                        bpm=entity.bpm,
                        key=entity.key,
                        duration_ms=entity.duration_ms,
                        has_preview=bool(entity.has_preview),
                    )
                )
        elif it.item_type == "set":
            entity = sets.get(it.item_id)
            if entity is None:
                out.append(
                    CollectionItemOut(**base, title=it.item_name, missing=True)
                )
            else:
                out.append(
                    CollectionItemOut(
                        **base,
                        title=entity.title,
                        subtitle=entity.event or entity.venue,
                        has_artwork=bool(entity.has_artwork),
                    )
                )
        elif it.item_type == "artist":
            entity = artists.get(it.item_id)
            if entity is None:
                out.append(
                    CollectionItemOut(**base, title=it.item_name, missing=True)
                )
            else:
                out.append(
                    CollectionItemOut(
                        **base,
                        title=entity.name,
                        has_artwork=bool(entity.has_artwork),
                    )
                )
        elif it.item_type == "playlist":
            entity = playlists.get(it.item_id)
            if entity is None:
                out.append(
                    CollectionItemOut(**base, title=it.item_name, missing=True)
                )
            else:
                out.append(
                    CollectionItemOut(
                        **base,
                        title=entity.title,
                        subtitle=entity.owner,
                        has_artwork=bool(entity.has_artwork),
                    )
                )
        else:  # pragma: no cover — schema validation blocks other types
            out.append(CollectionItemOut(**base, title=it.item_name, missing=True))

    return out
