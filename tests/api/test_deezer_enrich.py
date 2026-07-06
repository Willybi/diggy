"""Tests for server/api/deezer_enrich.py — pure logic tests."""
from unittest.mock import MagicMock, patch

import pytest
from database import Base
from deezer_enrich import (
    _first_artist,
    _is_remix_paren,
    _strip_non_remix_parens,
    _strip_safe_suffixes,
    enrich_entry,
    link_catalog_artist_from_hit,
)
from models import Artist, ArtistAlias, CatalogArtist, CatalogEntry
from services.image_service import ImageService
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class TestStripSafeSuffixes:
    def test_strips_feat(self):
        result = _strip_safe_suffixes("Track (feat. Artist X)")
        assert result == "Track"

    def test_strips_extended_mix(self):
        result = _strip_safe_suffixes("Track (Extended Mix)")
        assert result == "Track"

    def test_strips_remastered(self):
        result = _strip_safe_suffixes("Track (Remastered 2024)")
        assert result == "Track"

    def test_keeps_named_remix(self):
        # Named remix should not be stripped by _strip_safe_suffixes
        result = _strip_safe_suffixes("Track (Adam Port Edit)")
        assert result is None  # no safe suffix found

    def test_none_when_no_suffix(self):
        result = _strip_safe_suffixes("Simple Track")
        assert result is None

    def test_strips_ft(self):
        result = _strip_safe_suffixes("Track (ft. Someone)")
        assert result == "Track"

    def test_strips_brackets(self):
        result = _strip_safe_suffixes("Track [Extended Mix]")
        assert result == "Track"


class TestIsRemixParen:
    def test_named_remix(self):
        assert _is_remix_paren("Adam Port Edit") is True

    def test_generic_mix(self):
        assert _is_remix_paren("Extended Mix") is False

    def test_original_mix(self):
        assert _is_remix_paren("Original Mix") is False

    def test_named_with_generic(self):
        assert _is_remix_paren("Ferry Corsten Radio Edit") is True


class TestStripNonRemixParens:
    def test_strips_generic(self):
        result = _strip_non_remix_parens("Track (Original Mix)")
        assert result == "Track"

    def test_keeps_named_remix(self):
        result = _strip_non_remix_parens("Track (Adam Port Edit)")
        assert result is None  # kept, so no change


class TestFirstArtist:
    def test_comma(self):
        assert _first_artist("A, B") == "A"

    def test_ampersand(self):
        assert _first_artist("A & B") == "A"

    def test_feat(self):
        assert _first_artist("A feat. B") == "A"

    def test_ft(self):
        assert _first_artist("A ft. B") == "A"

    def test_single_artist(self):
        assert _first_artist("CamelPhat") is None


class TestEnrichEntry:
    def test_sets_deezer_id(self):
        entry = MagicMock()
        entry.deezer_id = None
        entry.isrc = None
        entry.duration_ms = None
        entry.has_preview = False
        entry.has_artwork = True
        entry.id = 1

        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://..."}
        result = enrich_entry(entry, hit, s3=None)
        assert result is True
        assert entry.deezer_id == "123"
        assert entry.isrc == "US1234"
        assert entry.duration_ms == 180_000
        assert entry.has_preview is True

    def test_skips_duplicate_isrc(self):
        entry = MagicMock()
        entry.deezer_id = None
        entry.isrc = None
        entry.duration_ms = None
        entry.has_preview = False
        entry.has_artwork = True
        entry.id = 1

        known = {"US1234"}
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}
        enrich_entry(entry, hit, s3=None, _known_isrcs=known)
        assert entry.isrc is None  # not set because already known

    def test_no_change_returns_false(self):
        entry = MagicMock()
        entry.deezer_id = "123"
        entry.isrc = "US1234"
        entry.duration_ms = 180_000
        entry.has_preview = True
        entry.has_artwork = True
        entry.id = 1

        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://..."}
        result = enrich_entry(entry, hit, s3=None)
        assert result is False


class TestImageServiceUploadFromUrl:
    def test_returns_false_for_empty_url(self):
        assert ImageService.upload_from_url("", "bucket", "key.jpg") is False

    def test_returns_false_for_none_url(self):
        assert ImageService.upload_from_url(None, "bucket", "key.jpg") is False

    @patch("services.image_service.requests.get")
    def test_returns_false_for_small_image(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"tiny"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = ImageService.upload_from_url("http://img.jpg", "bucket", "key.jpg")
        assert result is False

    @patch.object(ImageService, "upload_bytes", return_value=True)
    @patch("services.image_service.requests.get")
    def test_returns_true_for_valid_image(self, mock_get, mock_upload):
        mock_resp = MagicMock()
        mock_resp.content = b"x" * 2000
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = ImageService.upload_from_url("http://img.jpg", "bucket", "key.jpg")
        assert result is True
        mock_upload.assert_called_once_with(b"x" * 2000, "bucket", "key.jpg")


# ── Tests for multi-artist linking ──


@pytest.fixture
def sync_session():
    """Sync SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_catalog(session, title="Track", artist="Artist A"):
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{artist}|{title}".lower(),
    )
    session.add(entry)
    session.flush()
    return entry


class TestLinkCatalogArtistFromHit:
    def test_links_single_artist_from_search_hit(self, sync_session):
        entry = _make_catalog(sync_session)
        hit = {"artist": {"id": 100, "name": "Artist A"}}

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        links = sync_session.execute(
            select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
        ).scalars().all()
        assert len(links) == 1
        assert links[0].role == "primary"
        assert links[0].position == 0

    def test_links_multiple_artists_from_contributors(self, sync_session):
        entry = _make_catalog(sync_session)
        hit = {
            "artist": {"id": 100, "name": "Artist A"},
            "contributors": [
                {"id": 100, "name": "Artist A", "role": "Main"},
                {"id": 200, "name": "Artist B", "role": "Featured"},
            ],
        }

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        links = sync_session.execute(
            select(CatalogArtist)
            .where(CatalogArtist.catalog_id == entry.id)
            .order_by(CatalogArtist.position)
        ).scalars().all()
        assert len(links) == 2
        assert links[0].role == "primary"
        assert links[0].position == 0
        assert links[1].role == "featured"
        assert links[1].position == 1

    def test_idempotent_no_duplicates(self, sync_session):
        entry = _make_catalog(sync_session)
        hit = {
            "artist": {"id": 100, "name": "Artist A"},
            "contributors": [
                {"id": 100, "name": "Artist A", "role": "Main"},
                {"id": 200, "name": "Artist B", "role": "Featured"},
            ],
        }

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()
        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        links = sync_session.execute(
            select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
        ).scalars().all()
        assert len(links) == 2

    def test_creates_artist_if_not_exists(self, sync_session):
        entry = _make_catalog(sync_session)
        hit = {"artist": {"id": 999, "name": "New Artist"}}

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        artist = sync_session.execute(
            select(Artist).where(Artist.name == "New Artist")
        ).scalar_one()
        assert artist.deezer_id == "999"

    def test_resolves_via_alias(self, sync_session):
        artist = Artist(name="Official Name", normalized_name="official name")
        sync_session.add(artist)
        sync_session.flush()
        alias = ArtistAlias(
            artist_id=artist.id,
            alias="Alt Name",
            normalized_alias="alt name",
        )
        sync_session.add(alias)
        sync_session.flush()

        entry = _make_catalog(sync_session)
        hit = {"artist": {"id": 50, "name": "Alt Name"}}

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        link = sync_session.execute(
            select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
        ).scalar_one()
        assert link.artist_id == artist.id

    def test_maps_deezer_roles(self, sync_session):
        entry = _make_catalog(sync_session)
        hit = {
            "contributors": [
                {"id": 1, "name": "Main Guy", "role": "Main"},
                {"id": 2, "name": "Feat Guy", "role": "Featured"},
                {"id": 3, "name": "Unknown Role", "role": "SomeOther"},
            ],
        }

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        links = sync_session.execute(
            select(CatalogArtist)
            .where(CatalogArtist.catalog_id == entry.id)
            .order_by(CatalogArtist.position)
        ).scalars().all()
        assert [link.role for link in links] == ["primary", "featured", "primary"]

    def test_falls_back_when_no_contributors(self, sync_session):
        entry = _make_catalog(sync_session)
        # Empty contributors list — should fall back to hit["artist"]
        hit = {
            "artist": {"id": 100, "name": "Solo Artist"},
            "contributors": [],
        }

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        links = sync_session.execute(
            select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
        ).scalars().all()
        assert len(links) == 1
        assert links[0].role == "primary"

    def test_skips_duplicate_contributor_ids(self, sync_session):
        """Deezer sometimes returns same artist twice in contributors."""
        entry = _make_catalog(sync_session)
        hit = {
            "contributors": [
                {"id": 100, "name": "Artist A", "role": "Main"},
                {"id": 100, "name": "Artist A", "role": "Featured"},
            ],
        }

        link_catalog_artist_from_hit(sync_session, entry.id, hit)
        sync_session.flush()

        links = sync_session.execute(
            select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
        ).scalars().all()
        assert len(links) == 1
