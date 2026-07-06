from database import Base
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    google_id = Column(String(255), unique=True, nullable=False)
    picture_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False, server_default="false")
    settings = Column(JSON, default=dict, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True))
