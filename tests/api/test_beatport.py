"""Tests for server/api/beatport/ — client and enrichment logic."""
from datetime import date
from unittest.mock import MagicMock, patch

import sys
import os

# Patch infra deps before import
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.client", MagicMock())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))

from beatport.client import _key_to_camelot, _normalize_track, _artist_matches, _pick_best_track, _title_matches
from beatport.enrich import enrich_from_beatport


# ── _key_to_camelot ──


class TestKeyToCamelot:
    def test_ab_minor(self):
        assert _key_to_camelot("Ab Minor") == "1A"

    def test_b_major(self):
        assert _key_to_camelot("B Major") == "1B"

    def test_a_minor(self):
        assert _key_to_camelot("A Minor") == "8A"

    def test_f_sharp_minor(self):
        assert _key_to_camelot("F# Minor") == "11A"

    def test_a_sharp_major_enharmonic(self):
        assert _key_to_camelot("A# Major") == "6B"

    def test_none(self):
        assert _key_to_camelot(None) is None

    def test_unknown(self):
        assert _key_to_camelot("Z Minor") is None


# ── _normalize_track ──


SAMPLE_RAW_TRACK = {
    "track_id": 19431036,
    "track_name": "Strobe",
    "mix_name": "Layton Giordani Extended Remix",
    "bpm": 128,
    "key_name": "Ab Minor",
    "isrc": "GBTDG1302861",
    "artists": [{"artist_id": 12345, "artist_name": "deadmau5"}],
    "label": {"label_id": 6446, "label_name": "mau5trap"},
    "genre": [{"genre_id": 90, "genre_name": "Melodic House & Techno"}],
    "release": {
        "release_id": 4706244,
        "release_name": "Strobe (Layton Giordani Extended Remix)",
        "release_image_dynamic_uri": "https://geo-media.beatport.com/image_size/{w}x{h}/abc.jpg",
    },
    "publish_date": "2024-09-13T00:00:00",
}


class TestNormalizeTrack:
    def test_normalizes_fields(self):
        t = _normalize_track(SAMPLE_RAW_TRACK)
        assert t["id"] == 19431036
        assert t["name"] == "Strobe"
        assert t["bpm"] == 128
        assert t["key"] == "1A"
        assert t["isrc"] == "GBTDG1302861"
        assert t["label"]["name"] == "mau5trap"
        assert t["genre"]["name"] == "Melodic House & Techno"
        assert t["publish_date"] == "2024-09-13"
        assert t["release"]["label"]["name"] == "mau5trap"
        assert "abc.jpg" in t["release"]["image"]["dynamic_uri"]

    def test_handles_missing_genre(self):
        raw = {**SAMPLE_RAW_TRACK, "genre": []}
        t = _normalize_track(raw)
        assert t["genre"] is None

    def test_handles_missing_label(self):
        raw = {**SAMPLE_RAW_TRACK, "label": {}}
        t = _normalize_track(raw)
        assert t["label"] is None


# ── enrich_from_beatport ──


def _make_entry(**overrides):
    """Create a mock CatalogEntry with default NULL fields."""
    entry = MagicMock()
    entry.id = overrides.get("id", 1)
    entry.beatport_id = overrides.get("beatport_id", None)
    entry.bpm = overrides.get("bpm", None)
    entry.bpm_source = overrides.get("bpm_source", None)
    entry.key = overrides.get("key", None)
    entry.key_source = overrides.get("key_source", None)
    entry.label = overrides.get("label", None)
    entry.genre = overrides.get("genre", None)
    entry.release_date = overrides.get("release_date", None)
    entry.has_artwork = overrides.get("has_artwork", False)
    return entry


# Normalized format (as returned by _normalize_track)
SAMPLE_BP_TRACK = _normalize_track(SAMPLE_RAW_TRACK)


class TestEnrichFromBeatport:
    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_fills_all_fields(self, mock_upload):
        entry = _make_entry()
        changed = enrich_from_beatport(entry, SAMPLE_BP_TRACK)

        assert changed is True
        assert entry.beatport_id == "19431036"
        assert entry.bpm == 128.0
        assert entry.bpm_source == "beatport"
        assert entry.key == "1A"
        assert entry.key_source == "beatport"
        assert entry.label == "mau5trap"
        assert entry.genre == "Melodic House & Techno"
        assert entry.release_date == date(2024, 9, 13)

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_does_not_overwrite_beatport_bpm(self, mock_upload):
        entry = _make_entry(bpm=140.0, bpm_source="beatport")
        enrich_from_beatport(entry, SAMPLE_BP_TRACK)
        assert entry.bpm == 140.0

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_overwrites_deezer_bpm(self, mock_upload):
        entry = _make_entry(bpm=137.0, bpm_source="deezer")
        enrich_from_beatport(entry, SAMPLE_BP_TRACK)
        assert entry.bpm == 128.0
        assert entry.bpm_source == "beatport"

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_does_not_overwrite_existing_label(self, mock_upload):
        entry = _make_entry(label="Existing Label")
        enrich_from_beatport(entry, SAMPLE_BP_TRACK)
        assert entry.label == "Existing Label"

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_does_not_overwrite_existing_genre(self, mock_upload):
        entry = _make_entry(genre="Techno")
        enrich_from_beatport(entry, SAMPLE_BP_TRACK)
        assert entry.genre == "Techno"

    @patch("deezer_enrich.upload_cover_from_url", return_value=True)
    def test_uploads_artwork_when_missing(self, mock_upload):
        entry = _make_entry(has_artwork=False)
        s3 = MagicMock()
        enrich_from_beatport(entry, SAMPLE_BP_TRACK, s3=s3)
        assert entry.has_artwork is True
        mock_upload.assert_called_once()

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_skips_artwork_when_already_present(self, mock_upload):
        entry = _make_entry(has_artwork=True)
        s3 = MagicMock()
        enrich_from_beatport(entry, SAMPLE_BP_TRACK, s3=s3)
        mock_upload.assert_not_called()

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_no_change_returns_false(self, mock_upload):
        entry = _make_entry(
            beatport_id="19431036",
            bpm=128.0, bpm_source="beatport",
            key="1A", key_source="beatport",
            label="mau5trap",
            genre="Melodic House & Techno",
            release_date=date(2024, 9, 13),
            has_artwork=True,
        )
        changed = enrich_from_beatport(entry, SAMPLE_BP_TRACK)
        assert changed is False

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_handles_missing_key(self, mock_upload):
        track = {**SAMPLE_BP_TRACK, "key": None}
        entry = _make_entry()
        enrich_from_beatport(entry, track)
        assert entry.key is None
        assert entry.key_source is None

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_handles_missing_label(self, mock_upload):
        track = {**SAMPLE_BP_TRACK, "label": None, "release": {"name": "EP", "image": {}}}
        entry = _make_entry()
        enrich_from_beatport(entry, track)
        assert entry.label is None

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_handles_invalid_date(self, mock_upload):
        track = {**SAMPLE_BP_TRACK, "publish_date": "not-a-date"}
        entry = _make_entry()
        enrich_from_beatport(entry, track)
        assert entry.release_date is None


# ── _normalize_track artists ──


class TestNormalizeTrackArtists:
    def test_extracts_artists(self):
        t = _normalize_track(SAMPLE_RAW_TRACK)
        assert t["artists"] == [{"id": 12345, "name": "deadmau5"}]

    def test_handles_missing_artists(self):
        raw = {**SAMPLE_RAW_TRACK}
        del raw["artists"]
        t = _normalize_track(raw)
        assert t["artists"] == []


# ── _artist_matches ──


class TestArtistMatches:
    def test_exact_match_case_insensitive(self):
        assert _artist_matches([{"name": "Malugi"}], "MALUGI") is True

    def test_partial_match_bp_in_catalog(self):
        assert _artist_matches([{"name": "Tennis"}], "DJ Tennis") is True

    def test_partial_match_catalog_in_bp(self):
        assert _artist_matches([{"name": "DJ Tennis"}], "Tennis") is True

    def test_feat_split(self):
        assert _artist_matches([{"name": "Malugi"}], "Malugi feat. Sam Harper") is True

    def test_ampersand_split(self):
        assert _artist_matches([{"name": "ArtistA"}], "ArtistA & ArtistB") is True

    def test_no_match(self):
        assert _artist_matches([{"name": "Honest"}], "MALUGI") is False

    def test_none_catalog_artist_always_matches(self):
        assert _artist_matches([{"name": "Anyone"}], None) is True

    def test_empty_catalog_artist_always_matches(self):
        assert _artist_matches([{"name": "Anyone"}], "") is True

    def test_empty_bp_artists_no_match(self):
        assert _artist_matches([], "MALUGI") is False


# ── _pick_best_track ──


class TestTitleMatches:
    def test_exact_match(self):
        assert _title_matches("Honestly", "Honestly") is True

    def test_case_insensitive(self):
        assert _title_matches("HONESTLY", "honestly") is True

    def test_substring_bp_in_catalog(self):
        assert _title_matches("Honestly feat. Sam Harper", "Honestly") is True

    def test_substring_catalog_in_bp(self):
        assert _title_matches("Honestly", "Honestly feat. Sam Harper") is True

    def test_no_match(self):
        assert _title_matches("Baby", "Honestly") is False

    def test_none_values(self):
        assert _title_matches(None, "Honestly") is False
        assert _title_matches("Honestly", None) is False


class TestPickBestTrack:
    def test_picks_matching_artist_and_title(self):
        results = [
            {"name": "Honestly", "artists": [{"name": "Honest"}]},
            {"name": "Baby", "artists": [{"name": "Malugi"}]},
            {"name": "Honestly", "artists": [{"name": "Malugi"}]},
        ]
        picked = _pick_best_track(results, "MALUGI", "Honestly")
        assert picked["name"] == "Honestly"
        assert picked["artists"][0]["name"] == "Malugi"

    def test_skips_wrong_title(self):
        results = [
            {"name": "Honestly", "artists": [{"name": "Honest"}]},
            {"name": "Baby", "artists": [{"name": "Malugi"}]},
            {"name": "Reach Out", "artists": [{"name": "Malugi"}]},
        ]
        assert _pick_best_track(results, "MALUGI", "Honestly") is None

    def test_returns_none_when_no_match(self):
        results = [
            {"name": "Honestly", "artists": [{"name": "Honest"}]},
            {"name": "Something", "artists": [{"name": "Other"}]},
        ]
        assert _pick_best_track(results, "MALUGI", "Honestly") is None

    def test_none_artist_and_no_title_picks_first(self):
        results = [
            {"name": "Track1", "artists": [{"name": "A"}]},
            {"name": "Track2", "artists": [{"name": "B"}]},
        ]
        picked = _pick_best_track(results, None)
        assert picked["name"] == "Track1"

    def test_no_title_filter_matches_artist_only(self):
        results = [
            {"name": "Honestly", "artists": [{"name": "Honest"}]},
            {"name": "Baby", "artists": [{"name": "Malugi"}]},
        ]
        picked = _pick_best_track(results, "MALUGI")
        assert picked["name"] == "Baby"
