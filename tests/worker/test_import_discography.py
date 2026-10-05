"""Tests for the OPS import script (scripts/import_discography) ORCHESTRATION.

Exercises the testable core ``import_discography`` — validation, the per-hit routing
(fresh row enriched + LOW priority stamped, an already-linked row skipped, a
``CatalogEntryMerged`` folded away), the malformed/error accounting, the precision
sample, and dry-run (no commit) vs --apply (per-artist commit). The reused funnel
functions (``bulk_get_or_create_catalog`` / ``enrich_entry`` / the linkers /
``_mark_searched``) are MOCKED — they have their own tests, and ``bulk_get_or_create_
catalog`` uses a Postgres ``ON CONFLICT`` that will not run on SQLite. So this asserts
the script's own wiring against a fake session, not the funnel internals.

Same import/mocking preamble as test_import_set_artists_matches (redis + curl_cffi are
not installed in the test env and workers/* import them at load).
"""
import os
import sys
from unittest.mock import MagicMock

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.catalog_merge import CatalogEntryMerged  # noqa: E402

from scripts import import_discography as mod  # noqa: E402

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


class FakeEntry:
    def __init__(self, eid, deezer_id=None):
        self.id = eid
        self.deezer_id = deezer_id
        self.enrich_priority = None


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _patch_funnel(monkeypatch, *, already=(), merged=()):
    """Mock the reused funnel. Returns the list of entries the fake get-or-create made."""
    made = []
    ids = iter(range(1000, 9000))

    def fake_bulk(session, track_dicts):
        m = {}
        for td in track_dicts:
            nk = mod.make_normalized_key(td["title"], td["artist"])
            e = FakeEntry(next(ids), deezer_id=("D" if td["title"] in already else None))
            m[nk] = e
            made.append(e)
        return m

    def fake_enrich(entry, hit, **kw):
        if hit["title"] in merged:
            raise CatalogEntryMerged(999)
        entry.deezer_id = str(hit["id"])
        return True

    monkeypatch.setattr(mod, "bulk_get_or_create_catalog", fake_bulk)
    monkeypatch.setattr(mod, "enrich_entry", fake_enrich)
    monkeypatch.setattr(mod, "link_catalog_artist_from_hit", lambda *a, **k: None)
    monkeypatch.setattr(mod, "link_catalog_album_from_hit", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_mark_searched", lambda *a, **k: None)
    return made


def _hit(tid, title, artist="A", isrc=None):
    return {"id": tid, "title": title, "artist": {"name": artist}, "isrc": isrc}


def _artist_rec(artist_id, name, hits):
    return {"artist_id": artist_id, "name": name, "tier": "a_lib", "tracks": hits}


def test_basic_apply_enriches_and_stamps_priority(monkeypatch):
    made = _patch_funnel(monkeypatch)
    session = FakeSession()
    records = [_artist_rec(1, "Bicep", [_hit(11, "Cola"), _hit(12, "Breeze")])]
    stats, sample = mod.import_discography(session, records, apply=True)
    assert stats["artists"] == 1
    assert stats["deezer_applied"] == 2
    assert stats["created_or_linked"] == 2
    assert stats["already_deezer"] == 0
    # LOW priority stamped on every enriched entry
    assert all(e.enrich_priority == mod.DISCOGRAPHY_PRIORITY for e in made)
    # per-artist commit in --apply
    assert session.commits == 1
    assert sample == [("Bicep", 2)]


def test_already_deezer_is_skipped(monkeypatch):
    _patch_funnel(monkeypatch, already=("Cola",))
    session = FakeSession()
    records = [_artist_rec(1, "Bicep", [_hit(11, "Cola"), _hit(12, "Breeze")])]
    stats, _ = mod.import_discography(session, records, apply=True)
    assert stats["already_deezer"] == 1
    assert stats["deezer_applied"] == 1


def test_merged_is_counted_not_applied(monkeypatch):
    _patch_funnel(monkeypatch, merged=("Cola",))
    session = FakeSession()
    records = [_artist_rec(1, "Bicep", [_hit(11, "Cola"), _hit(12, "Breeze")])]
    stats, _ = mod.import_discography(session, records, apply=True)
    assert stats["merged"] == 1
    assert stats["deezer_applied"] == 1        # only Breeze


def test_dry_run_does_not_commit(monkeypatch):
    _patch_funnel(monkeypatch)
    session = FakeSession()
    records = [_artist_rec(1, "Bicep", [_hit(11, "Cola")])]
    stats, _ = mod.import_discography(session, records, apply=False)
    assert stats["deezer_applied"] == 1        # funnel still runs for the count
    assert session.commits == 0                # dry-run commits nothing (main rolls back)


def test_artist_with_no_new_tracks(monkeypatch):
    _patch_funnel(monkeypatch)
    session = FakeSession()
    records = [_artist_rec(1, "Bicep", [])]
    stats, sample = mod.import_discography(session, records, apply=True)
    assert stats["artists"] == 1
    assert stats["artists_no_new"] == 1
    assert sample == []


def test_malformed_records_counted(monkeypatch):
    _patch_funnel(monkeypatch)
    session = FakeSession()
    records = [
        mod._MALFORMED,
        {"artist_id": True, "tracks": []},         # bool id
        {"tracks": []},                            # missing id
        {"artist_id": 5, "tracks": "notalist"},    # non-list
        _artist_rec(6, "OK", [_hit(11, "X")]),
    ]
    stats, _ = mod.import_discography(session, records, apply=True)
    assert stats["malformed"] == 4
    assert stats["artists"] == 1


def test_bad_artist_rolls_back_and_continues(monkeypatch):
    _patch_funnel(monkeypatch)

    # make enrich blow up on the FIRST artist's track only
    def boom_enrich(entry, hit, **kw):
        if hit["title"] == "Boom":
            raise RuntimeError("kaboom")
        entry.deezer_id = str(hit["id"])
        return True

    monkeypatch.setattr(mod, "enrich_entry", boom_enrich)
    session = FakeSession()
    records = [
        _artist_rec(1, "Bad", [_hit(11, "Boom")]),
        _artist_rec(2, "Good", [_hit(12, "Fine")]),
    ]
    stats, _ = mod.import_discography(session, records, apply=True)
    assert stats["errors"] == 1
    assert session.rollbacks == 1              # the bad artist rolled back
    assert stats["artists"] == 1               # only the good one counted
    assert stats["deezer_applied"] == 1
