"""Tests for normalize_set_title() — set deduplication, lot L2.

5 real production pairs are covered as fixtures.
"""

from datetime import date

import pytest

from services.set_dedup_service import NormalizedTitle, normalize_set_title


# ---------------------------------------------------------------------------
# Paire 1 — titres identiques (sets 63 & 64)
# ---------------------------------------------------------------------------


class TestPaire1:
    def test_pipe_separator_unified(self):
        result = normalize_set_title("Overmono | Boiler Room: Manchester")
        assert result.text == "overmono - boiler room: manchester"

    def test_no_part_number(self):
        result = normalize_set_title("Overmono | Boiler Room: Manchester")
        assert result.part_number is None

    def test_no_date(self):
        result = normalize_set_title("Overmono | Boiler Room: Manchester")
        assert result.extracted_date is None

    def test_base_title_equals_text(self):
        result = normalize_set_title("Overmono | Boiler Room: Manchester")
        assert result.base_title == result.text


# ---------------------------------------------------------------------------
# Paire 2 — triplet avec variations @ (sets 19/20/21)
# ---------------------------------------------------------------------------


class TestPaire2:
    V1 = "Overmono, Fred Again.. & Lil Yachty @TheLotRadio"
    V2 = "Overmono, Fred again.. & Lil Yachty @ The Lot Radio"
    V3 = "Overmono, Fred Again.. & Lil Yachty @TheLotRadio"

    def test_at_spacing_inserted(self):
        """@word → @ word when @ is directly glued to the next token."""
        result = normalize_set_title(self.V1)
        assert "@ " in result.text

    def test_v1_and_v3_identical(self):
        """V1 and V3 are the same raw string → must produce the same text."""
        assert normalize_set_title(self.V1).text == normalize_set_title(self.V3).text

    def test_v2_already_spaced(self):
        """V2 already has a space after @, so no double-space is introduced."""
        result = normalize_set_title(self.V2)
        assert "  " not in result.text  # no double space
        assert "@ " in result.text

    def test_all_share_artist_prefix(self):
        """All 3 share the same artist prefix after normalization."""
        expected_prefix = "overmono, fred again.. & lil yachty @"
        for v in (self.V1, self.V2, self.V3):
            assert normalize_set_title(v).text.startswith(
                "overmono, fred again.. & lil yachty"
            )


# ---------------------------------------------------------------------------
# Paire 3 — cas dur (sets 7 & 11)
# Remarque : la normalisation du titre NE résout PAS cette paire.
# La paire 3 est résolue par l'overlap de tracks + date_match, pas par le titre.
# ---------------------------------------------------------------------------


_PAIR3_RAW1 = (
    "RazoratorCZ - Busy_P_b2b_Erol_Alkan_b2b_Fred_again.._b2b_"
    "Thomas_Bangalter_-_Live_at_Because_Beaubourg_Paris_25-10-2025-Razorator"
)
_PAIR3_RAW2 = (
    "Thomas Bangalter B2B Fred Again, Erol Alkan, Busy P "
    "@ Because Beaubourg [25/10/25]"
)


class TestPaire3:
    def test_input1_prefix_stripped(self):
        """Channel prefix 'RazoratorCZ - ' is removed."""
        result = normalize_set_title(_PAIR3_RAW1, channel="RazoratorCZ")
        assert result.text.startswith("busy p b2b")

    def test_input1_underscores_replaced(self):
        result = normalize_set_title(_PAIR3_RAW1, channel="RazoratorCZ")
        assert "_" not in result.text

    def test_input1_date_not_extracted(self):
        """The watermark '-Razorator' ≠ '-RazoratorCZ', so the suffix is NOT
        stripped and the date '25-10-2025' is not at the title end.
        The bare date regex (anchored with $) therefore cannot match.
        Date extraction for this variant is a known limitation of L2;
        the pair is resolved in L3 via track overlap + date_match."""
        result = normalize_set_title(_PAIR3_RAW1, channel="RazoratorCZ")
        assert result.extracted_date is None

    def test_input2_date_extracted_from_brackets(self):
        result = normalize_set_title(_PAIR3_RAW2)
        assert result.extracted_date == date(2025, 10, 25)

    def test_input2_bracket_tag_removed(self):
        result = normalize_set_title(_PAIR3_RAW2)
        assert "[25/10/25]" not in result.text
        assert "[" not in result.text

    def test_texts_differ(self):
        """Normalization does NOT bring the two titles close — expected."""
        r1 = normalize_set_title(_PAIR3_RAW1, channel="RazoratorCZ")
        r2 = normalize_set_title(_PAIR3_RAW2)
        assert r1.text != r2.text


# ---------------------------------------------------------------------------
# Paire 4 — titres identiques (sets 22 & 27)
# ---------------------------------------------------------------------------


class TestPaire4:
    def test_pipe_to_dash(self):
        result = normalize_set_title("Fred again.. | Boiler Room: London")
        assert result.text == "fred again.. - boiler room: london"


# ---------------------------------------------------------------------------
# Paire 5 — reformulation (sets 80 & 86)
# ---------------------------------------------------------------------------


class TestPaire5:
    V1 = "Barry Can't Swim Boiler Room X FLY Open Air 2023"
    V2 = "Barry Can't Swim | FLY Open Air 2023"

    def test_v1_normalizes(self):
        result = normalize_set_title(self.V1)
        assert result.text == "barry can't swim boiler room x fly open air 2023"

    def test_v2_pipe_to_dash(self):
        result = normalize_set_title(self.V2)
        assert result.text == "barry can't swim - fly open air 2023"

    def test_both_share_artist_and_event(self):
        """Titles differ but share key tokens; matching tolerance handles this."""
        r1 = normalize_set_title(self.V1)
        r2 = normalize_set_title(self.V2)
        assert "barry can't swim" in r1.base_title
        assert "barry can't swim" in r2.base_title
        assert "fly open air 2023" in r1.base_title
        assert "fly open air 2023" in r2.base_title


# ---------------------------------------------------------------------------
# Cas limites
# ---------------------------------------------------------------------------


class TestPartNumber:
    def test_part_numeric(self):
        result = normalize_set_title("DJ Set - Berlin Part 2")
        assert result.part_number == 2
        assert result.base_title == "dj set - berlin"

    def test_pt_dot(self):
        result = normalize_set_title("Boiler Room Pt.1")
        assert result.part_number == 1
        assert result.base_title == "boiler room"

    def test_no_part(self):
        result = normalize_set_title("Boiler Room London")
        assert result.part_number is None
        assert result.base_title == result.text


class TestDateExtraction:
    def test_brackets_dot_separator(self):
        result = normalize_set_title("Set [10.12.2022]")
        assert result.extracted_date == date(2022, 12, 10)
        assert "[" not in result.text

    def test_brackets_two_digit_year(self):
        result = normalize_set_title("Set [25/10/25]")
        assert result.extracted_date == date(2025, 10, 25)

    def test_two_digit_year_old(self):
        """YY > 50 → 1900+YY."""
        result = normalize_set_title("Set [10/06/99]")
        assert result.extracted_date == date(1999, 6, 10)

    def test_bare_date_at_end(self):
        result = normalize_set_title("Live at Fabric 15-03-2024")
        assert result.extracted_date == date(2024, 3, 15)
        assert "15-03-2024" not in result.text


class TestMisc:
    def test_underscores_become_spaces(self):
        result = normalize_set_title("Busy_P_b2b_Erol")
        assert result.text == "busy p b2b erol"

    def test_channel_prefix_stripped(self):
        result = normalize_set_title("MyChannel - Great Set", channel="MyChannel")
        assert result.text == "great set"

    def test_channel_suffix_stripped(self):
        result = normalize_set_title("Great Set-MyChannel", channel="MyChannel")
        assert result.text == "great set"

    def test_channel_suffix_with_space(self):
        result = normalize_set_title("Great Set - MyChannel", channel="MyChannel")
        assert result.text == "great set"

    def test_at_glued_inserts_space(self):
        result = normalize_set_title("Live @Fabric")
        assert "@ fabric" in result.text

    def test_at_already_spaced_unchanged(self):
        result = normalize_set_title("Live @ Fabric")
        assert "@ fabric" in result.text
        assert "@  " not in result.text  # no double space

    def test_decorative_tag_stripped(self):
        result = normalize_set_title("Big Set [Full Set HD]")
        assert "[full set hd]" not in result.text
        assert result.text == "big set"

    def test_returns_normalized_title_dataclass(self):
        result = normalize_set_title("Test")
        assert isinstance(result, NormalizedTitle)
        assert isinstance(result.text, str)
        assert isinstance(result.base_title, str)

    def test_part_total_none_for_digit_branch(self):
        result = normalize_set_title("DJ Set - Berlin Part 2")
        assert result.part_total is None


# ---------------------------------------------------------------------------
# C6.1 — Branche 2 : chiffres romains
# ---------------------------------------------------------------------------


class TestPartRoman:
    # Fixture réelle : set 5 (Thomas Bangalter of Daft Punk … Part II)
    _SET5 = (
        "Thomas Bangalter of Daft Punk and Fred again.. live in London "
        "USB002 (February 27, 2026) Part II"
    )

    def test_roman_ii_detected(self):
        result = normalize_set_title(self._SET5)
        assert result.part_number == 2

    def test_roman_part_total_is_none(self):
        result = normalize_set_title(self._SET5)
        assert result.part_total is None

    def test_roman_base_title_no_suffix(self):
        result = normalize_set_title(self._SET5)
        assert "part" not in result.base_title
        assert "ii" not in result.base_title

    def test_roman_i(self):
        result = normalize_set_title("Great Set Part I")
        assert result.part_number == 1

    def test_roman_iii(self):
        result = normalize_set_title("Great Set Part III")
        assert result.part_number == 3

    def test_roman_iv(self):
        result = normalize_set_title("Great Set Part IV")
        assert result.part_number == 4

    def test_roman_v(self):
        result = normalize_set_title("Great Set Pt. V")
        assert result.part_number == 5

    def test_roman_without_keyword_not_matched(self):
        """A bare roman numeral at the end (no part/pt keyword) must NOT match."""
        result = normalize_set_title("Boiler Room London II")
        assert result.part_number is None


# ---------------------------------------------------------------------------
# C6.1 — Branche 3 : fraction N/M
# ---------------------------------------------------------------------------


class TestPartFraction:
    # Fixture réelle : groupe Folamour (format 1/7 … 7/7)
    def test_folamour_1_7(self):
        result = normalize_set_title(
            "Folamour - The Very Best Of Folamour - Home Party Series 1/7"
        )
        assert result.part_number == 1
        assert result.part_total == 7

    def test_folamour_7_7(self):
        result = normalize_set_title(
            "Folamour - The Very Best Of Folamour - Home Party Series 7/7"
        )
        assert result.part_number == 7
        assert result.part_total == 7

    def test_fraction_base_title_no_suffix(self):
        result = normalize_set_title("Some DJ Set 3/5")
        assert "3/5" not in result.base_title
        assert result.base_title == "some dj set"

    def test_fraction_guard_n_greater_than_m(self):
        """9/7 is not a valid part fraction — n > m."""
        result = normalize_set_title("Some Set 9/7")
        assert result.part_number is None
        assert result.part_total is None

    def test_fraction_guard_denominator_too_large(self):
        """1/24 is more likely a date fragment — denominator > 20."""
        result = normalize_set_title("Some Set 1/24")
        assert result.part_number is None

    def test_fraction_guard_denominator_too_small(self):
        """X/1 — denominator must be >= 2."""
        result = normalize_set_title("Some Set 1/1")
        assert result.part_number is None

    # Fixture négative réelle : set 10 (6/1/24 = date, 3 composants)
    _SET10 = (
        "Clearcast b2b Vertigo @ Fred Again x Skrillex "
        "| Civic Center San Francisco | 6/1/24"
    )

    def test_anti_date_guard_three_components(self):
        """6/1/24 = date M/D/YY — must NOT produce part_number."""
        result = normalize_set_title(self._SET10)
        assert result.part_number is None
        assert result.part_total is None

    # Fixture synthétique : titre avec date d'événement + suffixe Part N
    _SYNTHETIC_P1 = "Live set @ Tresor x Mord Showcase 12.06.26 - Part 1"
    _SYNTHETIC_P2 = "Live set @ Tresor x Mord Showcase 12.06.26 - Part 2"

    def test_synthetic_part1_branch1(self):
        """Date extracted at step 6, then Part 1 at end → branch 1 matches."""
        result = normalize_set_title(self._SYNTHETIC_P1)
        assert result.part_number == 1

    def test_synthetic_part2_branch1(self):
        result = normalize_set_title(self._SYNTHETIC_P2)
        assert result.part_number == 2

    def test_synthetic_same_base_title(self):
        """Both synthetic parts must share the same base_title."""
        r1 = normalize_set_title(self._SYNTHETIC_P1)
        r2 = normalize_set_title(self._SYNTHETIC_P2)
        assert r1.base_title == r2.base_title
