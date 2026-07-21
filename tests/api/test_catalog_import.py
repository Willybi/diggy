"""
Tests for the manual import service + endpoint (services/catalog_service.import_external,
routers/catalog.py POST /api/catalog/import): creation, ISRC/normalized_key dedup,
artist linking, source-specific behaviour (Deezer deezer_id + contributors vs TIDAL
name-only), input validation and auth gating.

The source fetch helpers (_fetch_deezer_track / _fetch_tidal_track) are patched, exactly
like test_external_search.py patches the search helpers — no real HTTP. The artwork
upload is patched so tests depend neither on MinIO nor the network.
"""
from datetime import datetime, timezone

import pytest
from models import Artist, CatalogArtist, CatalogEntry
from services import catalog_service
from sqlalchemy import func, select
from utils import make_normalized_key


def _dz_detail(deezer_id="123", title="New Track", artist="New Artist",
               isrc="US1111111111", contributors=None):
    return {
        "deezer_id": deezer_id,
        "title": title,
        "artist": artist,
        "artists": [],
        "isrc": isrc,
        "duration_ms": 210000,
        "cover_url": "https://cdn/dz.jpg",
        "release_date": None,
        "preview": "https://cdn/preview.mp3",
        "contributors": contributors
        if contributors is not None
        else [{"id": 501, "name": artist, "role": "Main"}],
    }


def _td_detail(title="Tidal Track", artists=None, isrc="US2222222222"):
    # A non-null tidal_artist_id guards against the id leaking into deezer_id:
    # test_links_artist_by_name asserts artist.deezer_id stays None.
    arts = (
        artists
        if artists is not None
        else [{"name": "Tidal Artist", "tidal_artist_id": "9001"}]
    )
    return {
        "title": title,
        "artist": arts[0]["name"] if arts else None,
        "artists": arts,
        "isrc": isrc,
        "duration_ms": 180000,
        "cover_url": "https://cdn/td.jpg",
        "release_date": None,
        "preview": None,
        "contributors": [],
    }


def _mock_artwork(mocker):
    mocker.patch("services.image_service.ImageService.ensure_bucket", return_value=None)
    mocker.patch("services.image_service.ImageService.upload_from_url", return_value=True)


async def _catalog_count(db) -> int:
    return (await db.execute(select(func.count(CatalogEntry.id)))).scalar()


# ── Deezer import ─────────────────────────────────────────────────────────────

class TestImportDeezer:
    async def test_creates_new_shared_entry(self, db, mocker):
        _mock_artwork(mocker)
        mocker.patch.object(
            catalog_service, "_fetch_deezer_track", return_value=_dz_detail()
        )

        out = await catalog_service.import_external(db, deezer_id="123")

        assert out.created is True
        assert out.title == "New Track"
        entry = await db.get(CatalogEntry, out.catalog_id)
        assert entry.scope == "shared"
        assert entry.owner_id is None
        assert entry.deezer_id == "123"
        assert entry.has_preview is True
        assert entry.has_artwork is True

    async def test_links_artist(self, db, mocker):
        _mock_artwork(mocker)
        mocker.patch.object(
            catalog_service, "_fetch_deezer_track", return_value=_dz_detail()
        )

        out = await catalog_service.import_external(db, deezer_id="123")

        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == out.catalog_id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].role == "primary"
        artist = await db.get(Artist, links[0].artist_id)
        assert artist.name == "New Artist"
        assert artist.deezer_id == "501"

    async def test_links_multiple_contributors(self, db, mocker):
        _mock_artwork(mocker)
        mocker.patch.object(
            catalog_service,
            "_fetch_deezer_track",
            return_value=_dz_detail(
                contributors=[
                    {"id": 1, "name": "Main Guy", "role": "Main"},
                    {"id": 2, "name": "Feat Guy", "role": "Featured"},
                ]
            ),
        )

        out = await catalog_service.import_external(db, deezer_id="123")

        links = (
            await db.execute(
                select(CatalogArtist)
                .where(CatalogArtist.catalog_id == out.catalog_id)
                .order_by(CatalogArtist.position)
            )
        ).scalars().all()
        assert [ln.role for ln in links] == ["primary", "featured"]

    async def test_reimport_same_isrc_no_duplicate_and_no_downgrade(self, db, mocker):
        # Pre-existing entry with the same ISRC but no deezer_id.
        entry = CatalogEntry(
            title="Already Here",
            artist="Someone",
            normalized_key=make_normalized_key("Already Here", "Someone"),
            isrc="US1111111111",
            scope="shared",
            deezer_id=None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        before = await _catalog_count(db)

        mocker.patch.object(
            catalog_service, "_fetch_deezer_track", return_value=_dz_detail()
        )

        out = await catalog_service.import_external(db, deezer_id="123")

        assert out.created is False
        assert out.catalog_id == entry.id
        assert await _catalog_count(db) == before  # no duplicate
        await db.refresh(entry)
        assert entry.deezer_id is None  # existing entry not re-enriched

    async def test_reimport_matches_by_deezer_id(self, db, mocker):
        # Pre-existing entry carries deezer_id "123" but neither its ISRC nor its
        # normalized_key matches the incoming track → the deezer_id pre-check must
        # dedup it (X1/L2) instead of creating a second duplicate row.
        entry = CatalogEntry(
            title="Old Title",
            artist="Old Artist",
            normalized_key=make_normalized_key("Old Title", "Old Artist"),
            isrc="US0000000000",
            deezer_id="123",
            scope="shared",
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        before = await _catalog_count(db)

        mocker.patch.object(
            catalog_service,
            "_fetch_deezer_track",
            return_value=_dz_detail(
                deezer_id="123",
                title="Fresh Title",
                artist="Fresh Artist",
                isrc="US9999999999",
            ),
        )

        out = await catalog_service.import_external(db, deezer_id="123")

        assert out.created is False
        assert out.catalog_id == entry.id
        assert await _catalog_count(db) == before  # no duplicate created

    async def test_reimport_matches_by_normalized_key(self, db, mocker):
        entry = CatalogEntry(
            title="Nightcall",
            artist="Kavinsky",
            normalized_key=make_normalized_key("Nightcall", "Kavinsky"),
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        # Hit has no ISRC → dedup must fall back to normalized_key.
        mocker.patch.object(
            catalog_service,
            "_fetch_deezer_track",
            return_value=_dz_detail(
                title="Nightcall", artist="Kavinsky", isrc=None, contributors=[]
            ),
        )

        out = await catalog_service.import_external(db, deezer_id="123")

        assert out.created is False
        assert out.catalog_id == entry.id


# ── TIDAL import ──────────────────────────────────────────────────────────────

class TestImportTidal:
    async def test_creates_without_deezer_id(self, db, mocker):
        _mock_artwork(mocker)
        mocker.patch.object(
            catalog_service, "_fetch_tidal_track", return_value=_td_detail()
        )

        out = await catalog_service.import_external(db, tidal_id="55")

        assert out.created is True
        entry = await db.get(CatalogEntry, out.catalog_id)
        assert entry.deezer_id is None
        assert entry.scope == "shared"

    async def test_links_artist_by_name(self, db, mocker):
        _mock_artwork(mocker)
        mocker.patch.object(
            catalog_service, "_fetch_tidal_track", return_value=_td_detail()
        )

        out = await catalog_service.import_external(db, tidal_id="55")

        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == out.catalog_id)
            )
        ).scalars().all()
        assert len(links) == 1
        artist = await db.get(Artist, links[0].artist_id)
        assert artist.name == "Tidal Artist"
        assert artist.deezer_id is None


# ── Validation & errors (service level) ───────────────────────────────────────

class TestValidation:
    async def test_neither_id_raises_value_error(self, db):
        with pytest.raises(ValueError):
            await catalog_service.import_external(db)

    async def test_both_ids_raise_value_error(self, db):
        with pytest.raises(ValueError):
            await catalog_service.import_external(db, deezer_id="1", tidal_id="2")

    async def test_track_not_found_raises_lookup_error(self, db, mocker):
        mocker.patch.object(
            catalog_service,
            "_fetch_deezer_track",
            side_effect=LookupError("Track not found on Deezer"),
        )
        with pytest.raises(LookupError):
            await catalog_service.import_external(db, deezer_id="999")


# ── Endpoint ──────────────────────────────────────────────────────────────────

class TestImportEndpoint:
    async def test_guest_gets_401(self, client):
        resp = await client.post("/api/catalog/import", json={"deezer_id": "123"})
        assert resp.status_code == 401

    async def test_authenticated_happy_path(self, auth_client, mocker):
        _mock_artwork(mocker)
        mocker.patch.object(
            catalog_service, "_fetch_deezer_track", return_value=_dz_detail()
        )

        resp = await auth_client.post("/api/catalog/import", json={"deezer_id": "123"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is True
        assert body["title"] == "New Track"
        assert body["catalog_id"] > 0

    async def test_track_not_found_returns_404(self, auth_client, mocker):
        mocker.patch.object(
            catalog_service,
            "_fetch_deezer_track",
            side_effect=LookupError("Track not found on Deezer"),
        )
        resp = await auth_client.post("/api/catalog/import", json={"deezer_id": "999"})
        assert resp.status_code == 404

    async def test_both_ids_returns_422(self, auth_client):
        resp = await auth_client.post(
            "/api/catalog/import", json={"deezer_id": "1", "tidal_id": "2"}
        )
        assert resp.status_code == 422

    async def test_neither_id_returns_422(self, auth_client):
        resp = await auth_client.post("/api/catalog/import", json={})
        assert resp.status_code == 422
