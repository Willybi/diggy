"""Unit tests for the matching engine (L3) — no DB required.

Covers: token_set_ratio, compute_signals (incl. weighted_overlap / date_gap_days /
order_corr), compute_confidence, decide_verdict, prod calibration cases.
"""

from datetime import date

import pytest

from services.set_dedup_service import (
    AUTO_ATTACH_MAX_DATE_GAP_DAYS,
    FLAG_CONFIDENCE_THRESHOLD,
    MatchSignals,
    MatchVerdict,
    compute_confidence,
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

    def test_p1_new_signals(self):
        """Identical tracklists, no df → weighted_overlap=1, gap=0, order_corr=1."""
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        assert signals.weighted_overlap == pytest.approx(1.0)
        assert signals.date_gap_days == 0
        assert signals.order_corr == pytest.approx(1.0)

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
        assert signals.weighted_overlap == 0.0

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
# compute_signals — weighted_overlap (IDF)
# ---------------------------------------------------------------------------


class TestWeightedOverlap:
    def test_rare_tracks_equal_raw_overlap(self):
        """All df=1 (unique tracks) → weighted_overlap == raw overlap."""
        a = {"normalized_title": "x", "played_date": None,
             "identified_mtids": [1, 2, 3, 4]}
        b = {"normalized_title": "y", "played_date": None,
             "identified_mtids": [1, 2, 3, 9]}
        df = {1: 1, 2: 1, 3: 1, 4: 1, 9: 1}
        signals = compute_signals(a, b, shared_count=3, mtid_df=df)
        assert signals.overlap == pytest.approx(0.75)
        assert signals.weighted_overlap == pytest.approx(0.75)

    def test_anthems_crush_weighted_overlap(self):
        """Shared tracks present in 17 sets weigh ~0.24 each → wo << raw overlap."""
        a = {"normalized_title": "x", "played_date": None,
             "identified_mtids": [1, 2, 3, 4]}
        b = {"normalized_title": "y", "played_date": None,
             "identified_mtids": [1, 2, 3, 9]}
        # shared 1-3 are genre anthems (df=17), unique 4/9 are rare
        df = {1: 17, 2: 17, 3: 17, 4: 1, 9: 1}
        signals = compute_signals(a, b, shared_count=3, mtid_df=df)
        assert signals.overlap == pytest.approx(0.75)
        # 3 * (1/log2(18)) / (3 * (1/log2(18)) + 1) ≈ 0.4184
        assert signals.weighted_overlap == pytest.approx(0.4184, abs=1e-3)
        assert signals.weighted_overlap < signals.overlap

    def test_missing_df_key_defaults_to_one(self):
        """mtid absent from the df dict is treated as unique (df=1)."""
        a = {"normalized_title": "x", "played_date": None,
             "identified_mtids": [1, 2, 3]}
        b = {"normalized_title": "y", "played_date": None,
             "identified_mtids": [1, 2, 3]}
        signals = compute_signals(a, b, shared_count=3, mtid_df={})
        assert signals.weighted_overlap == pytest.approx(1.0)

    def test_no_df_argument_defaults_to_one(self):
        """Omitted mtid_df behaves like all-unique tracks."""
        a = {"normalized_title": "x", "played_date": None,
             "identified_mtids": [1, 2, 3, 4]}
        b = {"normalized_title": "y", "played_date": None,
             "identified_mtids": [1, 2, 5, 6]}
        signals = compute_signals(a, b, shared_count=2)
        assert signals.weighted_overlap == pytest.approx(0.5)

    def test_denominator_is_smaller_set(self):
        """Denominator = weights of the set with fewer identified mtids."""
        a = {"normalized_title": "x", "played_date": None,
             "identified_mtids": [1, 2]}  # smaller set
        b = {"normalized_title": "y", "played_date": None,
             "identified_mtids": [1, 2, 3, 4, 5, 6]}
        signals = compute_signals(a, b, shared_count=2)
        assert signals.weighted_overlap == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_signals — date_gap_days
# ---------------------------------------------------------------------------


class TestDateGapDays:
    def test_known_dates_absolute_gap(self):
        a = {**_SET_A_P1, "played_date": date(2026, 3, 1)}
        b = {**_SET_B_P1, "played_date": date(2026, 3, 17)}
        signals = compute_signals(a, b, shared_count=12)
        assert signals.date_gap_days == 16
        # gap is absolute: order of the two sets does not matter
        signals_rev = compute_signals(b, a, shared_count=12)
        assert signals_rev.date_gap_days == 16

    def test_unknown_date_gives_none(self):
        a = {**_SET_A_P1, "played_date": None}
        signals = compute_signals(a, _SET_B_P1, shared_count=12)
        assert signals.date_gap_days is None
        assert signals.date_match is False

    def test_gap_one_day_keeps_date_match(self):
        """date_match (<= 1 day) is preserved for audit_set_dedup compat."""
        a = {**_SET_A_P1, "played_date": date(2023, 9, 14)}
        signals = compute_signals(a, _SET_B_P1, shared_count=12)
        assert signals.date_gap_days == 1
        assert signals.date_match is True


# ---------------------------------------------------------------------------
# compute_signals — order_corr (Spearman)
# ---------------------------------------------------------------------------


def _sig_for_orders(mtids_a, mtids_b, shared_count):
    a = {"normalized_title": "x", "played_date": None, "identified_mtids": mtids_a}
    b = {"normalized_title": "y", "played_date": None, "identified_mtids": mtids_b}
    return compute_signals(a, b, shared_count=shared_count)


class TestOrderCorrelation:
    def test_same_order_is_one(self):
        signals = _sig_for_orders(list(range(1, 11)), list(range(1, 11)), 10)
        assert signals.order_corr == pytest.approx(1.0)

    def test_same_order_with_extra_tracks(self):
        """Non-shared tracks interleaved do not break a perfect shared order."""
        signals = _sig_for_orders([1, 90, 2, 3, 91], [1, 2, 80, 3], 3)
        assert signals.order_corr == pytest.approx(1.0)

    def test_reversed_order_is_negative(self):
        signals = _sig_for_orders([1, 2, 3, 4, 5], [5, 4, 3, 2, 1], 5)
        assert signals.order_corr == pytest.approx(-1.0)

    def test_shuffled_order_is_low(self):
        # ranks a: 1,2,3,4 → 0,1,2,3 ; b: 3,1,4,2 → Σd²=10 → rho = 0.0
        signals = _sig_for_orders([1, 2, 3, 4], [3, 1, 4, 2], 4)
        assert signals.order_corr == pytest.approx(0.0)

    def test_fewer_than_three_shared_is_none(self):
        signals = _sig_for_orders([1, 2, 99], [1, 2, 98], 2)
        assert signals.order_corr is None

    def test_no_shared_is_none(self):
        signals = _sig_for_orders([1, 2, 3], [7, 8, 9], 0)
        assert signals.order_corr is None


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------


def _signals(
    overlap=0.0,
    title_sim=0.0,
    date_match=False,
    first_track_match=False,
    weighted_overlap=0.0,
    date_gap_days=None,
    order_corr=None,
):
    return MatchSignals(
        overlap=overlap,
        title_sim=title_sim,
        date_match=date_match,
        first_track_match=first_track_match,
        weighted_overlap=weighted_overlap,
        date_gap_days=date_gap_days,
        order_corr=order_corr,
    )


class TestComputeConfidence:
    def test_base_formula(self):
        """0.55*wo + 0.25*title + 0.10*order + 0.10*first, no date factor."""
        s = _signals(
            weighted_overlap=0.8, title_sim=0.4, order_corr=0.5,
            first_track_match=True, date_gap_days=None,
        )
        assert compute_confidence(s) == pytest.approx(0.69)

    def test_same_day_boost(self):
        s = _signals(
            weighted_overlap=0.8, title_sim=0.4, order_corr=0.5,
            first_track_match=True, date_gap_days=0, date_match=True,
        )
        assert compute_confidence(s) == pytest.approx(0.69 * 1.15, abs=1e-4)

    def test_gap_two_days_neutral(self):
        s = _signals(weighted_overlap=0.8, title_sim=0.4, date_gap_days=2)
        assert compute_confidence(s) == pytest.approx(0.54)

    def test_gap_within_month_dampens(self):
        s = _signals(weighted_overlap=0.8, title_sim=0.4, date_gap_days=16)
        assert compute_confidence(s) == pytest.approx(0.54 * 0.6, abs=1e-4)

    def test_gap_over_month_crushes(self):
        s = _signals(weighted_overlap=0.8, title_sim=0.4, date_gap_days=45)
        assert compute_confidence(s) == pytest.approx(0.54 * 0.3, abs=1e-4)

    def test_negative_order_corr_clamped_to_zero(self):
        s = _signals(weighted_overlap=0.8, order_corr=-1.0)
        assert compute_confidence(s) == pytest.approx(0.44)

    def test_none_order_corr_counts_as_zero(self):
        s = _signals(weighted_overlap=0.8, order_corr=None)
        assert compute_confidence(s) == pytest.approx(0.44)

    def test_capped_at_one(self):
        s = _signals(
            weighted_overlap=1.0, title_sim=1.0, order_corr=1.0,
            first_track_match=True, date_gap_days=0, date_match=True,
        )
        assert compute_confidence(s) == 1.0

    def test_rounded_to_four_decimals(self):
        s = _signals(weighted_overlap=1 / 3)
        assert compute_confidence(s) == pytest.approx(round(0.55 / 3, 4), abs=1e-9)


# ---------------------------------------------------------------------------
# decide_verdict
# ---------------------------------------------------------------------------


def _verdict(signals):
    return decide_verdict(signals, compute_confidence(signals), None, None)


class TestDecideVerdict:
    def test_p1_auto_attach(self):
        """Paire 1: overlap=1.0, title_sim=1.0, gap=0 → AUTO_ATTACH."""
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH
        assert flag_type is None

    def test_p3_auto_attach_via_date(self):
        """Paire 3: overlap=0.842 >= 0.80, same day → AUTO_ATTACH (title_sim irrelevant)."""
        signals = compute_signals(_SET_A_P3, _SET_B_P3, shared_count=16)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH
        assert flag_type is None

    def test_grey_zone_uncorroborated_is_nothing(self):
        """Raw-overlap grey zone without corroboration no longer flags.

        Old rule: 0.50 <= overlap < 0.80 → FLAG unconditionally.
        New rule: confidence 0.55*0.6 + 0.25*0.4 = 0.43 < 0.45 → NOTHING.
        """
        signals = _signals(overlap=0.60, title_sim=0.40, weighted_overlap=0.60)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.NOTHING
        assert flag_type is None

    def test_grey_zone_with_first_track_flags(self):
        """Same grey zone WITH a corroborating first track → 0.53 >= 0.45 → FLAG."""
        signals = _signals(
            overlap=0.60, title_sim=0.40, weighted_overlap=0.60,
            first_track_match=True,
        )
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_dj_tour_is_nothing(self):
        """Two dates weeks apart + anthem-heavy overlap → NOTHING (was FLAG).

        The prod false-positive class: two DJs (or one DJ on tour) sharing the
        genre anthems. Weighted overlap is low and the date factor crushes it.
        """
        signals = _signals(
            overlap=0.65, title_sim=0.20, weighted_overlap=0.30, date_gap_days=45
        )
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.NOTHING
        assert flag_type is None

    def test_negative_nothing(self):
        """Low overlap + low title_sim → NOTHING."""
        signals = _signals(overlap=0.20, title_sim=0.30, weighted_overlap=0.20)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.NOTHING
        assert flag_type is None

    def test_high_title_sim_flag(self):
        """title_sim >= 0.90 AND overlap >= 0.30 → FLAG even below the confidence bar."""
        signals = _signals(overlap=0.35, title_sim=0.92, weighted_overlap=0.35)
        assert compute_confidence(signals) < FLAG_CONFIDENCE_THRESHOLD
        verdict, _ = _verdict(signals)
        assert verdict == MatchVerdict.FLAG

    def test_high_weighted_overlap_low_title_is_nothing(self):
        """overlap=0.75 of RARE tracks but title_sim=0.10 → 0.4375 < 0.45 → NOTHING.

        Old rule flagged any overlap in [0.50, 0.80); rarity alone without any
        other corroborating signal now stays just under the bar.
        """
        signals = _signals(overlap=0.75, title_sim=0.10, weighted_overlap=0.75)
        verdict, _ = _verdict(signals)
        assert verdict == MatchVerdict.NOTHING

    def test_auto_attach_title_sim_triggers(self):
        """overlap=0.85, title_sim=0.60, dates unknown → AUTO_ATTACH (no date guard)."""
        signals = _signals(overlap=0.85, title_sim=0.60, weighted_overlap=0.85)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH
        assert flag_type is None

    def test_strong_weighted_overlap_moderate_title_flags(self):
        """overlap=0.80 (excluded from auto: title<0.5, no date) → composite FLAG.

        Old rules left this NOTHING (outside every band); the composite
        confidence 0.55*0.8 + 0.25*0.4 = 0.54 >= 0.45 now surfaces it.
        """
        signals = _signals(overlap=0.80, title_sim=0.40, weighted_overlap=0.80)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_distinct_part_numbers_nothing(self):
        """Distinct part_numbers → parts path, never a pairwise verdict."""
        signals = compute_signals(_SET_A_P1, _SET_B_P1, shared_count=12)
        verdict, flag_type = decide_verdict(
            signals, compute_confidence(signals), 1, 2
        )
        assert verdict == MatchVerdict.NOTHING
        assert flag_type is None


class TestAutoAttachDateGuard:
    """AUTO_ATTACH is blocked when the two known dates are clearly distinct."""

    def _auto_signals(self, date_gap_days, date_match=False):
        return _signals(
            overlap=0.85, title_sim=0.60, weighted_overlap=0.78,
            first_track_match=True, order_corr=1.0,
            date_gap_days=date_gap_days, date_match=date_match,
        )

    def test_gap_zero_auto_attaches(self):
        signals = self._auto_signals(0, date_match=True)
        verdict, _ = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH

    def test_gap_at_threshold_auto_attaches(self):
        signals = self._auto_signals(AUTO_ATTACH_MAX_DATE_GAP_DAYS)
        verdict, _ = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH

    def test_gap_above_threshold_demotes_to_flag(self):
        signals = self._auto_signals(AUTO_ATTACH_MAX_DATE_GAP_DAYS + 1)
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_unknown_gap_does_not_block(self):
        signals = self._auto_signals(None)
        verdict, _ = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH


# ---------------------------------------------------------------------------
# Prod calibration cases (2026-08 pending-flags audit)
# ---------------------------------------------------------------------------


class TestProdCalibration:
    def test_case_a_anthem_overlap_is_nothing(self):
        """The emblematic '56%' false positive: anthem overlap, no title, 16 days.

        5/9 tracks shared but all high-df anthems (df 5-17) → weighted_overlap
        ≈ 0.28, title_sim ≈ 0.06, gap 16 d → confidence ≈ 0.10 → NOTHING.
        """
        a = {
            "normalized_title": "dj alpha live at warehouse berlin techno night",
            "played_date": date(2026, 3, 1),
            "identified_mtids": [1, 2, 3, 4, 5, 10, 11, 12, 13],
        }
        b = {
            "normalized_title": "dj bravo presents underground sessions vol 4 club madrid",
            "played_date": date(2026, 3, 17),
            "identified_mtids": [5, 3, 1, 2, 4, 20, 21, 22, 23, 24, 25, 26],
        }
        df = {1: 17, 2: 9, 3: 7, 4: 5, 5: 12}

        signals = compute_signals(a, b, shared_count=5, mtid_df=df)
        assert signals.overlap == pytest.approx(0.556, abs=1e-3)
        assert signals.title_sim == pytest.approx(0.0625)
        assert signals.date_gap_days == 16
        assert signals.weighted_overlap == pytest.approx(0.277, abs=1e-3)

        confidence = compute_confidence(signals)
        assert confidence < FLAG_CONFIDENCE_THRESHOLD
        verdict, _ = decide_verdict(signals, confidence, None, None)
        assert verdict == MatchVerdict.NOTHING

    def test_case_b_distant_dates_is_nothing(self):
        """overlap=0.64, title_sim=0.0, 271 days apart → NOTHING.

        Even an ungated weighted_overlap cannot pass the bar through the 0.3
        date factor: 0.55*0.64*0.3 ≈ 0.106.
        """
        signals = _signals(
            overlap=0.64, title_sim=0.0, weighted_overlap=0.64, date_gap_days=271
        )
        confidence = compute_confidence(signals)
        assert confidence < FLAG_CONFIDENCE_THRESHOLD
        verdict, _ = decide_verdict(signals, confidence, None, None)
        assert verdict == MatchVerdict.NOTHING

    def test_case_c_identical_title_flags(self):
        """title_sim=1.0, overlap=0.35, dates unknown → FLAG (title rule)."""
        signals = _signals(
            overlap=0.35, title_sim=1.0, weighted_overlap=0.20, date_gap_days=None
        )
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"

    def test_case_d_reupload_auto_attaches(self):
        """Real re-upload: overlap=0.85, title=0.6, order≈1, same day → AUTO_ATTACH."""
        signals = _signals(
            overlap=0.85, title_sim=0.6, weighted_overlap=0.78,
            first_track_match=True, order_corr=1.0,
            date_gap_days=0, date_match=True,
        )
        verdict, _ = _verdict(signals)
        assert verdict == MatchVerdict.AUTO_ATTACH

    def test_case_d_reupload_distant_date_flags(self):
        """Same signals but 40 days apart → date guard demotes to FLAG."""
        signals = _signals(
            overlap=0.85, title_sim=0.6, weighted_overlap=0.78,
            first_track_match=True, order_corr=1.0, date_gap_days=40,
        )
        verdict, flag_type = _verdict(signals)
        assert verdict == MatchVerdict.FLAG
        assert flag_type == "duplicate_candidate"
