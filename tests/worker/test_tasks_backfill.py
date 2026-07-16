"""
Tests for backfill_trackid_sets pure logic (C6.a.1 — Lot B).
Covers the extracted pure functions:
  - _collect_backfill_batch(audiostreams, cursor_date, max_sets)
  - _should_skip_backfill(cursor_date, min_date)
  - _resume_page_decision(start_page, first_added_on, cursor_date)
No Celery, no Redis, no DB required.
"""

import importlib.util
import os
import sys
from unittest.mock import MagicMock

# Mock celery ecosystem before any worker imports (celery is not installed locally)
for _mod in ["celery", "celery.schedules", "celery.signals", "celery._state"]:
    sys.modules.setdefault(_mod, MagicMock())

# Add server paths
_SERVER = os.path.join(os.path.dirname(__file__), "../../server")
_API = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in [_SERVER, _API]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Load sets.py directly to avoid workers.tasks.__init__ pulling all task modules
_sets_path = os.path.join(_SERVER, "workers", "tasks", "sets.py")
_spec = importlib.util.spec_from_file_location("workers.tasks.sets", _sets_path)
_sets_mod = importlib.util.module_from_spec(_spec)
sys.modules["workers.tasks.sets"] = _sets_mod
_spec.loader.exec_module(_sets_mod)

_collect_backfill_batch = _sets_mod._collect_backfill_batch
_should_skip_backfill = _sets_mod._should_skip_backfill
_resume_page_decision = _sets_mod._resume_page_decision


class TestCollectBackfillBatch:
    def test_collect_filters_by_cursor(self):
        """Sets with addedOn >= cursor_date are excluded; older ones are included."""
        audiostreams = [
            {"id": "1", "addedOn": "2024-07-10T12:00:00Z"},  # >= cursor → excluded
            {"id": "2", "addedOn": "2024-07-05T12:00:00Z"},  # < cursor → included
            {"id": "3", "addedOn": "2024-07-01T12:00:00Z"},  # < cursor → included
        ]
        batch, _ = _collect_backfill_batch(audiostreams, "2024-07-07", 100)
        assert len(batch) == 2
        assert batch[0]["id"] == "2"
        assert batch[1]["id"] == "3"

    def test_collect_respects_max_sets(self):
        """Stops at max_sets even if more eligible sets are available."""
        audiostreams = [
            {"id": str(i), "addedOn": f"2024-06-{i:02d}T00:00:00Z"}
            for i in range(1, 9)  # 8 items, all before 2024-07-07
        ]
        batch, _ = _collect_backfill_batch(audiostreams, "2024-07-07", 3)
        assert len(batch) == 3

    def test_collect_empty_input(self):
        """Empty input produces an empty batch with no oldest date."""
        batch, oldest = _collect_backfill_batch([], "2024-07-07", 100)
        assert batch == []
        assert oldest is None

    def test_collect_missing_added_on(self):
        """Audiostreams without an addedOn field are silently skipped."""
        audiostreams = [
            {"id": "1"},  # missing addedOn
            {"id": "2", "addedOn": "2024-06-01T00:00:00Z"},
        ]
        batch, _ = _collect_backfill_batch(audiostreams, "2024-07-07", 100)
        assert len(batch) == 1
        assert batch[0]["id"] == "2"

    def test_collect_returns_oldest(self):
        """oldest_added_on is the FULL addedOn timestamp of the oldest set.

        Previously this returned only the YYYY-MM-DD date; the cursor now keeps
        the full timestamp so the intra-day boundary is not lost.
        """
        audiostreams = [
            {"id": "1", "addedOn": "2024-06-15T00:00:00Z"},
            {"id": "2", "addedOn": "2024-06-01T00:00:00Z"},
            {"id": "3", "addedOn": "2024-05-10T08:30:00Z"},
        ]
        batch, oldest = _collect_backfill_batch(audiostreams, "2024-07-07", 100)
        assert len(batch) == 3
        assert oldest == "2024-05-10T08:30:00Z"

    def test_collect_splits_same_day_on_timestamp(self):
        """Two sets on the same day either side of a timestamp cursor are split.

        This is exactly the case the old date-only cursor lost: it truncated
        both to the same YYYY-MM-DD, so both compared >= cursor and the whole
        tail of the cursor's day was dropped forever.
        """
        cursor = "2024-06-01T12:00:00Z"
        audiostreams = [
            {"id": "after", "addedOn": "2024-06-01T15:00:00Z"},  # >= cursor → out
            {"id": "before", "addedOn": "2024-06-01T09:00:00Z"},  # < cursor → in
        ]
        batch, oldest = _collect_backfill_batch(audiostreams, cursor, 100)
        assert [a["id"] for a in batch] == ["before"]
        assert oldest == "2024-06-01T09:00:00Z"

    def test_collect_legacy_date_only_cursor(self):
        """A date-only cursor left by an older build behaves as before.

        "2024-07-07" is a lexicographic prefix of any "2024-07-07T..." value,
        so same-day items still compare >= cursor and are skipped while
        strictly-earlier days pass — the pre-timestamp semantics, unchanged.
        """
        audiostreams = [
            {"id": "same_day", "addedOn": "2024-07-07T23:59:59Z"},  # skipped
            {"id": "earlier", "addedOn": "2024-07-06T00:00:00Z"},  # included
        ]
        batch, _ = _collect_backfill_batch(audiostreams, "2024-07-07", 100)
        assert [a["id"] for a in batch] == ["earlier"]


class TestShouldSkipBackfill:
    def test_skip_when_cursor_before_min(self):
        """cursor_date < min_date means the cursor has gone too far back → True."""
        assert _should_skip_backfill("2022-01-01", "2022-07-01") is True

    def test_no_skip_when_cursor_after_min(self):
        """cursor_date >= min_date means there is still range to cover → False."""
        assert _should_skip_backfill("2024-01-01", "2022-07-01") is False
        assert _should_skip_backfill("2022-07-01", "2022-07-01") is False


class TestResumePageDecision:
    def test_start_page_zero_returns_zero(self):
        """No saved offset (0) → nothing to validate, collect from page 0."""
        assert _resume_page_decision(0, "2024-06-01T00:00:00Z", "2024-05-01") == 0

    def test_normal_resume_keeps_start_page(self):
        """First item newer-or-equal to the cursor → resume from the saved offset."""
        assert (
            _resume_page_decision(12, "2024-06-10T00:00:00Z", "2024-06-01T00:00:00Z")
            == 12
        )

    def test_guard1_empty_page_falls_back_to_zero(self):
        """Guard 1: empty page at the saved offset (stale) → full re-page from 0."""
        assert _resume_page_decision(12, None, "2024-06-01T00:00:00Z") == 0
        assert _resume_page_decision(12, "", "2024-06-01T00:00:00Z") == 0

    def test_guard2_overshoot_falls_back_to_zero(self):
        """Guard 2: first item already older than the cursor (overshoot) → re-page."""
        assert (
            _resume_page_decision(12, "2024-05-20T00:00:00Z", "2024-06-01T00:00:00Z")
            == 0
        )
