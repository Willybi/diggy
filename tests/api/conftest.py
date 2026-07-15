"""
Patch les dependances d'infra (boto3, botocore, storage) avant leur import.
Configure la DB pour les tests API : PostgreSQL si DATABASE_URL est set, sinon SQLite.
Permet de tester l'API sans MinIO ni variables d'environnement.
"""
from unittest.mock import MagicMock
import sys
import os
import pytest
import pytest_asyncio

# Modules non installes dans l'env de test
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server"))  # for workers.deezer_enrich
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from database import Base, get_db
from dependencies import get_current_user, get_current_user_optional, get_redis, require_admin
from models import User
import auth_middleware
auth_middleware.enabled = False  # Tests use dependency overrides, not real JWTs
from main import app

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
_is_postgres = TEST_DATABASE_URL.startswith("postgresql")

if _is_postgres:
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
else:
    test_engine = create_async_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )

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


if not _is_postgres:
    @event.listens_for(test_engine.sync_engine, "connect")
    def _register_sqlite_functions(dbapi_conn, _rec):
        dbapi_conn.create_function("unnest", 1, _sqlite_unnest)
        dbapi_conn.create_function("array_length", 2, _sqlite_array_length)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


class FakeRedis:
    """In-memory Redis mock for tests."""

    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def setex(self, key, ttl, value):
        self._store[key] = value

    async def delete(self, key):
        return 1 if self._store.pop(key, None) is not None else 0

    async def aclose(self):
        pass


_fake_redis = FakeRedis()


async def override_get_redis():
    yield _fake_redis


app.dependency_overrides[get_redis] = override_get_redis


@pytest_asyncio.fixture(autouse=True, scope="session")
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_db):
    yield
    # The shared FakeRedis persists across tests; clear it so a cached value
    # (e.g. reco:{user_id}) never leaks into the next test reusing the same id.
    _fake_redis._store.clear()
    # The similarity context is cached in-process (seed-agnostic maps); drop it so
    # a prior test's dataset never leaks into another's similarity/reco results.
    from services.similarity_service import reset_similarity_context_cache
    reset_similarity_context_cache()
    async with test_engine.begin() as conn:
        if _is_postgres:
            table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            from sqlalchemy import text
            await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        else:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())


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
        google_id="google-test-user",
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
        google_id="google-admin-user",
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
    app.dependency_overrides[get_current_user_optional] = lambda: auth_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


@pytest_asyncio.fixture
async def admin_client(admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_current_user_optional] = lambda: admin_user
    app.dependency_overrides[require_admin] = lambda: admin_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)
    app.dependency_overrides.pop(require_admin, None)
