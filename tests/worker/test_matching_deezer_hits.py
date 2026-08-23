"""Unit tests for ``workers.tasks.artists._matching_deezer_hits``.

The matcher is the SINGLE source of the Deezer artist-name match used by both the
nightly linker (``_link_artist_deezer``) and sync Phase B (``_deezer_artist_id``).
These tests pin the wiring of its three signals — raw exact, accent fold, and the
guarded punctuation fold on EITHER ``punct_fold_key`` (drop) or ``punct_sep_key``
(punctuation → space) — with the focus on the space-vs-punctuation case that the
drop-key alone misses ("R.Kelly" == "R. Kelly") and the false merges the sep-key
must keep excluded ("Will I Am" != "William").
"""

import os
import sys
from unittest.mock import MagicMock

# Path so the workers package is importable in tests.
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Mock infra that isn't available outside Docker (same pattern as the sibling
# task tests): curl_cffi + redis + celery are imported at module load time.
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "requests",
    "curl_cffi",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

from workers.tasks.artists import _matching_deezer_hits  # noqa: E402

_POPULAR = 50_000  # comfortably above FAN_FLOOR


def _hit(name, nb_fan=_POPULAR, id=1):
    return {"id": id, "name": name, "nb_fan": nb_fan}


def _names(hits):
    return [h["name"] for h in hits]


class TestMatchingDeezerHits:
    def test_raw_exact_match(self):
        assert _names(_matching_deezer_hits([_hit("Bicep")], "Bicep")) == ["Bicep"]

    def test_accent_fold_match(self):
        assert _matching_deezer_hits([_hit("Amélie Lens")], "Amelie Lens")

    def test_rkelly_spaced_dot_now_matches(self):
        # The whole point of the change: "R.Kelly" resolves the Deezer hit
        # "R. Kelly" via punct_sep_key (the drop-key would miss it).
        assert _matching_deezer_hits([_hit("R. Kelly")], "R.Kelly")

    def test_ice_t_hyphen_matches(self):
        assert _matching_deezer_hits([_hit("Ice-T")], "ICE T")

    def test_cromagnon_compound_still_matches(self):
        # The complementary drop-key path still fires for no-separator compounds.
        assert _matching_deezer_hits([_hit("Cromagnon")], "Cro-Magnon")

    def test_acronym_guard_still_refuses_lily(self):
        assert _matching_deezer_hits([_hit("Lily")], "L.I.L.Y") == []

    def test_below_fan_floor_refused(self):
        # The fold signals are floor-gated; a 12-fan parasite must not link.
        assert _matching_deezer_hits([_hit("R. Kelly", nb_fan=12)], "R.Kelly") == []

    def test_fan_floor_does_not_gate_exact_match(self):
        # Exact and accent matches are NOT floor-gated.
        assert _matching_deezer_hits([_hit("Bicep", nb_fan=0)], "Bicep")

    def test_ordered_by_fan_desc(self):
        hits = [_hit("R. Kelly", nb_fan=1000, id=1), _hit("R. Kelly", nb_fan=9000, id=2)]
        assert [h["id"] for h in _matching_deezer_hits(hits, "R.Kelly")] == [2, 1]

    # ── transliteration fold (cases 2 & 3), NOT floor-gated ──────────────────

    def test_turkish_dotless_i_matches_even_low_fan(self):
        # Accent/translit fold is a STRONG signal — links regardless of fan count.
        assert _matching_deezer_hits([_hit("Altın Gün", nb_fan=3)], "Altin Gün")

    def test_smart_apostrophe_matches_even_low_fan(self):
        assert _matching_deezer_hits(
            [_hit("ANGEL'IN HEAVY SYRUP", nb_fan=3)], "Angel’in Heavy Syrup"
        )

    # ── space fold (case 1): AUX88, hard-gated + ambiguity-rejected ──────────

    def test_pure_space_insertion_links_when_unambiguous(self):
        assert _matching_deezer_hits([_hit("AUX 88", nb_fan=1873)], "AUX88")

    def test_space_fold_floor_gated(self):
        assert _matching_deezer_hits([_hit("AUX 88", nb_fan=12)], "AUX88") == []

    def test_space_fold_min_length_gated(self):
        # "coro" (4) is below SPACE_FOLD_MIN_LEN → refused even as a lone hit.
        assert _matching_deezer_hits([_hit("Co Ro", nb_fan=9000)], "CoRo") == []

    def test_space_fold_ambiguous_two_distinct_ids_refused(self):
        # Two DIFFERENT artists both collapsing to "aux88" → link nothing.
        hits = [_hit("AUX 88", nb_fan=1873, id=1), _hit("A UX88", nb_fan=5000, id=2)]
        assert _matching_deezer_hits(hits, "AUX88") == []

    def test_space_fold_duplicate_same_id_still_links(self):
        # Same artist returned twice (one distinct id) is NOT ambiguous.
        hits = [_hit("AUX 88", nb_fan=1873, id=7), _hit("AUX88", nb_fan=1873, id=7)]
        assert _matching_deezer_hits(hits, "AUX88")

    def test_strong_match_takes_precedence_over_space_fold(self):
        # A dotted "will.i.am" is a STRONG sep-fold match for "Will I Am"; the
        # different-id "William" (space-fold only) must be ignored, not linked.
        hits = [
            _hit("will.i.am", nb_fan=200000, id=10),
            _hit("William", nb_fan=900000, id=11),
        ]
        out = _matching_deezer_hits(hits, "Will I Am")
        assert [h["id"] for h in out] == [10]

    def test_will_i_am_alone_against_william_is_accepted_residual_risk(self):
        # Without the real will.i.am in the results, "William" is space-fold-only
        # and a single distinct id — but it is a genuinely different name. This is
        # the accepted residual risk of the strict-guard design: it DOES link.
        # Pin the behaviour so a future tightening is a conscious change.
        assert _matching_deezer_hits([_hit("William", nb_fan=900000)], "Will I Am")
