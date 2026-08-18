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

from scripts.backfill_albums import backfill_from_payload  # noqa: E402

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
