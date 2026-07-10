"""
AU4-L3 observability tests.

Runs the real Celery task functions (celery ecosystem mocked, same pattern as
test_beatport_lock.py) against an in-memory SQLite engine to verify:
  - crawl_followed_sets and link_set_artists write a crawl_logs row,
    including on early returns (A3-09)
  - a materialize_parent failure is logged with context and does not
    interrupt the crawl (A3-08)
"""
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Path so workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Mock infra that isn't available outside Docker (same pattern as
# test_task_refactor.py — setdefault keeps this idempotent across files)
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "requests",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


# Same attributes as test_task_refactor.py's decorator: both files overwrite
# the shared workers.celery_app mock, so whichever import order pytest picks,
# tasks decorated by either mock must satisfy both test files' assertions
def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.autoretry_for = kwargs.get("autoretry_for", ())
        fn.bind = kwargs.get("bind", False)
        fn.soft_time_limit = kwargs.get("soft_time_limit")
        fn.time_limit = kwargs.get("time_limit")
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
_celery_app_mod = MagicMock(celery_app=_celery_mock)
sys.modules["workers.celery_app"] = _celery_app_mod

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import Base
from models import (
    Artist,
    CatalogEntry,
    CrawlLog,
    DJSet,
    SetArtist,
    SetTrack,
    User,
    UserSetFollow,
)


@pytest.fixture
def task_engine():
    """SQLite engine for running the real tasks.

    AUTOCOMMIT is required: the tasks overlap two sessions on one engine
    (the CrawlLogger session holds a flushed-but-uncommitted crawl_logs row
    while work sessions open and close). On SQLite :memory: all sessions
    share one connection, so a work session closing would roll back the
    pending crawl_logs INSERT. PG (prod) uses separate connections and has
    no such coupling.
    """
    engine = create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def tasks_env(task_engine, monkeypatch):
    """Import the real task modules with celery mocked + engine redirected."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.db as workers_db
    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)
    import workers.tasks.artists as artists_mod
    import workers.tasks.sets as sets_mod
    return SimpleNamespace(sets=sets_mod, artists=artists_mod)


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-obs"
    return task_self


def _get_crawl_log(engine, task_type):
    with Session(engine) as s:
        return s.execute(
            select(CrawlLog).where(CrawlLog.task_type == task_type)
        ).scalar_one()


class TestCrawlFollowedSetsCrawlLog:
    def test_no_followed_sets_writes_success_log(
        self, tasks_env, task_engine, fake_self
    ):
        """Early return (nothing followed) must still leave a crawl_logs line."""
        result = tasks_env.sets.crawl_followed_sets(fake_self)

        assert result == {"crawled": 0, "skipped_complete": 0, "skipped_recent": 0}
        log = _get_crawl_log(task_engine, "crawl_followed_sets")
        assert log.status == "success"
        assert log.stats == {"crawled": 0, "skipped_complete": 0, "skipped_recent": 0}
        assert log.celery_task_id == "task-obs"

    def test_all_sets_skipped_writes_success_log(
        self, tasks_env, task_engine, fake_self
    ):
        """Early return (nothing to crawl) must still leave a crawl_logs line."""
        with Session(task_engine) as s:
            u = User(email="t@t.com", username="t", google_id="g", is_active=True)
            s.add(u)
            s.flush()
            cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
            s.add(cat)
            s.flush()
            # 1 track, fully identified -> skipped_complete
            dj = DJSet(source="trackid", title="Complete Set")
            s.add(dj)
            s.flush()
            s.add(
                SetTrack(
                    set_id=dj.id,
                    position=1,
                    raw_title="T",
                    catalog_id=cat.id,
                    is_id=False,
                )
            )
            s.add(UserSetFollow(user_id=u.id, set_id=dj.id))
            s.commit()

        result = tasks_env.sets.crawl_followed_sets(fake_self)

        assert result == {"crawled": 0, "skipped_complete": 1, "skipped_recent": 0}
        log = _get_crawl_log(task_engine, "crawl_followed_sets")
        assert log.status == "success"
        assert log.stats == {"crawled": 0, "skipped_complete": 1, "skipped_recent": 0}


class TestLinkSetArtistsCrawlLog:
    def test_run_writes_success_log(self, tasks_env, task_engine, fake_self):
        with Session(task_engine) as s:
            s.add(Artist(name="ANNA", normalized_name="anna"))
            s.add(DJSet(source="trackid", title="ANNA at Boiler Room"))
            s.commit()

        result = tasks_env.artists.link_set_artists(fake_self)

        assert result == {"linked": 1, "skipped": 0}
        with Session(task_engine) as s:
            assert s.execute(select(SetArtist)).scalar_one() is not None
        log = _get_crawl_log(task_engine, "link_set_artists")
        assert log.status == "success"
        assert log.stats == {"linked": 1, "skipped": 0}
        assert log.celery_task_id == "task-obs"


class TestMaterializeParentLogging:
    def test_failure_is_logged_and_does_not_interrupt_crawl(
        self, tasks_env, task_engine, fake_self, monkeypatch, caplog
    ):
        """A3-08: materialize_parent raising must log a warning with the
        parent_set_id and traceback, and the crawl must complete normally."""
        with Session(task_engine) as s:
            u = User(email="t@t.com", username="t", google_id="g", is_active=True)
            s.add(u)
            s.flush()
            # Eligible: unresolved track, never crawled (last_crawled_at None)
            dj = DJSet(
                source="trackid",
                title="Eligible Set",
                external_id="ext-1",
                external_slug="slug-1",
            )
            s.add(dj)
            s.flush()
            s.add(SetTrack(set_id=dj.id, position=1, raw_title="Unknown", is_id=False))
            s.add(UserSetFollow(user_id=u.id, set_id=dj.id))
            s.commit()

        class FakeTrackIDClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        async def fake_import_audiostream(db, client, audiostream, min_age_hours=168):
            return SimpleNamespace(parent_set_id=99), 5

        async def failing_materialize_parent(db, parent_set_id):
            raise RuntimeError("boom")

        monkeypatch.setitem(
            sys.modules,
            "trackid.client",
            SimpleNamespace(TrackIDClient=FakeTrackIDClient),
        )
        monkeypatch.setitem(
            sys.modules,
            "trackid.importer",
            SimpleNamespace(import_audiostream=fake_import_audiostream),
        )
        monkeypatch.setitem(
            sys.modules,
            "services.set_dedup_service",
            SimpleNamespace(materialize_parent=failing_materialize_parent),
        )

        with caplog.at_level(logging.WARNING):
            result = tasks_env.sets.crawl_followed_sets(fake_self)

        # The crawl completed despite the materialize_parent failure
        assert result == {"crawled": 1, "skipped_complete": 0, "skipped_recent": 0}

        warnings = [
            r
            for r in caplog.records
            if "materialize_parent failed for set 99" in r.getMessage()
        ]
        assert len(warnings) == 1
        assert "RuntimeError" in caplog.text  # exc_info traceback attached

        log = _get_crawl_log(task_engine, "crawl_followed_sets")
        assert log.status == "success"
        assert log.stats == {"crawled": 1, "skipped_complete": 0, "skipped_recent": 0}
