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

    def test_will_i_am_not_matched_to_william(self):
        # invariant #4: a pure space insertion must NOT collapse to another name.
        assert _matching_deezer_hits([_hit("William")], "Will I Am") == []

    def test_george_s_not_matched_to_georges(self):
        assert _matching_deezer_hits([_hit("Georges")], "George S.") == []

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
