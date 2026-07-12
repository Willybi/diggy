"""
Tests for the external search service + endpoint (services/external_search_service.py,
routers/search.py GET /api/search/external): ISRC dedup (Deezer wins), catalog_id
detection, TIDAL graceful degradation, and auth gating.

The service's source helpers (_search_deezer / _search_tidal) are patched, exactly
like test_watchlist_service.py patches _fetch_deezer_playlist — no real HTTP.
"""
from datetime import datetime, timezone

from models import CatalogEntry
from services import external_search_service
from utils import make_normalized_key


def _dz(external_id, title, artist, isrc=None):
    return {
        "source": "deezer",
        "external_id": external_id,
        "title": title,
        "artist": artist,
        "isrc": isrc,
        "duration_ms": 200000,
        "artwork_url": "https://cdn/dz.jpg",
    }


def _td(external_id, title, artist, isrc=None):
    return {
        "source": "tidal",
        "external_id": external_id,
        "title": title,
        "artist": artist,
        "isrc": isrc,
        "duration_ms": 200000,
        "artwork_url": "https://cdn/td.jpg",
    }


# ── Merge / dedup by ISRC ─────────────────────────────────────────────────────

class TestIsrcDedup:
    async def test_same_isrc_keeps_deezer_only(self, db, mocker):
        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Track A", "Artist", isrc="US1234567890")],
        )
        mocker.patch.object(
            external_search_service,
            "_search_tidal",
            return_value=[_td("9", "Track A", "Artist", isrc="US1234567890")],
        )

        resp = await external_search_service.search_external(db, "track a", 20)

        assert len(resp.items) == 1
        assert resp.items[0].source == "deezer"
        assert resp.items[0].external_id == "1"

    async def test_tracks_without_isrc_are_not_merged(self, db, mocker):
        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Track A", "Artist", isrc=None)],
        )
        mocker.patch.object(
            external_search_service,
            "_search_tidal",
            return_value=[_td("9", "Track A", "Artist", isrc=None)],
        )

        resp = await external_search_service.search_external(db, "track a", 20)

        # No ISRC on either side → both kept, Deezer first.
        assert [i.source for i in resp.items] == ["deezer", "tidal"]


# ── catalog_id detection ──────────────────────────────────────────────────────

class TestCatalogDetection:
    async def test_matches_existing_by_isrc(self, db, mocker):
        entry = CatalogEntry(
            title="Known",
            artist="Someone",
            normalized_key=make_normalized_key("Known", "Someone"),
            isrc="US0000000001",
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Different Title", "X", isrc="US0000000001")],
        )
        mocker.patch.object(external_search_service, "_search_tidal", return_value=[])

        resp = await external_search_service.search_external(db, "q", 20)

        assert len(resp.items) == 1
        assert resp.items[0].catalog_id == entry.id

    async def test_matches_existing_by_normalized_key(self, db, mocker):
        entry = CatalogEntry(
            title="Nightcall",
            artist="Kavinsky",
            normalized_key=make_normalized_key("Nightcall", "Kavinsky"),
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        # No ISRC on the hit → falls back to normalized_key match.
        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Nightcall", "Kavinsky", isrc=None)],
        )
        mocker.patch.object(external_search_service, "_search_tidal", return_value=[])

        resp = await external_search_service.search_external(db, "nightcall", 20)

        assert resp.items[0].catalog_id == entry.id

    async def test_unknown_track_has_no_catalog_id(self, db, mocker):
        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Brand New", "Nobody", isrc="US9999999999")],
        )
        mocker.patch.object(external_search_service, "_search_tidal", return_value=[])

        resp = await external_search_service.search_external(db, "q", 20)

        assert resp.items[0].catalog_id is None


# ── TIDAL graceful degradation ────────────────────────────────────────────────

class TestTidalDegradation:
    async def test_tidal_raises_falls_back_to_deezer(self, db, mocker):
        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Track A", "Artist")],
        )
        mocker.patch.object(
            external_search_service,
            "_search_tidal",
            side_effect=RuntimeError("no tidal tokens"),
        )

        resp = await external_search_service.search_external(db, "track a", 20)

        assert [i.source for i in resp.items] == ["deezer"]

    async def test_internal_tidal_helper_returns_empty_on_error(self, mocker):
        # The helper itself swallows source errors (never propagates a 500).
        import workers.source_clients as sc

        mocker.patch.object(sc, "search_tidal", side_effect=RuntimeError("boom"))
        result = await external_search_service._search_tidal("q", 20)
        assert result == []


# ── Endpoint auth gating ──────────────────────────────────────────────────────

class TestEndpointAuth:
    async def test_guest_gets_401(self, client):
        resp = await client.get("/api/search/external", params={"q": "aphex"})
        assert resp.status_code == 401

    async def test_authenticated_gets_200(self, auth_client, mocker):
        mocker.patch.object(
            external_search_service,
            "_search_deezer",
            return_value=[_dz("1", "Windowlicker", "Aphex Twin")],
        )
        mocker.patch.object(external_search_service, "_search_tidal", return_value=[])

        resp = await auth_client.get("/api/search/external", params={"q": "aphex"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"][0]["source"] == "deezer"
        assert body["items"][0]["title"] == "Windowlicker"
