"""Tests for server/api/trackid/client.py — merge_tracklist logic."""
from trackid.client import TrackIDClient


class TestMergeTracklist:
    def _make_client(self):
        return TrackIDClient()

    def test_empty_detail(self):
        c = self._make_client()
        assert c.merge_tracklist({}) == []

    def test_single_process(self):
        c = self._make_client()
        detail = {
            "detectionProcesses": [{
                "detectionProcessMusicTracks": [
                    {"musicTrackId": 1, "title": "Track A", "startTime": "00:01:00.0000000"},
                    {"musicTrackId": 2, "title": "Track B", "startTime": "00:05:00.0000000"},
                ]
            }]
        }
        result = c.merge_tracklist(detail)
        assert len(result) == 2
        assert result[0]["musicTrackId"] == 1
        assert result[1]["musicTrackId"] == 2

    def test_dedup_by_music_track_id(self):
        c = self._make_client()
        detail = {
            "detectionProcesses": [
                {"detectionProcessMusicTracks": [
                    {"musicTrackId": 1, "title": "Track A", "startTime": "00:05:00.0000000"},
                ]},
                {"detectionProcessMusicTracks": [
                    {"musicTrackId": 1, "title": "Track A", "startTime": "00:01:00.0000000"},
                ]},
            ]
        }
        result = c.merge_tracklist(detail)
        assert len(result) == 1
        # Should keep the one with earlier startTime
        assert result[0]["startTime"] == "00:01:00.0000000"

    def test_sorted_by_start_time(self):
        c = self._make_client()
        detail = {
            "detectionProcesses": [{
                "detectionProcessMusicTracks": [
                    {"musicTrackId": 2, "title": "B", "startTime": "00:10:00.0000000"},
                    {"musicTrackId": 1, "title": "A", "startTime": "00:01:00.0000000"},
                    {"musicTrackId": 3, "title": "C", "startTime": "00:05:00.0000000"},
                ]
            }]
        }
        result = c.merge_tracklist(detail)
        assert [t["musicTrackId"] for t in result] == [1, 3, 2]

    def test_skips_null_music_track_id(self):
        c = self._make_client()
        detail = {
            "detectionProcesses": [{
                "detectionProcessMusicTracks": [
                    {"musicTrackId": None, "title": "Unknown"},
                    {"musicTrackId": 1, "title": "Known", "startTime": "00:01:00.0000000"},
                ]
            }]
        }
        result = c.merge_tracklist(detail)
        assert len(result) == 1
        assert result[0]["musicTrackId"] == 1
