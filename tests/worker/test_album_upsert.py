"""Tests for L2 — fil-de-l'eau Album upsert (Deezer).

At every Deezer enrichment/crawl, the track's album is upserted (get-or-create
by ``deezer_album_id``), linked to the catalog row via ``catalog_albums``, and
its cover uploaded once. The release-crawl path additionally tops up the
release-level metadata (record_type / release_date / label) it alone holds.

Covers: idempotent album upsert (a 2nd pass creates no duplicate), single
track→album link, cover upload + has_artwork guard, album without a Deezer id
ignored (invariant #4), and the conservative release-metadata top-up.

Uses a real sync SQLite session (sync_session fixture) so the queries actually
execute — same scaffolding as test_enrichment_m2m_artist.py.
"""
import os
import sys
from datetime import date
from unittest.mock import MagicMock

# Path so the workers package is importable (same pattern as the sibling tests)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis and curl_cffi are not installed in the test env; some worker modules
# import them at module load (kept for parity with the sibling tests).
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.deezer_enrich as deezer_enrich  # noqa: E402
from workers.deezer_enrich import (  # noqa: E402
    _map_album_type,
    _resolve_or_create_album,
    apply_album_release_metadata,
    link_catalog_album_from_hit,
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

from models import Album, AlbumType, CatalogAlbum, CatalogEntry  # noqa: E402


def _make_row(session, title="Track", artist="Artist"):
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{title.lower()}|{artist.lower()}",
    )
    session.add(entry)
    session.commit()
    return entry


def _album_obj(**overrides):
    obj = {
        "id": 555,
        "title": "Midnight EP",
        "cover_medium": "https://cdn.deezer/cover_med.jpg",
        "cover_big": "https://cdn.deezer/cover_big.jpg",
    }
    obj.update(overrides)
    return obj


def _no_upload(monkeypatch):
    """Neutralize the cover upload so tests don't hit the network."""
    monkeypatch.setattr(
        deezer_enrich.ImageService, "upload_from_url", lambda *a, **k: False
    )


# ── _resolve_or_create_album ──────────────────────────────────────────────────


class TestResolveOrCreateAlbum:
    def test_creates_with_title_and_deezer_id(self, sync_session):
        album = _resolve_or_create_album(sync_session, _album_obj(), artist_id=None)

        assert album is not None
        assert album.deezer_album_id == "555"
        assert album.title == "Midnight EP"
        assert album.normalized_title  # populated from the title
        assert sync_session.query(Album).count() == 1

    def test_idempotent_second_pass_no_duplicate(self, sync_session):
        first = _resolve_or_create_album(sync_session, _album_obj())
        sync_session.commit()
        second = _resolve_or_create_album(sync_session, _album_obj(title="Renamed"))

        assert first.id == second.id
        assert sync_session.query(Album).count() == 1
        # An existing album is returned untouched (no metadata clobber).
        assert second.title == "Midnight EP"

    def test_sets_artist_id_on_create(self, sync_session):
        album = _resolve_or_create_album(sync_session, _album_obj(), artist_id=42)
        assert album.artist_id == 42

    def test_empty_object_returns_none(self, sync_session):
        assert _resolve_or_create_album(sync_session, {}) is None
        assert _resolve_or_create_album(sync_session, None) is None
        assert sync_session.query(Album).count() == 0

    def test_missing_id_ignored(self, sync_session):
        # invariant #4: never create an album without a reliable deezer id.
        assert _resolve_or_create_album(sync_session, {"title": "No Id"}) is None
        assert sync_session.query(Album).count() == 0


# ── link_catalog_album_from_hit ───────────────────────────────────────────────


class TestLinkCatalogAlbumFromHit:
    def test_creates_album_and_link(self, sync_session, monkeypatch):
        _no_upload(monkeypatch)
        entry = _make_row(sync_session)
        hit = {"id": 1, "title": "Track", "album": _album_obj()}

        link_catalog_album_from_hit(sync_session, entry.id, hit)
        sync_session.commit()

        assert sync_session.query(Album).count() == 1
        links = sync_session.query(CatalogAlbum).all()
        assert len(links) == 1
        assert links[0].catalog_id == entry.id

    def test_link_created_only_once(self, sync_session, monkeypatch):
        _no_upload(monkeypatch)
        entry = _make_row(sync_session)
        hit = {"id": 1, "title": "Track", "album": _album_obj()}

        link_catalog_album_from_hit(sync_session, entry.id, hit)
        sync_session.commit()
        link_catalog_album_from_hit(sync_session, entry.id, hit)
        sync_session.commit()

        assert sync_session.query(CatalogAlbum).count() == 1
        assert sync_session.query(Album).count() == 1

    def test_uploads_cover_and_sets_has_artwork(self, sync_session, monkeypatch):
        calls = []

        def _fake_upload(url, bucket, key):
            calls.append((url, bucket, key))
            return True

        monkeypatch.setattr(
            deezer_enrich.ImageService, "upload_from_url", _fake_upload
        )
        entry = _make_row(sync_session)
        hit = {"id": 1, "album": _album_obj()}

        link_catalog_album_from_hit(sync_session, entry.id, hit)
        sync_session.commit()

        album = sync_session.query(Album).one()
        assert album.has_artwork is True
        assert len(calls) == 1
        url, bucket, key = calls[0]
        assert url == "https://cdn.deezer/cover_med.jpg"  # cover_medium preferred
        assert key == f"{album.id}.jpg"

    def test_cover_not_reuploaded_when_present(self, sync_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            deezer_enrich.ImageService,
            "upload_from_url",
            lambda *a, **k: calls.append(a) or True,
        )
        # Pre-existing album already covered.
        album = Album(title="Midnight EP", deezer_album_id="555", has_artwork=True)
        sync_session.add(album)
        sync_session.commit()
        entry = _make_row(sync_session)

        link_catalog_album_from_hit(
            sync_session, entry.id, {"id": 1, "album": _album_obj()}
        )
        sync_session.commit()

        assert calls == []  # no upload attempt when has_artwork already True

    def test_hit_without_album_is_noop(self, sync_session, monkeypatch):
        _no_upload(monkeypatch)
        entry = _make_row(sync_session)

        link_catalog_album_from_hit(sync_session, entry.id, {"id": 1})
        sync_session.commit()

        assert sync_session.query(Album).count() == 0
        assert sync_session.query(CatalogAlbum).count() == 0

    def test_album_without_id_ignored(self, sync_session, monkeypatch):
        _no_upload(monkeypatch)
        entry = _make_row(sync_session)

        link_catalog_album_from_hit(
            sync_session, entry.id, {"id": 1, "album": {"title": "No Id"}}
        )
        sync_session.commit()

        assert sync_session.query(Album).count() == 0
        assert sync_session.query(CatalogAlbum).count() == 0


# ── apply_album_release_metadata (releases path) ──────────────────────────────


class TestApplyAlbumReleaseMetadata:
    def test_fills_record_type_release_date_label(self, sync_session):
        obj = _album_obj(
            record_type="ep",
            release_date="2026-03-14",
            label="Some Label",
        )
        album = apply_album_release_metadata(sync_session, obj, artist_id=7)
        sync_session.commit()

        assert album.record_type == AlbumType.ep
        assert album.release_date == date(2026, 3, 14)
        assert album.label == "Some Label"
        assert album.artist_id == 7

    def test_conservative_does_not_overwrite_existing(self, sync_session):
        album = Album(
            title="Midnight EP",
            deezer_album_id="555",
            record_type=AlbumType.album,
            release_date=date(2020, 1, 1),
            label="Original Label",
            artist_id=99,
        )
        sync_session.add(album)
        sync_session.commit()

        apply_album_release_metadata(
            sync_session,
            _album_obj(record_type="single", release_date="2026-03-14", label="New"),
            artist_id=7,
        )
        sync_session.commit()

        sync_session.refresh(album)
        assert album.record_type == AlbumType.album  # unchanged
        assert album.release_date == date(2020, 1, 1)  # unchanged
        assert album.label == "Original Label"  # unchanged
        assert album.artist_id == 99  # unchanged

    def test_tops_up_after_base_upsert(self, sync_session, monkeypatch):
        """The base link upsert creates a bare album; the releases path then
        fills the metadata on the SAME row (idempotent, no duplicate)."""
        _no_upload(monkeypatch)
        entry = _make_row(sync_session)
        link_catalog_album_from_hit(
            sync_session, entry.id, {"id": 1, "album": _album_obj()}
        )
        sync_session.commit()

        apply_album_release_metadata(
            sync_session, _album_obj(record_type="album", release_date="2026-05-01")
        )
        sync_session.commit()

        album = sync_session.query(Album).one()  # still a single row
        assert album.record_type == AlbumType.album
        assert album.release_date == date(2026, 5, 1)

    def test_missing_id_returns_none(self, sync_session):
        assert apply_album_release_metadata(sync_session, {"record_type": "ep"}) is None


# ── _map_album_type ───────────────────────────────────────────────────────────


class TestMapAlbumType:
    def test_known_types(self):
        assert _map_album_type("album") == AlbumType.album
        assert _map_album_type("single") == AlbumType.single
        assert _map_album_type("ep") == AlbumType.ep
        assert _map_album_type("compile") == AlbumType.compile
        assert _map_album_type("compilation") == AlbumType.compile
        assert _map_album_type("EP") == AlbumType.ep  # case-insensitive

    def test_unknown_or_empty(self):
        assert _map_album_type(None) is None
        assert _map_album_type("") is None
        assert _map_album_type("mixtape") is None
