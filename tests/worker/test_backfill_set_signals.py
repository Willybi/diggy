"""Tests for the C13.a set-signals backfill (scripts/backfill_set_signals).

Exercises the pure ``backfill_set_signals`` function against a real sync SQLite
session (``sync_session`` fixture). The backfill reports the TrackID signals from
``trackid_index`` onto ``sets`` via the cast join
``sets.external_id = trackid_index.trackid_id::text`` — SQLite runs the CAST fine.
"""
import os
import sys

from sqlalchemy import select

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_SCRIPTS_PATH = os.path.join(_SERVER_PATH, "api", "scripts")
if _SCRIPTS_PATH not in sys.path:
    sys.path.insert(0, _SCRIPTS_PATH)

from models import DJSet, TrackIdIndex  # noqa: E402

from backfill_set_signals import backfill_set_signals  # noqa: E402


def _idx(session, trackid_id, **fields):
    idx = TrackIdIndex(trackid_id=trackid_id, hydration_state="hydrated", **fields)
    session.add(idx)
    session.flush()
    return idx


def _set(session, external_id, source="trackid", **fields):
    s = DJSet(external_id=external_id, source=source, title="t", **fields)
    session.add(s)
    session.flush()
    return s


class TestBackfillSetSignals:
    def test_reports_signals_from_index(self, sync_session):
        _idx(
            sync_session,
            391156,
            channel="LaR'Akaï",
            styles=["Techno", "House"],
            time_hit_rate=0.8,
            track_hit_rate=0.7,
            favourite_count=3,
            like_count=5,
        )
        s = _set(sync_session, "391156")
        sync_session.commit()

        stats = backfill_set_signals(sync_session, apply=True)
        assert stats["scanned"] == 1
        assert stats["changed"] == 1

        sync_session.expire_all()
        row = sync_session.execute(
            select(DJSet).where(DJSet.id == s.id)
        ).scalar_one()
        assert row.channel == "LaR'Akaï"
        assert row.styles == ["Techno", "House"]
        assert row.time_hit_rate == 0.8
        assert row.track_hit_rate == 0.7
        assert row.favourite_count == 3
        assert row.like_count == 5

    def test_dry_run_writes_nothing(self, sync_session):
        _idx(sync_session, 100, channel="Ch")
        s = _set(sync_session, "100")
        sync_session.commit()

        stats = backfill_set_signals(sync_session, apply=False)
        assert stats["changed"] == 1  # would change

        sync_session.expire_all()
        row = sync_session.execute(
            select(DJSet).where(DJSet.id == s.id)
        ).scalar_one()
        assert row.channel is None  # nothing written

    def test_idempotent_second_run_is_noop(self, sync_session):
        _idx(sync_session, 200, channel="Ch", styles=["Trance"])
        _set(sync_session, "200")
        sync_session.commit()

        backfill_set_signals(sync_session, apply=True)
        stats2 = backfill_set_signals(sync_session, apply=True)
        assert stats2["changed"] == 0

    def test_empty_styles_and_null_channel(self, sync_session):
        # index row with no signals (styles [] via StringArray, channel NULL)
        _idx(sync_session, 300)
        s = _set(sync_session, "300")
        sync_session.commit()

        stats = backfill_set_signals(sync_session, apply=True)
        # Nothing differs: sets.styles defaults to [] and channel to None already.
        assert stats["changed"] == 0

        sync_session.expire_all()
        row = sync_session.execute(
            select(DJSet).where(DJSet.id == s.id)
        ).scalar_one()
        assert row.channel is None
        assert row.styles == []

    def test_non_trackid_set_is_skipped(self, sync_session):
        _idx(sync_session, 400, channel="Ch")
        _set(sync_session, "400", source="1001tracklists")
        sync_session.commit()

        stats = backfill_set_signals(sync_session, apply=True)
        assert stats["scanned"] == 0
        assert stats["changed"] == 0
