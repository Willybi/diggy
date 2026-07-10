"""Tests for server/api/utils.py: normalize(), make_normalized_key(), like_escape()."""
from utils import like_escape, normalize, make_normalized_key


class TestNormalize:
    def test_lowercase(self):
        assert normalize("ANNA") == "anna"

    def test_strips_whitespace(self):
        assert normalize("  ANNA  ") == "anna"

    def test_none_returns_empty(self):
        assert normalize(None) == ""

    def test_empty_string(self):
        assert normalize("") == ""

    def test_smart_quotes_replaced(self):
        result = normalize("Fred again\u2019s")
        assert "\u2019" not in result
        assert "'" in result

    def test_ft_dot_normalized(self):
        assert normalize("Track ft. Artist") == "track ft artist"

    def test_feat_dot_normalized(self):
        assert normalize("Track feat. Artist") == "track feat artist"

    def test_preserves_numbers(self):
        assert normalize("Track 123") == "track 123"


class TestMakeNormalizedKey:
    def test_basic(self):
        result = make_normalized_key("Wannabe", "VOLAC")
        assert result == "wannabe - volac"

    def test_none_artist(self):
        result = make_normalized_key("Wannabe", None)
        assert result == "wannabe - "

    def test_empty_artist(self):
        result = make_normalized_key("Wannabe", "")
        assert result == "wannabe - "

    def test_normalizes_both(self):
        result = make_normalized_key("  COLA  ", "  CamelPhat  ")
        assert result == "cola - camelphat"

    def test_same_track_same_key(self):
        k1 = make_normalized_key("Cola", "CamelPhat")
        k2 = make_normalized_key("cola", "camelphat")
        assert k1 == k2


class TestLikeEscape:
    def test_no_metacharacters_unchanged(self):
        assert like_escape("cola") == "cola"

    def test_empty_string(self):
        assert like_escape("") == ""

    def test_percent_escaped(self):
        assert like_escape("100%") == "100\\%"

    def test_underscore_escaped(self):
        assert like_escape("ab_c") == "ab\\_c"

    def test_backslash_escaped(self):
        assert like_escape("a\\b") == "a\\\\b"

    def test_backslash_escaped_before_metacharacters(self):
        # \% must become \\\% (escaped backslash + escaped percent),
        # not \\\\% (double-escaped backslash swallowing the percent escape)
        assert like_escape("\\%") == "\\\\\\%"

    def test_all_metacharacters_combined(self):
        assert like_escape("a%b_c\\d") == "a\\%b\\_c\\\\d"
