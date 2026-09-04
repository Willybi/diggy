"""Tests for the L2 OPS backfill script (scripts/backfill_completion_pct).

Exercises the testable cores ``rebase_completion_pct`` (volet A) and
``rearm_final_sets`` (volet B) — extracted from ``main`` so they run without the
CLI — against a real sync SQLite session (``sync_session`` fixture). Asserts the
SELECTION + wiring (join to ``trackid_index.time_hit_rate``, re-base value, re-arm
condition, dry-run, idempotence). Same import/path pattern as
test_backfill_set_reliability.py.
"""
import itertools
import os
import sys

# Make server/api importable (same pattern as the sibling OPS-script tests).
_SERVER_API = os.path.join(os.path.dirname(__file__), "../../server/api")
if _SERVER_API not in sys.path:
    sys.path.insert(0, _SERVER_API)

from models import DJSet, TrackIdIndex  # noqa: E402

from scripts.backfill_completion_pct import (  # noqa: E402
    RECRAWL_FINAL_HITRATE,
    rearm_final_sets,
    rebase_completion_pct,
)

_n = itertools.count(1)


def _make_set(session, *, hit_rate=None, has_index=True, commit=True, **fields):
    """Insert a trackid DJSet + (optionally) its trackid_index row with ``hit_rate``."""
    i = next(_n)
    dj_set = DJSet(
        title=fields.pop("title", f"Set {i}"),
        source=fields.pop("source", "trackid"),
        **fields,
    )
    session.add(dj_set)
    session.flush()
    if has_index:
        session.add(
            TrackIdIndex(trackid_id=1000 + i, set_id=dj_set.id, time_hit_rate=hit_rate)
        )
    if commit:
        session.commit()
    return dj_set


class TestRebaseVoletA:
    def test_rebase_sets_completion_pct_to_hit_rate(self, sync_session):
        s = _make_set(sync_session, hit_rate=0.53, completion_pct=1.0)

        stats = rebase_completion_pct(sync_session, apply=True)

        assert stats["scanned"] == 1 and stats["changed"] == 1
        assert sync_session.get(DJSet, s.id).completion_pct == 0.53

    def test_no_index_row_is_left_as_is(self, sync_session):
        s = _make_set(sync_session, has_index=False, completion_pct=1.0)

        stats = rebase_completion_pct(sync_session, apply=True)

        assert stats["scanned"] == 1 and stats["changed"] == 0
        assert stats["skipped_no_index"] == 1
        assert sync_session.get(DJSet, s.id).completion_pct == 1.0

    def test_null_hit_rate_is_left_as_is(self, sync_session):
        s = _make_set(sync_session, hit_rate=None, completion_pct=1.0)

        stats = rebase_completion_pct(sync_session, apply=True)

        assert stats["changed"] == 0 and stats["skipped_no_index"] == 1
        assert sync_session.get(DJSet, s.id).completion_pct == 1.0

    def test_non_trackid_sets_are_ignored(self, sync_session):
        s = _make_set(sync_session, source="deezer", hit_rate=0.4, completion_pct=1.0)

        stats = rebase_completion_pct(sync_session, apply=True)

        assert stats["scanned"] == 0
        assert sync_session.get(DJSet, s.id).completion_pct == 1.0

    def test_dry_run_mutates_nothing(self, sync_session):
        s = _make_set(sync_session, hit_rate=0.53, completion_pct=1.0)

        stats = rebase_completion_pct(sync_session, apply=False)

        assert stats["changed"] == 1
        assert sync_session.get(DJSet, s.id).completion_pct == 1.0  # untouched

    def test_apply_is_idempotent(self, sync_session):
        _make_set(sync_session, hit_rate=0.53, completion_pct=1.0)

        first = rebase_completion_pct(sync_session, apply=True)
        assert first["changed"] == 1

        second = rebase_completion_pct(sync_session, apply=True)
        assert second["changed"] == 0


class TestRearmVoletB:
    def test_final_incomplete_set_is_rearmed(self, sync_session):
        s = _make_set(
            sync_session, hit_rate=0.5, recrawl_status="final", recrawl_count=3
        )

        stats = rearm_final_sets(sync_session, apply=True)

        assert stats["scanned"] == 1 and stats["rearmed"] == 1
        refreshed = sync_session.get(DJSet, s.id)
        assert refreshed.recrawl_status == "active"
        assert refreshed.recrawl_count == 0

    def test_final_complete_set_stays_final(self, sync_session):
        # hit_rate at/above the threshold → genuinely finalized, left alone.
        s = _make_set(
            sync_session,
            hit_rate=RECRAWL_FINAL_HITRATE,
            recrawl_status="final",
            recrawl_count=3,
        )

        stats = rearm_final_sets(sync_session, apply=True)

        assert stats["rearmed"] == 0 and stats["skipped"] == 1
        assert sync_session.get(DJSet, s.id).recrawl_status == "final"

    def test_active_set_is_not_scanned(self, sync_session):
        s = _make_set(sync_session, hit_rate=0.5, recrawl_status="active")

        stats = rearm_final_sets(sync_session, apply=True)

        assert stats["scanned"] == 0
        assert sync_session.get(DJSet, s.id).recrawl_status == "active"

    def test_virtual_parent_is_not_rearmed(self, sync_session):
        s = _make_set(
            sync_session, hit_rate=0.5, recrawl_status="final", is_virtual=True
        )

        stats = rearm_final_sets(sync_session, apply=True)

        assert stats["scanned"] == 0
        assert sync_session.get(DJSet, s.id).recrawl_status == "final"

    def test_final_without_index_row_stays_final(self, sync_session):
        s = _make_set(
            sync_session, has_index=False, recrawl_status="final", recrawl_count=3
        )

        stats = rearm_final_sets(sync_session, apply=True)

        assert stats["rearmed"] == 0 and stats["skipped"] == 1
        assert sync_session.get(DJSet, s.id).recrawl_status == "final"

    def test_dry_run_mutates_nothing(self, sync_session):
        s = _make_set(
            sync_session, hit_rate=0.5, recrawl_status="final", recrawl_count=3
        )

        stats = rearm_final_sets(sync_session, apply=False)

        assert stats["rearmed"] == 1
        refreshed = sync_session.get(DJSet, s.id)
        assert refreshed.recrawl_status == "final"  # untouched
        assert refreshed.recrawl_count == 3

    def test_apply_is_idempotent(self, sync_session):
        _make_set(sync_session, hit_rate=0.5, recrawl_status="final", recrawl_count=3)

        first = rearm_final_sets(sync_session, apply=True)
        assert first["rearmed"] == 1

        # Re-armed set is now 'active' → drops out of the 'final' selection.
        second = rearm_final_sets(sync_session, apply=True)
        assert second["scanned"] == 0 and second["rearmed"] == 0
