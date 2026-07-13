"""Regression tests for the preview-URL endpoint's Deezer error handling.

Bug: Deezer signals a quota overrun as HTTP 200 + ``{"error":{"code":4}}`` with
no ``preview`` field. The old code read ``data.get("preview","")`` → empty →
``LookupError`` → 404, so a throttled play looked like a missing preview and the
player closed. A retry 1s later (quota window reset) served 200 — intermittent
404s in prod.

Fix: inspect the JSON error payload (mirror of source_clients._deezer_get).
Transient errors (quota / 5xx / network) → 503 + one retry; genuine absence
(DataException / code 800) → 404. Resolved URLs are cached in Redis.
"""
import pytest
from models import CatalogEntry
from services import catalog_service

QUOTA_BODY = {"error": {"type": "Exception", "code": 4, "message": "Quota limit exceeded"}}
DATA_EXCEPTION_BODY = {"error": {"type": "DataException", "code": 800, "message": "no data"}}
OK_BODY = {"id": 123, "preview": "https://cdns-preview.deezer.com/stream/x.mp3"}


class _Resp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json


class _Client:
    """Async-context httpx.AsyncClient stand-in returning canned responses in
    sequence (the last one repeats), counting outbound Deezer calls."""

    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        i = self._calls["n"]
        self._calls["n"] += 1
        return self._responses[min(i, len(self._responses) - 1)]


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value


def _patch_deezer(monkeypatch, responses):
    """Route the service's httpx calls to canned ``responses``; return the call
    counter. Also zeroes the retry backoff so no real sleep happens."""
    calls = {"n": 0}
    monkeypatch.setattr(catalog_service, "_PREVIEW_RETRY_BACKOFF", 0)
    monkeypatch.setattr(
        catalog_service.httpx, "AsyncClient",
        lambda *a, **k: _Client(responses, calls),
    )
    return calls


async def _mk_entry(db, deezer_id="123", has_preview=True):
    c = CatalogEntry(
        title="T",
        artist="A",
        normalized_key=f"a|t-{deezer_id}",
        scope="shared",
        deezer_id=deezer_id,
        has_preview=has_preview,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


class TestTransientVsGenuine:
    async def test_quota_body_is_503_never_404(self, db, monkeypatch):
        """200 + quota error on a has_preview=true track → transient (503), and
        it retries once before giving up."""
        c = await _mk_entry(db, has_preview=True)
        calls = _patch_deezer(monkeypatch, [_Resp(QUOTA_BODY), _Resp(QUOTA_BODY)])
        with pytest.raises(catalog_service.PreviewUnavailableError):
            await catalog_service.get_preview_url(db, c.id, None, redis=None)
        assert calls["n"] == 2  # initial attempt + one retry
        # Never misclassified as absence: has_preview untouched.
        await db.refresh(c)
        assert c.has_preview is True

    async def test_quota_then_success_recovers_on_retry(self, db, monkeypatch):
        c = await _mk_entry(db)
        calls = _patch_deezer(monkeypatch, [_Resp(QUOTA_BODY), _Resp(OK_BODY)])
        res = await catalog_service.get_preview_url(db, c.id, None, redis=None)
        assert res == {"preview_url": OK_BODY["preview"]}
        assert calls["n"] == 2

    async def test_http_500_is_transient_503(self, db, monkeypatch):
        c = await _mk_entry(db)
        _patch_deezer(monkeypatch, [_Resp({}, status_code=500), _Resp({}, status_code=500)])
        with pytest.raises(catalog_service.PreviewUnavailableError):
            await catalog_service.get_preview_url(db, c.id, None, redis=None)

    async def test_data_exception_is_404_and_stamps(self, db, monkeypatch):
        """code 800 / DataException = real absence → LookupError (404), and the
        entry self-heals to has_preview=false."""
        c = await _mk_entry(db, has_preview=True)
        calls = _patch_deezer(monkeypatch, [_Resp(DATA_EXCEPTION_BODY)])
        with pytest.raises(LookupError):
            await catalog_service.get_preview_url(db, c.id, None, redis=None)
        assert calls["n"] == 1  # genuine absence is not retried
        await db.refresh(c)
        assert c.has_preview is False

    async def test_empty_preview_is_404_without_stamp(self, db, monkeypatch):
        """200, no error, empty preview → 404, but not stamped (may be region-scoped)."""
        c = await _mk_entry(db, has_preview=True)
        _patch_deezer(monkeypatch, [_Resp({"id": 123, "preview": ""})])
        with pytest.raises(LookupError):
            await catalog_service.get_preview_url(db, c.id, None, redis=None)
        await db.refresh(c)
        assert c.has_preview is True


class TestRedisCache:
    async def test_second_call_served_from_cache(self, db, monkeypatch):
        """A resolved URL is cached: the second call must not hit Deezer."""
        c = await _mk_entry(db)
        redis = _FakeRedis()
        calls = _patch_deezer(monkeypatch, [_Resp(OK_BODY)])
        r1 = await catalog_service.get_preview_url(db, c.id, None, redis=redis)
        r2 = await catalog_service.get_preview_url(db, c.id, None, redis=redis)
        assert r1 == r2 == {"preview_url": OK_BODY["preview"]}
        assert calls["n"] == 1  # single Deezer hit; second served from cache

    async def test_redis_down_fails_open(self, db, monkeypatch):
        """A raising Redis must not break the request (fail-open → recompute)."""
        class _BrokenRedis:
            async def get(self, key):
                raise RuntimeError("redis down")

            async def setex(self, key, ttl, value):
                raise RuntimeError("redis down")

        c = await _mk_entry(db)
        _patch_deezer(monkeypatch, [_Resp(OK_BODY)])
        res = await catalog_service.get_preview_url(db, c.id, None, redis=_BrokenRedis())
        assert res == {"preview_url": OK_BODY["preview"]}


class TestRouterMapping:
    async def test_router_returns_503_on_quota(self, db, client, monkeypatch):
        c = await _mk_entry(db)
        _patch_deezer(monkeypatch, [_Resp(QUOTA_BODY), _Resp(QUOTA_BODY)])
        resp = await client.get(f"/api/catalog/{c.id}/preview-url")
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "3"

    async def test_router_returns_404_on_data_exception(self, db, client, monkeypatch):
        c = await _mk_entry(db)
        _patch_deezer(monkeypatch, [_Resp(DATA_EXCEPTION_BODY)])
        resp = await client.get(f"/api/catalog/{c.id}/preview-url")
        assert resp.status_code == 404

    async def test_router_returns_200_on_success(self, db, client, monkeypatch):
        c = await _mk_entry(db)
        _patch_deezer(monkeypatch, [_Resp(OK_BODY)])
        resp = await client.get(f"/api/catalog/{c.id}/preview-url")
        assert resp.status_code == 200
        assert resp.json() == {"preview_url": OK_BODY["preview"]}
