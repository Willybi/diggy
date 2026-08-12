"""Regression tests for the Beatport outage guard (A3-02).

Twin of the Deezer guard (test_tasks_deezer_guard.py / test_enrichment_async.py):
when Beatport replies non-200 (a 403 Cloudflare block, a scrape outage), the
async search helpers now raise ``BeatportHTTPError`` instead of returning an
empty list. ``enrich_beatport_batch`` catches it, counts an ``error``, and does
NOT call ``_mark_searched`` — an outage is not a "not found" and must not burn
one of the 3 re-scan attempts, so the entry stays eligible for the next drain.

Two volets:
  (a) the searcher raises on a non-200 Beatport response;
  (b) the batch degrades cleanly — errors accounted, entry left unmarked — and,
      as a control, a real 200 "not found" DOES mark the entry (proving the
      distinction outage vs. not-found).
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Make the workers package importable (same pattern as test_beatport_release_fallback.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis / curl_cffi are not installed in the test env; enrichment.py and
# async_http.py import them at module load. Save/restore so other test files
# collected by pytest are not polluted.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.enrichment as enrichment_mod  # noqa: E402
from workers.async_http import BeatportHTTPError  # noqa: E402
from workers.enrichment import (  # noqa: E402
    _search_beatport_async,
    enrich_beatport_batch,
)

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

from models import CatalogEntry  # noqa: E402


class _FakePool:
    """Serve every Beatport request with a fixed status; records the paths."""

    def __init__(self, status_code: int, text: str = ""):
        self._status_code = status_code
        self._text = text
        self.paths: list[str] = []

    async def beatport_get(self, path: str):
        self.paths.append(path)
        return SimpleNamespace(status_code=self._status_code, text=self._text)


def _make_row(session, title="Track", artist="Artist", **overrides):
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{title.lower()}|{artist.lower()}",
        has_artwork=overrides.pop("has_artwork", True),  # skips cover upload path
        **overrides,
    )
    session.add(entry)
    session.commit()
    return entry


# ── Volet (a): the searcher raises on a non-200 ──────────────────────────────


class TestSearchBeatportAsyncRaises:
    async def test_non_200_raises_beatport_http_error(self):
        """A 403 during the track search (Strategy 2) raises instead of masking
        the outage as an empty result."""
        pool = _FakePool(403)

        with pytest.raises(BeatportHTTPError) as exc:
            await _search_beatport_async(pool, "Track", "Artist", None)

        assert exc.value.status_code == 403
        # Strategy 2 hit the track search endpoint before failing.
        assert pool.paths and "type=tracks" in pool.paths[0]


# ── Volet (b): the batch degrades cleanly (outage ≠ attempt) ─────────────────


class TestEnrichBeatportBatchOutageGuard:
    async def test_outage_counts_error_and_leaves_unmarked(
        self, sync_session, monkeypatch
    ):
        """A Beatport 403 during enrich_beatport_batch → errors >= 1, and the
        entry keeps beatport_searched_at=None and beatport_search_attempts=0
        (not marked as searched — the outage is retried next drain)."""
        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)
        entry = _make_row(sync_session)
        pool = _FakePool(403)

        stats = await enrich_beatport_batch(sync_session, [entry], pool, None)

        assert stats["errors"] >= 1
        assert stats["enriched"] == 0
        assert entry.beatport_searched_at is None
        assert entry.beatport_search_attempts == 0

    async def test_real_not_found_marks_searched(self, sync_session, monkeypatch):
        """Control: a genuine 200 "not found" (empty tracklist) is NOT an outage
        → the entry IS marked, proving the guard distinguishes the two cases."""
        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)
        entry = _make_row(sync_session)
        # 200 page whose track search yields no results → search returns None.
        empty_page = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"dehydratedState":{"queries":'
            '[{"state":{"data":{"tracks":{"data":[]}}}}]}}}}'
            "</script></html>"
        )
        pool = _FakePool(200, empty_page)

        stats = await enrich_beatport_batch(sync_session, [entry], pool, None)

        assert stats["errors"] == 0
        assert stats["not_found"] == 1
        assert entry.beatport_searched_at is not None
        assert entry.beatport_search_attempts == 1
