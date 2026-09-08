"""Tests for the pure set-title metadata helpers (workers/set_title_meta, C13.e).

Two pure functions, no I/O — imported directly (same sys.path pattern as
test_artist_names.py). The GUARD cases (ambiguous → None, out-of-range → None,
bare year → None, conflicting dates → None) matter as much as the nominal ones:
they encode project invariant #4 (a missing date beats a wrong one).
"""
import datetime
import os
import sys

# Make the workers package importable (same pattern as test_artist_names.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from workers.set_title_meta import (  # noqa: E402
    canonicalize_channel,
    extract_event_date,
    is_known_channel,
)

D = datetime.date


class TestExtractEventDateForms:
    def test_iso(self):
        assert extract_event_date("Boiler Room 2021-12-25 HD") == D(2021, 12, 25)

    def test_iso_slash_and_dot(self):
        assert extract_event_date("live 2021/12/25") == D(2021, 12, 25)
        assert extract_event_date("live 2021.12.25") == D(2021, 12, 25)

    def test_dmy_day_over_12_disambiguates(self):
        # 25 > 12 → 25 is the day, 12 the month (DD/MM order)
        assert extract_event_date("Set 25/12/2021") == D(2021, 12, 25)

    def test_mdy_second_over_12_disambiguates(self):
        # 25 > 12 in the SECOND slot → MM/DD order (US style)
        assert extract_event_date("Set 12/25/2021") == D(2021, 12, 25)

    def test_dmy_two_digit_year(self):
        assert extract_event_date("Set 25.12.21") == D(2021, 12, 25)

    def test_named_month_day_first(self):
        assert extract_event_date("Recorded 20th Feb 2032") == D(2032, 2, 20)
        assert extract_event_date("2 January 2020 mix") == D(2020, 1, 2)

    def test_named_month_month_first(self):
        assert extract_event_date("February 20, 2032 session") == D(2032, 2, 20)
        assert extract_event_date("Feb 20 2032") == D(2032, 2, 20)

    def test_glued_8_digits_ddmmyyyy(self):
        assert extract_event_date("mix 25122021 final") == D(2021, 12, 25)

    def test_glued_6_digits_ddmmyy(self):
        assert extract_event_date("mix 251221 final") == D(2021, 12, 25)

    def test_glued_yyyymmdd_falls_out_of_ddmm_order(self):
        # 20211225: day=20, month=21 → invalid month in the fixed DD-MM-YYYY order,
        # so it produces no candidate (abstain rather than mis-parse).
        assert extract_event_date("mix 20211225 x") is None


class TestExtractEventDateGuards:
    def test_ambiguous_both_le_12_returns_none(self):
        # 05 and 06 both ≤ 12 → D/M order unknown → abstain
        assert extract_event_date("Set 05/06/2021") is None

    def test_bare_year_returns_none(self):
        assert extract_event_date("Boiler Room Berlin 2021") is None

    def test_out_of_range_year_returns_none(self):
        assert extract_event_date("Set 25/12/1980") is None
        assert extract_event_date("Set 25/12/2099") is None

    def test_impossible_calendar_date_returns_none(self):
        assert extract_event_date("Set 31/02/2021") is None

    def test_no_date_returns_none(self):
        assert extract_event_date("Charlotte de Witte @ Awakenings") is None

    def test_none_and_empty_return_none(self):
        assert extract_event_date(None) is None
        assert extract_event_date("") is None

    def test_conflicting_dates_returns_none(self):
        # two DISTINCT parseable dates in the same title → abstain
        assert extract_event_date("2021-12-25 rerun of 2020-01-02") is None

    def test_same_date_twice_collapses(self):
        # the same date spelled two ways is not a conflict
        assert extract_event_date("2021-12-25 aka 25/12/2021") == D(2021, 12, 25)

    def test_two_digit_year_in_dead_band_returns_none(self):
        # yy=50 → neither 20xx (≤35) nor 19xx (≥90) → implausible → abstain
        assert extract_event_date("Set 25.12.50") is None


class TestCanonicalizeChannel:
    def test_gazetteer_exact(self):
        assert canonicalize_channel("Boiler Room") == "Boiler Room"

    def test_gazetteer_descriptive_suffix(self):
        assert (
            canonicalize_channel("Boiler Room: Streaming from Isolation")
            == "Boiler Room"
        )

    def test_gazetteer_containment_extra_tokens(self):
        assert canonicalize_channel("HÖR Berlin") == "HÖR"

    def test_gazetteer_alias(self):
        assert canonicalize_channel("NTS") == "NTS Radio"
        assert canonicalize_channel("NTS Radio") == "NTS Radio"

    def test_short_alias_is_whole_token_not_substring(self):
        # "RA" must NOT fire on "radio rudina" (it is not a whole token there);
        # Radio Rudina is its own gazetteer entry.
        assert canonicalize_channel("Radio Rudina") == "Radio Rudina"

    def test_short_alias_matches_as_whole_token(self):
        assert canonicalize_channel("RA") == "Resident Advisor"

    def test_records_suffix_stripped(self):
        # unknown channel, "Records" suffix dropped, passthrough of the cleaned raw
        assert canonicalize_channel("Some Label Records") == "Some Label"

    def test_passthrough_unknown(self):
        assert canonicalize_channel("Local Bedroom Radio") == "Local Bedroom Radio"

    def test_trim_passthrough(self):
        assert canonicalize_channel("  Cercle  ") == "Cercle"

    def test_none_and_blank_return_none(self):
        assert canonicalize_channel(None) is None
        assert canonicalize_channel("") is None
        assert canonicalize_channel("   ") is None
        assert canonicalize_channel(": only a suffix") is None


class TestIsKnownChannel:
    def test_known_media_channels(self):
        # Big media/label channels — hosts, never the DJ (C2c-3).
        assert is_known_channel("Boiler Room") is True
        assert is_known_channel("NTS Radio") is True
        assert is_known_channel("NTS") is True
        assert is_known_channel("Resident Advisor") is True
        assert is_known_channel("Cercle") is True

    def test_known_via_containment_and_suffix(self):
        # Same whole-token containment / suffix cleaning as canonicalize_channel.
        assert is_known_channel("HÖR Berlin") is True
        assert is_known_channel("Boiler Room: Streaming from Isolation") is True

    def test_short_alias_whole_token_only(self):
        # "RA" as a whole token → known; but "Radio Rudina" is its own entry, not RA.
        assert is_known_channel("RA") is True
        assert is_known_channel("Radio Rudina") is True  # its own gazetteer entry

    def test_unknown_channel_is_not_known(self):
        # An artist's own account / an out-of-gazetteer channel is still emitted.
        assert is_known_channel("Fred again..") is False
        assert is_known_channel("Some Unknown DJ") is False
        assert is_known_channel("Local Bedroom Radio") is False

    def test_none_and_blank(self):
        assert is_known_channel(None) is False
        assert is_known_channel("") is False
        assert is_known_channel("   ") is False

    def test_curated_media_denylist_channels(self):
        # Out-of-gazetteer media channels recognised via MEDIA_CHANNEL_KEYS (C2c-4).
        assert is_known_channel("NTS Latest") is True
        assert is_known_channel("Resident Advisor") is True
        assert is_known_channel("Refuge Worldwide") is True
        assert is_known_channel("Data Transmission Radio") is True

    def test_curated_denylist_does_not_flag_real_artist_channels(self):
        # A KEEP artist's own channel must stay unknown → still emitted downstream.
        assert is_known_channel("John Digweed") is False
        assert is_known_channel("Nicole Moudaber") is False
        assert is_known_channel("Andrei Mor") is False
        assert is_known_channel("BORIS") is False

    def test_denylist_channel_keys_disjoint_from_keep(self):
        # Anti-regression guard: no channel denylist key matches a real KEEP artist.
        from workers.artist_names import punct_fold_key
        from workers.set_artist_media_denylist import MEDIA_CHANNEL_KEYS

        for keep in ("John Digweed", "Nicole Moudaber", "Andrei Mor", "BORIS",
                     "UMEK", "Joris Voorn", "Christian Smith", "Slam"):
            assert punct_fold_key(keep) not in MEDIA_CHANNEL_KEYS
