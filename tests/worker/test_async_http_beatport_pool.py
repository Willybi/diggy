"""Tests for HttpPool's Beatport threadpool lifecycle (L1f).

Focus (no network):
- the executor width honours BEATPORT_CONCURRENCY (default 2 = PROD unchanged);
- beatport_get lazily creates a curl_cffi session PER executor thread and tracks
  it, so __aexit__ closes every session it created.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

# Make server/ importable so `workers.async_http` resolves (conftest only adds
# server/api).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# curl_cffi / redis are not installed in the test env; async_http imports them
# at module load. Mock them, import, then restore sys.modules.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")

_fake_curl = MagicMock()
sys.modules["curl_cffi"] = _fake_curl

from workers.async_http import HttpPool  # noqa: E402

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl


@pytest.mark.asyncio
async def test_executor_width_defaults_to_two(monkeypatch):
    """No BEATPORT_CONCURRENCY env → max_workers == 2 (PROD unchanged)."""
    monkeypatch.delenv("BEATPORT_CONCURRENCY", raising=False)
    pool = HttpPool()
    async with pool:
        assert pool._bp_executor._max_workers == 2
        assert pool._bp_sessions == []


@pytest.mark.asyncio
async def test_executor_width_honours_env(monkeypatch):
    """BEATPORT_CONCURRENCY=6 → executor sized to 6 (local scraper case)."""
    monkeypatch.setenv("BEATPORT_CONCURRENCY", "6")
    pool = HttpPool()
    async with pool:
        assert pool._bp_executor._max_workers == 6


@pytest.mark.asyncio
async def test_beatport_get_creates_and_closes_thread_local_session(monkeypatch):
    """beatport_get creates a session, tracks it; __aexit__ closes it."""
    monkeypatch.setenv("BEATPORT_CONCURRENCY", "1")  # single thread → one session

    created = []

    def _make_session(impersonate=None):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        resp.content = b"ok"
        session.get.return_value = resp
        created.append(session)
        return session

    # Patch the curl_requests.Session symbol used inside async_http.
    import workers.async_http as async_http

    monkeypatch.setattr(async_http.curl_requests, "Session", _make_session)

    pool = HttpPool()
    async with pool:
        r = await pool.beatport_get("/search?q=test")
        assert r.status_code == 200
        assert r.text == "ok"
        # exactly one session created and tracked
        assert len(created) == 1
        assert pool._bp_sessions == created
        # a second call on the same (single) thread reuses the session
        await pool.beatport_get("/search?q=again")
        assert len(created) == 1

    # __aexit__ closed the tracked session and cleared the list
    created[0].close.assert_called_once()
    assert pool._bp_sessions == []
