"""
Tests for the Rekordbox XML upload lock (AU4-L1 / A3-14).

The per-user import lock must be acquired atomically (SET NX EX) before any
side effect: two concurrent uploads for the same user used to both pass the
old exists-then-set check.
"""
import pytest
import pytest_asyncio

from main import app
from dependencies import get_redis
from routers.import_rb import IMPORT_LOCK_TTL

VALID_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="0"></COLLECTION></DJ_PLAYLISTS>'
)


class LockFakeRedis:
    """In-memory Redis mock with SET NX EX semantics, recording set() calls."""

    def __init__(self):
        self._store = {}
        self.set_calls = []

    async def set(self, key, value, nx=False, ex=None):
        self.set_calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        return 1 if self._store.pop(key, None) is not None else 0

    async def aclose(self):
        pass


@pytest_asyncio.fixture
async def lock_redis():
    """Replace the conftest FakeRedis (no set/get) with a lock-capable one."""
    fake = LockFakeRedis()
    old = app.dependency_overrides.get(get_redis)

    async def _override():
        yield fake

    app.dependency_overrides[get_redis] = _override
    yield fake
    if old is not None:
        app.dependency_overrides[get_redis] = old
    else:
        app.dependency_overrides.pop(get_redis, None)


@pytest_asyncio.fixture
async def s3_mock(mocker):
    mocker.patch("services.image_service.ImageService.ensure_bucket")
    s3 = mocker.patch("services.image_service.ImageService._get_s3").return_value
    return s3


def _upload(client):
    return client.post(
        "/api/import/rekordbox-xml",
        files={"file": ("export.xml", VALID_XML, "application/xml")},
    )


class TestImportLockAcquisition:
    async def test_upload_acquires_lock_atomically(
        self, auth_client, auth_user, lock_redis, s3_mock
    ):
        r = await _upload(auth_client)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "queued"

        lock_call = lock_redis.set_calls[0]
        assert lock_call["key"] == f"import:lock:{auth_user.id}"
        assert lock_call["value"] == body["task_id"]
        assert lock_call["nx"] is True
        assert lock_call["ex"] == IMPORT_LOCK_TTL
        s3_mock.upload_fileobj.assert_called_once()

    async def test_second_upload_conflicts_409(
        self, auth_client, auth_user, lock_redis, s3_mock
    ):
        r1 = await _upload(auth_client)
        assert r1.status_code == 200

        r2 = await _upload(auth_client)
        assert r2.status_code == 409
        assert r2.json()["detail"] == "Un import est déjà en cours pour ce compte"

    async def test_409_happens_before_any_side_effect(
        self, auth_client, auth_user, lock_redis, s3_mock
    ):
        """When the lock is held, the upload must be rejected before MinIO is touched."""
        lock_redis._store[f"import:lock:{auth_user.id}"] = "other-task"

        r = await _upload(auth_client)

        assert r.status_code == 409
        s3_mock.upload_fileobj.assert_not_called()
        # Only the failed lock acquisition hit Redis, no progress key was written
        assert len(lock_redis.set_calls) == 1

    async def test_lock_ttl_covers_task_time_limit(self):
        """The task inherits the global CELERY_TIME_LIMIT (3600s)."""
        assert IMPORT_LOCK_TTL > 3600


class TestImportLockReleaseOnFailure:
    """A failure between lock acquisition and task enqueue must free the lock:
    the task will never run, so nothing else could release it before its TTL."""

    async def test_failed_upload_releases_lock_and_allows_retry(
        self, auth_client, auth_user, lock_redis, s3_mock
    ):
        s3_mock.upload_fileobj.side_effect = RuntimeError("minio down")

        with pytest.raises(RuntimeError):
            await _upload(auth_client)

        assert f"import:lock:{auth_user.id}" not in lock_redis._store

        # An immediate retry re-acquires the lock and succeeds
        s3_mock.upload_fileobj.side_effect = None
        r = await _upload(auth_client)
        assert r.status_code == 200
        assert r.json()["status"] == "queued"

    async def test_failed_upload_keeps_lock_owned_by_another_import(
        self, auth_client, auth_user, lock_redis, s3_mock
    ):
        """If the lock expired mid-request and a newer import re-acquired it,
        the failing request must not delete the new owner's lock."""
        lock_key = f"import:lock:{auth_user.id}"

        def steal_lock_then_fail(*args, **kwargs):
            lock_redis._store[lock_key] = "task-other"
            raise RuntimeError("minio down")

        s3_mock.upload_fileobj.side_effect = steal_lock_then_fail

        with pytest.raises(RuntimeError):
            await _upload(auth_client)

        assert lock_redis._store[lock_key] == "task-other"
