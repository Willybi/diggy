"""X3.b — the async Beatport release fallback must require a title match.

`_search_beatport_async` Strategy 3 (release fallback) shares ONE beatport_id
across a release tracklist. It used to return a release's single track blindly
(``if len(tracks) == 1``) or on a loose substring match, stamping the id onto
the wrong recording. These tests drive the real async function with a fake HTTP
pool serving crafted ``__NEXT_DATA__`` pages (no network) and assert the
tightened, remix-aware matcher.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

# Make the workers package importable (same pattern as test_enrich_candidates.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis / curl_cffi are not installed in the test env; enrichment.py imports
# them at module load. Save/restore so other test files are not polluted.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.enrichment import _search_beatport_async  # noqa: E402

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


def _next_data_html(state_data: dict) -> str:
    """Wrap a query ``state.data`` payload into a Beatport __NEXT_DATA__ page."""
    payload = {
        "props": {
            "pageProps": {
                "dehydratedState": {"queries": [{"state": {"data": state_data}}]}
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


def _releases_page(artist="Malugi"):
    return _next_data_html(
        {
            "releases": {
                "data": [
                    {
                        "release_id": 1,
                        "release_name": "Some EP",
                        "artists": [{"artist_id": 5, "artist_name": artist}],
                    }
                ]
            }
        }
    )


def _release_tracks_page(tracks: list[dict]):
    return _next_data_html({"results": tracks})


class _FakePool:
    """Serve crafted pages by request path; records the paths requested."""

    def __init__(self, releases_html: str, tracks_html: str):
        self._releases_html = releases_html
        self._tracks_html = tracks_html
        self.paths: list[str] = []

    async def beatport_get(self, path: str):
        self.paths.append(path)
        if "type=tracks" in path:
            # Strategy 2 (track search) misses → forces the release fallback.
            return SimpleNamespace(status_code=200, text=_next_data_html({"tracks": {"data": []}}))
        if "type=releases" in path:
            return SimpleNamespace(status_code=200, text=self._releases_html)
        if path.startswith("/release/"):
            return SimpleNamespace(status_code=200, text=self._tracks_html)
        return SimpleNamespace(status_code=404, text="")


async def test_rejects_single_non_matching_release_track():
    pool = _FakePool(
        _releases_page(),
        _release_tracks_page(
            [{"id": 99, "name": "Different Song", "mix_name": "Original Mix", "artists": []}]
        ),
    )
    result = await _search_beatport_async(pool, "Honestly", "Malugi", None)
    assert result is None


async def test_rejects_multi_track_release_when_none_match():
    pool = _FakePool(
        _releases_page(),
        _release_tracks_page(
            [
                {"id": 1, "name": "Song A", "mix_name": None, "artists": []},
                {"id": 2, "name": "Song B", "mix_name": None, "artists": []},
            ]
        ),
    )
    result = await _search_beatport_async(pool, "Honestly", "Malugi", None)
    assert result is None


async def test_accepts_matching_release_track():
    pool = _FakePool(
        _releases_page(),
        _release_tracks_page(
            [
                {"id": 1, "name": "Baby", "mix_name": None, "artists": []},
                {"id": 2, "name": "Honestly", "mix_name": "Original Mix", "artists": []},
            ]
        ),
    )
    result = await _search_beatport_async(pool, "Honestly", "Malugi", None)
    assert result is not None
    assert result["id"] == 2
