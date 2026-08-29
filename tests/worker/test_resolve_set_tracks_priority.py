"""C12 L3 — enrich_priority stamping in resolve_set_tracks.

Drives the REAL helpers from workers.tasks.sets (_build_set_priority_map,
_merge_priority, FLUX_PRIORITY). celery/redis/requests are mocked so the module
imports outside Docker (same preamble as test_tasks_crawl_latest.py); the
priority logic itself runs against a real SQLite session (sync_session fixture).
"""

import os
import sys
from unittest.mock import MagicMock

from sqlalchemy import select

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


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock = MagicMock()
_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

from models import CatalogEntry, DJSet, SetTrack, TrackIdIndex  # noqa: E402
from utils import make_normalized_key  # noqa: E402
from workers.tasks import sets as sets_mod  # noqa: E402


def _resolve_and_stamp(session):
    """Mirror of _run_resolve_set_tracks' core loop: link set_tracks to catalog
    and stamp enrich_priority via the REAL C12 helpers (a shared song resolves
    to the SAME catalog row, so cross-set MAX accumulates as in the task)."""
    tracks = session.execute(
        select(SetTrack).where(
            SetTrack.catalog_id.is_(None),
            SetTrack.is_id == False,  # noqa: E712
            SetTrack.raw_title.isnot(None),
        )
    ).scalars().all()

    prio_map = sets_mod._build_set_priority_map(
        session, {st.set_id for st in tracks}
    )

    for st in tracks:
        nk = make_normalized_key(st.raw_title, st.raw_artist)
        entry = session.execute(
            select(CatalogEntry).where(CatalogEntry.normalized_key == nk)
        ).scalar_one_or_none()
        if entry is None:
            entry = CatalogEntry(
                title=st.raw_title, artist=st.raw_artist, normalized_key=nk
            )
            session.add(entry)
            session.flush()
        st.catalog_id = entry.id
        prio = prio_map.get(st.set_id, sets_mod.FLUX_PRIORITY)
        entry.enrich_priority = sets_mod._merge_priority(
            entry.enrich_priority, prio
        )
    session.commit()


class TestMergePriority:
    def test_null_start_takes_new(self):
        assert sets_mod._merge_priority(None, 70) == 70

    def test_keeps_max(self):
        assert sets_mod._merge_priority(90, 70) == 90
        assert sets_mod._merge_priority(60, 90) == 90


class TestBuildSetPriorityMap:
    def test_empty_set_ids(self, sync_session):
        assert sets_mod._build_set_priority_map(sync_session, set()) == {}

    def test_scored_set_rounds_score(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="A", external_id="12345")
        s.add(dj)
        s.flush()
        s.add(TrackIdIndex(trackid_id=12345, score=75.4))
        s.commit()

        m = sets_mod._build_set_priority_map(s, {dj.id})
        assert m == {dj.id: 75}

    def test_omits_unscored_and_scoreless_and_nontrackid(self, sync_session):
        s = sync_session
        # scored trackid set → present
        dj_ok = DJSet(source="trackid", title="OK", external_id="111")
        # trackid set with a NULL-score index row → absent
        dj_nullscore = DJSet(source="trackid", title="NullScore", external_id="222")
        # trackid set with no index row at all → absent
        dj_noidx = DJSet(source="trackid", title="NoIdx", external_id="333")
        # non-trackid set whose external_id matches an index row → absent (scoped)
        dj_manual = DJSet(source="manual", title="Manual", external_id="444")
        s.add_all([dj_ok, dj_nullscore, dj_noidx, dj_manual])
        s.flush()
        s.add_all(
            [
                TrackIdIndex(trackid_id=111, score=82.6),
                TrackIdIndex(trackid_id=222, score=None),
                TrackIdIndex(trackid_id=444, score=50.0),
            ]
        )
        s.commit()

        m = sets_mod._build_set_priority_map(
            s, {dj_ok.id, dj_nullscore.id, dj_noidx.id, dj_manual.id}
        )
        assert m == {dj_ok.id: 83}


class TestStampPriority:
    def test_scored_set_stamps_rounded_priority(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Set A", external_id="12345")
        s.add(dj)
        s.flush()
        s.add(TrackIdIndex(trackid_id=12345, score=74.5))
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        _resolve_and_stamp(s)

        cat = s.execute(select(CatalogEntry)).scalar_one()
        assert cat.enrich_priority == round(74.5)  # 74 (banker's rounding)

    def test_unscored_set_gets_flux_priority(self, sync_session):
        s = sync_session
        assert sets_mod.FLUX_PRIORITY == 100
        dj = DJSet(source="trackid", title="Set B", external_id="99999")
        s.add(dj)
        s.flush()
        # no trackid_index row for this set → live flux
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="New", raw_artist="Nobody"))
        s.commit()

        _resolve_and_stamp(s)

        cat = s.execute(select(CatalogEntry)).scalar_one()
        assert cat.enrich_priority == sets_mod.FLUX_PRIORITY

    def test_shared_row_takes_max_across_sets(self, sync_session):
        s = sync_session
        dj_lo = DJSet(source="trackid", title="Lo", external_id="111")
        dj_hi = DJSet(source="trackid", title="Hi", external_id="222")
        s.add_all([dj_lo, dj_hi])
        s.flush()
        s.add_all(
            [
                TrackIdIndex(trackid_id=111, score=60.0),
                TrackIdIndex(trackid_id=222, score=90.0),
            ]
        )
        # SAME song in both sets → one catalog row
        s.add(SetTrack(set_id=dj_lo.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.add(SetTrack(set_id=dj_hi.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        _resolve_and_stamp(s)

        cat = s.execute(select(CatalogEntry)).scalar_one()
        assert cat.enrich_priority == 90

    def test_existing_priority_is_maxed(self, sync_session):
        s = sync_session
        # A catalog row already carrying a higher priority from a prior run.
        nk = make_normalized_key("Cola", "CamelPhat")
        cat = CatalogEntry(
            title="Cola", artist="CamelPhat", normalized_key=nk, enrich_priority=95
        )
        s.add(cat)
        dj = DJSet(source="trackid", title="Set", external_id="111")
        s.add(dj)
        s.flush()
        s.add(TrackIdIndex(trackid_id=111, score=60.0))
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        _resolve_and_stamp(s)

        s.refresh(cat)
        assert cat.enrich_priority == 95  # max(95, 60)

    def test_existing_priority_raised_by_higher(self, sync_session):
        s = sync_session
        nk = make_normalized_key("Cola", "CamelPhat")
        cat = CatalogEntry(
            title="Cola", artist="CamelPhat", normalized_key=nk, enrich_priority=60
        )
        s.add(cat)
        dj = DJSet(source="trackid", title="Set", external_id="222")
        s.add(dj)
        s.flush()
        s.add(TrackIdIndex(trackid_id=222, score=90.0))
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        _resolve_and_stamp(s)

        s.refresh(cat)
        assert cat.enrich_priority == 90  # max(60, 90)
