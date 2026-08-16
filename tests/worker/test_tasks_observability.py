"""
AU4-L3 observability tests.

Runs the real Celery task functions (celery ecosystem mocked, same pattern as
test_beatport_lock.py) against an in-memory SQLite engine to verify that
link_set_artists writes a crawl_logs row (A3-09).

The crawl_followed_sets observability tests (crawl_logs on early return,
materialize_parent failure logged and non-fatal, A3-08) moved to
test_tasks_recrawl_sets.py with the replacement task (C6.b).
"""
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
    CrawlLog,
    DJSet,
    SetArtist,
)
from workers.crawl_logger import CrawlLogger


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


class TestCrawlLoggerDurability:
    """A3-07: the "running" row is committed at __enter__ so a worker killed
    mid-run (SIGKILL on deploy, OOM) before __exit__ still leaves a visible row.

    Uses the plain (non-AUTOCOMMIT) ``sync_engine`` on purpose: on an AUTOCOMMIT
    engine a flush() is already durable, so it could not tell the old (flush)
    behaviour apart from the new (commit-at-enter) one.
    """

    def test_enter_commits_running_row(self, sync_engine):
        # __enter__ then simulate the worker dying mid-run: its connection is
        # reaped and whatever it had uncommitted is rolled back by the DB. The
        # "running" marker must already be durable — a plain flush() would be
        # undone by this rollback and the run would vanish.
        log_session = Session(sync_engine)
        clog = CrawlLogger(
            log_session, task_type="unit_running", target_label="Killed run"
        )
        clog.__enter__()
        log_session.rollback()
        log_session.close()

        with Session(sync_engine) as verify:
            row = verify.execute(
                select(CrawlLog).where(CrawlLog.task_type == "unit_running")
            ).scalar_one()
        assert row.status == "running"
        assert row.finished_at is None
        assert row.duration_ms is None

    def test_exit_updates_same_row_to_final(self, sync_engine):
        # A normal run: __exit__ must UPDATE the row committed at __enter__,
        # not INSERT a second one.
        with Session(sync_engine) as s:
            with CrawlLogger(s, task_type="unit_success") as clog:
                clog.set_stats({"done": 1})

        with Session(sync_engine) as verify:
            rows = (
                verify.execute(
                    select(CrawlLog).where(CrawlLog.task_type == "unit_success")
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1  # UPDATE, not a second INSERT
        assert rows[0].status == "success"
        assert rows[0].stats == {"done": 1}
        assert rows[0].finished_at is not None
        assert rows[0].duration_ms is not None

    def test_exit_records_error_and_reraises(self, sync_engine):
        log_session = Session(sync_engine)
        with pytest.raises(ValueError, match="boom"):
            with CrawlLogger(log_session, task_type="unit_error"):
                raise ValueError("boom")
        log_session.close()

        with Session(sync_engine) as verify:
            row = verify.execute(
                select(CrawlLog).where(CrawlLog.task_type == "unit_error")
            ).scalar_one()
        assert row.status == "error"
        # AV8-04: error_message is now type-prefixed ("<ExcType>: <str(e)>")
        # so a blank-str() exception still records the type. The original
        # message is preserved after the prefix.
        assert row.error_message == "ValueError: boom"
        assert row.finished_at is not None

    def test_exit_error_message_prefixes_type_when_str_empty(self, sync_engine):
        # AV8-04: some exceptions have an empty str() (a re-raised
        # httpx.ReadTimeout, a bare TimeoutError()). Before the fix error_message
        # was left blank ("failed after Nms: ") and the cause was undiagnosable —
        # verify the type name is always kept so the row is never uninformative.
        log_session = Session(sync_engine)
        with pytest.raises(TimeoutError):
            with CrawlLogger(log_session, task_type="unit_error_empty"):
                raise TimeoutError()
        log_session.close()

        with Session(sync_engine) as verify:
            row = verify.execute(
                select(CrawlLog).where(CrawlLog.task_type == "unit_error_empty")
            ).scalar_one()
        assert row.status == "error"
        assert str(TimeoutError()) == ""  # guard: the exception really is blank
        assert row.error_message  # non-empty despite the blank str()
        assert "TimeoutError" in row.error_message
