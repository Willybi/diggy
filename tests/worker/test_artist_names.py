"""Tests for the pure artist-name hygiene helpers (workers/artist_names).

Four pure functions, no I/O — imported directly (the module has no celery/redis
dependency), same sys.path pattern as test_catalog_merge.py. The GUARD cases
(what must NOT change / must NOT match) are as important as the nominal ones:
they encode project invariant #4 (err toward separation).
"""
import os
import sys

# Make the workers package importable (same pattern as test_catalog_merge.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from workers.artist_names import (  # noqa: E402
    FAN_FLOOR,
    FAN_RATIO,
    SPACE_FOLD_MIN_LEN,
    dominant_by_fans,
    fold_base,
    is_placeholder_artist,
    looks_acronym,
    punct_fold_key,
    punct_sep_key,
    space_fold_key,
    strip_artist_noise,
)

# ── strip_artist_noise ──────────────────────────────────────────────────────


class TestStripArtistNoise:
    def test_pro_suffix_gema_stripped(self):
        assert strip_artist_noise("Ioannis Siopis (GEMA)") == "Ioannis Siopis"

    def test_pro_suffix_case_insensitive(self):
        assert strip_artist_noise("Ioannis Siopis (gema)") == "Ioannis Siopis"

    def test_pro_suffix_soundexchange_mixed_case(self):
        # Multi-word-looking society, matched case-insensitively as one token.
        assert strip_artist_noise("Some One (SoundExchange)") == "Some One"

    def test_every_whitelisted_society_is_stripped(self):
        for pro in [
            "GEMA", "ASCAP", "BMI", "SACEM", "PRS", "SABAM", "BUMA", "STIM",
            "SUISA", "SIAE", "SoundExchange", "PPL", "GVL",
        ]:
            assert strip_artist_noise(f"Artist X ({pro})") == "Artist X"

    def test_pro_suffix_only_at_end(self):
        # A PRO token that is NOT a trailing parenthesised suffix stays intact.
        assert strip_artist_noise("GEMA Collective") == "GEMA Collective"

    def test_pro_suffix_inner_whitespace_tolerated(self):
        assert strip_artist_noise("Ioannis Siopis ( GEMA )") == "Ioannis Siopis"

    def test_bullet_prefix_vinyl_stripped(self):
        assert strip_artist_noise("Vinyl • Harvey Mason") == "Harvey Mason"

    def test_bullet_prefix_bare_bullet(self):
        assert strip_artist_noise("• Harvey Mason") == "Harvey Mason"

    def test_bullet_prefix_middle_dot(self):
        assert strip_artist_noise("· Harvey Mason") == "Harvey Mason"

    def test_bullet_prefix_case_insensitive_vinyl(self):
        assert strip_artist_noise("VINYL • Harvey Mason") == "Harvey Mason"

    def test_prefix_and_suffix_both_stripped(self):
        assert strip_artist_noise("Vinyl • Harvey Mason (BMI)") == "Harvey Mason"

    # ── guards: these must NOT change ──

    def test_discogs_numeric_suffix_untouched(self):
        assert strip_artist_noise("Amy Cooper (4)") == "Amy Cooper (4)"

    def test_vinyl_face_marker_a1_untouched(self):
        assert strip_artist_noise("A1 Bassline") == "A1 Bassline"

    def test_vinyl_face_marker_m1_untouched(self):
        assert strip_artist_noise("M1 Matteo DiMarr") == "M1 Matteo DiMarr"

    def test_slash_separator_untouched(self):
        assert strip_artist_noise("AC/DC") == "AC/DC"

    def test_legit_group_untouched(self):
        assert strip_artist_noise("Tomeka Reid Quartet") == "Tomeka Reid Quartet"

    def test_non_pro_label_suffix_untouched(self):
        # "Sofa Beats" is a label, not a PRO → the suffix stays.
        assert strip_artist_noise("Kapchiz (Sofa Beats)") == "Kapchiz (Sofa Beats)"

    def test_non_ascii_name_untouched(self):
        assert strip_artist_noise("桜井　哲夫") == "桜井　哲夫"

    def test_no_noise_returns_identical_object(self):
        name = "Tomeka Reid Quartet"
        assert strip_artist_noise(name) is name

    def test_empty_string_passthrough(self):
        assert strip_artist_noise("") == ""

    def test_strip_that_would_empty_returns_original(self):
        # Only a bullet + nothing else → stripping would empty it → keep original.
        assert strip_artist_noise("•") == "•"

    def test_pro_only_would_empty_returns_original(self):
        assert strip_artist_noise("(GEMA)") == "(GEMA)"


# ── punct_fold_key ──────────────────────────────────────────────────────────


class TestPunctFoldKey:
    def test_st_germain_dot_equals_no_dot(self):
        assert punct_fold_key("St. Germain") == punct_fold_key("St Germain")

    def test_mr_oizo_dot_equals_no_dot(self):
        assert punct_fold_key("Mr. Oizo") == punct_fold_key("Mr Oizo")

    def test_nerd_trailing_dot_equivalence(self):
        assert punct_fold_key("N.E.R.D.") == punct_fold_key("N.E.R.D")

    def test_double_space_collapsed(self):
        assert punct_fold_key("Dark  Energy") == punct_fold_key("Dark Energy")

    def test_hyphen_removed_not_spaced(self):
        assert punct_fold_key("Cro-Magnon") == punct_fold_key("Cromagnon")

    def test_fred_again_trailing_dots(self):
        assert punct_fold_key("Fred again..") == punct_fold_key("Fred Again")

    def test_accent_folded(self):
        # NFKD + ASCII fold: accented spelling folds to the plain one (MATCH key,
        # NOT an identity key — identity keeps accents, see utils.normalize).
        assert punct_fold_key("Amélie Lens") == punct_fold_key("Amelie Lens")

    def test_ampersand_preserved(self):
        # "&" is a separator handled elsewhere → NOT stripped by the fold key.
        assert "&" in punct_fold_key("Earth, Wind & Fire")

    def test_pipe_preserved(self):
        assert "|" in punct_fold_key("A|B")

    def test_slash_preserved(self):
        assert "/" in punct_fold_key("AC/DC")

    def test_comma_removed(self):
        assert "," not in punct_fold_key("Earth, Wind & Fire")

    def test_apostrophe_removed(self):
        assert punct_fold_key("D'Angelo") == punct_fold_key("DAngelo")

    def test_fully_non_ascii_folds_to_empty(self):
        assert punct_fold_key("桜井　哲夫") == ""

    def test_none_input_folds_to_empty(self):
        assert punct_fold_key(None) == ""

    def test_result_is_lowercased(self):
        assert punct_fold_key("ST GERMAIN") == "st germain"

    def test_leading_trailing_whitespace_trimmed(self):
        assert punct_fold_key("  St Germain  ") == "st germain"


# ── punct_sep_key ───────────────────────────────────────────────────────────


class TestPunctSepKey:
    def test_rkelly_spaced_dot_equivalence(self):
        # The headline case punct_fold_key misses: dot-with-no-space vs
        # dot-with-space fold together only when punctuation becomes a space.
        assert punct_sep_key("R.Kelly") == punct_sep_key("R. Kelly")

    def test_rkelly_not_folded_by_drop_key(self):
        # Guard the regression this whole change fixes: the drop-key does NOT
        # equate the pair (that is why the second key exists).
        assert punct_fold_key("R.Kelly") != punct_fold_key("R. Kelly")

    def test_mr_oizo_collapsed_dot(self):
        assert punct_sep_key("Mr.Oizo") == punct_sep_key("Mr. Oizo")

    def test_ice_t_hyphen_vs_space(self):
        assert punct_sep_key("ICE T") == punct_sep_key("Ice-T")

    def test_jay_z_hyphen_vs_space(self):
        assert punct_sep_key("JAY-Z") == punct_sep_key("JAY Z")

    def test_h_man_hyphen_vs_space(self):
        assert punct_sep_key("H Man") == punct_sep_key("H-Man")

    def test_pure_space_insertion_not_folded(self):
        # The invariant #4 guard: a space inserted with NO punctuation must not
        # collapse two words. "Will I Am" != "William", "George S." != "Georges".
        assert punct_sep_key("Will I Am") != punct_sep_key("William")
        assert punct_sep_key("George S.") != punct_sep_key("Georges")

    def test_no_separator_compound_not_folded_here(self):
        # punct_sep_key deliberately does NOT fold "Cro-Magnon" == "Cromagnon"
        # (that is punct_fold_key's job); a caller matches on EITHER key.
        assert punct_sep_key("Cro-Magnon") != punct_sep_key("Cromagnon")
        assert punct_fold_key("Cro-Magnon") == punct_fold_key("Cromagnon")

    def test_st_germain_still_equivalent(self):
        assert punct_sep_key("St. Germain") == punct_sep_key("St Germain")

    def test_accent_folded(self):
        assert punct_sep_key("Amélie Lens") == punct_sep_key("Amelie Lens")

    def test_fully_non_ascii_folds_to_empty(self):
        assert punct_sep_key("桜井　哲夫") == ""

    def test_none_input_folds_to_empty(self):
        assert punct_sep_key(None) == ""

    def test_result_lowercased_and_trimmed(self):
        assert punct_sep_key("  R. KELLY  ") == "r kelly"


# ── is_placeholder_artist ────────────────────────────────────────────────────


class TestIsPlaceholderArtist:
    def test_various_artists(self):
        assert is_placeholder_artist("Various Artists")
        assert is_placeholder_artist("various artists")
        assert is_placeholder_artist("  Various   Artists  ")  # whitespace-tolerant

    def test_unknown_artist_and_va(self):
        assert is_placeholder_artist("Unknown Artist")
        assert is_placeholder_artist("VA")
        assert is_placeholder_artist("V/A")
        assert is_placeholder_artist("N/A")
        assert is_placeholder_artist("Compilation")

    def test_bare_various_and_unknown(self):
        assert is_placeholder_artist("Various")
        assert is_placeholder_artist("Unknown")

    def test_real_artists_containing_the_words_are_not_placeholders(self):
        # invariant #4: substring must NOT match — these are real artists.
        for real in [
            "Unknown Mortal Orchestra", "Origin Unknown", "Unknown T",
            "Unknown Mobile", "Daft Punk", "Various Production",
            "The Unknowns", "DJ Unknown",
        ]:
            assert not is_placeholder_artist(real), real

    def test_excluded_ambiguous_names(self):
        # deliberately OUT of the whitelist (a real name / a legit folk credit).
        assert not is_placeholder_artist("Na")
        assert not is_placeholder_artist("Traditional")

    def test_empty_and_none(self):
        assert not is_placeholder_artist("")
        assert not is_placeholder_artist(None)


# ── fold_base ───────────────────────────────────────────────────────────────


class TestFoldBase:
    def test_turkish_dotless_i_transliterated(self):
        # ı (U+0131) has no NFKD decomposition; ascii-ignore would DROP it,
        # turning "Altın" into "altn". The transliteration recovers the i.
        assert fold_base("Altın Gün") == fold_base("Altin Gün") == "altin gun"

    def test_smart_apostrophe_unified_with_straight(self):
        # ’ (U+2019) folds to the same key as ' (U+0027).
        assert fold_base("Angel’in Heavy Syrup") == fold_base("ANGEL'IN HEAVY SYRUP")

    def test_slashed_o_and_stroked_l(self):
        assert fold_base("Møme") == "mome"
        assert fold_base("Włodek") == "wlodek"

    def test_eszett_and_ligatures(self):
        assert fold_base("Straße") == "strasse"
        assert fold_base("Encÿclopædia") == "encyclopaedia"

    def test_em_dash_normalized(self):
        assert fold_base("Death—Grips") == fold_base("Death-Grips")

    def test_fully_non_latin_still_blank(self):
        # The load-bearing invariant #4 guard must survive transliteration.
        assert fold_base("桜井　哲夫") == ""
        assert fold_base("נוער שוליים") == ""

    def test_none_and_empty(self):
        assert fold_base(None) == ""
        assert fold_base("") == ""

    def test_plain_ascii_unchanged(self):
        assert fold_base("Bicep") == "bicep"


# ── space_fold_key ──────────────────────────────────────────────────────────


class TestSpaceFoldKey:
    def test_pure_space_insertion_folds(self):
        assert space_fold_key("AUX88") == space_fold_key("AUX 88") == "aux88"

    def test_letters_only_space_insertion_folds_too(self):
        # space_fold is deliberately aggressive (unlike punct_sep_key): it DOES
        # collapse a letter-only space insertion — which is why the caller gates
        # it hard and rejects ambiguity.
        assert space_fold_key("DJ Rum") == space_fold_key("Djrum") == "djrum"
        assert space_fold_key("Will I Am") == space_fold_key("William")

    def test_punctuation_also_removed(self):
        assert space_fold_key("R. Kelly") == space_fold_key("R.Kelly") == "rkelly"

    def test_min_len_constant_lets_aux88_through_but_not_coro(self):
        assert len(space_fold_key("AUX 88")) >= SPACE_FOLD_MIN_LEN
        assert len(space_fold_key("Co Ro")) < SPACE_FOLD_MIN_LEN

    def test_fully_non_latin_blank(self):
        assert space_fold_key("桜井　哲夫") == ""


# ── dominant_by_fans ────────────────────────────────────────────────────────


class TestDominantByFans:
    def test_dominant_when_far_ahead(self):
        assert dominant_by_fans(70000, 12) is True

    def test_not_dominant_when_comparable(self):
        assert dominant_by_fans(50000, 48000) is False

    def test_not_dominant_below_floor(self):
        # 10× of 10 is 100, but the absolute floor (1000) is not met.
        assert dominant_by_fans(500, 10) is False

    def test_dominant_at_floor(self):
        assert dominant_by_fans(2000, 10) is True

    def test_low_zero_dominant_at_floor(self):
        assert dominant_by_fans(FAN_FLOOR, 0) is True

    def test_low_zero_below_floor_not_dominant(self):
        assert dominant_by_fans(FAN_FLOOR - 1, 0) is False

    def test_exactly_at_floor_boundary_is_inclusive(self):
        assert dominant_by_fans(1000, 50) is True  # max(1000, 500) == 1000

    def test_ratio_boundary_inclusive(self):
        # high == ratio * low, both above the floor → inclusive True.
        assert dominant_by_fans(20000, 2000) is True

    def test_just_under_ratio_not_dominant(self):
        assert dominant_by_fans(19999, 2000) is False

    def test_custom_floor_and_ratio(self):
        # Custom floor 200 dominates the ratio term (20*5 == 100 < 200).
        assert dominant_by_fans(150, 5, floor=200, ratio=20) is False
        assert dominant_by_fans(200, 5, floor=200, ratio=20) is True
        # Custom ratio 20 dominates the floor (20*50 == 1000 > 200).
        assert dominant_by_fans(999, 50, floor=200, ratio=20) is False
        assert dominant_by_fans(1000, 50, floor=200, ratio=20) is True

    def test_module_constants_default(self):
        assert FAN_FLOOR == 1000
        assert FAN_RATIO == 10


# ── looks_acronym ───────────────────────────────────────────────────────────


class TestLooksAcronym:
    def test_dotted_initials_trailing_dot(self):
        assert looks_acronym("N.E.R.D.") is True

    def test_dotted_initials_no_trailing_dot(self):
        assert looks_acronym("L.I.L.Y") is True

    def test_dotted_initials_short(self):
        assert looks_acronym("D.S.L") is True

    def test_single_char_token_run(self):
        assert looks_acronym("A X L") is True

    def test_two_single_char_tokens_minimum(self):
        assert looks_acronym("A B") is True

    # ── guards: NOT acronyms ──

    def test_st_germain_not_acronym(self):
        assert looks_acronym("St. Germain") is False

    def test_mr_oizo_not_acronym(self):
        assert looks_acronym("Mr. Oizo") is False

    def test_group_name_not_acronym(self):
        assert looks_acronym("Tomeka Reid Quartet") is False

    def test_single_letter_alone_not_acronym(self):
        # One single-char token is not a run of two.
        assert looks_acronym("M") is False

    def test_isolated_single_letter_among_words_not_acronym(self):
        assert looks_acronym("John B Smooth") is False

    def test_empty_not_acronym(self):
        assert looks_acronym("") is False

    def test_none_not_acronym(self):
        assert looks_acronym(None) is False
