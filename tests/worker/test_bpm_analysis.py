"""Tests for the E2.c preview-BPM analysis logic (workers/bpm_analysis).

Covers the PURE logic — no real network, no real Essentia (the CI env has
neither essentia nor ffmpeg): the Essentia call is isolated behind the module
function ``_analyze_blocking``, which the batch tests monkeypatch. Asserted:

  - the confidence gate (conf >= min_conf writes bpm+source; below it does not);
  - the ``bpm is None`` guard (never overwrites an existing bpm — invariant #3);
  - attempt stamping ONLY on a verdict (ok / low_conf / no_preview), never on a
    simulated network/HTTP failure (an outage is not an attempt);
  - candidate selection goes through the shared ``bpm_analysis_candidate_filter``.

Import dance (redis/curl_cffi absent in the test env) mirrors
test_enrich_candidates.py so it does not pollute sibling test modules.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

# Path so the workers package is importable (same pattern as test_enrich_candidates.py)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis and curl_cffi are not installed in the test env; async_http.py (imported
# by bpm_analysis) pulls curl_cffi at module load. Same save/restore dance as
# test_enrich_candidates.py to avoid polluting other test files.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.bpm_analysis as bpm_mod  # noqa: E402
from workers.async_http import DeezerHTTPError  # noqa: E402
from workers.bpm_analysis import (  # noqa: E402
    _record_bpm_verdict,
    analyze_bpm_batch,
    select_bpm_candidates,
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

NOW = datetime(2026, 8, 8, 1, 0, 0, tzinfo=timezone.utc)
MIN_CONF = 2.0


def _make_row(session, n, **overrides):
    entry = CatalogEntry(
        title=f"Track {n}",
        artist="Artist",
        normalized_key=f"track {n} - artist",
        **overrides,
    )
    session.add(entry)
    session.commit()
    return entry


# ── Candidate selection (shared filter) ──


class TestSelectBpmCandidates:
    def test_only_shared_filter_rows_selected(self, sync_session):
        """A candidate has: a preview, no bpm, a real deezer_id, never analyzed.
        Each non-candidate below breaks exactly one clause of the shared filter."""
        good = _make_row(
            sync_session, 1, has_preview=True, deezer_id="dz-1", bpm=None
        )
        # no preview
        _make_row(sync_session, 2, has_preview=False, deezer_id="dz-2", bpm=None)
        # already has a bpm
        _make_row(sync_session, 3, has_preview=True, deezer_id="dz-3", bpm=128.0)
        # no deezer_id
        _make_row(sync_session, 4, has_preview=True, deezer_id=None, bpm=None)
        # NOT_FOUND sentinel is not a real id
        _make_row(
            sync_session, 5, has_preview=True, deezer_id="NOT_FOUND", bpm=None
        )
        # already analyzed
        _make_row(
            sync_session,
            6,
            has_preview=True,
            deezer_id="dz-6",
            bpm=None,
            bpm_analyzed_at=NOW,
        )

        result = select_bpm_candidates(sync_session, limit=10)

        assert [e.id for e in result] == [good.id]

    def test_newest_first_and_limit(self, sync_session):
        rows = [
            _make_row(sync_session, n, has_preview=True, deezer_id=f"dz-{n}", bpm=None)
            for n in range(3)
        ]

        result = select_bpm_candidates(sync_session, limit=2)

        # id DESC (freshness proxy) + limit honored
        assert [e.id for e in result] == [rows[2].id, rows[1].id]

    def test_zero_limit_selects_nothing(self, sync_session):
        _make_row(sync_session, 1, has_preview=True, deezer_id="dz-1", bpm=None)

        assert select_bpm_candidates(sync_session, limit=0) == []


# ── Verdict recording (gate + guard + stamping) — pure, no IO ──


class TestRecordBpmVerdict:
    def _entry(self, **kw):
        e = MagicMock()
        e.bpm = kw.get("bpm", None)
        e.bpm_source = kw.get("bpm_source", None)
        e.bpm_analyzed_at = None
        e.bpm_analysis_attempts = kw.get("attempts", 0)
        return e

    def test_conf_at_gate_writes_estimated_bpm(self):
        entry = self._entry()

        status = _record_bpm_verdict(entry, 127.34, MIN_CONF, MIN_CONF, NOW)

        assert status == "estimated"
        assert entry.bpm == 127.3  # rounded to 1 decimal
        assert entry.bpm_source == "analysis"
        assert entry.bpm_analyzed_at == NOW
        assert entry.bpm_analysis_attempts == 1

    def test_conf_below_gate_writes_no_bpm_but_stamps(self):
        entry = self._entry()

        status = _record_bpm_verdict(entry, 127.3, 1.99, MIN_CONF, NOW)

        assert status == "low_conf"
        assert entry.bpm is None
        assert entry.bpm_source is None
        # still a verdict → stamped + incremented
        assert entry.bpm_analyzed_at == NOW
        assert entry.bpm_analysis_attempts == 1

    def test_existing_bpm_never_overwritten(self):
        # Defensive guard: even a high-confidence result must not clobber an
        # existing (authoritative) bpm — invariant #3.
        entry = self._entry(bpm=128.0, bpm_source="beatport")

        status = _record_bpm_verdict(entry, 90.0, 5.0, MIN_CONF, NOW)

        assert status == "skipped"
        assert entry.bpm == 128.0
        assert entry.bpm_source == "beatport"
        # a verdict was still reached → stamped
        assert entry.bpm_analyzed_at == NOW
        assert entry.bpm_analysis_attempts == 1

    def test_null_attempts_becomes_one(self):
        entry = self._entry(attempts=None)

        _record_bpm_verdict(entry, 120.0, 3.0, MIN_CONF, NOW)

        assert entry.bpm_analysis_attempts == 1


# ── Batch pipeline (stamping on verdict vs transient failure) ──


@asynccontextmanager
async def _noop_cm(*args, **kwargs):
    yield


def _pool(preview="https://cdn/preview.mp3", audio=b"\xff\xf3mp3-bytes", hit_error=None):
    """MagicMock HttpPool: deezer_get resolves a /track hit, download_audio the bytes."""
    pool = MagicMock()
    if hit_error is not None:
        pool.deezer_get = AsyncMock(side_effect=hit_error)
    else:
        pool.deezer_get = AsyncMock(return_value={"id": 1, "preview": preview})
    pool.download_audio = AsyncMock(return_value=audio)
    # `_analyze_one` wraps the download in `pool.limiter.acquire("deezer_preview")`;
    # a fresh no-op async CM per call keeps the batch pipeline testable.
    pool.limiter.acquire = MagicMock(side_effect=lambda *a, **k: _noop_cm())
    return pool


def _entry_row():
    e = MagicMock()
    e.id = 1
    e.deezer_id = "dz-1"
    e.bpm = None
    e.bpm_source = None
    e.bpm_analyzed_at = None
    e.bpm_analysis_attempts = 0
    return e


class TestAnalyzeBpmBatch:
    async def test_success_writes_bpm_and_stamps(self, monkeypatch):
        # Essentia isolated: patch the module's blocking analyzer.
        monkeypatch.setattr(bpm_mod, "_analyze_blocking", lambda path: (124.5, 3.1))
        entry = _entry_row()
        pool = _pool()

        with ThreadPoolExecutor(max_workers=1) as ex:
            stats = await analyze_bpm_batch(
                None, [entry], pool, ex, min_conf=MIN_CONF
            )

        assert stats["estimated"] == 1
        assert entry.bpm == 124.5
        assert entry.bpm_source == "analysis"
        assert isinstance(entry.bpm_analyzed_at, datetime)
        assert entry.bpm_analysis_attempts == 1

    async def test_low_conf_stamps_but_no_bpm(self, monkeypatch):
        monkeypatch.setattr(bpm_mod, "_analyze_blocking", lambda path: (124.5, 1.0))
        entry = _entry_row()
        pool = _pool()

        with ThreadPoolExecutor(max_workers=1) as ex:
            stats = await analyze_bpm_batch(
                None, [entry], pool, ex, min_conf=MIN_CONF
            )

        assert stats["low_conf"] == 1
        assert entry.bpm is None
        assert entry.bpm_source is None
        assert isinstance(entry.bpm_analyzed_at, datetime)
        assert entry.bpm_analysis_attempts == 1

    async def test_no_preview_is_a_verdict_and_stamps(self, monkeypatch):
        # _analyze_blocking must NOT be reached when there is no preview.
        called = {"n": 0}

        def _boom(path):
            called["n"] += 1
            raise AssertionError("analysis must not run without a preview")

        monkeypatch.setattr(bpm_mod, "_analyze_blocking", _boom)
        entry = _entry_row()
        pool = _pool(preview="")  # Deezer returns an empty preview

        with ThreadPoolExecutor(max_workers=1) as ex:
            stats = await analyze_bpm_batch(
                None, [entry], pool, ex, min_conf=MIN_CONF
            )

        assert stats["no_preview"] == 1
        assert called["n"] == 0
        assert entry.bpm is None
        # verdict → stamped
        assert isinstance(entry.bpm_analyzed_at, datetime)
        assert entry.bpm_analysis_attempts == 1

    async def test_deezer_http_error_leaves_unstamped(self, monkeypatch):
        monkeypatch.setattr(bpm_mod, "_analyze_blocking", lambda path: (124.5, 3.1))
        entry = _entry_row()
        pool = _pool(hit_error=DeezerHTTPError(503, "/track/dz-1"))

        with ThreadPoolExecutor(max_workers=1) as ex:
            stats = await analyze_bpm_batch(
                None, [entry], pool, ex, min_conf=MIN_CONF
            )

        assert stats["errors"] == 1
        # an outage is NOT an attempt → untouched, retried next night
        assert entry.bpm is None
        assert entry.bpm_analyzed_at is None
        assert entry.bpm_analysis_attempts == 0

    async def test_download_failure_leaves_unstamped(self, monkeypatch):
        monkeypatch.setattr(bpm_mod, "_analyze_blocking", lambda path: (124.5, 3.1))
        entry = _entry_row()
        pool = _pool(audio=None)  # CDN download returned nothing

        with ThreadPoolExecutor(max_workers=1) as ex:
            stats = await analyze_bpm_batch(
                None, [entry], pool, ex, min_conf=MIN_CONF
            )

        assert stats["errors"] == 1
        assert entry.bpm_analyzed_at is None
        assert entry.bpm_analysis_attempts == 0

    async def test_analysis_exception_leaves_unstamped(self, monkeypatch):
        # A decode/analysis failure is transient too — no verdict, retry.
        def _raise(path):
            raise RuntimeError("corrupt mp3")

        monkeypatch.setattr(bpm_mod, "_analyze_blocking", _raise)
        entry = _entry_row()
        pool = _pool()

        with ThreadPoolExecutor(max_workers=1) as ex:
            stats = await analyze_bpm_batch(
                None, [entry], pool, ex, min_conf=MIN_CONF
            )

        assert stats["errors"] == 1
        assert entry.bpm_analyzed_at is None
        assert entry.bpm_analysis_attempts == 0
