import pytest
from unittest.mock import patch, MagicMock

from worker.rekordbox.extractor import RekordboxExtractor
from tests.rekordbox.fakes import TRACKS, CUES, TAGS, SONG_MY_TAGS


@pytest.fixture
def extractor(mocker):
    mock_db = MagicMock()
    mock_db.get_content.return_value = TRACKS
    mock_db.get_cue.return_value = CUES
    mock_db.get_my_tag.return_value = TAGS
    mock_db.get_my_tag_songs.return_value = SONG_MY_TAGS
    mocker.patch("worker.rekordbox.extractor.Rekordbox6Database", return_value=mock_db)
    return RekordboxExtractor(artwork_root="C:/fake/share")


class TestGetTracks:
    def test_returns_only_active_tracks(self, extractor):
        tracks = extractor.get_tracks()
        assert len(tracks) == 2

    def test_excludes_deleted_tracks(self, extractor):
        tracks = extractor.get_tracks()
        ids = [t.ID for t in tracks]
        assert 99999999 not in ids

    def test_filters_by_rb_data_status_256(self, extractor):
        tracks = extractor.get_tracks()
        assert all(t.rb_data_status == 256 for t in tracks)


class TestGetTrackMetadata:
    def test_basic_fields(self, extractor):
        track = TRACKS[0]
        meta = extractor.get_track_metadata(track)
        assert meta["id"] == 80011739
        assert meta["title"] == "Wannabe"
        assert meta["artist"] == "VOLAC"
        assert meta["rating"] == 3
        assert meta["duration"] == 165
        assert meta["file_path"] == "C:/Music/Wannabe.mp3"

    def test_bpm_divided_by_100(self, extractor):
        meta = extractor.get_track_metadata(TRACKS[0])
        assert meta["bpm"] == 128.0

    def test_bpm_rounded_to_2_decimals(self, extractor):
        meta = extractor.get_track_metadata(TRACKS[1])
        assert meta["bpm"] == 117.88

    def test_key_scale_name(self, extractor):
        meta = extractor.get_track_metadata(TRACKS[0])
        assert meta["key"] == "6A"

    def test_key_none_when_missing(self, extractor):
        meta = extractor.get_track_metadata(TRACKS[2])
        assert meta["key"] is None

    def test_tags_as_list(self, extractor):
        meta = extractor.get_track_metadata(TRACKS[0])
        assert meta["tags"] == ["Tech House"]  # TO_CUE filtered out (RB internal tag)

    def test_tags_empty_list_when_none(self, extractor):
        meta = extractor.get_track_metadata(TRACKS[2])
        assert meta["tags"] == []


class TestGetTrackCues:
    def test_returns_cues_for_track(self, extractor):
        cues = extractor.get_track_cues(80011739)
        assert len(cues) == 3

    def test_sorted_by_position(self, extractor):
        cues = extractor.get_track_cues(80011739)
        positions = [c["position_ms"] for c in cues]
        assert positions == sorted(positions)

    def test_hot_cue_label(self, extractor):
        cues = extractor.get_track_cues(80011739)
        labels = {c["label"] for c in cues}
        assert "A" in labels
        assert "B" in labels

    def test_memory_cue_label(self, extractor):
        cues = extractor.get_track_cues(80011739)
        labels = [c["label"] for c in cues]
        assert "MEM" in labels

    def test_loop_flag(self, extractor):
        cues = extractor.get_track_cues(52608202)
        assert cues[0]["is_loop"] is True

    def test_returns_empty_for_unknown_track(self, extractor):
        cues = extractor.get_track_cues(0)
        assert cues == []


class TestGetTagsStructure:
    def test_groups_tags_by_category(self, extractor):
        structure = extractor.get_tags_structure()
        assert "STYLE" in structure
        assert "PROCESS" in structure

    def test_tags_in_correct_group(self, extractor):
        structure = extractor.get_tags_structure()
        assert "Tech House" in structure["STYLE"]
        assert "French Touch" in structure["STYLE"]
        assert "TO_CUE" in structure["PROCESS"]

    def test_excludes_unused_tags(self, extractor):
        structure = extractor.get_tags_structure()
        all_tags = [t for group in structure.values() for t in group]
        assert "EMPTY_TAG" not in all_tags

    def test_excludes_empty_groups(self, extractor):
        structure = extractor.get_tags_structure()
        assert all(len(v) > 0 for v in structure.values())


class TestGetArtworkB64:
    def test_returns_none_when_no_image_path_and_no_audio(self, extractor):
        track = TRACKS[1]  # pas d'ImagePath
        result = extractor.get_artwork_b64(track)
        assert result is None

    def test_reads_rb_share_when_file_exists(self, extractor, tmp_path):
        fake_img = tmp_path / "artwork.jpg"
        fake_img.write_bytes(b"FAKEIMAGE")
        extractor.artwork_root = str(tmp_path)

        track = TRACKS[0]
        track.ImagePath = "/PIONEER/Artwork/abc/123/artwork.jpg"

        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b"FAKEIMAGE"
            result = extractor.get_artwork_b64(track)

        import base64
        assert result == base64.b64encode(b"FAKEIMAGE").decode()

    def test_fallback_to_audio_when_rb_path_missing(self, extractor, mocker):
        track = TRACKS[1]  # pas d'ImagePath
        mocker.patch.object(extractor, "_get_artwork_from_audio", return_value="base64data")
        result = extractor.get_artwork_b64(track)
        assert result == "base64data"

    def test_returns_none_when_audio_file_missing(self, extractor):
        track = TRACKS[1]
        with patch("os.path.exists", return_value=False):
            result = extractor._get_artwork_from_audio(track.FolderPath)
        assert result is None
