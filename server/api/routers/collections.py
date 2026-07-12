from datetime import datetime, timezone

from database import get_db
from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from models import CatalogEntry, CollectionItem, User, UserCollection
from schemas import (
    CollectionCreateIn,
    CollectionDetailOut,
    CollectionItemAddIn,
    CollectionItemOut,
    CollectionOut,
)
from services.catalog_service import catalog_visible
from sqlalchemy import func, select
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
            UserCollection.created_at,
            func.count(CollectionItem.catalog_id).label("item_count"),
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
        created_at=coll.created_at,
        item_count=0,
    )


@router.get("/{collection_id}", response_model=CollectionDetailOut)
async def get_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    coll = await _get_user_collection(db, collection_id, user.id)

    items_q = (
        select(
            CollectionItem.catalog_id,
            CollectionItem.position,
            CollectionItem.added_at,
            CatalogEntry.title,
            CatalogEntry.artist,
            CatalogEntry.bpm,
            CatalogEntry.key,
            CatalogEntry.duration_ms,
            CatalogEntry.has_artwork,
            CatalogEntry.has_preview,
        )
        .join(CatalogEntry, CollectionItem.catalog_id == CatalogEntry.id)
        .where(CollectionItem.collection_id == collection_id, catalog_visible(user.id))
        .order_by(CollectionItem.position)
    )
    result = await db.execute(items_q)
    items = [CollectionItemOut.model_validate(row._mapping) for row in result]

    return CollectionDetailOut(
        id=coll.id,
        name=coll.name,
        type=coll.type,
        created_at=coll.created_at,
        item_count=len(items),
        items=items,
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

    # Check catalog entry exists and is visible to this user
    cat = await db.execute(
        select(CatalogEntry).where(
            CatalogEntry.id == body.catalog_id, catalog_visible(user.id)
        )
    )
    if not cat.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Catalog entry not found")

    # Check not already in collection
    existing = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.catalog_id == body.catalog_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Track already in collection")

    # Next position
    max_pos = await db.execute(
        select(func.coalesce(func.max(CollectionItem.position), 0)).where(
            CollectionItem.collection_id == collection_id
        )
    )
    next_pos = (max_pos.scalar() or 0) + 1

    item = CollectionItem(
        collection_id=collection_id,
        catalog_id=body.catalog_id,
        position=next_pos,
        added_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.commit()

    # Fetch catalog info for response
    cat_q = await db.execute(
        select(CatalogEntry).where(CatalogEntry.id == body.catalog_id)
    )
    cat_entry = cat_q.scalar_one()

    return CollectionItemOut(
        catalog_id=cat_entry.id,
        position=next_pos,
        added_at=item.added_at,
        title=cat_entry.title,
        artist=cat_entry.artist,
        bpm=cat_entry.bpm,
        key=cat_entry.key,
        duration_ms=cat_entry.duration_ms,
        has_artwork=cat_entry.has_artwork,
        has_preview=cat_entry.has_preview,
    )


@router.delete("/{collection_id}/items/{catalog_id}", status_code=204)
async def remove_item(
    collection_id: int,
    catalog_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_user_collection(db, collection_id, user.id)

    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.catalog_id == catalog_id,
        )
    )
    item = result.scalar_one_or_none()
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
