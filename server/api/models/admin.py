from database import Base
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action = Column(String(64), nullable=False, index=True)
    target_type = Column(String(64), nullable=True)
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User")


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(64), nullable=False, index=True)
    target_id = Column(Integer, nullable=True)
    target_label = Column(String(500), nullable=True)
    source = Column(String(64), nullable=True)
    status = Column(
        String(20), nullable=False, server_default="running", default="running"
    )
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    stats = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
