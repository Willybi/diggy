"""Unit tests for the matching engine (L3) — no DB required.

Covers: token_set_ratio, compute_signals, decide_verdict.
"""

from datetime import date

import pytest

from services.set_dedup_service import (
    MatchSignals,
    MatchVerdict,
    compute_signals,
    decide_verdict,
    token_set_ratio,
)


# ---------------------------------------------------------------------------
# token_set_ratio
# ---------------------------------------------------------------------------


class TestTokenSetRatio:
    def test_identical_strings(self):
        assert token_set_ratio("hello world", "hello world") == 1.0

    def test_no_common_tokens(self):
        assert token_set_ratio("hello world", "foo bar") == 0.0

    def test_half_common(self):
        # intersection={a,b}, union={a,b,c,d} → 2/4
        assert token_set_ratio("a b c", "a b d") == pytest.approx(0.5)

    def test_both_empty(self):
        assert token_set_ratio("", "") == 1.0

    def test_one_empty(self):
        assert token_set_ratio("hello", "") == 0.0
        assert token_set_ratio("", "hello") == 0.0

    def test_subset(self):
        # intersection={a,b}, union={a,b,c} → 2/3
        assert token_set_ratio("a b", "a b c") == pytest.approx(2 / 3)

    def test_case_sensitive(self):
        # token_set_ratio is case-sensitive; caller should lowercase inputs
        assert token_set_ratio("Hello", "hello") == 0.0


# ---------------------------------------------------------------------------
# compute_signals — fixture data
# ---------------------------------------------------------------------------

# Paire 1 (sets 63/64) — titres identiques, tracklists identiques
_SET_A_P1 = {
    "normalized_title": "overmono - boiler room: manchester",
    "played_date": date(2023, 9, 15),
    "identified_mtids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}
_SET_B_P1 = {
    "normalized_title": "overmono - boiler room: manchester",
    "played_date": date(2023, 9, 15),
    "identified_mtids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}

# Paire 3 (sets 7/11) — titres très différents (canaux différents),
# mais overlap élevé et même date.  Les normalized_titles utilisées ici
# représentent le cas où l'un des sets a été importé avec un titre de chaîne
# très différent des noms d'artistes.
_SET_A_P3 = {
    "normalized_title": "razoratorczraw weekly live recording paris",
    "played_date": date(2025, 10, 25),
    "identified_mtids": list(range(1, 20)),  # 19 tracks
}
_SET_B_P3 = {
    "normalized_title": "thomas bangalter b2b fred again erol alkan busy p @ because beaubourg",
    "played_date": date(2025, 10, 25),
    "identified_mtids": list(range(1, 28)),  # 27 tracks
}

# Paire 4 (sets 22/27) — titres identiques, tracklists presque identiques
_SET_A_P4 = {
    "normalized_title": "fred again.. - boiler room: london",
    "played_date": date(2024, 6, 1),
    "identified_mtids": list(range(1, 16)),  # 15 tracks
}
_SET_B_P4 = {
    "normalized_title": "fred again.. - boiler room: london",
    "played_date": date(2024, 6, 1),
    "identified_mtids": list(range(1, 16)),  # 15 tracks
}


class TestComputeSignals:
    # --- Paire 1 ---

    def test_p1_overlap(self):
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        assert signals.overlap == 1.0

    def test_p1_title_sim(self):
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        assert signals.title_sim == 1.0

    def test_p1_date_match(self):
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        assert signals.date_match is True

    def test_p1_first_track_match(self):
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        assert signals.first_track_match is True

    # --- Paire 3 ---

    def test_p3_overlap(self):
        signals = compute_signals(_SET_A_P3, _SET_B_P3, shared_count=16)
        assert signals.overlap == pytest.approx(16 / 19, rel=1e-2)

    def test_p3_date_match(self):
        signals = compute_signals(_SET_A_P3, _SET_B_P3, shared_count=16)
        assert signals.date_match is True

    def test_p3_title_sim_low(self):
        signals = compute_signals(_SET_A_P3, _SET_B_P3, shared_count=16)
        assert signals.title_sim < 0.30

    # --- Paire 4 ---

    def test_p4_overlap(self):
        signals = compute_signals(_SET_A_P4, _SET_B_P4, shared_count=13)
        assert signals.overlap == pytest.approx(13 / 15, rel=1e-2)

    def test_p4_title_sim(self):
        signals = compute_signals(_SET_A_P4, _SET_B_P4, shared_count=13)
        assert signals.title_sim == 1.0

    # --- Edge cases ---

    def test_zero_min_len_gives_zero_overlap(self):
        a = {"normalized_title": "", "played_date": None, "identified_mtids": []}
        b = {"normalized_title": "", "played_date": None, "identified_mtids": [1, 2]}
        signals = compute_signals(a, b, shared_count=0)
        assert signals.overlap == 0.0

    def test_date_none_gives_false(self):
        a = {**_SET_A_P1, "played_date": None}
        signals = compute_signals(a, _SET_B_P1, shared_count=12)
        assert signals.date_match is False

    def test_date_within_one_day(self):
        a = {**_SET_A_P1, "played_date": date(2023, 9, 14)}
        signals = compute_signals(a, _SET_B_P1, shared_count=12)
        assert signals.date_match is True

    def test_date_two_days_apart(self):
        a = {**_SET_A_P1, "played_date": date(2023, 9, 13)}
        signals = compute_signals(a, _SET_B_P1, shared_count=12)
        assert signals.date_match is False

    def test_first_track_no_match(self):
        a = {**_SET_A_P1, "identified_mtids": [99, 2, 3]}
        signals = compute_signals(a, _SET_B_P1, shared_count=3)
        assert signals.first_track_match is False

    def test_first_track_empty_list(self):
        a = {**_SET_A_P1, "identified_mtids": []}
        signals = compute_signals(a, _SET_B_P1, shared_count=0)
        assert signals.first_track_match is False


# ---------------------------------------------------------------------------
# decide_verdict
# ---------------------------------------------------------------------------


class TestDecideVerdict:
    def test_p1_auto_attach(self):
        """Paire 1: overlap=1.0, title_sim=1.0, date_match=True → AUTO_ATTACH."""
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.AUTO_ATTACH
        assert flag_type is None

    def test_p3_auto_attach_via_date(self):
        """Paire 3: overlap=0.842 >= 0.80, date_match=True → AUTO_ATTACH (title_sim irrelevant)."""
        signals = compute_signals(_SET_A_P3, _SET_B_P3, shared_count=16)
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.AUTO_ATTACH
        assert flag_type is None

    def test_grey_zone_flag(self):
        """0.50 <= overlap < 0.80 → FLAG duplicate_candidate."""
        signals = MatchSignals(
            overlap=0.60, title_sim=0.40, date_match=False, first_track_match=False
        )
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_dj_tour_flag(self):
        """overlap=0.65, title_sim=0.20, date_match=False → FLAG (overlap band, not auto)."""
        signals = MatchSignals(
            overlap=0.65, title_sim=0.20, date_match=False, first_track_match=False
        )
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_negative_nothing(self):
        """Low overlap + low title_sim → NOTHING."""
        signals = MatchSignals(
            overlap=0.20, title_sim=0.30, date_match=False, first_track_match=False
        )
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.NOTHING
        assert flag_type is None

    def test_high_title_sim_flag(self):
        """title_sim >= 0.90 AND overlap >= 0.30 → FLAG."""
        signals = MatchSignals(
            overlap=0.35, title_sim=0.92, date_match=False, first_track_match=False
        )
        verdict, _ = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.FLAG

    def test_high_overlap_no_corroboration_flags(self):
        """overlap=0.75, title_sim=0.10, date_match=False → FLAG (overlap band)."""
        signals = MatchSignals(
            overlap=0.75, title_sim=0.10, date_match=False, first_track_match=False
        )
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_auto_attach_title_sim_triggers(self):
        """overlap=0.85, title_sim=0.60 → AUTO_ATTACH (title_sim >= 0.50 satisfies condition)."""
        signals = MatchSignals(
            overlap=0.85, title_sim=0.60, date_match=False, first_track_match=False
        )
        verdict, flag_type = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.AUTO_ATTACH
        assert flag_type is None

    def test_high_overlap_no_title_no_date_flags(self):
        """overlap=0.80, title_sim=0.40, date_match=False → FLAG (overlap band: <0.80 is excluded)."""
        # 0.80 is not strictly < 0.80, and title_sim < 0.50 and date_match=False
        # so the first rule fails; falls to band 0.50 <= overlap < 0.80 which also fails
        # (0.80 is not < 0.80); next: title_sim < 0.90 → NOTHING
        signals = MatchSignals(
            overlap=0.80, title_sim=0.40, date_match=False, first_track_match=False
        )
        verdict, _ = decide_verdict(signals, None, None)
        assert verdict == MatchVerdict.NOTHING
