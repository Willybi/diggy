"""Tests for server/api/utils.py: normalize(), make_normalized_key(), like_escape(),
space_insensitive_ilike(), space_insensitive_contains()."""
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)
from utils import (
    like_escape,
    make_normalized_key,
    normalize,
    space_insensitive_contains,
    space_insensitive_ilike,
)


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


class TestSpaceInsensitiveIlike:
    """X4.h: the shared SQL builder — matches a spaced-out name by its compact
    spelling AND keeps the plain match, escaping LIKE metacharacters. Exercised
    behaviorally on SQLite (the suite's backend), mirroring prod."""

    def _matches(self, names, q):
        engine = create_engine("sqlite://")
        md = MetaData()
        t = Table(
            "t", md,
            Column("id", Integer, primary_key=True),
            Column("name", String),
        )
        md.create_all(engine)
        with engine.begin() as conn:
            conn.execute(insert(t), [{"name": n} for n in names])
        with engine.connect() as conn:
            rows = conn.execute(
                select(t.c.name).where(space_insensitive_ilike(q, t.c.name))
            ).scalars().all()
        return set(rows)

    def test_compact_matches_spaced_name(self):
        # The plain ILIKE alone would miss the letter-spaced name.
        assert self._matches(
            ["t e s t p r e s s", "Carl Cox"], "testpress"
        ) == {"t e s t p r e s s"}

    def test_plain_match_still_works(self):
        assert self._matches(["Carl Cox", "ANNA"], "carl") == {"Carl Cox"}

    def test_multi_column(self):
        # Both columns are ORed; a compact hit on the SECOND column matches.
        engine = create_engine("sqlite://")
        md = MetaData()
        t = Table(
            "t2", md,
            Column("id", Integer, primary_key=True),
            Column("title", String),
            Column("artist", String),
        )
        md.create_all(engine)
        with engine.begin() as conn:
            conn.execute(insert(t), [
                {"title": "Some Track", "artist": "t e s t p r e s s"},
                {"title": "Other", "artist": "Carl Cox"},
            ])
        with engine.connect() as conn:
            rows = conn.execute(
                select(t.c.title).where(
                    space_insensitive_ilike("testpress", t.c.title, t.c.artist)
                )
            ).scalars().all()
        assert set(rows) == {"Some Track"}

    def test_underscore_stays_literal(self):
        # "ab_" collapses to "ab_"; "_" must be a literal, not a wildcard.
        assert self._matches(["a b_c", "a b X c"], "ab_") == {"a b_c"}

    def test_percent_stays_literal(self):
        assert self._matches(["100% Pure", "100 Degrees"], "100%") == {"100% Pure"}

    def test_null_column_does_not_crash(self):
        assert self._matches([None, "Carl Cox"], "carl") == {"Carl Cox"}


class TestSpaceInsensitiveContains:
    """X4.h: the in-memory twin used by the radar bi-score feed filter."""

    def test_plain_substring(self):
        assert space_insensitive_contains("carl", "Carl Cox") is True

    def test_compact_matches_spaced_text(self):
        assert space_insensitive_contains("testpress", "t e s t p r e s s") is True

    def test_spaced_query_on_spaced_text(self):
        assert space_insensitive_contains("carl cox", "Carl Cox") is True

    def test_no_match(self):
        assert space_insensitive_contains("techno", "Carl Cox") is False

    def test_matches_any_of_several_texts(self):
        assert space_insensitive_contains(
            "testpress", "Some Title", "t e s t p r e s s"
        ) is True

    def test_underscore_is_literal(self):
        # No LIKE semantics in memory: "_" is a plain character.
        assert space_insensitive_contains("ab_", "abXc") is False
        assert space_insensitive_contains("ab_", "a b_c") is True

    def test_percent_is_literal(self):
        assert space_insensitive_contains("100%", "100% Pure") is True
        assert space_insensitive_contains("100%", "1000 Pure") is False

    def test_none_text_handled(self):
        assert space_insensitive_contains("carl", None) is False
        assert space_insensitive_contains("carl", None, "Carl Cox") is True

    def test_none_query_handled(self):
        # Defensive: a None/empty query never crashes.
        assert space_insensitive_contains(None, "Carl Cox") is True

    def test_empty_query_matches(self):
        # Mirrors the "%%" SQL pattern: empty query is a substring of any text.
        assert space_insensitive_contains("", "anything") is True

    def test_no_texts_returns_false(self):
        assert space_insensitive_contains("carl") is False
