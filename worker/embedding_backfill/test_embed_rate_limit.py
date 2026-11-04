"""Unit tests for the 429 handling of ``embed.py`` (no Essentia, no network).

``embed.py`` imports essentia/numpy/requests at module level because it runs in the
container, so they are stubbed here. Run standalone from the repo root:

    pytest worker/embedding_backfill/test_embed_rate_limit.py -q
"""

import importlib.util
import os
import sys
import types

import pytest


class FakeHTTPError(Exception):
    def __init__(self, response):
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if body is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHTTPError(self)

    def json(self):
        return self._body


class Clock:
    """Fake time: sleep() advances monotonic(), so global pauses resolve instantly."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def embed(monkeypatch):
    essentia_stub = types.ModuleType("essentia")
    essentia_stub.log = types.SimpleNamespace(warningActive=True)
    for name, module in (
        ("essentia", essentia_stub),
        ("numpy", types.ModuleType("numpy")),
        ("requests", types.ModuleType("requests")),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embed.py")
    spec = importlib.util.spec_from_file_location("embed_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.time = Clock()
    return module


def _serve(embed, responses):
    """Make requests.get return ``responses`` in order; returns the call list."""
    queue = iter(responses)
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return next(queue)

    embed.requests.get = fake_get
    return calls


def test_429_pauses_then_succeeds(embed):
    calls = _serve(embed, [FakeResponse(429), FakeResponse(200)])
    assert embed._get("u").status_code == 200
    assert len(calls) == 2
    assert embed.time.sleeps == [embed.RATE_LIMIT_BASE_DELAY]


def test_429_honors_numeric_retry_after(embed):
    _serve(embed, [FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200)])
    embed._get("u")
    assert embed.time.sleeps == [7.0]


def test_429_ignores_non_numeric_retry_after(embed):
    _serve(
        embed,
        [
            FakeResponse(429, headers={"Retry-After": "Wed, 04 Nov 2026 12:00:00 GMT"}),
            FakeResponse(200),
        ],
    )
    embed._get("u")
    assert embed.time.sleeps == [embed.RATE_LIMIT_BASE_DELAY]


def test_429_backoff_is_capped_then_raises_without_extra_calls(embed):
    calls = _serve(embed, [FakeResponse(429)] * (embed.RATE_LIMIT_TRIES + 1))
    with pytest.raises(FakeHTTPError):
        embed._get("u")
    assert len(calls) == embed.RATE_LIMIT_TRIES + 1
    assert embed.time.sleeps == [30.0, 60.0, 120.0, 240.0, 300.0]


def test_pause_holds_other_threads_requests(embed):
    embed._pause_all(50)
    _serve(embed, [FakeResponse(200)])
    embed._get("u")
    assert embed.time.sleeps == [50]


def test_other_http_errors_keep_the_short_retries(embed):
    calls = _serve(embed, [FakeResponse(500), FakeResponse(500), FakeResponse(500)])
    with pytest.raises(FakeHTTPError):
        embed._get("u", tries=3)
    assert len(calls) == 3
    assert embed.time.sleeps == [0.5, 1.0, 1.5]


def test_network_failure_keeps_the_short_retries(embed):
    def boom(url, timeout):
        raise ConnectionError("down")

    embed.requests.get = boom
    with pytest.raises(ConnectionError):
        embed._get("u", tries=2)
    assert embed.time.sleeps == [0.5, 1.0]


def test_fetch_preview_treats_no_data_as_no_preview(embed):
    _serve(embed, [FakeResponse(200, {"error": {"code": 800, "message": "no data"}})])
    assert embed.fetch_preview_url("1") == ""


def test_fetch_preview_waits_on_quota_error(embed):
    _serve(
        embed,
        [
            FakeResponse(200, {"error": {"code": 4, "message": "Quota limit exceeded"}}),
            FakeResponse(200, {"preview": " https://cdn/x.mp3 "}),
        ],
    )
    assert embed.fetch_preview_url("1") == "https://cdn/x.mp3"
    assert embed.RATE_LIMIT_BASE_DELAY in embed.time.sleeps


def test_fetch_preview_raises_on_other_deezer_errors(embed):
    _serve(embed, [FakeResponse(200, {"error": {"code": 100, "message": "other"}})])
    with pytest.raises(RuntimeError):
        embed.fetch_preview_url("1")


def test_process_reports_http_code_in_status(embed):
    _serve(
        embed,
        [FakeResponse(200, {"preview": "https://cdn/x.mp3"})]
        + [FakeResponse(429)] * (embed.RATE_LIMIT_TRIES + 1),
    )
    out = embed.process({"id": "9", "deezer_id": "1"})
    assert out["status"] == "error:HTTP429"
    assert out["emb"] == ""
