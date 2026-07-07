"""
Tests for crawl_trackid_latest cursor filtering logic.
Replicates the filtering logic without Celery, Redis, or async.
"""

from datetime import datetime, timedelta, timezone

from trackid.parsing import parse_trackid_date


# ---------------------------------------------------------------------------
# Pure helpers that replicate the task logic — testable without Celery
# ---------------------------------------------------------------------------


def _filter_audiostreams_by_cursor(
    audiostreams: list, last_run_ts: datetime
) -> tuple[list, bool]:
    """Replicate the per-page filtering logic from crawl_trackid_latest.

    Returns (to_import, stop_flag).
    stop_flag=True means pagination should stop (an older-than-cursor item was found).
    """
    to_import = []
    stop_flag = False
    for audiostream in audiostreams:
        added_on_str = audiostream.get("addedOn")
        if not added_on_str:
            continue
        added_on = parse_trackid_date(added_on_str)
        if added_on is None:
            continue
        if added_on <= last_run_ts:
            stop_flag = True
            break
        to_import.append(audiostream)
    return to_import, stop_flag


def _get_last_run_ts(cursor_value: str | None) -> datetime:
    """Replicate the cursor-reading logic from crawl_trackid_latest."""
    if not cursor_value:
        return datetime.now(timezone.utc) - timedelta(hours=24)
    dt = datetime.fromisoformat(cursor_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Fixture cursor — 2026-07-07 10:00 UTC
# ---------------------------------------------------------------------------

CURSOR = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFilterAudiostreamsByCursor:
    def test_filter_newer_than_cursor(self):
        """All sets newer than cursor → all imported, stop_flag=False."""
        audiostreams = [
            {"id": 1, "addedOn": "2026-07-08T12:00:00"},
            {"id": 2, "addedOn": "2026-07-08T11:00:00"},
        ]
        to_import, stop_flag = _filter_audiostreams_by_cursor(audiostreams, CURSOR)
        assert len(to_import) == 2
        assert to_import[0]["id"] == 1
        assert to_import[1]["id"] == 2
        assert stop_flag is False

    def test_filter_stops_at_cursor(self):
        """Set older than cursor triggers stop; subsequent items not included."""
        audiostreams = [
            {"id": 1, "addedOn": "2026-07-08T12:00:00"},  # newer → import
            {"id": 2, "addedOn": "2026-07-07T09:00:00"},  # older → stop
            {"id": 3, "addedOn": "2026-07-06T08:00:00"},  # not reached
        ]
        to_import, stop_flag = _filter_audiostreams_by_cursor(audiostreams, CURSOR)
        assert len(to_import) == 1
        assert to_import[0]["id"] == 1
        assert stop_flag is True

    def test_filter_empty_list(self):
        """Empty input → empty output, no stop."""
        to_import, stop_flag = _filter_audiostreams_by_cursor([], CURSOR)
        assert to_import == []
        assert stop_flag is False

    def test_filter_missing_added_on(self):
        """Audiostream without addedOn is silently skipped; others processed normally."""
        audiostreams = [
            {"id": 1, "title": "No date field"},
            {"id": 2, "addedOn": "2026-07-08T12:00:00"},
        ]
        to_import, stop_flag = _filter_audiostreams_by_cursor(audiostreams, CURSOR)
        assert len(to_import) == 1
        assert to_import[0]["id"] == 2
        assert stop_flag is False

    def test_first_run_no_cursor(self):
        """Absent cursor yields last_run_ts ≈ now - 24h."""
        ts = _get_last_run_ts(None)
        age = datetime.now(timezone.utc) - ts
        # Should be approximately 24 hours (test runs in microseconds)
        assert timedelta(hours=23, minutes=59) < age < timedelta(hours=24, minutes=1)
        assert ts.tzinfo is not None
