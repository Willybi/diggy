"""
Patch les dépendances d'infra (boto3, botocore, storage) avant leur import.
Configure la DB SQLite en mémoire partagée pour tous les tests API.
Permet de tester l'API sans MinIO ni variables d'environnement.
"""
from unittest.mock import MagicMock
import sys
import os
import pytest
import pytest_asyncio

# Modules non installés dans l'env de test
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.client", MagicMock())

# Celery mock: send_task() must return an object with a string .id
_mock_task_result = MagicMock()
_mock_task_result.id = "fake-task-id"
mock_celery_mod = MagicMock()
mock_celery_mod.Celery.return_value.send_task.return_value = _mock_task_result
sys.modules.setdefault("celery", mock_celery_mod)
sys.modules.setdefault("celery.result", MagicMock())

# storage.py lit des vars d'env à l'import — on le remplace entièrement
mock_storage = MagicMock()
mock_storage.ensure_bucket = MagicMock()
mock_storage.upload_artwork = MagicMock()
sys.modules["storage"] = mock_storage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database import Base, get_db
from dependencies import get_current_user, require_admin
from models import User
from auth import hash_password
from main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


def _sqlite_unnest(val):
    """SQLite shim: return first element of a JSON array (genres stored as JSON in SQLite)."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            arr = json.loads(val)
            return arr[0] if arr else None
        except (json.JSONDecodeError, IndexError):
            return val
    return val


def _sqlite_array_length(val, _dim=None):
    if val is None:
        return 0
    if isinstance(val, str):
        try:
            return len(json.loads(val))
        except (json.JSONDecodeError, TypeError):
            return 0
    return 0


@event.listens_for(test_engine.sync_engine, "connect")
def _register_sqlite_functions(dbapi_conn, _rec):
    dbapi_conn.create_function("unnest", 1, _sqlite_unnest)
    dbapi_conn.create_function("array_length", 2, _sqlite_array_length)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_user(db):
    user = User(
        email="test@test.com",
        username="testuser",
        hashed_password=hash_password("testpass"),
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db):
    user = User(
        email="admin@test.com",
        username="admin",
        hashed_password=hash_password("adminpass"),
        is_active=True,
        is_admin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_client(auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def admin_client(admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[require_admin] = lambda: admin_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)
