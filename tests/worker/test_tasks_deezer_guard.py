"""
Regression tests for the uq_artists_deezer_id collision fix in sync_artists.

Two volets:
  (a) The partial unique index is visible in the test schema (create_all on
      SQLite): two artists cannot share a real deezer_id, but the NOT_FOUND
      sentinel may repeat freely.
  (b) The assignment guard _assign_deezer_id refuses a deezer_id already held
      by another row, leaving the newcomer at deezer_id=NULL and logging a
      warning — no crash. The "Åskar"/"Askar" diacritic pair is the real case
      that sent the prod task to the DLQ (2026-07-11): both names pass the local
      dedup check yet resolve to the same Deezer id 1795761.
"""

import importlib.util
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest
from models import Artist
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Mock celery ecosystem before any worker imports (celery is not installed locally)
for _mod in ["celery", "celery.schedules", "celery.signals", "celery._state"]:
    sys.modules.setdefault(_mod, MagicMock())

_SERVER = os.path.join(os.path.dirname(__file__), "../../server")
_API = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in [_SERVER, _API]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# redis / curl_cffi are imported at async_http module load but not installed in
# the test env. Mock them for the artists.py import, then restore (same pattern
# as test_tasks_artist_research.py).
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

# Load artists.py directly to avoid workers.tasks.__init__ pulling all task modules
_artists_path = os.path.join(_SERVER, "workers", "tasks", "artists.py")
_spec = importlib.util.spec_from_file_location("workers.tasks.artists", _artists_path)
_artists_mod = importlib.util.module_from_spec(_spec)
sys.modules["workers.tasks.artists"] = _artists_mod
_spec.loader.exec_module(_artists_mod)

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

_assign_deezer_id = _artists_mod._assign_deezer_id


def _artist(name, **kw):
    return Artist(name=name, normalized_name=name.lower(), **kw)


# ── Volet (a): the constraint exists in the test schema ─────────────────────────


class TestDeezerIdUniqueConstraint:
    def test_duplicate_deezer_id_rejected(self, sync_session):
        """Two artists cannot share the same real deezer_id."""
        sync_session.add(_artist("Åskar", deezer_id="1795761"))
        sync_session.commit()

        sync_session.add(_artist("Askar", deezer_id="1795761"))
        with pytest.raises(IntegrityError):
            sync_session.commit()
        sync_session.rollback()

    def test_not_found_sentinel_may_repeat(self, sync_session):
        """The NOT_FOUND sentinel is excluded from the partial index."""
        sync_session.add(_artist("Ghost One", deezer_id="NOT_FOUND"))
        sync_session.add(_artist("Ghost Two", deezer_id="NOT_FOUND"))
        sync_session.commit()  # must not raise

        rows = sync_session.execute(
            select(Artist).where(Artist.deezer_id == "NOT_FOUND")
        ).scalars().all()
        assert len(rows) == 2

    def test_null_deezer_id_may_repeat(self, sync_session):
        """NULL deezer_id (never searched) never collides."""
        sync_session.add(_artist("Anon One"))
        sync_session.add(_artist("Anon Two"))
        sync_session.commit()  # must not raise


# ── Volet (b): the assignment guard ─────────────────────────────────────────────


class TestAssignDeezerIdGuard:
    def test_assigns_when_free(self):
        used = {"111"}
        a = _artist("Boris Brejcha")
        result = _assign_deezer_id(a, "42", used)
        assert result is True
        assert a.deezer_id == "42"
        assert "42" in used

    def test_no_id_is_noop(self):
        used = set()
        a = _artist("Unknown DJ")
        # None and empty string both mean "no Deezer match": not a collision.
        assert _assign_deezer_id(a, None, used) is None
        assert _assign_deezer_id(a, "", used) is None
        assert a.deezer_id is None
        assert used == set()

    def test_refuses_taken_id_and_logs(self, caplog):
        """The real prod case: 'Askar' resolves to id 1795761 already held by
        'Åskar'. The newcomer stays NULL, no crash, a warning is logged."""
        used = {"1795761"}
        newcomer = _artist("Askar")
        newcomer.id = 999

        with caplog.at_level(logging.WARNING, logger="workers.tasks.artists"):
            result = _assign_deezer_id(newcomer, "1795761", used)

        assert result is False
        assert newcomer.deezer_id is None  # err toward separation, never merge
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("1795761" in r.getMessage() for r in warnings)
        assert any("Askar" in r.getMessage() for r in warnings)

    def test_guard_prevents_integrity_error_at_commit(self, sync_session):
        """End-to-end: the guard keeps the DB commit from tripping the unique
        index. Without it, adding 'Askar' with the same id would raise."""
        sync_session.add(_artist("Åskar", deezer_id="1795761"))
        sync_session.commit()

        used = {
            r[0]
            for r in sync_session.execute(
                select(Artist.deezer_id).where(Artist.deezer_id.isnot(None))
            ).all()
        }

        askar = _artist("Askar")
        sync_session.add(askar)
        sync_session.flush()
        refused = _assign_deezer_id(askar, "1795761", used)

        assert refused is False
        sync_session.commit()  # must not raise IntegrityError
        assert askar.deezer_id is None
