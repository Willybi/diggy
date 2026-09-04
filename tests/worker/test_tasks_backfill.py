"""C12 L4 — backfill_trackid_sets now consumes trackid_index by score.

The chronological-cursor helpers this file used to cover
(_collect_backfill_batch / _should_skip_backfill / _resume_page_decision) were
DELETED in L4: the drain no longer crawls the TrackID listing by addedOn, it
selects the next sets to hydrate straight from ``trackid_index`` ordered by
score desc. Those pure-function tests are replaced here by DB-backed tests of
the two new statement builders (_select_sets_to_hydrate_stmt /
_mark_hydrated_stmt), driven against a real SQLite session (sync_session
fixture) — same harness as test_resolve_set_tracks_priority.py.
"""

import os
import sys
from unittest.mock import MagicMock

# workers package importable (conftest only adds server/api)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "requests",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# Set the FULL attribute surface (soft_time_limit / autoretry_for / …): this
# file overwrites the shared workers.celery_app mock, and test_deadline_exit /
# test_task_refactor assert those attributes on the decorated tasks. Whichever
# import order pytest picks, the decorator must satisfy every file's assertions.
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


_celery_mock = MagicMock()
_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

import pytest  # noqa: E402
from models import TrackIdIndex  # noqa: E402
from sqlalchemy import select  # noqa: E402
from workers.tasks import sets as sets_mod  # noqa: E402


def _add(session, **kwargs):
    row = TrackIdIndex(**kwargs)
    session.add(row)
    return row


class TestSelectSetsToHydrate:
    def test_orders_by_score_desc(self, sync_session):
        s = sync_session
        _add(s, trackid_id=1, slug="a", score=10.0)
        _add(s, trackid_id=2, slug="b", score=90.0)
        _add(s, trackid_id=3, slug="c", score=50.0)
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        assert [tid for tid, _slug in rows] == [2, 3, 1]
        # slug rides along for import_audiostream
        assert dict(rows) == {2: "b", 3: "c", 1: "a"}

    def test_respects_limit_cap(self, sync_session):
        s = sync_session
        for i in range(1, 6):
            _add(s, trackid_id=i, slug=f"s{i}", score=float(i))
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(3)).all()
        assert len(rows) == 3
        # Highest scores first: 5, 4, 3
        assert [tid for tid, _slug in rows] == [5, 4, 3]

    def test_excludes_null_score(self, sync_session):
        s = sync_session
        _add(s, trackid_id=1, slug="scored", score=70.0)
        _add(s, trackid_id=2, slug="unscored", score=None)
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        assert [tid for tid, _slug in rows] == [1]

    def test_excludes_already_hydrated(self, sync_session):
        s = sync_session
        _add(s, trackid_id=1, slug="fresh", score=70.0)
        _add(
            s, trackid_id=2, slug="done", score=80.0, hydration_state="hydrated"
        )
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        # The higher-scored row is skipped because it is already hydrated.
        assert [tid for tid, _slug in rows] == [1]

    def test_tie_break_trackid_id_desc(self, sync_session):
        s = sync_session
        _add(s, trackid_id=1, slug="a", score=50.0)
        _add(s, trackid_id=2, slug="b", score=50.0)
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        assert [tid for tid, _slug in rows] == [2, 1]

    def test_empty_when_nothing_eligible(self, sync_session):
        s = sync_session
        _add(s, trackid_id=1, slug="unscored", score=None)
        _add(
            s, trackid_id=2, slug="done", score=80.0, hydration_state="hydrated"
        )
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        assert rows == []


class TestSelectSetsIgnoresClaimed:
    def test_claimed_rows_are_not_selected(self, sync_session):
        # A set the local trackid_hydrate tool has CLAIMED is invisible to the drain
        # (it selects only 'not_hydrated'), even at a higher score — the dynamic
        # reservation, no static shard needed.
        s = sync_session
        _add(s, trackid_id=1, slug="free", score=50.0)
        _add(s, trackid_id=2, slug="reserved", score=90.0, hydration_state="claimed")
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        assert [tid for tid, _slug in rows] == [1]


class TestMarkHydrated:
    def test_marks_row_hydrated(self, sync_session):
        s = sync_session
        _add(s, trackid_id=42, slug="x", score=60.0)
        s.commit()

        s.execute(sets_mod._mark_hydrated_stmt(42))
        s.commit()

        row = s.execute(
            select(TrackIdIndex).where(TrackIdIndex.trackid_id == 42)
        ).scalar_one()
        assert row.hydration_state == "hydrated"

    def test_marked_row_is_no_longer_selected(self, sync_session):
        s = sync_session
        _add(s, trackid_id=1, slug="a", score=90.0)
        _add(s, trackid_id=2, slug="b", score=50.0)
        s.commit()

        # Hydrate the top-scored one, then it drops out of the selection.
        s.execute(sets_mod._mark_hydrated_stmt(1))
        s.commit()

        rows = s.execute(sets_mod._select_sets_to_hydrate_stmt(10)).all()
        assert [tid for tid, _slug in rows] == [2]


# ── reaper (PG-only: now()/make_interval + timestamptz arithmetic) ──────────────
#
# The reaper SQL (_REAP_STALE_CLAIMS_SQL, executed by the async _reap_stale_claims)
# uses now()/make_interval, which SQLite cannot run. So this section is skipped
# unless DATABASE_URL points at PostgreSQL, and it creates its OWN throwaway
# database (never create_all/drop_all on the shared DATABASE_URL — under xdist
# loadscope a tests/api module can share this worker process and rely on that
# schema; same guard as tests/worker/test_import_rb_upsert.py).

_PG_ONLY = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="reaper SQL is PostgreSQL-only (now()/make_interval on timestamptz)",
)

_MAINT_LOCK_KEY = 0xC1A1  # serialises the throwaway-DB DDL


def _run_maintenance(maint_dsn, statements):
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


def _terminate_backends_sql(db_name):
    return (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
    )


@pytest.fixture
def pg_reaper_engine():
    from database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    base_url = make_url(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    worker = os.environ.get("PYTEST_XDIST_WORKER", "solo")
    test_db = f"{base_url.database}_claimreaper_{worker}"
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


@_PG_ONLY
def test_reaper_resets_only_stale_claims(pg_reaper_engine):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    with Session(pg_reaper_engine) as s:
        # A claim older than the 2h lease (stale), a fresh claim, and a plain
        # not_hydrated row that must stay untouched.
        s.execute(
            text(
                "INSERT INTO trackid_index "
                "(trackid_id, slug, score, hydration_state, claimed_at) VALUES "
                "(1, 'stale', 90, 'claimed', now() - make_interval(secs => 10800)),"
                "(2, 'fresh', 80, 'claimed', now()),"
                "(3, 'free',  70, 'not_hydrated', NULL)"
            )
        )
        s.commit()

        # Execute the SAME SQL the async reaper runs (lease = 2h).
        res = s.execute(
            text(sets_mod._REAP_STALE_CLAIMS_SQL), {"lease": 7200}
        )
        s.commit()
        assert res.rowcount == 1  # only the stale claim was reaped

        states = dict(
            s.execute(
                text("SELECT trackid_id, hydration_state FROM trackid_index")
            ).all()
        )
        assert states[1] == "not_hydrated"  # stale claim returned to the pool
        assert states[2] == "claimed"       # fresh claim untouched
        assert states[3] == "not_hydrated"  # plain row untouched

        claimed_at_1 = s.execute(
            text("SELECT claimed_at FROM trackid_index WHERE trackid_id = 1")
        ).scalar_one()
        assert claimed_at_1 is None  # reaper nulls claimed_at on reset
