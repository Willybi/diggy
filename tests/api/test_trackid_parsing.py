"""Tests for server/api/trackid/parsing.py."""
from datetime import datetime, timezone

from trackid.parsing import parse_timespan_to_ms, parse_trackid_date, is_id_track


class TestParseTimespanToMs:
    def test_standard_format(self):
        # 1h 32m 30s 100ms
        result = parse_timespan_to_ms("01:32:30.1000000")
        assert result == 5550100

    def test_zero(self):
        assert parse_timespan_to_ms("00:00:00.0000000") == 0

    def test_seconds_only(self):
        assert parse_timespan_to_ms("00:00:45.0000000") == 45000

    def test_with_days(self):
        # 1 day + 2h
        result = parse_timespan_to_ms("1.02:00:00.0000000")
        assert result == 86_400_000 + 7_200_000

    def test_no_fractional(self):
        assert parse_timespan_to_ms("01:00:00") == 3_600_000

    def test_none_returns_none(self):
        assert parse_timespan_to_ms(None) is None

    def test_empty_string_returns_none(self):
        assert parse_timespan_to_ms("") is None

    def test_whitespace_returns_none(self):
        assert parse_timespan_to_ms("   ") is None


class TestParseTrackidDate:
    def test_iso_with_z(self):
        result = parse_trackid_date("2026-06-16T00:00:00Z")
        assert result == datetime(2026, 6, 16, tzinfo=timezone.utc)

    def test_dotnet_default_returns_none(self):
        assert parse_trackid_date("0001-01-01T00:00:00") is None

    def test_none_returns_none(self):
        assert parse_trackid_date(None) is None

    def test_empty_returns_none(self):
        assert parse_trackid_date("") is None

    def test_with_time(self):
        result = parse_trackid_date("2024-03-15T14:30:00Z")
        assert result.hour == 14
        assert result.minute == 30

    def test_invalid_returns_none(self):
        assert parse_trackid_date("not-a-date") is None


class TestIsIdTrack:
    def test_id_id(self):
        assert is_id_track("ID", "ID") is True

    def test_id_dash_id(self):
        assert is_id_track("ID - ID", None) is True

    def test_id_none(self):
        assert is_id_track("ID", None) is True

    def test_none_none(self):
        assert is_id_track(None, None) is True

    def test_empty_empty(self):
        assert is_id_track("", "") is True

    def test_question_mark(self):
        assert is_id_track("?", "?") is True

    def test_unknown(self):
        assert is_id_track("unknown", "unknown") is True

    def test_real_track(self):
        assert is_id_track("Wannabe", "VOLAC") is False

    def test_real_title_no_artist(self):
        assert is_id_track("Wannabe", None) is False

    def test_case_insensitive(self):
        assert is_id_track("id", "ID") is True
