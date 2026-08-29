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

from sqlalchemy import select  # noqa: E402

from models import TrackIdIndex  # noqa: E402
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
