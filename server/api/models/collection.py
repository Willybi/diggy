from database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class CollectionFolder(Base):
    """A private folder grouping the user's collections (C5 v2 — one flat level,
    no nesting). A collection may live in at most one folder; deleting a folder
    orphans its collections (folder_id → NULL) rather than deleting them."""

    __tablename__ = "collection_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    position = Column(Integer, server_default="0", default=0)
    created_at = Column(DateTime(timezone=True))

    user = relationship("User")


class UserCollection(Base):
    __tablename__ = "user_collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    type = Column(String(20), server_default="playlist", default="playlist")
    # Optional parent folder. ON DELETE SET NULL: a collection survives its
    # folder's deletion as an "orphan" (folder_id NULL).
    folder_id = Column(
        Integer, ForeignKey("collection_folders.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True))

    user = relationship("User")
    items = relationship(
        "CollectionItem",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionItem.position",
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(
        Integer,
        ForeignKey("user_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Polymorphic curation item (C5 v2): any entity can be pinned to a
    # collection. There is deliberately NO native FK to a target table — the
    # same slot can point at a track/set/artist/genre/playlist, so integrity is
    # enforced at the application layer (mirrors user_opinions' entity_type/
    # entity_key pattern). item_id is NULL for a genre (addressed by item_name);
    # item_name holds the genre name / a display fallback for the other types.
    item_type = Column(String(20), nullable=False)
    item_id = Column(Integer, nullable=True)
    item_name = Column(String(255), nullable=True)
    position = Column(Integer, server_default="0", default=0)
    added_at = Column(DateTime(timezone=True))

    collection = relationship("UserCollection", back_populates="items")
