"""Tests for server/api/deezer_enrich.py — pure logic tests."""
from unittest.mock import MagicMock, patch

from deezer_enrich import (
    _strip_safe_suffixes,
    _strip_non_remix_parens,
    _first_artist,
    _is_remix_paren,
    enrich_entry,
    upload_image_to_bucket,
)


class TestStripSafeSuffixes:
    def test_strips_feat(self):
        result = _strip_safe_suffixes("Track (feat. Artist X)")
        assert result == "Track"

    def test_strips_extended_mix(self):
        result = _strip_safe_suffixes("Track (Extended Mix)")
        assert result == "Track"

    def test_strips_remastered(self):
        result = _strip_safe_suffixes("Track (Remastered 2024)")
        assert result == "Track"

    def test_keeps_named_remix(self):
        # Named remix should not be stripped by _strip_safe_suffixes
        result = _strip_safe_suffixes("Track (Adam Port Edit)")
        assert result is None  # no safe suffix found

    def test_none_when_no_suffix(self):
        result = _strip_safe_suffixes("Simple Track")
        assert result is None

    def test_strips_ft(self):
        result = _strip_safe_suffixes("Track (ft. Someone)")
        assert result == "Track"

    def test_strips_brackets(self):
        result = _strip_safe_suffixes("Track [Extended Mix]")
        assert result == "Track"


class TestIsRemixParen:
    def test_named_remix(self):
        assert _is_remix_paren("Adam Port Edit") is True

    def test_generic_mix(self):
        assert _is_remix_paren("Extended Mix") is False

    def test_original_mix(self):
        assert _is_remix_paren("Original Mix") is False

    def test_named_with_generic(self):
        assert _is_remix_paren("Ferry Corsten Radio Edit") is True


class TestStripNonRemixParens:
    def test_strips_generic(self):
        result = _strip_non_remix_parens("Track (Original Mix)")
        assert result == "Track"

    def test_keeps_named_remix(self):
        result = _strip_non_remix_parens("Track (Adam Port Edit)")
        assert result is None  # kept, so no change


class TestFirstArtist:
    def test_comma(self):
        assert _first_artist("A, B") == "A"

    def test_ampersand(self):
        assert _first_artist("A & B") == "A"

    def test_feat(self):
        assert _first_artist("A feat. B") == "A"

    def test_ft(self):
        assert _first_artist("A ft. B") == "A"

    def test_single_artist(self):
        assert _first_artist("CamelPhat") is None


class TestEnrichEntry:
    def test_sets_deezer_id(self):
        entry = MagicMock()
        entry.deezer_id = None
        entry.isrc = None
        entry.duration_ms = None
        entry.has_preview = False
        entry.has_artwork = True
        entry.id = 1

        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://..."}
        result = enrich_entry(entry, hit, s3=None)
        assert result is True
        assert entry.deezer_id == "123"
        assert entry.isrc == "US1234"
        assert entry.duration_ms == 180_000
        assert entry.has_preview is True

    def test_skips_duplicate_isrc(self):
        entry = MagicMock()
        entry.deezer_id = None
        entry.isrc = None
        entry.duration_ms = None
        entry.has_preview = False
        entry.has_artwork = True
        entry.id = 1

        known = {"US1234"}
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}
        enrich_entry(entry, hit, s3=None, _known_isrcs=known)
        assert entry.isrc is None  # not set because already known

    def test_no_change_returns_false(self):
        entry = MagicMock()
        entry.deezer_id = "123"
        entry.isrc = "US1234"
        entry.duration_ms = 180_000
        entry.has_preview = True
        entry.has_artwork = True
        entry.id = 1

        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://..."}
        result = enrich_entry(entry, hit, s3=None)
        assert result is False


class TestUploadImageToBucket:
    def test_returns_false_for_empty_url(self):
        assert upload_image_to_bucket(MagicMock(), "", "key.jpg", "bucket") is False

    def test_returns_false_for_none_url(self):
        assert upload_image_to_bucket(MagicMock(), None, "key.jpg", "bucket") is False

    @patch("deezer_enrich.requests.get")
    def test_returns_false_for_small_image(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"tiny"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = upload_image_to_bucket(MagicMock(), "http://img.jpg", "key.jpg", "bucket")
        assert result is False

    @patch("deezer_enrich.os.unlink")
    @patch("deezer_enrich.requests.get")
    def test_returns_true_for_valid_image(self, mock_get, mock_unlink):
        mock_resp = MagicMock()
        mock_resp.content = b"x" * 2000
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        mock_s3 = MagicMock()
        result = upload_image_to_bucket(mock_s3, "http://img.jpg", "key.jpg", "bucket")
        assert result is True
        mock_s3.upload_file.assert_called_once()
