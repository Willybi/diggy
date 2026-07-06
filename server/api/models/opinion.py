from database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String


class UserOpinion(Base):
    __tablename__ = "user_opinions"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    entity_type = Column(
        String(20), primary_key=True, nullable=False
    )  # artist, set, playlist, genre
    entity_key = Column(
        String(255), primary_key=True, nullable=False
    )  # id as string, or genre name
    opinion = Column(String(20), nullable=False)  # liked | disliked
    created_at = Column(DateTime(timezone=True))
