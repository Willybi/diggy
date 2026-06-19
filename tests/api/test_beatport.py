"""Tests for server/api/beatport/ — client and enrichment logic."""
import json
from datetime import date
from unittest.mock import MagicMock, patch, PropertyMock

import sys
import os

# Patch infra deps before import
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.client", MagicMock())
sys.modules.setdefault("redis", MagicMock())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))

from beatport.enrich import parse_camelot_key, enrich_from_beatport


# ── parse_camelot_key ──


class TestParseCamelotKey:
    def test_valid_key(self):
        assert parse_camelot_key({"camelot_number": 7, "camelot_letter": "A"}) == "7A"

    def test_double_digit(self):
        assert parse_camelot_key({"camelot_number": 11, "camelot_letter": "B"}) == "11B"

    def test_none_input(self):
        assert parse_camelot_key(None) is None

    def test_empty_dict(self):
        assert parse_camelot_key({}) is None

    def test_missing_letter(self):
        assert parse_camelot_key({"camelot_number": 7}) is None

    def test_missing_number(self):
        assert parse_camelot_key({"camelot_letter": "A"}) is None


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


SAMPLE_BP_TRACK = {
    "id": 99999,
    "name": "Acid Rain",
    "mix_name": "Original Mix",
    "bpm": 138,
    "key": {"name": "A min", "camelot_number": 8, "camelot_letter": "A"},
    "isrc": "GBUM71234567",
    "label": {"name": "Drumcode", "slug": "drumcode"},
    "genre": {"name": "Techno (Raw / Deep / Hypnotic)"},
    "release": {
        "name": "Acid Rain EP",
        "image": {"dynamic_uri": "https://geo-media.beatport.com/image_size/{w}x{h}/abc.jpg"},
    },
    "publish_date": "2024-01-15",
}


class TestEnrichFromBeatport:
    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_fills_all_fields(self, mock_upload):
        entry = _make_entry()
        changed = enrich_from_beatport(entry, SAMPLE_BP_TRACK)

        assert changed is True
        assert entry.beatport_id == "99999"
        assert entry.bpm == 138.0
        assert entry.bpm_source == "beatport"
        assert entry.key == "8A"
        assert entry.key_source == "beatport"
        assert entry.label == "Drumcode"
        assert entry.genre == "Techno (Raw / Deep / Hypnotic)"
        assert entry.release_date == date(2024, 1, 15)

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_does_not_overwrite_beatport_bpm(self, mock_upload):
        entry = _make_entry(bpm=140.0, bpm_source="beatport")
        changed = enrich_from_beatport(entry, SAMPLE_BP_TRACK)

        # beatport_id and other fields still change, but bpm stays
        assert entry.bpm == 140.0
        assert entry.bpm_source == "beatport"

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_overwrites_deezer_bpm(self, mock_upload):
        entry = _make_entry(bpm=137.0, bpm_source="deezer")
        enrich_from_beatport(entry, SAMPLE_BP_TRACK)

        assert entry.bpm == 138.0
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
        mock_upload.assert_called_once_with(
            s3, "https://geo-media.beatport.com/image_size/500x500/abc.jpg", 1
        )

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_skips_artwork_when_already_present(self, mock_upload):
        entry = _make_entry(has_artwork=True)
        s3 = MagicMock()
        enrich_from_beatport(entry, SAMPLE_BP_TRACK, s3=s3)

        mock_upload.assert_not_called()

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_no_change_returns_false(self, mock_upload):
        entry = _make_entry(
            beatport_id="99999",
            bpm=138.0, bpm_source="beatport",
            key="8A", key_source="beatport",
            label="Drumcode",
            genre="Techno",
            release_date=date(2024, 1, 15),
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
        track = {**SAMPLE_BP_TRACK, "label": None}
        entry = _make_entry()
        enrich_from_beatport(entry, track)

        assert entry.label is None

    @patch("deezer_enrich.upload_cover_from_url", return_value=False)
    def test_handles_invalid_date(self, mock_upload):
        track = {**SAMPLE_BP_TRACK, "publish_date": "not-a-date"}
        entry = _make_entry()
        enrich_from_beatport(entry, track)

        assert entry.release_date is None
