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

# google-auth n'est pas installé en CI
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.id_token", MagicMock())
sys.modules.setdefault("google.auth", MagicMock())
sys.modules.setdefault("google.auth.transport", MagicMock())
sys.modules.setdefault("google.auth.transport.requests", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database import Base, get_db
from dependencies import get_current_user, require_admin
from models import User
from auth import create_token
from main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


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
        google_id="google-test-123",
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
        google_id="google-admin-456",
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
