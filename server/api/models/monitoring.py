from database import Base
from sqlalchemy import JSON, Column, DateTime, Integer


class MetricSnapshot(Base):
    """Time-series sample of enrichment/crawl backlog sizes.

    One row per hourly ``snapshot_backlogs`` run. ``payload`` is a free-form
    JSON dict structured by domain (enrich/artists/sets/catalog) — kept generic
    (``Column(JSON)``, not JSONB) for parity with the rest of the codebase and
    so the SQLite-backed test suite handles it identically.
    """

    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
