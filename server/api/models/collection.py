from database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class UserCollection(Base):
    __tablename__ = "user_collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    type = Column(String(20), server_default="playlist", default="playlist")
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

    collection_id = Column(
        Integer, ForeignKey("user_collections.id", ondelete="CASCADE"), primary_key=True
    )
    catalog_id = Column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True
    )
    position = Column(Integer, server_default="0", default=0)
    added_at = Column(DateTime(timezone=True))

    collection = relationship("UserCollection", back_populates="items")
    catalog = relationship("CatalogEntry")
