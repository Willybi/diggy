import os
import pytest

from worker.relocate_tracks import (
    W_MIX_ROOT,
    _is_style_tag,
    get_style_tag,
    expected_folder,
)


class TestIsStyleTag:
    def test_style_tag_is_valid(self):
        assert _is_style_tag("Tech House") is True

    def test_to_prefix_is_not_style(self):
        assert _is_style_tag("TO_ENERGY") is False

    def test_to_prefix_case_insensitive(self):
        assert _is_style_tag("to_rate") is False

    def test_soundcloud_is_not_style(self):
        assert _is_style_tag("soundcloud") is False

    def test_soundcloud_case_insensitive(self):
        assert _is_style_tag("SoundCloud") is False


class TestGetStyleTag:
    def test_returns_style_tag_ignoring_to_tags(self):
        assert get_style_tag(["TO_ENERGY", "TO_CUE", "Tech House"]) == "Tech House"

    def test_returns_first_style_tag(self):
        assert get_style_tag(["Nu-Disco", "French Touch"]) == "Nu-Disco"

    def test_returns_none_when_only_to_tags(self):
        assert get_style_tag(["TO_ENERGY", "TO_SORT", "TO_RATE"]) is None

    def test_returns_none_when_empty(self):
        assert get_style_tag([]) is None

    def test_ignores_soundcloud_tag(self):
        assert get_style_tag(["SoundCloud", "TO_ENERGY"]) is None

    def test_soundcloud_with_style_returns_style(self):
        # soundcloud prend la priorité dans expected_folder, mais get_style_tag retourne quand même le style
        assert get_style_tag(["SoundCloud", "Tech House"]) == "Tech House"


class TestExpectedFolder:
    def test_style_tag_maps_to_w_folder(self):
        result = expected_folder(["Tech House"])
        assert result == os.path.join(W_MIX_ROOT, "W - Tech House")

    def test_soundcloud_maps_to_import(self):
        result = expected_folder(["SoundCloud", "TO_ENERGY"])
        assert result == os.path.join(W_MIX_ROOT, "_IMPORT")

    def test_soundcloud_takes_priority_over_style(self):
        result = expected_folder(["SoundCloud", "Tech House"])
        assert result == os.path.join(W_MIX_ROOT, "_IMPORT")

    def test_only_to_tags_returns_none(self):
        assert expected_folder(["TO_ENERGY", "TO_SORT"]) is None

    def test_empty_tags_returns_none(self):
        assert expected_folder([]) is None

    def test_classic_min_techno_mapping(self):
        result = expected_folder(["Classic/Min. Techno"])
        assert result == os.path.join(W_MIX_ROOT, "W - Classic_Min. Techno")

    def test_hard_dark_techno_mapping(self):
        result = expected_folder(["Hard/Dark Techno"])
        assert result == os.path.join(W_MIX_ROOT, "W - Hard_Dark Techno")

    def test_nu_disco_mapping(self):
        result = expected_folder(["Nu-Disco"])
        assert result == os.path.join(W_MIX_ROOT, "W - Nu Disco")

    def test_to_tags_ignored_to_find_style(self):
        result = expected_folder(["TO_CUE", "TO_LOOP", "Deep House"])
        assert result == os.path.join(W_MIX_ROOT, "W - Deep House")
