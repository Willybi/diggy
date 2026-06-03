import pytest
from unittest.mock import patch, MagicMock

from server.deezer.extractor import DeezerExtractor
from tests.deezer.fakes import (
    PLAYLISTS_PAGE_1,
    PLAYLISTS_PAGINATED,
    PLAYLISTS_PAGE_2,
    TRACKS_PAGE_1,
    TRACKS_PAGINATED,
    TRACKS_PAGE_2,
)


def make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    return mock


@pytest.fixture
def extractor():
    return DeezerExtractor(user_id="123")


class TestGetPlaylists:
    def test_returns_only_playlists_with_prefix(self, extractor):
        with patch("requests.get", return_value=make_response(PLAYLISTS_PAGE_1)):
            playlists = extractor.get_playlists()
        assert len(playlists) == 2
        assert all(pl["title"].startswith("W -") for pl in playlists)

    def test_excludes_playlists_without_prefix(self, extractor):
        with patch("requests.get", return_value=make_response(PLAYLISTS_PAGE_1)):
            playlists = extractor.get_playlists()
        titles = [pl["title"] for pl in playlists]
        assert "Favorites" not in titles

    def test_custom_prefix(self, extractor):
        with patch("requests.get", return_value=make_response(PLAYLISTS_PAGE_1)):
            playlists = extractor.get_playlists(prefix="Favorites")
        assert len(playlists) == 1
        assert playlists[0]["title"] == "Favorites"

    def test_handles_pagination(self, extractor):
        responses = [
            make_response(PLAYLISTS_PAGINATED),
            make_response(PLAYLISTS_PAGE_2),
        ]
        with patch("requests.get", side_effect=responses):
            playlists = extractor.get_playlists()
        assert len(playlists) == 2

    def test_returns_empty_when_no_match(self, extractor):
        data = {"data": [{"id": "1", "title": "Favorites", "nb_tracks": 1}], "next": None}
        with patch("requests.get", return_value=make_response(data)):
            playlists = extractor.get_playlists()
        assert playlists == []


class TestGetTracks:
    def test_returns_all_tracks(self, extractor):
        with patch("requests.get", return_value=make_response(TRACKS_PAGE_1)):
            tracks = extractor.get_tracks("111")
        assert len(tracks) == 2

    def test_track_fields_present(self, extractor):
        with patch("requests.get", return_value=make_response(TRACKS_PAGE_1)):
            tracks = extractor.get_tracks("111")
        assert tracks[0]["title"] == "Wannabe"
        assert tracks[0]["artist"]["name"] == "VOLAC"
        assert tracks[0]["duration"] == 185

    def test_handles_pagination(self, extractor):
        responses = [
            make_response(TRACKS_PAGINATED),
            make_response(TRACKS_PAGE_2),
        ]
        with patch("requests.get", side_effect=responses):
            tracks = extractor.get_tracks("111")
        assert len(tracks) == 2

    def test_returns_empty_for_empty_playlist(self, extractor):
        data = {"data": [], "next": None}
        with patch("requests.get", return_value=make_response(data)):
            tracks = extractor.get_tracks("999")
        assert tracks == []


class TestGetAllTracks:
    def test_keys_are_playlist_titles(self, extractor):
        def side_effect(url, **kwargs):
            if "/playlists" in url:
                return make_response(PLAYLISTS_PAGE_1)
            return make_response(TRACKS_PAGE_1)

        with patch("requests.get", side_effect=side_effect):
            all_tracks = extractor.get_all_tracks()

        assert "W - Tech House" in all_tracks
        assert "W - Melodic" in all_tracks
        assert "Favorites" not in all_tracks

    def test_values_are_track_lists(self, extractor):
        def side_effect(url, **kwargs):
            if "/playlists" in url:
                return make_response(PLAYLISTS_PAGE_1)
            return make_response(TRACKS_PAGE_1)

        with patch("requests.get", side_effect=side_effect):
            all_tracks = extractor.get_all_tracks()

        assert isinstance(all_tracks["W - Tech House"], list)
        assert len(all_tracks["W - Tech House"]) == 2
