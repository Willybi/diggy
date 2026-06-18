"""
Shared fixtures for worker tests.
Centralizes sys.path hacks, sys.modules mocks, and sync DB setup.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

# --- sys.path: make server/api importable ---
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))

# --- Mock infra modules not available in test env ---
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.client", MagicMock())
mock_storage = MagicMock()
sys.modules.setdefault("storage", mock_storage)

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base


@pytest.fixture
def sync_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    with Session(sync_engine) as session:
        yield session
