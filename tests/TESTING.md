# Diggy — Test Standard

Reference document for writing and maintaining all tests.

## Framework

- **pytest** + **pytest-asyncio** + **httpx** (API tests)
- **pytest-mock** (`mocker` fixture) for mocking external services
- `asyncio_mode = "auto"` in `pyproject.toml` — no `pytestmark` needed

## Database

- **API tests**: SQLite in-memory via `aiosqlite` (async), configured in `tests/api/conftest.py`
- **Worker tests**: SQLite in-memory via `sqlite3` (sync), configured in `tests/worker/conftest.py`
- `autouse` fixture creates/drops all tables per test

## Patterns

### API endpoint tests (async)

```python
from httpx import AsyncClient, ASGITransport
from main import app

async def test_list_returns_200(client):
    r = await client.get("/api/endpoint/")
    assert r.status_code == 200
    assert r.json() == []
```

- Use the shared `client` fixture from conftest
- For authenticated endpoints, use `auth_client` or `admin_client`
- Group related tests in classes: `class TestListSets:`
- Mock external services with `mocker.patch("module.function")`

### Worker tests (sync)

```python
from sqlalchemy.orm import Session

def test_logic(sync_session):
    # seed data
    sync_session.add(SomeModel(...))
    sync_session.commit()
    # run core logic (not the Celery task itself)
    result = _core_logic(sync_session)
    assert result == expected
```

- Extract core logic from Celery tasks into testable functions
- Never import or instantiate Celery in tests
- Use the shared `sync_engine` and `sync_session` fixtures from `tests/worker/conftest.py`

### Pure logic tests (sync, no DB)

```python
def test_normalize():
    assert normalize("Fred again..") == "fred again"
```

- No DB, no mocks, no async
- Direct function import and assertion

## Mocking

- `boto3`, `botocore`, `storage` are mocked via `sys.modules` in conftest (not available in test env)
- Deezer API: `mocker.patch("requests.get", ...)` or mock the helper function
- TrackID: `mocker.patch("trackid.client.TrackIDClient", ...)`
- Celery: `mocker.patch("celery.Celery.send_task", ...)` or mock at call site
- S3/MinIO: `mocker.patch("deezer_enrich._get_s3", ...)`

## Auth fixtures

- `client`: unauthenticated AsyncClient
- `auth_client`: authenticated as regular user (dependency override)
- `admin_client`: authenticated as admin user (dependency override)

## Naming

- Files: `test_<module>.py`
- Classes: `Test<Feature>` (e.g., `TestListSets`, `TestImportSet`)
- Methods: `test_<description>` (e.g., `test_returns_empty_list`, `test_404_when_not_found`)

## Assertions

- Always check `status_code` + JSON body
- Use exact values, not magic matchers
- For lists: check `len()` + specific item fields

## Rules

- No Celery framework in tests
- No `sleep` or real network calls
- No `pytestmark = pytest.mark.asyncio` (handled by config)
- Fake data in `tests/<module>/fakes.py` when shared across test files
- `sys.path` and `sys.modules` hacks centralized in conftest files only
