"""Tests for the pure name→artist resolution helpers (workers/set_artist_link).

Pure module, no I/O — imported directly (same sys.path pattern as
test_set_artist_extract.py). The lookup corpus is SYNTHETIC ``(name, artist_id)``
pairs; the DB loader that builds the real corpus (artist names + aliases) is the
next lot. The GUARD cases (placeholder excluded, mono-token key never scanned,
longest-first non-overlap) matter as much as the nominal ones: C2c-1 resolves
against our own base and must never mis-link (invariant #4).
"""

import os
import sys

# Make the workers package importable (same pattern as test_set_artist_extract.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from workers.set_artist_link import (  # noqa: E402
    build_artist_lookup,
    resolve_name_to_id,
    scan_known_artists,
)


# ── build_artist_lookup ───────────────────────────────────────────────────────


class TestBuildLookup:
    def test_maps_fold_key_to_id(self):
        lookup = build_artist_lookup([("Ricardo Villalobos", 1), ("Move D", 2)])
        assert lookup == {"ricardo villalobos": 1, "move d": 2}

    def test_excludes_placeholders(self):
        lookup = build_artist_lookup(
            [("Various Artists", 99), ("Unknown", 98), ("Real Artist", 1)]
        )
        assert 99 not in lookup.values()
        assert 98 not in lookup.values()
        assert lookup == {"real artist": 1}

    def test_excludes_blank_fold(self):
        # Fully non-Latin folds away under punct_fold_key/fold_base but casefold keeps
        # it — a blank/whitespace name must still be dropped.
        lookup = build_artist_lookup([("   ", 5), ("", 6), ("OK", 7)])
        assert lookup == {"ok": 7}

    def test_first_pair_wins_on_collision(self):
        # "St. Germain" and "St Germain" fold to the same key.
        lookup = build_artist_lookup([("St. Germain", 1), ("St Germain", 2)])
        assert lookup == {"st germain": 1}

    def test_accepts_any_iterable(self):
        lookup = build_artist_lookup(iter([("A B", 1)]))
        assert lookup == {"a b": 1}


# ── resolve_name_to_id ─────────────────────────────────────────────────────────


class TestResolve:
    def setup_method(self):
        self.lookup = build_artist_lookup(
            [("St. Germain", 1), ("Mr. Oizo", 2), ("Kaytranada", 3)]
        )

    def test_hit(self):
        assert resolve_name_to_id("Kaytranada", self.lookup) == 3

    def test_miss(self):
        assert resolve_name_to_id("Nobody Here", self.lookup) is None

    def test_punctuation_fold_equivalence(self):
        # "St Germain" (no dot) resolves to the "St. Germain" row and vice-versa.
        assert resolve_name_to_id("St Germain", self.lookup) == 1
        assert resolve_name_to_id("St. Germain", self.lookup) == 1
        assert resolve_name_to_id("Mr Oizo", self.lookup) == 2

    def test_blank_returns_none(self):
        assert resolve_name_to_id("", self.lookup) is None
        assert resolve_name_to_id("   ", self.lookup) is None
        assert resolve_name_to_id(None, self.lookup) is None

    def test_never_matches_placeholder(self):
        lookup = build_artist_lookup([("Various Artists", 1)])
        assert resolve_name_to_id("Various Artists", lookup) is None


# ── scan_known_artists ─────────────────────────────────────────────────────────


class TestScan:
    def test_finds_buried_multiword_artist(self):
        lookup = build_artist_lookup([("Ricardo Villalobos", 1)])
        found = scan_known_artists(
            "Ricardo Villalobos Recorded Live from Fabric 2019", lookup
        )
        assert found == [("Ricardo Villalobos", 1)]

    def test_ignores_mono_token_key(self):
        # "Live" and "Fabric" are single-word known artists — precision guard means
        # a free-text scan NEVER matches them, even though both appear in the title.
        lookup = build_artist_lookup(
            [("Ricardo Villalobos", 1), ("Live", 50), ("Fabric", 51)]
        )
        found = scan_known_artists(
            "Ricardo Villalobos Recorded Live from Fabric 2019", lookup
        )
        assert found == [("Ricardo Villalobos", 1)]

    def test_longest_first(self):
        lookup = build_artist_lookup(
            [("Deep Space", 10), ("Deep Space Orchestra", 11)]
        )
        found = scan_known_artists("Deep Space Orchestra live at X", lookup)
        assert found == [("Deep Space Orchestra", 11)]

    def test_non_overlapping_multiple_matches(self):
        lookup = build_artist_lookup([("Alpha Bravo", 1), ("Charlie Delta", 2)])
        found = scan_known_artists("Alpha Bravo Charlie Delta", lookup)
        assert found == [("Alpha Bravo", 1), ("Charlie Delta", 2)]

    def test_spaced_dash_breaks_run(self):
        # The "Artist - Track" dash folds to "" → it breaks contiguity, so a key
        # straddling the dash never matches, but each side is scanned independently.
        lookup = build_artist_lookup([("Ricardo Villalobos", 1)])
        found = scan_known_artists("Ricardo Villalobos - Live Set", lookup)
        assert found == [("Ricardo Villalobos", 1)]

    def test_matches_across_edge_punctuation(self):
        # Parenthesised / bracketed occurrences still match after edge-trimming.
        lookup = build_artist_lookup([("Ricardo Villalobos", 1)])
        found = scan_known_artists("Boiler Room (Ricardo Villalobos)", lookup)
        assert found == [("Ricardo Villalobos", 1)]

    def test_folds_title_tokens(self):
        # Title carries a dotted spelling of a dot-less known key.
        lookup = build_artist_lookup([("St Germain", 1)])
        found = scan_known_artists("Tonight: St. Germain plays house", lookup)
        assert found == [("St. Germain", 1)]

    def test_no_known_artist_returns_empty(self):
        lookup = build_artist_lookup([("Ricardo Villalobos", 1)])
        assert scan_known_artists("Some Random Untitled Mix 2020", lookup) == []

    def test_empty_inputs(self):
        assert scan_known_artists("", {"a b": 1}) == []
        assert scan_known_artists("Ricardo Villalobos", {}) == []
        assert scan_known_artists(None, {"a b": 1}) == []

    def test_only_mono_keys_returns_empty(self):
        lookup = build_artist_lookup([("Live", 50), ("Fabric", 51)])
        assert scan_known_artists("Live at Fabric", lookup) == []
