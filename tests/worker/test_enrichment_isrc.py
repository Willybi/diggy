"""Tests for the ISRC conflict resolution in workers/enrichment (A6-04).

_enrich_entry_async guards against IntegrityError on the catalog.isrc unique
constraint with a conditional raw UPDATE. Uses a real sync SQLite session
(sync_session fixture) so the "UPDATE catalog ... NOT EXISTS" statement
actually executes instead of being mocked away.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

# Path so the workers package is importable (same pattern as test_beatport_lock.py)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis and curl_cffi are not installed in the test env; enrichment.py and
# async_http.py import them at module load. Same save/restore dance as
# tests/api/test_enrichment_async.py to avoid polluting other test files.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.enrichment import _enrich_entry_async  # noqa: E402

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

from models import CatalogEntry  # noqa: E402


def _make_hit(isrc, deezer_id=123):
    """Minimal Deezer hit: no album key, so the cover download path is skipped."""
    return {"id": deezer_id, "isrc": isrc, "preview": ""}


def _make_row(session, title, artist, **overrides):
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{title.lower()} - {artist.lower()}",
        has_artwork=True,  # skips the cover upload path
        **overrides,
    )
    session.add(entry)
    session.commit()
    return entry


class TestIsrcConflictResolution:
    async def test_known_isrc_is_skipped(self, sync_session):
        """An ISRC already claimed this batch is never written again."""
        entry = _make_row(sync_session, "Mine", "Y")
        known = {"US123"}

        changed = await _enrich_entry_async(
            entry, _make_hit("US123"), MagicMock(), None, known, session=sync_session
        )

        assert changed is True  # deezer_id was still applied
        assert entry.isrc is None

    async def test_isrc_taken_by_another_row_is_not_written(self, sync_session):
        """The conditional UPDATE must not match when another catalog row
        already owns the ISRC (rowcount == 0 → entry.isrc stays None)."""
        _make_row(sync_session, "Other", "X", isrc="US999")
        entry = _make_row(sync_session, "Mine", "Y")
        known = set()

        changed = await _enrich_entry_async(
            entry, _make_hit("US999"), MagicMock(), None, known, session=sync_session
        )

        assert changed is True  # deezer_id applied, but not the ISRC
        assert entry.isrc is None
        sync_session.commit()
        rows = (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.isrc == "US999")
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].title == "Other"
        # Current behavior: the conflicting ISRC is added to known_isrcs anyway,
        # so later entries in the batch skip it without another round-trip.
        assert "US999" in known

    async def test_free_isrc_is_written(self, sync_session):
        entry = _make_row(sync_session, "Mine", "Y")
        known = set()

        changed = await _enrich_entry_async(
            entry, _make_hit("GB111"), MagicMock(), None, known, session=sync_session
        )

        assert changed is True
        assert entry.isrc == "GB111"
        assert "GB111" in known
        sync_session.commit()
        row = sync_session.execute(
            select(CatalogEntry).where(CatalogEntry.id == entry.id)
        ).scalar_one()
        assert row.isrc == "GB111"

    async def test_no_session_assigns_directly(self):
        """session=None (legacy callers): plain attribute assignment, no SQL."""
        entry = MagicMock()
        entry.id = 1
        entry.deezer_id = None
        entry.isrc = None
        entry.duration_ms = None
        entry.has_preview = False
        entry.has_artwork = True
        entry.scope = "shared"
        pool = MagicMock()
        pool.download_image = AsyncMock(return_value=None)
        known = set()

        changed = await _enrich_entry_async(
            entry, _make_hit("FR222"), pool, None, known, session=None
        )

        assert changed is True
        assert entry.isrc == "FR222"
        assert "FR222" in known
