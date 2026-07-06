from database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship


class GenreNode(Base):
    __tablename__ = "genre_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wikidata_id = Column(String(64), unique=True, nullable=False)
    label = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True))

    outgoing_edges = relationship(
        "GenreEdge",
        foreign_keys="GenreEdge.from_node_id",
        back_populates="from_node",
        cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "GenreEdge",
        foreign_keys="GenreEdge.to_node_id",
        back_populates="to_node",
        cascade="all, delete-orphan",
    )


class GenreEdge(Base):
    __tablename__ = "genre_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_node_id = Column(
        Integer,
        ForeignKey("genre_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id = Column(
        Integer,
        ForeignKey("genre_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String(20), nullable=False)
    source = Column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("from_node_id", "to_node_id", "type", name="uq_genre_edge"),
    )

    from_node = relationship(
        "GenreNode", foreign_keys=[from_node_id], back_populates="outgoing_edges"
    )
    to_node = relationship(
        "GenreNode", foreign_keys=[to_node_id], back_populates="incoming_edges"
    )


class GenreMapping(Base):
    __tablename__ = "genre_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_name = Column(String(255), unique=True, nullable=False)
    node_id = Column(
        Integer,
        ForeignKey("genre_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    node = relationship("GenreNode")
