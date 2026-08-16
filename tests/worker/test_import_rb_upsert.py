"""Test the PostgreSQL upsert core of the Rekordbox import (A6-08).

``workers.tasks.import_rb.import_rekordbox_xml`` writes each imported track's
``user_track`` through ``sqlalchemy.dialects.postgresql.insert(...)
.on_conflict_do_update(...)``. That ``ON CONFLICT`` clause is PostgreSQL-only —
SQLite cannot execute it — so this whole module is skipped unless DATABASE_URL
points at PostgreSQL (the CI matrix). psycopg2 backs the sync engine.

We patch away everything that is not the upsert (S3 download, XML parsing, Redis,
Celery) and drive the raw task function directly, asserting:
  * first import  -> inserted=2, updated=0, 2 user_tracks
  * same tracks   -> inserted=0, updated=2, still 2 user_tracks (idempotent)
  * changed bpm   -> on_conflict_do_update refreshes rb_bpm on the existing row

The XML parser itself is already covered by test_rekordbox_xml.py, hence the stub.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="RB import upsert is PostgreSQL-only (ON CONFLICT DO UPDATE)",
)

# --- Path so the `workers` package is importable (same pattern as
# test_genres_reclassify.py; conftest already adds server/api for models/utils) ---
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# --- Mock infra not available outside Docker (mirrors test_genres_reclassify.py).
# Importing workers.tasks.import_rb runs workers/tasks/__init__.py, which eagerly
# imports the WHOLE task graph (artists -> enrichment -> async_http, genres, ...),
# so the same mock set is required even though the upsert task needs none of it. ---
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "requests",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# genres.py does `from celery.exceptions import SoftTimeLimitExceeded` and catches
# it; expose a REAL Exception subclass so both the import and the `except` clause
# are valid (a bare MagicMock attribute is not a class). Same trick as
# test_genres_reclassify.py.
class _FakeSoftTimeLimitExceeded(Exception):
    pass


_celery_exceptions = sys.modules.setdefault("celery.exceptions", MagicMock())
_celery_exceptions.SoftTimeLimitExceeded = _FakeSoftTimeLimitExceeded

# Mock workers.celery_app so the `.task` decorator returns the RAW function
# (undecorated), letting us call the task body directly.
_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn

    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

# Force a fresh import so the tasks are decorated by the mock above.
for _m in [k for k in list(sys.modules) if k.startswith("workers.tasks")]:
    del sys.modules[_m]

# redis / curl_cffi are not installed in the test env; import_rb imports redis at
# module load and the task-graph __init__ pulls curl_cffi. Save/restore dance
# (same as test_genres_reclassify.py) so we don't pollute other worker test files.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.db as workers_db  # noqa: E402
import workers.tasks.import_rb as import_rb  # noqa: E402

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl
del _saved_curl

import services.rekordbox_xml as rekordbox_xml  # noqa: E402
from database import Base  # noqa: E402
from models import CatalogEntry, User, UserTrack  # noqa: E402
from schemas import TrackImport  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from utils import make_normalized_key  # noqa: E402

# Advisory-lock key serialising the throwaway-DB DDL (see _run_maintenance).
_MAINT_LOCK_KEY = 0xA608


def _run_maintenance(maint_dsn: str, statements: list[str]) -> None:
    """Run CREATE/DROP DATABASE (autocommit) on a maintenance DB under an
    advisory lock, mirroring tests/api/conftest.py's _run_maintenance. psycopg2
    forbids CREATE/DROP DATABASE inside a transaction, hence autocommit."""
    import psycopg2

    conn = psycopg2.connect(maint_dsn)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_lock(%s)", (_MAINT_LOCK_KEY,))
        try:
            for stmt in statements:
                cur.execute(stmt)
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_MAINT_LOCK_KEY,))
        cur.close()
    finally:
        conn.close()


def _terminate_backends_sql(db_name: str) -> str:
    return (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
    )


@pytest.fixture
def pg_engine():
    """A sync psycopg2 engine on a THROWAWAY database created just for this test.

    NB: we deliberately do NOT create_all/drop_all on DATABASE_URL itself. Under
    xdist a worker can run this module AND tests/api modules in the same process
    (tests/api/conftest.py rewrites DATABASE_URL to a per-worker DB whose schema
    is SESSION-scoped) — a drop_all there would wipe the schema those api tests
    still rely on. A dedicated database (same pattern as tests/api's own
    _create_worker_database) keeps this test fully isolated.
    """
    base_url = make_url(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    worker = os.environ.get("PYTEST_XDIST_WORKER", "solo")
    test_db = f"{base_url.database}_rbupsert_{worker}"
    maint_dsn = base_url.render_as_string(hide_password=False)

    _run_maintenance(
        maint_dsn,
        [
            _terminate_backends_sql(test_db),
            f'DROP DATABASE IF EXISTS "{test_db}"',
            f'CREATE DATABASE "{test_db}"',
        ],
    )
    engine = create_engine(
        base_url.set(database=test_db).render_as_string(hide_password=False)
    )
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        _run_maintenance(
            maint_dsn,
            [
                _terminate_backends_sql(test_db),
                f'DROP DATABASE IF EXISTS "{test_db}"',
            ],
        )


def _make_user(engine) -> int:
    with Session(engine) as session:
        user = User(
            email="rb-import@example.com",
            username="rb-importer",
            google_id="google-rb-import",
            settings={},
        )
        session.add(user)
        session.commit()
        return user.id


def _make_tracks(bpm_first: float):
    """Two tracks with DISTINCT normalized keys, stable across calls so a
    re-import hits the same catalog rows (the update path)."""
    return [
        TrackImport(
            id=101,
            title="Strobe",
            artist="Deadmau5",
            bpm=bpm_first,
            key="8A",
            duration=600000,
            file_path="file:///music/strobe.mp3",
            date_added=None,
            tags=["peak"],
        ),
        TrackImport(
            id=102,
            title="Ghosts n Stuff",
            artist="Deadmau5",
            bpm=128.0,
            key="9A",
            duration=210000,
            file_path="file:///music/ghosts.mp3",
            date_added=None,
            tags=[],
        ),
    ]


def _count_user_tracks(engine, user_id: int) -> int:
    with Session(engine) as session:
        return session.execute(
            select(func.count())
            .select_from(UserTrack)
            .where(UserTrack.user_id == user_id)
        ).scalar_one()


def _wire_task(monkeypatch, engine, tracks_ref: dict):
    """Patch away S3, Redis, the XML parser and the engine factory; return the
    list the task's progress payloads are recorded into."""
    progress: list[dict] = []

    def _spy_progress(r, task_id, data):
        progress.append(dict(data))

    monkeypatch.setattr(import_rb, "_set_progress", _spy_progress)

    fake_s3 = MagicMock()
    fake_body = MagicMock()
    fake_body.read.return_value = b"<DJ_PLAYLISTS/>"  # parse is stubbed anyway
    fake_s3.get_object.return_value = {"Body": fake_body}
    monkeypatch.setattr(import_rb, "_get_s3", lambda: fake_s3)

    monkeypatch.setattr(import_rb.redis_lib, "from_url", MagicMock())
    monkeypatch.setattr(workers_db, "get_engine", lambda: engine)
    monkeypatch.setattr(
        rekordbox_xml, "parse_rekordbox_xml", lambda content: tracks_ref["tracks"]
    )
    return progress


def test_import_upsert_insert_then_update_then_refresh(pg_engine, monkeypatch):
    user_id = _make_user(pg_engine)
    tracks_ref = {"tracks": _make_tracks(bpm_first=128.0)}
    progress = _wire_task(monkeypatch, pg_engine, tracks_ref)

    # --- First import: two brand-new user_tracks ---
    import_rb.import_rekordbox_xml(MagicMock(), "task-1", user_id)
    done = progress[-1]
    assert done["status"] == "done"
    assert done["inserted"] == 2
    assert done["updated"] == 0
    assert _count_user_tracks(pg_engine, user_id) == 2

    # --- Second import, same tracks: upsert updates, never duplicates ---
    progress.clear()
    import_rb.import_rekordbox_xml(MagicMock(), "task-2", user_id)
    done = progress[-1]
    assert done["status"] == "done"
    assert done["inserted"] == 0
    assert done["updated"] == 2
    assert _count_user_tracks(pg_engine, user_id) == 2

    # --- Third import with a changed bpm: on_conflict_do_update refreshes it ---
    tracks_ref["tracks"] = _make_tracks(bpm_first=130.0)
    progress.clear()
    import_rb.import_rekordbox_xml(MagicMock(), "task-3", user_id)
    done = progress[-1]
    assert done["updated"] == 2
    assert _count_user_tracks(pg_engine, user_id) == 2

    norm_key = make_normalized_key("Strobe", "Deadmau5")
    with Session(pg_engine) as session:
        catalog_id = session.execute(
            select(CatalogEntry.id).where(CatalogEntry.normalized_key == norm_key)
        ).scalar_one()
        rb_bpm = session.execute(
            select(UserTrack.rb_bpm).where(
                UserTrack.user_id == user_id,
                UserTrack.catalog_id == catalog_id,
            )
        ).scalar_one()
    assert rb_bpm == 130.0
