"""
Lot 1 — extra artist-string separators + anti-false-positive guards.

Exercises the REAL dispatch code: sync_artists Phase A (classify_artist_string)
and Phase C (split_artist_parts) delegate their separator logic to the two
module-level pure helpers, which MUST stay mirror images of each other. Removing
a branch/guard from either helper makes a test here fail (no shadow reimpl).

The module is loaded exactly as in test_tasks_pipe_separator.py — mocking the
celery / redis / curl_cffi imports that fire at module load, because
workers.tasks.artists pulls those in transitively.
"""
import importlib.util
import os
import sys
from unittest.mock import MagicMock

# Mock celery ecosystem before any worker imports (celery is not installed locally)
for _mod in ["celery", "celery.schedules", "celery.signals", "celery._state"]:
    sys.modules.setdefault(_mod, MagicMock())

_SERVER = os.path.join(os.path.dirname(__file__), "../../server")
_API = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in [_SERVER, _API]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# redis / curl_cffi are imported at async_http module load but not installed in
# the test env. Mock them for the artists.py import, then restore.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

_artists_path = os.path.join(_SERVER, "workers", "tasks", "artists.py")
_spec = importlib.util.spec_from_file_location("workers.tasks.artists", _artists_path)
_artists_mod = importlib.util.module_from_spec(_spec)
sys.modules["workers.tasks.artists"] = _artists_mod
_spec.loader.exec_module(_artists_mod)

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl
del _saved_curl

# The real dispatch helpers + guards under test.
classify_artist_string = _artists_mod.classify_artist_string
split_artist_parts = _artists_mod.split_artist_parts
_is_stylized_name = _artists_mod._is_stylized_name
_article_after_separator = _artists_mod._article_after_separator

from utils import normalize  # noqa: E402  (server/api is on sys.path above)


class TestPresents:
    """'presents' family — a LOCAL split (no Deezer), every token primary."""

    def test_presents_splits_locally(self):
        assert classify_artist_string(
            "Larry Heard presents Mr. White", known_norms=set()
        ) == ("split", ["Larry Heard", "Mr. White"])

    def test_pres_dot_splits_locally(self):
        assert classify_artist_string(
            "Antoine Clamaran pres. D-Plac", known_norms=set()
        ) == ("split", ["Antoine Clamaran", "D-Plac"])

    def test_bare_pres_splits_locally(self):
        # "pres" without a trailing dot (pres\.? — dot optional).
        assert classify_artist_string("A pres B", known_norms=set()) == (
            "split",
            ["A", "B"],
        )

    def test_presente_accent_splits_locally(self):
        assert classify_artist_string("DJ Foo présente Bar", known_norms=set()) == (
            "split",
            ["DJ Foo", "Bar"],
        )

    def test_presents_is_case_insensitive(self):
        assert classify_artist_string("Foo PRESENTS Bar", known_norms=set()) == (
            "split",
            ["Foo", "Bar"],
        )

    def test_presents_never_defers_to_deezer(self):
        # Even with no known token, presents resolves locally (unlike ampersand).
        status = classify_artist_string(
            "Larry Heard presents Mr. White", known_norms=set()
        )[0]
        assert status == "split"

    def test_presents_parts_all_primary(self):
        assert split_artist_parts("Larry Heard presents Mr. White") == [
            ("Larry Heard", "primary", 0),
            ("Mr. White", "primary", 1),
        ]

    def test_pres_dot_parts_all_primary(self):
        assert split_artist_parts("Antoine Clamaran pres. D-Plac") == [
            ("Antoine Clamaran", "primary", 0),
            ("D-Plac", "primary", 1),
        ]

    def test_presenter_word_is_not_a_separator(self):
        # "Presence"/"Presenter" must not trip the presents regex (\s+-bounded).
        assert classify_artist_string("Presence", known_norms=set()) == (
            "single",
            ["Presence"],
        )


class TestAmpersandFamilySeparators:
    """" + " / " x " / " and " / " y " / " e " all route through the ampersand rule."""

    def test_plus_defers_to_deezer(self):
        assert classify_artist_string("Sultan + Shepard", known_norms=set()) == (
            "needs_deezer",
            ["Sultan", "Shepard"],
            "ampersand",
        )

    def test_x_defers_to_deezer(self):
        assert classify_artist_string(
            "Nicky Romero x David Guetta", known_norms=set()
        ) == ("needs_deezer", ["Nicky Romero", "David Guetta"], "ampersand")

    def test_x_is_case_insensitive(self):
        assert classify_artist_string("Foo X Bar", known_norms=set()) == (
            "needs_deezer",
            ["Foo", "Bar"],
            "ampersand",
        )

    def test_and_defers_to_deezer(self):
        assert classify_artist_string(
            "21 Savage and Metro Boomin", known_norms=set()
        ) == ("needs_deezer", ["21 Savage", "Metro Boomin"], "ampersand")

    def test_y_defers_to_deezer(self):
        assert classify_artist_string("Amato Y Mariana", known_norms=set()) == (
            "needs_deezer",
            ["Amato", "Mariana"],
            "ampersand",
        )

    def test_e_defers_to_deezer(self):
        assert classify_artist_string("Cravo e Canela", known_norms=set()) == (
            "needs_deezer",
            ["Cravo", "Canela"],
            "ampersand",
        )

    def test_new_separators_mirror_ampersand_when_unknown(self):
        amp = classify_artist_string("Foo & Bar", known_norms=set())
        for raw in ["Foo + Bar", "Foo x Bar", "Foo and Bar", "Foo y Bar", "Foo e Bar"]:
            assert classify_artist_string(raw, known_norms=set()) == amp

    def test_x_with_known_token_splits_locally(self):
        # A known member turns the ampersand rule into a local split (like " & ").
        result = classify_artist_string(
            "Nicky Romero x David Guetta",
            known_norms={normalize("Nicky Romero")},
        )
        assert result == ("split", ["Nicky Romero", "David Guetta"])

    def test_plus_with_known_token_splits_locally(self):
        result = classify_artist_string(
            "Sultan + Shepard", known_norms={normalize("Shepard")}
        )
        assert result == ("split", ["Sultan", "Shepard"])


class TestAmpersandFamilyParts:
    """Phase C mirrors: every ampersand-family token is a primary part."""

    def test_plus_parts(self):
        assert split_artist_parts("Sultan + Shepard") == [
            ("Sultan", "primary", 0),
            ("Shepard", "primary", 1),
        ]

    def test_x_parts(self):
        assert split_artist_parts("Nicky Romero x David Guetta") == [
            ("Nicky Romero", "primary", 0),
            ("David Guetta", "primary", 1),
        ]

    def test_and_parts(self):
        assert split_artist_parts("21 Savage and Metro Boomin") == [
            ("21 Savage", "primary", 0),
            ("Metro Boomin", "primary", 1),
        ]

    def test_y_parts(self):
        assert split_artist_parts("Amato Y Mariana") == [
            ("Amato", "primary", 0),
            ("Mariana", "primary", 1),
        ]

    def test_e_parts(self):
        assert split_artist_parts("Cravo e Canela") == [
            ("Cravo", "primary", 0),
            ("Canela", "primary", 1),
        ]

    def test_new_separators_mirror_ampersand_parts(self):
        amp = split_artist_parts("Foo & Bar")
        for raw in ["Foo + Bar", "Foo x Bar", "Foo and Bar", "Foo y Bar", "Foo e Bar"]:
            assert split_artist_parts(raw) == amp


class TestStylizedGuard:
    """A letter-by-letter stylized name is a single artist, never split."""

    def test_axl_is_single(self):
        assert classify_artist_string("A X L", known_norms=set()) == (
            "single",
            ["A X L"],
        )

    def test_testpress_is_single(self):
        # Contains " e " (between t and s) but is stylized → guarded before " e ".
        assert classify_artist_string("t e s t p r e s s", known_norms=set()) == (
            "single",
            ["t e s t p r e s s"],
        )

    def test_jay_electronica_is_single(self):
        # Contains " e " and " y " but is stylized → single.
        assert classify_artist_string(
            "J A Y E L E C T R O N I C A", known_norms=set()
        ) == ("single", ["J A Y E L E C T R O N I C A"])

    def test_stylized_yields_single_part(self):
        assert split_artist_parts("A X L") == [("A X L", "primary", 0)]
        assert split_artist_parts("t e s t p r e s s") == [
            ("t e s t p r e s s", "primary", 0)
        ]

    def test_comma_beats_stylized_guard(self):
        # "A X L, SH.AH" — the comma (unambiguous, higher precedence) wins over the
        # stylized guard: the stylized member stays whole inside the comma split.
        assert classify_artist_string("A X L, SH.AH", known_norms=set()) == (
            "needs_deezer",
            ["A X L", "SH.AH"],
            "comma",
        )

    def test_comma_beats_stylized_guard_parts(self):
        assert split_artist_parts("A X L, SH.AH") == [
            ("A X L", "primary", 0),
            ("SH.AH", "primary", 1),
        ]

    def test_helper_majority_rule(self):
        assert _is_stylized_name("A X L") is True
        assert _is_stylized_name("t e s t p r e s s") is True
        # A single one-char token among two real tokens is NOT a majority.
        assert _is_stylized_name("Nicky Romero x David Guetta") is False
        assert _is_stylized_name("J Balvin") is False
        assert _is_stylized_name("Solo") is False


class TestArticleGuard:
    """" and " / " y " followed by an article = group name, kept single."""

    def test_amyl_and_the_sniffers_is_single(self):
        assert classify_artist_string(
            "Amyl and the Sniffers", known_norms=set()
        ) == ("single", ["Amyl and the Sniffers"])

    def test_cortijo_y_su_maquina_is_single(self):
        assert classify_artist_string(
            "Cortijo Y Su Maquina Del Tiempo", known_norms=set()
        ) == ("single", ["Cortijo Y Su Maquina Del Tiempo"])

    def test_no_article_still_defers_to_deezer(self):
        # "Belle and Sebastian" — no article after " and ", so Deezer decides.
        assert classify_artist_string(
            "Belle and Sebastian", known_norms=set()
        ) == ("needs_deezer", ["Belle", "Sebastian"], "ampersand")

    def test_article_guard_only_when_article_present(self):
        assert classify_artist_string("Amato Y Mariana", known_norms=set()) == (
            "needs_deezer",
            ["Amato", "Mariana"],
            "ampersand",
        )

    def test_article_group_yields_single_part(self):
        assert split_artist_parts("Amyl and the Sniffers") == [
            ("Amyl and the Sniffers", "primary", 0)
        ]
        assert split_artist_parts("Cortijo Y Su Maquina Del Tiempo") == [
            ("Cortijo Y Su Maquina Del Tiempo", "primary", 0)
        ]

    def test_no_article_yields_split_parts(self):
        assert split_artist_parts("Belle and Sebastian") == [
            ("Belle", "primary", 0),
            ("Sebastian", "primary", 1),
        ]

    def test_article_helper(self):
        assert _article_after_separator(["Amyl", "the Sniffers"]) is True
        assert _article_after_separator(["Cortijo", "Su Maquina Del Tiempo"]) is True
        assert _article_after_separator(["Belle", "Sebastian"]) is False
        assert _article_after_separator(["Amato", "Mariana"]) is False


class TestNoRegression:
    """Existing feat / comma / & / | behaviour is untouched."""

    def test_ampersand_unchanged(self):
        assert classify_artist_string("A & B", known_norms=set()) == (
            "needs_deezer",
            ["A", "B"],
            "ampersand",
        )

    def test_pipe_unchanged(self):
        assert classify_artist_string("A | B", known_norms=set()) == (
            "needs_deezer",
            ["A", "B"],
            "ampersand",
        )

    def test_comma_unchanged(self):
        assert classify_artist_string("A, B", known_norms=set()) == (
            "needs_deezer",
            ["A", "B"],
            "comma",
        )

    def test_feat_unchanged(self):
        assert classify_artist_string("A feat. B", known_norms=set()) == (
            "split",
            ["A", "B"],
        )

    def test_feat_parts_featured_role_unchanged(self):
        assert split_artist_parts("A feat. B") == [
            ("A", "primary", 0),
            ("B", "featured", 1),
        ]

    def test_solo_is_single(self):
        assert classify_artist_string("Solo", known_norms=set()) == (
            "single",
            ["Solo"],
        )

    def test_solo_part_unchanged(self):
        assert split_artist_parts("Solo") == [("Solo", "primary", 0)]

    def test_ampersand_known_token_splits_unchanged(self):
        assert classify_artist_string("A & B", known_norms={normalize("A")}) == (
            "split",
            ["A", "B"],
        )
