"""C8 — tests for server/api/trackid/reliability.py.

Pure module: the reliability rule (compute_set_unreliable), the placeholder
matchers and the exclusion predicates need no DB session. set_reliable() /
set_reliable_sql() are exercised for the shape of the predicate they build.
"""

import hashlib

from trackid.reliability import (
    ID_RATIO_UNRELIABLE,
    PLACEHOLDER_ARTWORK_MD5_PREFIX,
    PLACEHOLDER_ARTWORK_URL,
    artwork_bytes_are_placeholder,
    compute_set_unreliable,
    is_placeholder_artwork_url,
    set_reliable,
    set_reliable_sql,
)


class TestComputeSetUnreliable:
    def test_nominal_reliable(self):
        # Mostly identified, real source, no placeholder → reliable
        assert compute_set_unreliable(10, 2, "https://trackid.net/set/x", False) is False

    def test_mostly_id_is_unreliable(self):
        # 9/10 ID tracks (>= 0.8) → dominant signal fires regardless of the rest
        assert (
            compute_set_unreliable(10, 9, "https://trackid.net/set/x", False) is True
        )

    def test_ratio_exactly_at_threshold_is_unreliable(self):
        # The threshold is inclusive (>=).
        assert compute_set_unreliable(10, 8, "https://x", False) is True

    def test_ratio_just_below_threshold_is_reliable(self):
        assert compute_set_unreliable(10, 7, "https://x", False) is False

    def test_missing_source_url_alone_is_reliable(self):
        # Secondary signal needs BOTH source_url absent AND placeholder.
        assert compute_set_unreliable(10, 2, None, False) is False

    def test_placeholder_alone_is_reliable(self):
        assert compute_set_unreliable(10, 2, "https://x", True) is False

    def test_no_source_and_placeholder_is_unreliable(self):
        assert compute_set_unreliable(10, 2, None, True) is True

    def test_blank_source_url_counts_as_missing(self):
        assert compute_set_unreliable(10, 2, "   ", True) is True

    def test_empty_source_url_counts_as_missing(self):
        assert compute_set_unreliable(10, 2, "", True) is True

    def test_zero_tracks_is_unreliable(self):
        assert compute_set_unreliable(0, 0, "https://x", False) is True

    def test_negative_total_is_unreliable(self):
        assert compute_set_unreliable(-1, 0, "https://x", False) is True

    def test_threshold_constant_is_a_ratio(self):
        assert 0.0 < ID_RATIO_UNRELIABLE <= 1.0


class TestPlaceholderMatchers:
    def test_url_match(self):
        assert is_placeholder_artwork_url(PLACEHOLDER_ARTWORK_URL) is True

    def test_url_match_with_surrounding_whitespace(self):
        assert is_placeholder_artwork_url(f"  {PLACEHOLDER_ARTWORK_URL}  ") is True

    def test_real_cover_url_is_not_placeholder(self):
        assert is_placeholder_artwork_url("https://trackid.net/cover/123.jpg") is False

    def test_none_url_is_not_placeholder(self):
        assert is_placeholder_artwork_url(None) is False

    def test_empty_url_is_not_placeholder(self):
        assert is_placeholder_artwork_url("") is False

    def test_bytes_match_by_md5_prefix(self):
        # Craft bytes whose md5 starts with the known prefix would require a
        # preimage; instead assert the prefix logic against the real digest.
        data = b"some placeholder image bytes"
        digest = hashlib.md5(data).hexdigest()
        expected = digest.startswith(PLACEHOLDER_ARTWORK_MD5_PREFIX)
        assert artwork_bytes_are_placeholder(data) is expected

    def test_empty_bytes_is_not_placeholder(self):
        assert artwork_bytes_are_placeholder(b"") is False

    def test_none_bytes_is_not_placeholder(self):
        assert artwork_bytes_are_placeholder(None) is False


class TestExclusionPredicates:
    def test_orm_predicate_targets_unreliable_false(self):
        from models import DJSet

        pred = set_reliable()
        # Compiles to the reliable-rows predicate `sets.unreliable IS false`.
        compiled = str(pred.compile(compile_kwargs={"literal_binds": True}))
        assert "sets.unreliable" in compiled
        assert "false" in compiled.lower()
        # It is built from the DJSet.unreliable column.
        assert pred.left.compare(DJSet.unreliable.__clause_element__())

    def test_sql_fragment_default_alias(self):
        assert set_reliable_sql() == "s.unreliable IS NOT TRUE"

    def test_sql_fragment_custom_alias(self):
        assert set_reliable_sql("dj") == "dj.unreliable IS NOT TRUE"
