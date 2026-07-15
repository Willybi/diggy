"""
N2.b — the " | " (pipe) separator in sync_artists.

These tests exercise the REAL dispatch code: sync_artists Phase A and Phase C
now delegate their separator logic to the module-level pure helpers
`classify_artist_string` / `split_artist_parts`, so removing the " | " branch
from either helper makes a test here fail (no shadow reimplementation).

The module is loaded the same way as test_tasks_deezer_guard.py — mocking the
celery / redis / curl_cffi imports that fire at module load — because
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

# The real dispatch helpers under test.
classify_artist_string = _artists_mod.classify_artist_string
split_artist_parts = _artists_mod.split_artist_parts

from utils import normalize  # noqa: E402  (server/api is on sys.path above)


class TestClassifyPipe:
    def test_pipe_with_known_token_splits_locally(self):
        # "A" is already a known artist → the pipe pair splits without Deezer.
        result = classify_artist_string("A | B", known_norms={normalize("A")})
        assert result == ("split", ["A", "B"])

    def test_pipe_with_unknown_tokens_routes_via_ampersand_rule(self):
        # Coupling requirement: an unresolved pipe name is deferred to Deezer
        # with rule_type "ampersand" so Phase B disambiguates it full-string-vs-
        # tokens (else it would fall through to a single combined artist).
        result = classify_artist_string("A | B", known_norms=set())
        assert result == ("needs_deezer", ["A", "B"], "ampersand")

    def test_pipe_mirrors_ampersand(self):
        # Parity: "|" and "&" reach the same dispatch decision.
        pipe = classify_artist_string("X | Y", known_norms=set())
        amp = classify_artist_string("X & Y", known_norms=set())
        assert pipe == amp == ("needs_deezer", ["X", "Y"], "ampersand")

    def test_pipe_strips_whitespace_and_drops_empties(self):
        result = classify_artist_string("A |  | B", known_norms={normalize("A")})
        assert result == ("split", ["A", "B"])

    def test_bare_pipe_no_spaces_is_recognised(self):
        # Real-world data: "Oliver Ho|James Ruskin" (no spaces around the pipe).
        result = classify_artist_string("Oliver Ho|James Ruskin", known_norms=set())
        assert result == ("needs_deezer", ["Oliver Ho", "James Ruskin"], "ampersand")

    def test_bare_pipe_splits_locally_with_known_token(self):
        result = classify_artist_string("A|B", known_norms={normalize("A")})
        assert result == ("split", ["A", "B"])

    def test_plain_name_is_single(self):
        # Regression: a name without a recognised separator is untouched.
        assert classify_artist_string("Solo", known_norms=set()) == ("single", ["Solo"])


class TestSplitArtistPartsPipe:
    def test_pipe_builds_primary_parts(self):
        assert split_artist_parts("A | B") == [
            ("A", "primary", 0),
            ("B", "primary", 1),
        ]

    def test_pipe_mirrors_ampersand_parts(self):
        assert split_artist_parts("X | Y") == split_artist_parts("X & Y")

    def test_bare_pipe_no_spaces_builds_parts(self):
        assert split_artist_parts("Oliver Ho|James Ruskin") == [
            ("Oliver Ho", "primary", 0),
            ("James Ruskin", "primary", 1),
        ]

    def test_non_pipe_name_unaffected(self):
        assert split_artist_parts("Solo") == [("Solo", "primary", 0)]
