"""
Tests for the watchlist service (services/watchlist_service.py):
_fetch_deezer_playlist's {} fallback and request_crawl's 12h cooldown.
"""
from datetime import datetime, timedelta, timezone

import pytest

from models import WatchedEntity
from services import watchlist_service


# ── _fetch_deezer_playlist ────────────────────────────────────────────────────

class TestFetchDeezerPlaylist:
    async def test_returns_empty_dict_when_httpx_raises(self, mocker):
        mocker.patch(
            "services.watchlist_service.httpx.AsyncClient",
            side_effect=RuntimeError("network down"),
        )
        result = await watchlist_service._fetch_deezer_playlist("123")
        assert result == {}


# ── request_crawl : cooldown 12h ──────────────────────────────────────────────

async def _make_entity(db, external_id, last_crawled_delta):
    entity = WatchedEntity(
        external_id=external_id,
        source="deezer",
        title="Cooldown PL",
        last_crawled_at=datetime.now(timezone.utc) - last_crawled_delta,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


class TestRequestCrawlCooldown:
    async def test_crawl_just_under_12h_raises(self, db, mocker):
        mocker.patch("services.watchlist_service._trigger_crawl")
        entity = await _make_entity(db, "cd-under", timedelta(hours=11, minutes=59))

        with pytest.raises(ValueError, match="Crawl cooldown: retry in"):
            await watchlist_service.request_crawl(db, entity.id)

    async def test_crawl_just_over_12h_queues(self, db, mocker):
        trigger = mocker.patch("services.watchlist_service._trigger_crawl")
        entity = await _make_entity(db, "cd-over", timedelta(hours=12, minutes=1))

        result = await watchlist_service.request_crawl(db, entity.id)
        assert result == {"status": "crawl_queued", "playlist_id": entity.id}
        trigger.assert_awaited_once()
