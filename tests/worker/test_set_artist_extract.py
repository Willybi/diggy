"""Tests for the pure subtractive set-title → artist-candidate extractor
(workers/set_artist_extract).

Pure module, no I/O — imported directly (same sys.path pattern as
test_artist_names.py). The GUARD cases (placeholder rejected, pure-noise title
yields no title candidate, dedup) matter as much as the nominal ones: C13.c
PROPOSES, a later lot verifies against Deezer, so a bad extraction must cost
recall, never a false link.
"""

import os
import sys

# Make the workers package importable (same pattern as test_artist_names.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from workers.set_artist_extract import (  # noqa: E402
    Candidate,
    extract_artist_candidates,
    extract_candidate_names,
    split_artists,
    strip_title_noise,
)


def names(title, channel=None):
    return extract_candidate_names(title, channel)


# ── nominal: connectors split into several candidates ────────────────────────


class TestConnectors:
    def test_b2b_two_candidates(self):
        assert names("Artist One b2b Artist Two") == ["Artist One", "Artist Two"]

    def test_b3b_f2f_vs_x_all_split(self):
        assert names("Alpha B3B Beta") == ["Alpha", "Beta"]
        assert names("Alpha F2F Beta") == ["Alpha", "Beta"]
        assert names("Alpha VS Beta") == ["Alpha", "Beta"]
        assert names("Alpha vs. Beta") == ["Alpha", "Beta"]
        assert names("Bonobo x Floating Points") == ["Bonobo", "Floating Points"]

    def test_ampersand_and_feat_split(self):
        assert names("Artist A & Artist B") == ["Artist A", "Artist B"]
        assert names("Peggy Gou feat. Lenny") == ["Peggy Gou", "Lenny"]
        assert names("Peggy Gou ft Lenny") == ["Peggy Gou", "Lenny"]

    def test_presents_splits(self):
        assert names("Franky Wah presents Someone") == ["Franky Wah", "Someone"]

    def test_x_not_split_inside_word(self):
        # standalone x is a connector; x inside a name is not
        assert names("Max Cooper") == ["Max Cooper"]

    def test_vs_not_split_inside_word(self):
        assert names("Elvis Presley") == ["Elvis Presley"]

    def test_three_way_lineup(self):
        assert names("A b2b B b2b C") == ["A", "B", "C"]


# ── nominal: "Artist - Track" collapses to the leading (artist) segment ──────


class TestArtistTrackDash:
    def test_dash_keeps_only_leading_artist(self):
        assert names("Ley Moore - Songs of Spring") == ["Ley Moore"]

    def test_dash_with_collab_on_the_left(self):
        # the track title (right of dash) is dropped; the left line-up is split
        assert names("Amanita Phalloides & Heavenchord - When The Birds Are Calling") == [
            "Amanita Phalloides",
            "Heavenchord",
        ]

    def test_dash_with_lineup_and_venue_tail(self):
        assert names("Max Graef B2B Glenn Astro - AYLI Open Air 09/20/15") == [
            "Max Graef",
            "Glenn Astro",
        ]

    def test_intra_name_hyphen_preserved(self):
        # a hyphen WITHOUT surrounding spaces is not the artist/track boundary
        assert names("Cro-Magnon") == ["Cro-Magnon"]
        assert names("JAY-Z") == ["JAY-Z"]


# ── noise stripping ──────────────────────────────────────────────────────────


class TestNoiseStripping:
    def test_pure_noise_title_no_title_candidate_channel_kept(self):
        # title is only bricks → 0 title candidates, the channel survives
        cands = extract_artist_candidates("Live 2024 #5", "Boiler Room")
        assert cands == [Candidate("Boiler Room", "channel", False)]

    def test_venue_tail_after_at_dropped(self):
        assert names("Takaya Nagase @ Joy 4/23/2016") == ["Takaya Nagase"]

    def test_date_and_episode_stripped(self):
        assert names("Gai Barone Patterns 697") == ["Gai Barone Patterns"]
        assert names("XXX Radio #185") == ["XXX Radio"]

    def test_format_word_stripped(self):
        assert names("Tony Romera Live") == ["Tony Romera"]

    def test_strip_title_noise_helper(self):
        tagged = strip_title_noise("Artist Live 2024 #5")
        assert "\x00" in tagged
        # the residue word survives
        assert "Artist" in tagged


# ── buried artist (mid-phrase), structural regions ──────────────────────────


class TestBuriedArtist:
    def test_artist_recovered_after_hosting_prefix(self):
        # "by X" region → X recovered even though it is last in the title
        assert "Miss Monique" in names(
            "deep story nr. 167 | server farm | by Miss Monique"
        )

    def test_artist_recovered_after_presents_connector(self):
        assert "Peggy Gou" in names("Boiler Room presents Peggy Gou")

    def test_leading_region_is_boosted(self):
        cands = extract_artist_candidates("Alpha | Beta", None)
        by_name = {c.name: c for c in cands}
        assert by_name["Alpha"].is_boosted is True
        assert by_name["Beta"].is_boosted is False


# ── channel handling ─────────────────────────────────────────────────────────


class TestChannel:
    def test_channel_always_added(self):
        cands = extract_artist_candidates("Deadmau5", "Boiler Room")
        assert Candidate("Boiler Room", "channel", False) in cands

    def test_channel_collab_split(self):
        cands = extract_artist_candidates("", "Susi&Paula")
        assert [c.name for c in cands] == ["Susi", "Paula"]
        assert all(c.source == "channel" for c in cands)

    def test_channel_none_only_title(self):
        cands = extract_artist_candidates("Deadmau5", None)
        assert cands == [Candidate("Deadmau5", "title", True)]

    def test_channel_empty_string_only_title(self):
        assert names("Deadmau5", "") == ["Deadmau5"]


# ── placeholder rejection ────────────────────────────────────────────────────


class TestPlaceholderRejection:
    def test_various_artists_title_rejected(self):
        # the placeholder is dropped; only the (real) channel survives
        assert names("Various Artists", "Real Channel") == ["Real Channel"]

    def test_unknown_artist_rejected_both_sources(self):
        assert names("Unknown Artist", "unknown") == []

    def test_placeholder_in_lineup_dropped_others_kept(self):
        assert names("VA & Peggy Gou") == ["Peggy Gou"]


# ── dedup by fold key ────────────────────────────────────────────────────────


class TestDedup:
    def test_title_and_channel_same_artist_deduped(self):
        # title candidate wins (added first), channel duplicate folds away
        cands = extract_artist_candidates("Peggy Gou", "peggy gou")
        assert cands == [Candidate("Peggy Gou", "title", True)]

    def test_punctuation_insensitive_dedup(self):
        # "St. Germain" and "St Germain" fold together → one candidate
        cands = extract_artist_candidates("St. Germain & St Germain", None)
        assert [c.name for c in cands] == ["St. Germain"]

    def test_repeated_name_kept_once(self):
        assert names("A b2b B b2b A") == ["A", "B"]


# ── edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_title_and_channel(self):
        assert extract_artist_candidates("", "") == []
        assert extract_artist_candidates("", None) == []

    def test_none_title(self):
        assert extract_artist_candidates(None, "Chan") == [
            Candidate("Chan", "channel", False)
        ]

    def test_none_everything(self):
        assert extract_artist_candidates(None, None) == []

    def test_number_only_residue_rejected(self):
        # a bare number region carries no letter → no candidate from the title
        assert names("2024", "Chan") == ["Chan"]

    def test_bracketed_noise_dropped_name_kept(self):
        # "(Live Set)" is pure noise → dropped; the name outside stays
        assert names("Peggy Gou (Live Set)") == ["Peggy Gou"]


# ── split_artists (exposed helper) ───────────────────────────────────────────


class TestSplitArtists:
    def test_splits_on_all_connectors(self):
        assert [p.strip() for p in split_artists("A & B b2b C, D")] == [
            "A",
            "B",
            "C",
            "D",
        ]

    def test_no_connector_single_fragment(self):
        assert [p.strip() for p in split_artists("Solo Artist")] == ["Solo Artist"]

    def test_empty(self):
        assert split_artists("") == []
        assert split_artists(None) == []
