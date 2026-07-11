"""
C6.b — tests for recrawl_incomplete_sets.

Runs the real task function (celery ecosystem mocked, same pattern as
test_tasks_observability.py) plus direct tests of the pure helpers
(_completion_pct, _recrawl_decision, _apply_recrawl_outcome).

The full-task tests use a file-backed SQLite DB so the sync engine
(workers.db.get_engine, monkeypatched) and the async engine the task builds
from DATABASE_URL see the same data — :memory: would give the async side an
empty, table-less database. The TrackID client and import_audiostream are
mocked (no network); the fake import mutates set_tracks through the task's
own AsyncSession to simulate TrackID identification progress.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
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
from models import CrawlLog, DJSet, SetTrack


@pytest.fixture
def task_engine(tmp_path, monkeypatch):
    """File-backed SQLite shared by the task's sync and async engines.

    AUTOCOMMIT for the same reason as test_tasks_observability.py: the
    CrawlLogger session holds a flushed crawl_logs row while work sessions
    (including the async one) open and write on the same database.
    """
    db_path = (tmp_path / "recrawl.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    engine = create_engine(
        f"sqlite:///{db_path}", isolation_level="AUTOCOMMIT"
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def tasks_env(task_engine, monkeypatch):
    """Import the real task module with celery mocked + engine redirected."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.db as workers_db
    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)
    import workers.tasks.sets as sets_mod
    return SimpleNamespace(sets=sets_mod)


@pytest.fixture
def sets_mod(monkeypatch):
    """Lightweight module import for pure-helper tests (no DB needed)."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.tasks.sets as sets
    return sets


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-recrawl"
    return task_self


class FakeTrackIDClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _make_fake_import(progress_ext_ids=frozenset(), fail_ext_ids=frozenset()):
    """import_audiostream stand-in working through the task's AsyncSession.

    Sets in progress_ext_ids get one unidentified track flipped to
    identified (simulating TrackID progress since the last crawl); sets in
    fail_ext_ids raise like a network failure.
    """
    async def fake_import(db, client, audiostream, min_age_hours=168):
        ext_id = str(audiostream["id"])
        if ext_id in fail_ext_ids:
            raise RuntimeError("trackid down")
        result = await db.execute(
            select(DJSet).where(
                DJSet.external_id == ext_id, DJSet.source == "trackid"
            )
        )
        dj_set = result.scalar_one()
        if ext_id in progress_ext_ids:
            tr = (
                (
                    await db.execute(
                        select(SetTrack)
                        .where(
                            SetTrack.set_id == dj_set.id,
                            SetTrack.is_id.is_(True),
                        )
                        .order_by(SetTrack.position)
                    )
                )
                .scalars()
                .first()
            )
            if tr is not None:
                tr.is_id = False
        dj_set.last_crawled_at = datetime.now(timezone.utc)
        await db.flush()
        return dj_set, 1

    return fake_import


def _install_trackid_mocks(monkeypatch, fake_import):
    monkeypatch.setitem(
        sys.modules,
        "trackid.client",
        SimpleNamespace(TrackIDClient=FakeTrackIDClient),
    )
    monkeypatch.setitem(
        sys.modules,
        "trackid.importer",
        SimpleNamespace(import_audiostream=fake_import),
    )


def _make_set(
    session,
    ext_id,
    *,
    identified=0,
    unidentified=0,
    created_days_ago=2.0,
    last_crawled_hours_ago=30.0,
    completion_pct=None,
    recrawl_count=0,
    recrawl_status="active",
    source="trackid",
    is_virtual=False,
    parent_set_id=None,
):
    now = datetime.now(timezone.utc)
    dj = DJSet(
        source=source,
        title=f"Set {ext_id}",
        external_id=ext_id,
        external_slug=f"slug-{ext_id}",
        created_at=now - timedelta(days=created_days_ago),
        last_crawled_at=(
            now - timedelta(hours=last_crawled_hours_ago)
            if last_crawled_hours_ago is not None
            else None
        ),
        is_virtual=is_virtual,
        parent_set_id=parent_set_id,
        completion_pct=completion_pct,
        recrawl_count=recrawl_count,
        recrawl_status=recrawl_status,
    )
    session.add(dj)
    session.flush()
    pos = 0
    for _ in range(identified):
        pos += 1
        session.add(
            SetTrack(set_id=dj.id, position=pos, raw_title=f"T{pos}", is_id=False)
        )
    for _ in range(unidentified):
        pos += 1
        session.add(
            SetTrack(set_id=dj.id, position=pos, raw_title="ID", is_id=True)
        )
    return dj


def _reload_set(engine, set_id):
    with Session(engine) as s:
        return s.get(DJSet, set_id)


def _get_crawl_log(engine):
    with Session(engine) as s:
        return s.execute(
            select(CrawlLog).where(
                CrawlLog.task_type == "recrawl_incomplete_sets"
            )
        ).scalar_one()


# ── Pure helpers ──────────────────────────────────────────────────────────────


class TestCompletionPct:
    def test_zero_tracks_is_incomplete(self, sets_mod):
        assert sets_mod._completion_pct(0, 0) == 0.0

    def test_partial(self, sets_mod):
        assert sets_mod._completion_pct(4, 1) == 0.75

    def test_full(self, sets_mod):
        assert sets_mod._completion_pct(3, 0) == 1.0


class TestRecrawlDecision:
    NOW = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)

    def _decide(self, sets_mod, age_days, ref_days_ago):
        created = self.NOW - timedelta(days=age_days)
        ref = (
            self.NOW - timedelta(days=ref_days_ago)
            if ref_days_ago is not None
            else None
        )
        return sets_mod._recrawl_decision(self.NOW, created, ref)

    def test_never_crawled_is_due(self, sets_mod):
        assert self._decide(sets_mod, 2, None) == "crawl"

    def test_young_set_24h_tier(self, sets_mod):
        assert self._decide(sets_mod, 2, 25 / 24) == "crawl"
        assert self._decide(sets_mod, 2, 23 / 24) == "wait"

    def test_week_old_set_7d_tier(self, sets_mod):
        assert self._decide(sets_mod, 10, 8) == "crawl"
        assert self._decide(sets_mod, 10, 6) == "wait"

    def test_month_old_set_30d_tier(self, sets_mod):
        assert self._decide(sets_mod, 45, 31) == "crawl"
        assert self._decide(sets_mod, 45, 29) == "wait"

    def test_past_90_days_is_final(self, sets_mod):
        assert self._decide(sets_mod, 91, 40) == "final"

    def test_missing_created_at_treated_as_new(self, sets_mod):
        assert sets_mod._recrawl_decision(
            self.NOW, None, self.NOW - timedelta(hours=25)
        ) == "crawl"

    def test_naive_datetimes_accepted(self, sets_mod):
        """SQLite returns naive datetimes; they must be treated as UTC."""
        created = (self.NOW - timedelta(days=2)).replace(tzinfo=None)
        ref = (self.NOW - timedelta(hours=25)).replace(tzinfo=None)
        assert sets_mod._recrawl_decision(self.NOW, created, ref) == "crawl"


class TestApplyRecrawlOutcome:
    NOW = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)

    def _set(self, count=0, pct=None):
        return SimpleNamespace(
            recrawl_count=count,
            recrawl_status="active",
            completion_pct=pct,
            last_recrawl_at=None,
        )

    def test_progression_resets_counter(self, sets_mod):
        dj = self._set(count=2, pct=0.3)
        finalized = sets_mod._apply_recrawl_outcome(dj, 0.3, 0.5, self.NOW)
        assert finalized is None
        assert dj.recrawl_count == 0
        assert dj.recrawl_status == "active"
        assert dj.completion_pct == 0.5
        assert dj.last_recrawl_at == self.NOW

    def test_null_previous_pct_counts_as_progression(self, sets_mod):
        dj = self._set(count=2, pct=None)
        finalized = sets_mod._apply_recrawl_outcome(dj, None, 0.0, self.NOW)
        assert finalized is None
        assert dj.recrawl_count == 0

    def test_stagnation_increments_counter(self, sets_mod):
        dj = self._set(count=0, pct=0.5)
        finalized = sets_mod._apply_recrawl_outcome(dj, 0.5, 0.5, self.NOW)
        assert finalized is None
        assert dj.recrawl_count == 1
        assert dj.recrawl_status == "active"

    def test_third_stale_run_finalizes(self, sets_mod):
        dj = self._set(count=2, pct=0.5)
        finalized = sets_mod._apply_recrawl_outcome(dj, 0.5, 0.5, self.NOW)
        assert finalized == "stale"
        assert dj.recrawl_count == 3
        assert dj.recrawl_status == "final"

    def test_full_completion_finalizes(self, sets_mod):
        dj = self._set(count=2, pct=0.5)
        finalized = sets_mod._apply_recrawl_outcome(dj, 0.5, 1.0, self.NOW)
        assert finalized == "complete"
        assert dj.recrawl_count == 0
        assert dj.recrawl_status == "final"
        assert dj.completion_pct == 1.0


# ── Full task: pre-pass + eligibility (no crawl) ─────────────────────────────


class TestRecrawlPrepassAndEligibility:
    def test_empty_db_writes_success_log(self, tasks_env, task_engine, fake_self):
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result == {
            "eligible": 0,
            "crawled": 0,
            "finalized_complete": 0,
            "finalized_age": 0,
            "finalized_stale": 0,
            "errors": 0,
            "dropped_by_cap": 0,
        }
        log = _get_crawl_log(task_engine)
        assert log.status == "success"
        assert log.stats == result
        assert log.celery_task_id == "task-recrawl"

    def test_prepass_finalizes_complete_set_without_crawl(
        self, tasks_env, task_engine, fake_self
    ):
        with Session(task_engine) as s:
            dj = _make_set(s, "done-1", identified=2, unidentified=0)
            s.commit()
            set_id = dj.id

        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["finalized_complete"] == 1
        assert result["eligible"] == 0
        assert result["crawled"] == 0
        dj = _reload_set(task_engine, set_id)
        assert dj.completion_pct == 1.0
        assert dj.recrawl_status == "final"
        tasks_env.sets.resolve_set_tracks.delay.assert_not_called()

    def test_non_trackid_virtual_and_final_sets_ignored(
        self, tasks_env, task_engine, fake_self
    ):
        with Session(task_engine) as s:
            manual = _make_set(s, "man-1", identified=1, source="manual")
            virtual = _make_set(s, "virt-1", unidentified=1, is_virtual=True)
            final = _make_set(s, "fin-1", unidentified=1, recrawl_status="final")
            s.commit()
            ids = (manual.id, virtual.id, final.id)

        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["eligible"] == 0
        assert result["finalized_complete"] == 0
        assert result["finalized_age"] == 0
        for set_id in ids:
            dj = _reload_set(task_engine, set_id)
            assert dj.completion_pct is None
            assert dj.last_recrawl_at is None

    def test_recent_reference_waits(self, tasks_env, task_engine, fake_self):
        with Session(task_engine) as s:
            dj = _make_set(
                s, "recent-1", identified=1, unidentified=1,
                created_days_ago=2.0, last_crawled_hours_ago=2.0,
            )
            s.commit()
            set_id = dj.id

        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["eligible"] == 0
        assert result["crawled"] == 0
        dj = _reload_set(task_engine, set_id)
        assert dj.recrawl_status == "active"
        tasks_env.sets.resolve_set_tracks.delay.assert_not_called()

    def test_set_older_than_90_days_finalized_without_crawl(
        self, tasks_env, task_engine, fake_self
    ):
        with Session(task_engine) as s:
            dj = _make_set(
                s, "old-1", identified=1, unidentified=1,
                created_days_ago=100.0, last_crawled_hours_ago=24 * 40,
            )
            s.commit()
            set_id = dj.id

        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["finalized_age"] == 1
        assert result["eligible"] == 0
        assert result["crawled"] == 0
        dj = _reload_set(task_engine, set_id)
        assert dj.recrawl_status == "final"

    def test_zero_track_set_is_eligible(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        """total=0 → completion 0.0 → incomplete, must be crawled."""
        with Session(task_engine) as s:
            _make_set(s, "empty-1", identified=0, unidentified=0)
            s.commit()

        _install_trackid_mocks(monkeypatch, _make_fake_import())
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["eligible"] == 1
        assert result["crawled"] == 1


# ── Full task: crawl outcomes ─────────────────────────────────────────────────


class TestRecrawlCrawlOutcomes:
    def test_progression_resets_counter(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        with Session(task_engine) as s:
            dj = _make_set(
                s, "prog-1", identified=1, unidentified=2,
                completion_pct=1 / 3, recrawl_count=2,
            )
            s.commit()
            set_id = dj.id

        _install_trackid_mocks(
            monkeypatch, _make_fake_import(progress_ext_ids={"prog-1"})
        )
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["crawled"] == 1
        assert result["finalized_stale"] == 0
        dj = _reload_set(task_engine, set_id)
        assert dj.recrawl_count == 0
        assert dj.recrawl_status == "active"
        assert dj.completion_pct == pytest.approx(2 / 3)
        assert dj.last_recrawl_at is not None
        tasks_env.sets.resolve_set_tracks.delay.assert_called_once()

    def test_no_progression_increments_counter(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        with Session(task_engine) as s:
            dj = _make_set(
                s, "stale-1", identified=1, unidentified=1,
                completion_pct=0.5, recrawl_count=0,
            )
            s.commit()
            set_id = dj.id

        _install_trackid_mocks(monkeypatch, _make_fake_import())
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["crawled"] == 1
        assert result["finalized_stale"] == 0
        dj = _reload_set(task_engine, set_id)
        assert dj.recrawl_count == 1
        assert dj.recrawl_status == "active"

    def test_third_stale_run_finalizes(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        with Session(task_engine) as s:
            dj = _make_set(
                s, "stale-3", identified=1, unidentified=1,
                completion_pct=0.5, recrawl_count=2,
            )
            s.commit()
            set_id = dj.id

        _install_trackid_mocks(monkeypatch, _make_fake_import())
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["finalized_stale"] == 1
        dj = _reload_set(task_engine, set_id)
        assert dj.recrawl_count == 3
        assert dj.recrawl_status == "final"

    def test_full_identification_finalizes_complete(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        with Session(task_engine) as s:
            dj = _make_set(
                s, "comp-1", identified=1, unidentified=1,
                completion_pct=0.5, recrawl_count=2,
            )
            s.commit()
            set_id = dj.id

        _install_trackid_mocks(
            monkeypatch, _make_fake_import(progress_ext_ids={"comp-1"})
        )
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["finalized_complete"] == 1
        assert result["finalized_stale"] == 0
        dj = _reload_set(task_engine, set_id)
        assert dj.completion_pct == 1.0
        assert dj.recrawl_count == 0
        assert dj.recrawl_status == "final"

    def test_cap_keeps_newest_and_logs_dropped(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        monkeypatch.setenv("RECRAWL_MAX_SETS_PER_RUN", "1")
        with Session(task_engine) as s:
            newest = _make_set(s, "new-1", unidentified=1, created_days_ago=1.0)
            oldest = _make_set(s, "old-2", unidentified=1, created_days_ago=5.0)
            s.commit()
            newest_id, oldest_id = newest.id, oldest.id

        _install_trackid_mocks(monkeypatch, _make_fake_import())
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["eligible"] == 2
        assert result["crawled"] == 1
        assert result["dropped_by_cap"] == 1
        assert _reload_set(task_engine, newest_id).last_recrawl_at is not None
        assert _reload_set(task_engine, oldest_id).last_recrawl_at is None

    def test_per_set_error_does_not_abort_run(
        self, tasks_env, task_engine, fake_self, monkeypatch
    ):
        with Session(task_engine) as s:
            failing = _make_set(s, "err-1", unidentified=1, created_days_ago=1.0)
            ok = _make_set(s, "ok-1", unidentified=1, created_days_ago=5.0)
            s.commit()
            failing_id, ok_id = failing.id, ok.id

        _install_trackid_mocks(
            monkeypatch, _make_fake_import(fail_ext_ids={"err-1"})
        )
        result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["errors"] == 1
        assert result["crawled"] == 1
        # The failed set keeps its state: an outage is not an attempt
        assert _reload_set(task_engine, failing_id).last_recrawl_at is None
        assert _reload_set(task_engine, ok_id).last_recrawl_at is not None
        log = _get_crawl_log(task_engine)
        assert log.status == "success"

    def test_materialize_parent_failure_logged_and_non_fatal(
        self, tasks_env, task_engine, fake_self, monkeypatch, caplog
    ):
        """A3-08 guarantee carried over from crawl_followed_sets: a
        materialize_parent failure is logged with the parent_set_id and the
        crawl completes normally."""
        with Session(task_engine) as s:
            parent = _make_set(s, "parent-1", is_virtual=True)
            child = _make_set(s, "child-1", unidentified=1, parent_set_id=parent.id)
            s.commit()
            parent_id, child_id = parent.id, child.id

        async def failing_materialize_parent(db, parent_set_id):
            raise RuntimeError("boom")

        _install_trackid_mocks(monkeypatch, _make_fake_import())
        monkeypatch.setitem(
            sys.modules,
            "services.set_dedup_service",
            SimpleNamespace(materialize_parent=failing_materialize_parent),
        )

        with caplog.at_level(logging.WARNING):
            result = tasks_env.sets.recrawl_incomplete_sets(fake_self)

        assert result["crawled"] == 1
        assert result["errors"] == 0
        warnings = [
            r
            for r in caplog.records
            if f"materialize_parent failed for set {parent_id}" in r.getMessage()
        ]
        assert len(warnings) == 1
        assert _reload_set(task_engine, child_id).last_recrawl_at is not None
        log = _get_crawl_log(task_engine)
        assert log.status == "success"
