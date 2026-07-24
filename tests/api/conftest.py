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

# --- Per-xdist-worker database isolation (PostgreSQL only) ------------------
# pytest-xdist names each worker ("gw0", "gw1", ...) via PYTEST_XDIST_WORKER
# (unset when serial). The per-test TRUNCATE ... CASCADE below wipes EVERY
# table, so workers sharing one PostgreSQL database would destroy each other's
# fixtures mid-test. Each worker therefore gets its OWN database
# (diggy_test_gw0, ...), created at session start (see setup_db). We rewrite
# DATABASE_URL *before* importing the app so EVERY engine derived from it — the
# ORM test engine, the app's own engine, and the sync engines a few tests build
# straight from os.environ["DATABASE_URL"] — targets the per-worker database.
# SQLite runs in-memory (already isolated per worker *process*) and is untouched.
from sqlalchemy.engine import make_url

_is_postgres = os.environ["DATABASE_URL"].startswith("postgresql")
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
_maintenance_url = None  # base DB, used only to CREATE/DROP the per-worker DB
_worker_db_name = None
if _is_postgres and _xdist_worker:
    _base_url = make_url(os.environ["DATABASE_URL"])
    _worker_db_name = f"{_base_url.database}_{_xdist_worker}"
    _maintenance_url = os.environ["DATABASE_URL"]
    # render_as_string(hide_password=False): plain str(URL) masks the password.
    os.environ["DATABASE_URL"] = _base_url.set(
        database=_worker_db_name
    ).render_as_string(hide_password=False)

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
import rate_limit

# DATABASE_URL was already rewritten to the per-worker database above (xdist+PG).
TEST_DATABASE_URL = os.environ["DATABASE_URL"]

if _is_postgres:
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
else:
    test_engine = create_async_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )

TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

# All workers serialize their CREATE DATABASE on this fixed advisory-lock key:
# concurrent "CREATE DATABASE ... TEMPLATE template1" can otherwise fail with
# "template1 is being accessed by other users".
_CREATE_DB_LOCK_KEY = 0xD1CC1


async def _run_maintenance(statements):
    """Run DDL on the base DB in AUTOCOMMIT under an advisory lock.

    asyncpg forbids CREATE/DROP DATABASE inside a transaction, hence AUTOCOMMIT.
    """
    from sqlalchemy import text

    maint_engine = create_async_engine(
        _maintenance_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        async with maint_engine.connect() as conn:
            await conn.execute(
                text("SELECT pg_advisory_lock(:k)"), {"k": _CREATE_DB_LOCK_KEY}
            )
            try:
                for stmt in statements:
                    await conn.execute(text(stmt))
            finally:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": _CREATE_DB_LOCK_KEY}
                )
    finally:
        await maint_engine.dispose()


def _terminate_backends_sql():
    return (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{_worker_db_name}' AND pid <> pg_backend_pid()"
    )


async def _create_worker_database():
    await _run_maintenance(
        [
            _terminate_backends_sql(),
            f'DROP DATABASE IF EXISTS "{_worker_db_name}"',
            f'CREATE DATABASE "{_worker_db_name}"',
        ]
    )


async def _drop_worker_database():
    await _run_maintenance(
        [
            _terminate_backends_sql(),
            f'DROP DATABASE IF EXISTS "{_worker_db_name}"',
        ]
    )


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


class _AllowAllRateLimitRedis:
    """Fast, network-free stand-in for the rate-limit middleware's Redis.

    Reports a count of 1 for every key, so no request ever trips a limit —
    behaviourally identical to the middleware's fail-open path, but without the
    ~2 s connection timeout it pays per request when Redis is absent (redis-py
    retries a dead host with backoff). The dedicated rate-limit tests
    (test_rate_limit.py) patch ``rate_limit._redis`` with their own *counting*
    fake, so their 429 assertions still hold.
    """

    def incr(self, key):
        return 1

    def expire(self, key, ttl):
        pass

    def ttl(self, key):
        return 60


# Preset the module global so RateLimitMiddleware._get_redis() returns this fake
# and never performs the lazy ``import redis`` / real connection.
rate_limit._redis = _AllowAllRateLimitRedis()


class _FakeAsyncRedisClient:
    """Minimal async Redis client for the /api/health check (ping + close)."""

    async def ping(self):
        return True

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _neutralize_health_redis(monkeypatch):
    """The /api/health endpoint opens a real ``redis.asyncio`` connection at call
    time; against an absent Redis that costs ~2 s per hit. Point ``from_url`` at
    an in-memory client so health checks stay instant.

    Function-scoped with monkeypatch's auto-undo, so the patch is torn down after
    every test and never leaks into worker tests that may share this xdist
    process. Skipped when redis is not installed (e.g. CI, where health already
    fails fast via ImportError).
    """
    try:
        import redis.asyncio  # noqa: F401
    except Exception:
        return
    monkeypatch.setattr(
        "redis.asyncio.from_url", lambda *a, **k: _FakeAsyncRedisClient()
    )


@pytest_asyncio.fixture(autouse=True, scope="session")
async def setup_db():
    if _is_postgres and _worker_db_name:
        await _create_worker_database()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    if _is_postgres and _worker_db_name:
        # The whole per-worker database is dropped, so create_all's drop_all is
        # redundant; dispose our connections first so DROP DATABASE succeeds.
        await test_engine.dispose()
        await _drop_worker_database()
    else:
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
