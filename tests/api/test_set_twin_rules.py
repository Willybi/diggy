"""Twin rules (C14-dedup-yt L4) — real prod pairs against the pure decide_twin rules."""

from datetime import date

import pytest

from services.set_twin_rules import (
    COLLAB_WORDS,
    GENERIC_TITLE_WORDS,
    TwinInput,
    TwinVerdict,
    decide_twin,
    video_id_from_url,
)


def s(title, channel=None, minutes=60.0, **kwargs):
    """A TwinInput from a title, a channel and a duration in minutes."""
    duration_ms = None if minutes is None else int(minutes * 60_000)
    return TwinInput(title=title, channel=channel, duration_ms=duration_ms, **kwargs)


JUNE_21 = date(2025, 6, 21)


# ---------------------------------------------------------------------------
# video_id_from_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=TXFggcNJzMs",
        "https://www.youtube.com/watch?list=PL1&v=TXFggcNJzMs&t=30s",
        "https://m.youtube.com/watch?v=TXFggcNJzMs",
        "https://youtu.be/TXFggcNJzMs",
        "https://youtu.be/TXFggcNJzMs?si=abc",
        "https://www.youtube.com/live/TXFggcNJzMs",
        "https://www.youtube.com/live/TXFggcNJzMs?feature=share",
        "https://www.youtube.com/embed/TXFggcNJzMs",
        "youtu.be/TXFggcNJzMs",
    ],
)
def test_video_id_from_url(url):
    assert video_id_from_url(url) == "TXFggcNJzMs"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "https://trackid.net/audiostream/some-slug",
        "https://example.com/watch?v=TXFggcNJzMs",
        "https://soundcloud.com/live/TXFggcNJzMs",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/@channel",
        "https://youtu.be/",
    ],
)
def test_video_id_from_url_rejects_non_video(url):
    assert video_id_from_url(url) is None


# ---------------------------------------------------------------------------
# ATTACH — real pairs
# ---------------------------------------------------------------------------


def test_attach_same_video_id():
    decision = decide_twin(
        s("Some title", "A", 60, external_id="TXFggcNJzMs"),
        s(
            "Totally different",
            "B",
            120,
            source_url="https://www.youtube.com/watch?v=TXFggcNJzMs",
        ),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "video"


@pytest.mark.parametrize(
    "yt, other",
    [
        pytest.param(
            s(
                "Adam Beyer @ Space Miami, 21st June 2025",
                "Adam Beyer",
                243,
                event_date=JUNE_21,
            ),
            s(
                "Adam Beyer @Space Miami 21st June 2025",
                "adambeyer",
                243,
                event_date=JUNE_21,
            ),
            id="adam-beyer",
        ),
        pytest.param(
            s("Akvani - ROMAN [28.08.26]", "Mutant Radio Tbilisi", 108),
            s("Akvani - ROMAN [28.08.26]", "Mutant Radio", 108),
            id="akvani",
        ),
        pytest.param(
            s("James Blake @TheLotRadio 02-26-2026", "The Lot Radio", 54),
            s("James Blake - Beats By Me @ The Lot Radio 02-26-2026", "The Lot Radio", 56),
            id="james-blake",
        ),
        pytest.param(
            s(
                "Blech / (Mutant Radio x Retreat Radio @INTONAL) [25.04.26]",
                "Mutant Radio Tbilisi",
                54,
            ),
            s(
                "Blech [Retreat x Mutant Radio | Intonal] (25/04/26)",
                "Retreat Radio",
                54,
            ),
            id="blech",
        ),
        pytest.param(
            s("Red D @ Kiosk Radio 06.09.2026", "Kiosk Radio", 59),
            s("Red D @ Kiosk Radio 06.09.2026", "Kiosk Radio", 59),
            id="red-d",
        ),
        pytest.param(
            s(
                "juli chaos & pablo paresse╚═ Future Intel  ═╗ 18 09 2026",
                "Future Intel",
                129,
            ),
            s(
                "juli chaos & pablo parrese ╚═ Future Intel  ═╗ 18 09 2026",
                "Future Intel",
                128,
            ),
            id="juli-chaos-typo",
        ),
        pytest.param(
            s("N-JOY Residents: VIZE (14.04.2023)", "djsets4u", 60),
            s("djsets4u - N-JOY Resident - VIZE (14.04.2023)", "djsets4u", 60),
            id="n-joy-vize",
        ),
        pytest.param(
            s(
                "Ginte Presaite / (Mutant Radio x Retreat Radio @INTONAL) [24.04.26]",
                "Mutant Radio Tbilisi",
                54,
            ),
            s(
                "Gintė Preisaitė [Retreat x Mutant Radio | Intonal] (24/04/26)",
                "Retreat Radio",
                54,
            ),
            id="ginte-preisaite",
        ),
    ],
)
def test_attach_date_step(yt, other):
    decision = decide_twin(yt, other)
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "date"
    assert decision.signals["same_date"] is True


@pytest.mark.parametrize(
    "yt, other",
    [
        pytest.param(
            s("GLAU | Boiler Room: Rio de Janeiro", "Boiler Room", 61),
            s("GLAU | Boiler Room: Rio de Janeiro", "Boiler Room", 61),
            id="glau",
        ),
        pytest.param(
            s("Olga B. (DJ Set) | Rinse France", "Rinse France", 58),
            s("Olga B. - 07 Juin 2026", "Rinse France", 58),
            id="olga-b",
        ),
        pytest.param(
            s(
                "Glitterbox Radio Show 370: Hosted by Melvo Baptiste",
                "Glitterbox Recordings",
                60,
            ),
            s(
                "Glitterbox Radio Show 370: Hosted by Melvo Baptiste",
                "Glitterbox Recordings",
                60,
            ),
            id="glitterbox",
        ),
        pytest.param(
            s("FJAAK DJ set | Mixmag Cover Mix", "Mixmag", 62),
            s("The Cover Mix: FJAAK", "Mixmag", 62),
            id="fjaak",
        ),
        pytest.param(
            s("ZAVITNIK (DJ Set) | Rinse France", "Rinse France", 60),
            s("ZAVITNIK - 30 Juillet 2026", "Rinse France", 60),
            id="zavitnik",
        ),
        pytest.param(
            s("RONY (DJ Set) | Rinse France", "Rinse France", 60),
            s("RONY - 12 Mai 2026", "Rinse France", 60),
            id="rony",
        ),
        pytest.param(
            s("Errol | The Mix 006", "Mixmag", 60),
            s("The Mix 006: Errol", "Mixmag", 60),
            id="errol",
        ),
    ],
)
def test_attach_channel_step(yt, other):
    decision = decide_twin(yt, other)
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"
    assert decision.signals["same_channel"] is True


# ---------------------------------------------------------------------------
# REVIEW — real pairs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "yt, other",
    [
        pytest.param(
            s("Vitaline invite Camporeale (DJ Set) | Rinse France", "Rinse France", 58),
            s("Vitaline", "Rinse France", 57),
            id="vitaline",
        ),
        pytest.param(
            s("Kora Core (DJ Set) | Rinse France", "Rinse France", 55),
            s("Queer Cult Takeover : Kora Core - 30 JUIN 2026", "Rinse France", 55),
            id="kora-core",
        ),
        pytest.param(
            s("RONI (Dj Set) | Rinse France", "Rinse France", 60),
            s("RONI B2B Lisa More (DJ Set) | Rinse France", "Rinse France", 60 * 1.001),
            id="roni-b2b",
        ),
        pytest.param(
            s(
                "Chloé Caillet | Mixmag Cover Mix | House, Balearic, Italo",
                "Mixmag",
                60,
            ),
            s("In Session: Chloé Caillet", "Mixmag", 60 * 1.006),
            id="chloe-caillet",
        ),
        pytest.param(
            s("Mona Yim B2B Bonobo | Rinse FM", "Rinse FM", 60),
            s("Mona Yim - 24th September 2026", "Rinse FM", 60 * 1.007),
            id="mona-yim-b2b",
        ),
        pytest.param(
            s("Bambi invite su:zy (DJ Set) | Rinse France", "Rinse France", 60),
            s(
                "Bambi présente Odd Seeds ⎯ 001 avec su:zy - 07 Septembre 2026",
                "Rinse France",
                60,
            ),
            id="bambi-suzy",
        ),
    ],
)
def test_review_channel_step(yt, other):
    decision = decide_twin(yt, other)
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"


def test_review_same_date_each_title_has_own_artist():
    decision = decide_twin(
        s(
            "UNSERDING ClubDing: Florian Schumacher & GoldFish (31.07.2023)",
            "djsets4u",
            60,
        ),
        s(
            "UNSERDING ClubDing - Florian Schumacher & Wave Wave (31.07.2023)",
            "SaviourGermany",
            60,
        ),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "date"


# ---------------------------------------------------------------------------
# NOTHING — real pairs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "yt, other",
    [
        pytest.param(
            s("Brent Honey | Radio Rudina", "Radio Rudina", 71),
            s("Brent Honey | Radio Rudina", "Radio Rudina", 74),
            id="brent-honey-duration-gap",
        ),
        pytest.param(
            s("Komatsu ╚═ Future Intel  x WEST ═╗ 06 08 2026", "Future Intel", 62),
            s("Cvalda ╚═ Future Intel  x WEST ═╗ 06 08 2026", "Future Intel", 62),
            id="komatsu-cvalda-same-date",
        ),
        pytest.param(
            s(
                "Glitterbox Radio Show 370: Hosted by Melvo Baptiste",
                "Glitterbox Recordings",
                60,
            ),
            s(
                "Glitterbox Radio Show 371: Hosted by Melvo Baptiste",
                "Glitterbox Recordings",
                60,
            ),
            id="glitterbox-episodes",
        ),
        pytest.param(
            s(
                "SESH with MCR-T 24H DJ Set | Twitch Livestream (PART 3)",
                "MCR-T",
                368,
                part_number=3,
            ),
            s(
                "SESH with MCR-T 24H DJ Set | Twitch Livestream (PART 2)",
                "MCR-T",
                360,
                part_number=2,
            ),
            id="sesh-parts",
        ),
        pytest.param(
            s("Kurilo | themuddshow", "themuddshow", 59),
            s("Kurilo | Numéro Netherlands", "Numéro Netherlands", 62),
            id="kurilo",
        ),
        pytest.param(
            s("Yazzus | themuddshow x Mala Junta", "themuddshow", 61),
            s("Mala Junta w/ Yazzus 170423", "NTS Monday", 60),
            id="yazzus",
        ),
        pytest.param(
            s("Emanuel | themuddshow x by jello x Threads & Thrills", "themuddshow", 63),
            s(
                "Maja Korpi | themuddshow x by jello x Threads & Thrills",
                "themuddshow",
                64,
            ),
            id="emanuel-maja",
        ),
        pytest.param(
            s("Red D @ Kiosk Radio 06.09.2026", "Kiosk Radio", 59),
            s("Red D @ Kiosk Radio 13.09.2026", "Kiosk Radio", 59),
            id="same-title-different-dates",
        ),
        pytest.param(
            s("ENERGY Extravadance: Meduza (28.07.2023)", "djsets4u", 59),
            s("ENERGY Extravadance: Dominik Koislmeyer (28.07.2023)", "djsets4u", 60),
            id="energy-different-artists",
        ),
        pytest.param(
            s(
                "Boeuf & Brocoli @ Nuits sonores 2026 (DJ set) | Rinse France",
                "Rinse France",
                86,
            ),
            s(
                "Boeuf & Brocoli - OffTheWall & Rhahis : Carhartt WIP Radio",
                "Rinse France",
                86 * 1.002,
            ),
            id="boeuf-brocoli",
        ),
        pytest.param(
            s("Gabbie Mobili 007 with Obre 30.01.26", "Fritto FM", 60),
            s("Gabbie Mobili 008 with Obre 30.01.26", "Fritto FM", 60),
            id="gabbie-mobili-episodes",
        ),
        pytest.param(
            s("N JOY Residents: Jerome (11.08.2023)", "djsets4u", 60),
            s("N-JOY Residents: Martin Solveig (11.08.2023)", "djsets4u", 60),
            id="n-joy-different-artists",
        ),
    ],
)
def test_nothing_pairs(yt, other):
    decision = decide_twin(yt, other)
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.step == ""


def test_nothing_when_other_is_unreliable_even_on_same_video():
    decision = decide_twin(
        s("Some title", external_id="TXFggcNJzMs"),
        s(
            "Some title",
            source_url="https://www.youtube.com/watch?v=TXFggcNJzMs",
            unreliable=True,
        ),
    )
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.reason == "other set is unreliable"


# ---------------------------------------------------------------------------
# Rule details
# ---------------------------------------------------------------------------


def test_missing_ids_never_read_as_same_video():
    decision = decide_twin(s("A title", "A"), s("Another title", "B"))
    assert decision.step != "video"


@pytest.mark.parametrize(
    "minutes_yt, minutes_other",
    [(None, 60), (60, None), (0, 60)],
)
def test_nothing_on_missing_duration(minutes_yt, minutes_other):
    decision = decide_twin(
        s("Red D @ Kiosk Radio 06.09.2026", "Kiosk Radio", minutes_yt),
        s("Red D @ Kiosk Radio 06.09.2026", "Kiosk Radio", minutes_other),
    )
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.reason == "missing duration"
    assert decision.signals["dd"] is None


def test_same_video_wins_over_missing_duration():
    decision = decide_twin(
        s("A", minutes=None, external_id="TXFggcNJzMs"),
        s("B", minutes=None, source_url="https://youtu.be/TXFggcNJzMs"),
    )
    assert decision.verdict == TwinVerdict.ATTACH


def test_nothing_on_different_event_dates():
    decision = decide_twin(
        s("Olga B.", "Rinse France", event_date=date(2026, 6, 7)),
        s("Olga B.", "Rinse France", event_date=date(2026, 6, 8)),
    )
    assert decision.reason == "different event dates"


def test_same_event_date_counts_as_same_date():
    decision = decide_twin(
        s("Olga B. Paris", "A", event_date=date(2026, 6, 7)),
        s("Olga B. Paris", "B", event_date=date(2026, 6, 7)),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "date"


def test_title_dates_ignore_day_month_order():
    decision = decide_twin(
        s("Red D Kiosk 09.24.2022", "A"),
        s("Red D Kiosk 24/09/2022", "B"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "date"


def test_spaced_date_equals_dotted_date():
    decision = decide_twin(
        s("Red D Kiosk 31 07 2026", "A"),
        s("Red D Kiosk 31.07.2026", "B"),
    )
    assert decision.signals["same_date"] is True
    assert decision.verdict == TwinVerdict.ATTACH


def test_spaced_dates_can_separate():
    decision = decide_twin(
        s("Komatsu ╚═ Future Intel ═╗ 06 08 2026", "Future Intel"),
        s("Komatsu ╚═ Future Intel ═╗ 13 08 2026", "Future Intel"),
    )
    assert decision.reason == "different title dates"


def test_named_month_dates_can_separate():
    """Same artist on the same channel, a week apart: two performances."""
    decision = decide_twin(
        s("Olga B. - 07 Juin 2026", "Rinse France"),
        s("Olga B. - 14 Juin 2026", "Rinse France"),
    )
    assert decision.reason == "different title dates"


def test_named_month_date_equals_numeric_date():
    decision = decide_twin(
        s("Olga B. Paris - 07 Juin 2026", "A"),
        s("Olga B. Paris 07.06.2026", "B"),
    )
    assert decision.signals["same_date"] is True


def test_date_number_is_not_an_episode_number():
    """Once dates are gone, a trailing day must not read as an episode number."""
    decision = decide_twin(
        s("Flow 542 2024-02-25", "A"),
        s("Flow 542", "A"),
    )
    assert decision.reason != "different episode numbers"
    assert decision.verdict == TwinVerdict.ATTACH


def test_year_is_not_an_episode_number_but_still_separates_editions():
    decision = decide_twin(
        s("Awakenings 2024", "Awakenings"),
        s("Awakenings 2025", "Awakenings"),
    )
    assert decision.reason != "different episode numbers"
    assert decision.verdict == TwinVerdict.NOTHING


def test_month_name_outside_a_date_stays_a_word():
    """"May" is the artist here: dropping it would merge two different DJs."""
    decision = decide_twin(
        s("Derrick May | Boiler Room", "Boiler Room"),
        s("Derrick Carter | Boiler Room", "Boiler Room"),
    )
    assert decision.verdict == TwinVerdict.NOTHING


def test_glued_glyphs_fold_away():
    decision = decide_twin(
        s("Frida╚═ Future Intel  ═╗ 18 09 2026", "Future Intel"),
        s("Frida ╚═ Future Intel  ═╗ 18 09 2026", "Future Intel"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.signals["cont"] == 1.0


def test_non_latin_names_stay_distinct():
    """search_fold blanks both names: they must not compare as one title."""
    decision = decide_twin(
        s("Иван x Boris Paris Club Night", "Radio"),
        s("Пётр x Boris Paris Club Night", "Radio"),
    )
    assert decision.signals["both_own"] is True
    assert decision.verdict == TwinVerdict.NOTHING


def test_title_reduced_to_channel_and_generic_words_is_no_evidence():
    decision = decide_twin(
        s("Boiler Room (DJ Set)", "Boiler Room"),
        s("Boiler Room Live", "Boiler Room"),
    )
    assert decision.signals["cont"] == 0.0
    assert decision.verdict == TwinVerdict.NOTHING


def test_same_date_each_title_has_own_words_goes_to_review():
    decision = decide_twin(
        s("Alpha Beta Gamma Delta Epsilon 12.03.2024", "A"),
        s(
            "Alpha Beta Gamma Delta Omega with a much longer tail here 12.03.2024",
            "B",
        ),
    )
    assert decision.signals["cont"] == 0.8
    assert decision.signals["both_own"] is True
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "date"


def test_same_date_each_title_has_own_words_near_identical_attaches():
    decision = decide_twin(
        s("Alpha Beta Gamma Delta Epsilonn 12.03.2024", "A"),
        s("Alpha Beta Gamma Delta Epsilon 12.03.2024", "B"),
    )
    assert decision.signals["both_own"] is True
    assert decision.signals["lev"] >= 0.90
    assert decision.verdict == TwinVerdict.ATTACH


def test_differing_number_cannot_use_the_levenshtein():
    """A near-identical title with another number stays a human decision."""
    decision = decide_twin(
        s("Alpha Beta 007 Gamma Delta 12.03.2024", "A"),
        s("Alpha Beta 008 Gamma Delta 12.03.2024", "A"),
    )
    assert decision.signals["lev"] >= 0.90
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "date"


def test_levenshtein_ignores_channel_names_and_word_order():
    decision = decide_twin(
        s("Boiler Room Berlin: Alpha Beta Gammaa 12.03.2024", "Boiler Room"),
        s("Gamma Beta Alpha | Boiler Room Berlin 12.03.2024", "Boiler Room"),
    )
    assert decision.signals["lev"] >= 0.90
    assert decision.verdict == TwinVerdict.ATTACH


def test_titles_without_significant_words_never_match_on_levenshtein():
    """Two empty word sets would score 1.0 on no evidence at all."""
    decision = decide_twin(
        s("Boiler Room (DJ Set) 12.03.2024", "Boiler Room"),
        s("Boiler Room Live 12.03.2024", "Boiler Room"),
    )
    assert "lev" not in decision.signals
    assert decision.verdict == TwinVerdict.NOTHING


def test_one_word_title_attaches_on_near_exact_duration():
    decision = decide_twin(
        s("Vitaline", "Rinse France", 100),
        s("Vitaline (DJ Set)", "Rinse France", 100.4),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"


def test_one_word_title_with_close_duration_goes_to_review():
    decision = decide_twin(
        s("Vitaline", "Rinse France", 100),
        s("Vitaline (DJ Set)", "Rinse France", 101),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"


def test_short_title_with_extra_words_goes_to_review_despite_exact_duration():
    decision = decide_twin(
        s("Vitaline", "Rinse France", 100),
        s("Vitaline invite Camporeale", "Rinse France", 100),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"


def test_three_word_title_with_extra_words_attaches():
    decision = decide_twin(
        s("Alpha Beta Gamma", "Rinse France"),
        s("Alpha Beta Gamma Delta", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"


@pytest.mark.parametrize("word", sorted(COLLAB_WORDS))
def test_collab_word_in_one_title_only_goes_to_review(word):
    decision = decide_twin(
        s("Alpha Beta Gamma", "Rinse France"),
        s(f"Alpha Beta Gamma {word} Delta", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"
    assert word in decision.reason


def test_collab_word_in_both_titles_is_not_a_blocker():
    decision = decide_twin(
        s("Alpha B2B Beta Gamma", "Rinse France"),
        s("Alpha B2B Beta Gamma Delta", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.ATTACH


def test_collab_words_are_not_generic():
    assert COLLAB_WORDS.isdisjoint(GENERIC_TITLE_WORDS)


# ---------------------------------------------------------------------------
# Publication window (recurring shows)
# ---------------------------------------------------------------------------

OTTO_LIVE = "Otto Diva (Live) | Rinse France"
OTTO_JUNE = s("Otto Diva - 13 Juin 2026", "Rinse France")


def otto(upload_date):
    return s(OTTO_LIVE, "Rinse France", upload_date=upload_date)


def test_window_upload_on_event_day_attaches():
    decision = decide_twin(otto(date(2026, 6, 13)), OTTO_JUNE)
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"
    assert decision.signals["upload_delta_days"] == 0


@pytest.mark.parametrize(
    "yt, other",
    [
        pytest.param(
            otto(date(2026, 6, 13)),
            s("Otto Diva - 20 Septembre 2025", "Rinse France"),
            id="otto-diva",
        ),
        pytest.param(
            s(
                "The Mel V Show (DJ Set) | Rinse France",
                "Rinse France",
                upload_date=date(2026, 10, 27),
            ),
            s("The Mel V Show - 17 Juin 2025", "Rinse France"),
            id="mel-v-show",
        ),
    ],
)
def test_window_upload_far_after_event_is_nothing(yt, other):
    decision = decide_twin(yt, other)
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.step == ""
    assert decision.reason == "uploaded long after the event"


def test_window_named_month_date_still_reads_both_ways():
    """"04 September" also reads 9 April, 61 days before the upload: that reading wins.

    On the real date (4 September, 87 days after the upload) the pair would be NOTHING.
    """
    decision = decide_twin(
        s("Rinse HQ081 | Kassian", "Rinse FM", 60, upload_date=date(2024, 6, 9)),
        s("Kassian - 04 September 2024", "Rinse FM", 60 * 1.01),
    )
    assert decision.signals["upload_delta_days"] == 61
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"
    assert decision.reason == "uploaded long after the event"


def test_window_upload_before_event_is_nothing():
    decision = decide_twin(
        s("Zenker Brothers | Rinse FM", "Rinse FM", upload_date=date(2025, 10, 8)),
        s("Zenker Brothers - 04 May 2026", "Rinse FM"),
    )
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.step == ""
    assert decision.reason == "uploaded before the event"


def test_window_upload_shortly_after_event_attaches():
    decision = decide_twin(
        s(
            "Coffintexts invite Marie Nyx (DJ Set) | Rinse France",
            "Rinse France",
            upload_date=date(2026, 6, 29),
        ),
        s("Coffintexts invite Marie Nyx - 27 Juin 2026", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"
    assert decision.signals["upload_delta_days"] == 2


@pytest.mark.parametrize(
    "upload_date, delta, verdict",
    [
        (date(2026, 6, 6), -7, TwinVerdict.ATTACH),
        (date(2026, 6, 5), -8, TwinVerdict.NOTHING),
        (date(2026, 7, 13), 30, TwinVerdict.ATTACH),
        (date(2026, 7, 14), 31, TwinVerdict.REVIEW),
        (date(2026, 9, 11), 90, TwinVerdict.REVIEW),
        (date(2026, 9, 12), 91, TwinVerdict.NOTHING),
    ],
)
def test_window_bounds(upload_date, delta, verdict):
    decision = decide_twin(otto(upload_date), OTTO_JUNE)
    assert decision.signals["upload_delta_days"] == delta
    assert decision.verdict == verdict
    if delta > 30:
        assert decision.reason == "uploaded long after the event"


@pytest.mark.parametrize(
    "yt, other",
    [
        pytest.param(
            otto(date(2020, 1, 1)),
            s("Otto Diva", "Rinse France"),
            id="other-undated",
        ),
        pytest.param(otto(None), OTTO_JUNE, id="no-upload-date"),
        pytest.param(
            s(
                "Otto Diva 13.06.2026",
                "Rinse France",
                upload_date=date(2020, 1, 1),
            ),
            s("Otto Diva", "Rinse France", event_date=date(2020, 6, 1)),
            id="yt-title-date",
        ),
        pytest.param(
            s(
                OTTO_LIVE,
                "Rinse France",
                event_date=date(2026, 6, 13),
                upload_date=date(2020, 1, 1),
            ),
            OTTO_JUNE,
            id="yt-event-date",
        ),
    ],
)
def test_window_has_no_effect(yt, other):
    decision = decide_twin(yt, other)
    assert "upload_delta_days" not in decision.signals
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"


def test_window_reads_other_event_date():
    decision = decide_twin(
        otto(date(2026, 6, 13)),
        s("Otto Diva", "Rinse France", event_date=date(2026, 6, 13)),
    )
    assert decision.signals["upload_delta_days"] == 0


def test_window_never_reads_other_upload_date():
    decision = decide_twin(
        otto(date(2026, 6, 13)),
        s("Otto Diva", "Rinse France", upload_date=date(2020, 1, 1)),
    )
    assert "upload_delta_days" not in decision.signals


@pytest.mark.parametrize(
    "upload_date, delta",
    [
        # 03.04.2026 reads 3 April or 4 March: the closest reading wins.
        (date(2026, 4, 5), 2),
        (date(2026, 3, 1), -3),
    ],
)
def test_window_ambiguous_date_keeps_the_closest_reading(upload_date, delta):
    decision = decide_twin(
        otto(upload_date),
        s("Otto Diva 03.04.2026", "Rinse France"),
    )
    assert decision.signals["upload_delta_days"] == delta
    assert decision.verdict == TwinVerdict.ATTACH


def test_window_same_day_and_month_is_a_single_date():
    decision = decide_twin(
        otto(date(2026, 7, 9)),
        s("Otto Diva 07.07.2026", "Rinse France"),
    )
    assert decision.signals["upload_delta_days"] == 2


def test_window_ignores_the_invalid_reading():
    decision = decide_twin(
        otto(date(2026, 8, 1)),
        s("Otto Diva 31.07.2026", "Rinse France"),
    )
    assert decision.signals["upload_delta_days"] == 1


# ---------------------------------------------------------------------------
# Digit word in one title only
# ---------------------------------------------------------------------------


def test_digit_word_in_one_title_only_goes_to_review():
    decision = decide_twin(
        s(
            "Glitterbox Radio Show Hosted by Yasmin 11.03.26",
            "Glitterbox Recordings",
            upload_date=date(2026, 2, 12),
        ),
        s("Glitterbox Radio Show 458: Hosted by Yasmin", "Glitterbox Recordings"),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"
    assert "458" in decision.reason


def test_glitterbox_upload_before_event_is_nothing():
    """Uploaded 27 days before the closest reading of the date (11 March)."""
    decision = decide_twin(
        s(
            "Glitterbox Radio Show 458: Hosted by Yasmin",
            "Glitterbox Recordings",
            upload_date=date(2026, 2, 12),
        ),
        s(
            "Glitterbox Radio Show Hosted by Yasmin 11.03.26",
            "Glitterbox Recordings",
        ),
    )
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.step == ""
    assert decision.reason == "uploaded before the event"


def test_glitterbox_upload_in_window_goes_to_review_on_the_digit_word():
    decision = decide_twin(
        s(
            "Glitterbox Radio Show 465: Hosted by Yasmin",
            "Glitterbox Recordings",
            upload_date=date(2026, 4, 8),
        ),
        s(
            "Glitterbox Radio Show Hosted by Yasmin 11.03.26",
            "Glitterbox Recordings",
        ),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"
    assert "465" in decision.reason


def test_collab_word_reason_wins_over_digit_word_reason():
    decision = decide_twin(
        s("Alpha Beta Gamma", "Rinse France"),
        s("Alpha Beta Gamma B2B Delta 007", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "channel"
    assert decision.reason.startswith("collaboration marker")


def test_same_digit_word_on_both_sides_attaches():
    decision = decide_twin(
        s("Glitterbox Radio Show 472: Hosted by L3ni", "Glitterbox Recordings"),
        s("Glitterbox Radio Show 472: Hosted by L3ni", "Glitterbox Recordings"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "channel"


# ---------------------------------------------------------------------------
# Date step: collaboration marker, own words
# ---------------------------------------------------------------------------


def test_date_step_collab_word_in_one_title_goes_to_review():
    decision = decide_twin(
        s("RONI 12.03.2024", "Rinse France"),
        s("RONI B2B Lisa More 12.03.2024", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "date"
    assert "b2b" in decision.reason


def test_date_step_collab_word_without_containment_is_nothing():
    """Two different artists the same day: a lone B2B is no reason to ask a human."""
    decision = decide_twin(
        s("Peach b2b Shanti Celeste 12.03.2024", "Channel A"),
        s("Marcel Dettmann 12.03.2024", "Channel B"),
    )
    assert decision.signals["cont"] == 0.0
    assert decision.verdict == TwinVerdict.NOTHING
    assert decision.step == ""


def test_channel_step_collab_word_reason():
    decision = decide_twin(
        s("RONI (Dj Set) | Rinse France", "Rinse France", 60),
        s("RONI B2B Lisa More (DJ Set) | Rinse France", "Rinse France", 60 * 1.001),
    )
    assert decision.step == "channel"
    assert decision.reason.startswith("collaboration marker")


def test_date_step_short_title_guard_is_not_applied():
    decision = decide_twin(
        s("Kora Core 30.06.2026", "Rinse France"),
        s("Queer Cult Takeover Kora Core 30.06.2026", "Rinse France"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "date"


def test_date_step_collab_word_in_both_titles_attaches():
    decision = decide_twin(
        s("Peach b2b Shanti Celeste @TheLotRadio 10-19-2026", "The Lot Radio"),
        s("Peach b2b Shanti Celeste @ The Lot Radio 10-19-2026", "The Lot Radio"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "date"


def test_levenshtein_refuses_a_short_own_word():
    decision = decide_twin(
        s("Ana Bob West Club Night Paris 12.03.2024", "Radio"),
        s("Aya Bob West Club Night Paris 12.03.2024", "Radio"),
    )
    assert decision.signals["lev"] >= 0.90
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "date"


def test_levenshtein_refusal_below_containment_is_nothing():
    decision = decide_twin(
        s("Kim Warehouse Project Amsterdam 12.03.2024", "Radio"),
        s("Kai Warehouse Project Amsterdam 12.03.2024", "Radio"),
    )
    assert decision.signals["lev"] >= 0.90
    assert decision.verdict == TwinVerdict.NOTHING


def test_levenshtein_accepts_a_misspelled_long_own_word():
    decision = decide_twin(
        s("Marc Dupont Warehouse Project Paris 12.03.2024", "Radio"),
        s("Marc Dupond Warehouse Project Paris 12.03.2024", "Radio"),
    )
    assert decision.verdict == TwinVerdict.ATTACH
    assert decision.step == "date"


def test_levenshtein_refuses_own_words_that_do_not_resemble():
    """Long enough, but the words differ: the title-wide ratio must not carry them."""
    decision = decide_twin(
        s("Warehouse Project Amsterdam Festival Closing Marco 12.03.2024", "Radio"),
        s("Warehouse Project Amsterdam Festival Closing Polly 12.03.2024", "Radio"),
    )
    assert decision.verdict == TwinVerdict.REVIEW
    assert decision.step == "date"


def test_channel_canonical_counts_as_same_channel():
    decision = decide_twin(
        s("GLAU Rio", "Boiler Room: Rio", channel_canonical="Boiler Room"),
        s("GLAU Rio", "Boiler Room Brasil", channel_canonical="Boiler Room"),
    )
    assert decision.signals["same_channel"] is True
    assert decision.verdict == TwinVerdict.ATTACH


def test_empty_channels_are_not_the_same_channel():
    decision = decide_twin(s("GLAU Rio", None), s("GLAU Rio", ""))
    assert decision.signals["same_channel"] is False
    assert decision.verdict == TwinVerdict.NOTHING


@pytest.mark.parametrize(
    "yt, other",
    [
        (s("Red D", "A"), s("Red D", "A")),
        (s("Red D", "A", None), s("Red D", "A")),
        (s("X", external_id="abc"), s("Y", source_url="https://youtu.be/abc")),
        (s("X"), s("Y", unreliable=True)),
    ],
)
def test_signals_always_carry_the_core_keys(yt, other):
    signals = decide_twin(yt, other).signals
    assert {"cont", "dd", "both_own", "same_date", "same_channel"} <= signals.keys()


def test_generic_words_are_in_folded_form():
    assert "presente" in GENERIC_TITLE_WORDS
    assert "présente" not in GENERIC_TITLE_WORDS
