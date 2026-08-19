"""Tests for the Album L3 OPS backfill script (scripts/backfill_albums).

Exercises the network-free ``payload`` source core ``backfill_from_payload``
(extracted from ``main`` so it runs without the CLI) against a real sync SQLite
session (``sync_session`` fixture). The album upsert itself reuses L2's
``apply_album_release_metadata`` — these tests assert the SELECTION + wiring
(candidate = release activity with a payload album_id AND a catalog_id, counts,
idempotence), NOT the upsert threshold (that is L2's own test's job).

The ``deezer`` source is a rate-limited network drain (mocked/skipped per the L3
brief) — not covered here; only its read-only eligibility count is trivial.

Same import/mocking pattern as test_album_upsert.py (redis + curl_cffi are not
installed in the test env and some worker modules import them at load).
"""
import os
import sys
from unittest.mock import MagicMock

# server/api on path (same pattern as test_backfill_set_reliability.py).
_SERVER_API = os.path.join(os.path.dirname(__file__), "../../server/api")
if _SERVER_API not in sys.path:
    sys.path.insert(0, _SERVER_API)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from scripts.backfill_albums import (  # noqa: E402
    _covers_candidates,
    backfill_from_payload,
    count_covers_eligible,
    topup_album_from_data,
)
import scripts.backfill_albums as _bfa  # noqa: E402

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

from models import (  # noqa: E402
    Album,
    ArtistActivity,
    CatalogAlbum,
    CatalogEntry,
)

_seq = 0


def _make_catalog(session):
    global _seq
    _seq += 1
    entry = CatalogEntry(
        title=f"Track {_seq}",
        artist="Artist",
        normalized_key=f"track{_seq}|artist",
    )
    session.add(entry)
    session.commit()
    return entry


def _make_release_activity(session, *, catalog_id, album_id="555", **payload_extra):
    """Insert a release artist_activity carrying an album payload."""
    payload = {
        "album_id": album_id,
        "album_title": "Midnight EP",
        "record_type": "ep",
        "release_date": "2026-03-14",
    }
    payload.update(payload_extra)
    if album_id is None:
        payload.pop("album_id", None)
    global _seq
    _seq += 1
    act = ArtistActivity(
        artist_id=1,
        activity_type="release",
        source="deezer",
        external_id=f"trk-{_seq}",
        catalog_id=catalog_id,
        payload=payload,
    )
    session.add(act)
    session.commit()
    return act


class TestPayloadBackfill:
    def test_creates_album_and_link(self, sync_session):
        entry = _make_catalog(sync_session)
        _make_release_activity(sync_session, catalog_id=entry.id)

        stats = backfill_from_payload(sync_session, apply=True)

        assert stats["scanned"] == 1
        assert stats["albums_created"] == 1
        assert stats["links_created"] == 1
        album = sync_session.query(Album).one()
        assert album.deezer_album_id == "555"
        link = sync_session.query(CatalogAlbum).one()
        assert link.catalog_id == entry.id and link.album_id == album.id

    def test_second_pass_is_idempotent(self, sync_session):
        entry = _make_catalog(sync_session)
        _make_release_activity(sync_session, catalog_id=entry.id)

        first = backfill_from_payload(sync_session, apply=True)
        assert first["albums_created"] == 1 and first["links_created"] == 1

        second = backfill_from_payload(sync_session, apply=True)
        assert second["albums_created"] == 0
        assert second["links_created"] == 0
        assert second["already"] == 1
        assert sync_session.query(Album).count() == 1
        assert sync_session.query(CatalogAlbum).count() == 1

    def test_dry_run_writes_nothing_but_reports_same_counts(self, sync_session):
        entry = _make_catalog(sync_session)
        _make_release_activity(sync_session, catalog_id=entry.id)

        stats = backfill_from_payload(sync_session, apply=False)

        assert stats["albums_created"] == 1 and stats["links_created"] == 1
        assert sync_session.query(Album).count() == 0
        assert sync_session.query(CatalogAlbum).count() == 0

    def test_shared_album_two_catalog_rows_one_album_two_links(self, sync_session):
        a = _make_catalog(sync_session)
        b = _make_catalog(sync_session)
        _make_release_activity(sync_session, catalog_id=a.id, album_id="777")
        _make_release_activity(sync_session, catalog_id=b.id, album_id="777")

        stats = backfill_from_payload(sync_session, apply=True)

        assert stats["albums_created"] == 1  # one distinct deezer_album_id
        assert stats["links_created"] == 2  # both catalog rows linked
        assert sync_session.query(Album).count() == 1
        assert sync_session.query(CatalogAlbum).count() == 2

    def test_activity_without_album_id_is_skipped(self, sync_session):
        entry = _make_catalog(sync_session)
        _make_release_activity(sync_session, catalog_id=entry.id, album_id=None)

        stats = backfill_from_payload(sync_session, apply=True)

        assert stats["scanned"] == 1
        assert stats["no_album_id"] == 1
        assert stats["albums_created"] == 0
        assert sync_session.query(Album).count() == 0

    def test_activity_without_catalog_id_not_selected(self, sync_session):
        # A link-only release card (catalog_id NULL) is out of scope: no catalog row
        # to link the album to.
        _make_release_activity(sync_session, catalog_id=None)

        stats = backfill_from_payload(sync_session, apply=True)

        assert stats["scanned"] == 0
        assert sync_session.query(Album).count() == 0

    def test_metadata_topped_up_from_payload(self, sync_session):
        from datetime import date

        from models import AlbumType

        entry = _make_catalog(sync_session)
        _make_release_activity(sync_session, catalog_id=entry.id)

        backfill_from_payload(sync_session, apply=True)

        album = sync_session.query(Album).one()
        assert album.title == "Midnight EP"
        assert album.record_type == AlbumType.ep
        assert album.release_date == date(2026, 3, 14)

    def test_limit_caps_scanned(self, sync_session):
        for _ in range(3):
            e = _make_catalog(sync_session)
            _make_release_activity(sync_session, catalog_id=e.id, album_id=str(e.id))

        stats = backfill_from_payload(sync_session, apply=True, limit=2, batch_size=1)

        assert stats["scanned"] == 2


def _make_album(session, *, deezer_album_id="900", has_artwork=False, record_type=None):
    global _seq
    _seq += 1
    album = Album(
        title=f"Album {_seq}",
        deezer_album_id=deezer_album_id,
        has_artwork=has_artwork,
        record_type=record_type,
    )
    session.add(album)
    session.commit()
    return album


def _album_payload(album_id=900, **extra):
    """A minimal /album/{id} response: record_type/release_date + a cover."""
    data = {
        "id": album_id,
        "title": "Midnight EP",
        "record_type": "ep",
        "release_date": "2026-03-14",
        "label": "Some Label",
        "cover_medium": "https://deezer/cover_medium.jpg",
        "cover_big": "https://deezer/cover_big.jpg",
    }
    data.update(extra)
    return data


class TestCoversSelection:
    def test_missing_artwork_is_eligible(self, sync_session):
        _make_album(sync_session, has_artwork=False, record_type=None)
        assert count_covers_eligible(sync_session) == 1

    def test_missing_record_type_only_is_eligible(self, sync_session):
        # Has artwork but no record_type → still eligible (metadata catch-up).
        _make_album(sync_session, has_artwork=True, record_type=None)
        assert count_covers_eligible(sync_session) == 1

    def test_complete_album_not_eligible(self, sync_session):
        from models import AlbumType

        _make_album(sync_session, has_artwork=True, record_type=AlbumType.ep)
        assert count_covers_eligible(sync_session) == 0

    def test_null_deezer_id_not_eligible(self, sync_session):
        # An album without a reliable deezer_album_id is never re-fetched.
        _make_album(sync_session, deezer_album_id=None)
        assert count_covers_eligible(sync_session) == 0

    def test_candidates_keyset_returns_eligible_ids(self, sync_session):
        a = _make_album(sync_session, deezer_album_id="901")
        rows = _covers_candidates(sync_session, 0, 50)
        assert [(r[0], r[1]) for r in rows] == [(a.id, "901")]

    def test_count_makes_no_network_call(self, sync_session, monkeypatch):
        # The dry-run path only counts — it must never touch ImageService/network.
        def _boom(*a, **k):
            raise AssertionError("network called during dry-run count")

        monkeypatch.setattr(_bfa.ImageService, "upload_from_url", _boom)
        _make_album(sync_session)
        assert count_covers_eligible(sync_session) == 1


class TestCoversTopup:
    def test_topup_fills_metadata_and_cover(self, sync_session, monkeypatch):
        from datetime import date

        from models import AlbumType

        monkeypatch.setattr(
            _bfa.ImageService, "upload_from_url", lambda *a, **k: True
        )
        album = _make_album(sync_session, has_artwork=False, record_type=None)

        meta_up, cover_up = topup_album_from_data(
            sync_session, album, _album_payload(album_id=int(album.deezer_album_id))
        )
        sync_session.commit()

        assert meta_up is True and cover_up is True
        assert album.record_type == AlbumType.ep
        assert album.release_date == date(2026, 3, 14)
        assert album.has_artwork is True
        # Now complete → drops out of the selection (idempotence).
        assert count_covers_eligible(sync_session) == 0

    def test_topup_is_idempotent(self, sync_session, monkeypatch):
        monkeypatch.setattr(
            _bfa.ImageService, "upload_from_url", lambda *a, **k: True
        )
        album = _make_album(sync_session, has_artwork=False, record_type=None)
        data = _album_payload(album_id=int(album.deezer_album_id))

        topup_album_from_data(sync_session, album, data)
        sync_session.commit()

        # Second pass: nothing left to fill, no cover re-uploaded, no new album.
        meta_up, cover_up = topup_album_from_data(sync_session, album, data)
        sync_session.commit()
        assert meta_up is False and cover_up is False
        assert sync_session.query(Album).count() == 1

    def test_topup_no_cover_when_upload_fails(self, sync_session, monkeypatch):
        # A failed upload leaves has_artwork False → the album stays eligible.
        monkeypatch.setattr(
            _bfa.ImageService, "upload_from_url", lambda *a, **k: False
        )
        album = _make_album(sync_session, has_artwork=False, record_type=None)

        meta_up, cover_up = topup_album_from_data(
            sync_session, album, _album_payload(album_id=int(album.deezer_album_id))
        )
        sync_session.commit()

        assert meta_up is True and cover_up is False
        assert album.has_artwork is False
        assert count_covers_eligible(sync_session) == 1  # still eligible
