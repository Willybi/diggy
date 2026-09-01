"""Tests for the L1b OPS import script (scripts/import_beatport_matches).

Exercises the testable core ``import_matches`` (extracted from ``main`` so it
runs without the CLI) against a real sync SQLite session (``sync_session``
fixture). Asserts the per-record ROUTING (found→enriched/not_matched,
not_found→marked), the freshness guard (a row already carrying a beatport_id is
skipped, nothing re-stamped), the merged case (the id already belongs to another
same-recording row → folded, dead row NOT marked), malformed-record handling,
and dry-run (no commit) vs --apply (committed).

The script REUSES ``beatport.enrich.enrich_from_beatport`` +
``workers.enrichment._mark_searched`` — these tests do NOT re-test the mapping
(that is those functions' own tests' job); they assert the wiring + accounting.
bp_track dicts deliberately omit ``release.image`` so the artwork branch (the
only network path in enrich_from_beatport) is never taken — no ImageService mock
needed.

Same import/mocking pattern as test_enrich_candidates.py (redis + curl_cffi are
not installed in the test env and workers/enrichment imports them at load).
"""
import itertools
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Make the workers package importable (same pattern as test_enrich_candidates.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from scripts.import_beatport_matches import (  # noqa: E402
    _MALFORMED,
    _read_ndjson,
    import_matches,
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

from models import CatalogEntry  # noqa: E402

_nk = itertools.count(1)
NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)


def _cat(session, **fields):
    """Insert a CatalogEntry with a unique normalized_key; return it."""
    n = next(_nk)
    entry = CatalogEntry(
        title=fields.pop("title", f"Track {n}"),
        artist=fields.pop("artist", f"Artist {n}"),
        normalized_key=fields.pop("normalized_key", f"nk-{n}"),
        **fields,
    )
    session.add(entry)
    session.commit()
    return entry


class TestRouting:
    def test_found_enriches_and_marks(self, sync_session):
        entry = _cat(sync_session)
        record = {
            "catalog_id": entry.id,
            "status": "found",
            "bp_track": {"id": "12345", "bpm": 128, "key": "8A"},
        }

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        assert stats["enriched"] == 1
        assert stats["total"] == 1
        sync_session.refresh(entry)
        assert entry.beatport_id == "12345"
        assert entry.bpm == 128
        assert entry.key == "8A"
        # SQLite drops tzinfo on round-trip; only presence matters here.
        assert entry.beatport_searched_at is not None
        assert entry.beatport_search_attempts == 1

    def test_found_but_no_change_counts_not_matched(self, sync_session):
        # A found row whose bp_track carries nothing enrich_from_beatport writes
        # (no id, no bpm/key/label/genre/date) still records a completed attempt.
        entry = _cat(sync_session)
        record = {"catalog_id": entry.id, "status": "found", "bp_track": {}}

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        assert stats["not_matched"] == 1
        assert stats["enriched"] == 0
        sync_session.refresh(entry)
        assert entry.beatport_id is None
        assert entry.beatport_search_attempts == 1  # attempt still recorded

    def test_not_found_marks_attempt_only(self, sync_session):
        entry = _cat(sync_session)
        record = {"catalog_id": entry.id, "status": "not_found", "bp_track": None}

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        assert stats["not_found_marked"] == 1
        sync_session.refresh(entry)
        assert entry.beatport_id is None
        assert entry.beatport_searched_at is not None
        assert entry.beatport_search_attempts == 1

    def test_missing_catalog_row(self, sync_session):
        record = {"catalog_id": 999999, "status": "found", "bp_track": {"id": "1"}}

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        assert stats["missing"] == 1
        assert stats["enriched"] == 0


class TestFreshnessGuard:
    def test_already_linked_is_skipped_and_not_restamped(self, sync_session):
        # The VPS drain linked this row between the scrape and the import: the
        # import must skip it and never re-stamp the id or the search state.
        entry = _cat(
            sync_session,
            beatport_id="OLD",
            beatport_searched_at=NOW,
            beatport_search_attempts=1,
        )
        record = {
            "catalog_id": entry.id,
            "status": "found",
            "bp_track": {"id": "NEW", "bpm": 140},
        }

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        assert stats["already_linked"] == 1
        assert stats["enriched"] == 0
        sync_session.refresh(entry)
        assert entry.beatport_id == "OLD"  # untouched
        assert entry.bpm is None
        assert entry.beatport_search_attempts == 1  # not incremented


class TestMerged:
    def test_id_owned_by_same_recording_folds_and_does_not_mark(self, sync_session):
        # A pre-existing row already carries the beatport_id AND is the same
        # recording (identical title, no ISRC) → the enriched row is folded into
        # it (CatalogEntryMerged) and NOT marked (twin of enrich_beatport_batch).
        holder = _cat(sync_session, title="Meridian", beatport_id="999")
        loser = _cat(sync_session, title="Meridian")
        record = {
            "catalog_id": loser.id,
            "status": "found",
            "bp_track": {"id": "999", "bpm": 122},
        }

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        assert stats["merged"] == 1
        assert stats["enriched"] == 0
        # The loser row was folded into the canonical and deleted.
        assert sync_session.get(CatalogEntry, loser.id) is None
        assert sync_session.get(CatalogEntry, holder.id) is not None


class TestMalformed:
    def test_malformed_records_are_counted_and_skip_db(self, sync_session):
        entry = _cat(sync_session)
        records = [
            _MALFORMED,  # bad JSON line
            {"status": "found", "bp_track": {"id": "1"}},  # no catalog_id
            {"catalog_id": True, "status": "found", "bp_track": {}},  # bool id
            {"catalog_id": entry.id, "status": "weird"},  # bad status
            {"catalog_id": entry.id, "status": "found", "bp_track": None},  # found w/o dict
        ]

        stats = import_matches(sync_session, records, apply=True, now=NOW)

        assert stats["malformed"] == 5
        assert stats["total"] == 5
        sync_session.refresh(entry)
        assert entry.beatport_searched_at is None  # nothing written


class TestDryRunVsApply:
    def test_dry_run_computes_counts_but_writes_nothing(self, sync_session):
        entry = _cat(sync_session)
        record = {
            "catalog_id": entry.id,
            "status": "found",
            "bp_track": {"id": "555", "bpm": 130},
        }

        stats = import_matches(sync_session, [record], apply=False, now=NOW)

        # The count is accurate (the reused code ran)...
        assert stats["enriched"] == 1
        # ...but nothing is committed: rolling back discards the in-memory mutation.
        sync_session.rollback()
        entry = sync_session.get(CatalogEntry, entry.id)
        assert entry.beatport_id is None
        assert entry.beatport_searched_at is None

    def test_apply_persists_across_sessions(self, sync_engine):
        from sqlalchemy.orm import Session

        with Session(sync_engine) as s:
            entry = _cat(s)
            entry_id = entry.id
            record = {
                "catalog_id": entry_id,
                "status": "found",
                "bp_track": {"id": "777", "bpm": 124},
            }
            import_matches(s, [record], apply=True, now=NOW)

        # A brand-new session sees the committed write.
        with Session(sync_engine) as s2:
            reloaded = s2.get(CatalogEntry, entry_id)
            assert reloaded.beatport_id == "777"
            assert reloaded.beatport_search_attempts == 1


class TestBatchCommit:
    def test_commits_every_batch(self, sync_engine):
        from sqlalchemy.orm import Session

        with Session(sync_engine) as s:
            entries = [_cat(s) for _ in range(5)]
            records = [
                {
                    "catalog_id": e.id,
                    "status": "found",
                    "bp_track": {"id": f"bp-{e.id}", "bpm": 120},
                }
                for e in entries
            ]
            # commit_every=2 → commits at 2, 4, then a trailing commit for the 5th.
            stats = import_matches(
                s, records, apply=True, commit_every=2, now=NOW
            )
            assert stats["enriched"] == 5

        with Session(sync_engine) as s2:
            linked = (
                s2.query(CatalogEntry)
                .filter(CatalogEntry.beatport_id.isnot(None))
                .count()
            )
            assert linked == 5


class TestDryRunNoArtworkUpload:
    """The L1b correctif: dry-run must make NO external write, including the
    cover upload enrich_from_beatport does via ImageService.upload_from_url. The
    guard suppresses it in dry-run only; --apply uploads normally. Counter
    fidelity is preserved (beatport_id is stamped regardless of artwork)."""

    _BP_WITH_IMAGE = {
        "id": "42",
        "bpm": 126,
        "release": {"image": {"dynamic_uri": "https://cdn.beatport.com/{w}x{h}.jpg"}},
    }

    def test_dry_run_does_not_call_upload(self, sync_session, monkeypatch):
        from services.image_service import ImageService

        spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_from_url", spy)

        entry = _cat(sync_session)
        record = {
            "catalog_id": entry.id,
            "status": "found",
            "bp_track": self._BP_WITH_IMAGE,
        }

        stats = import_matches(sync_session, [record], apply=False, now=NOW)

        # The upload was suppressed for the whole dry-run: the real spy is never hit.
        assert spy.call_count == 0
        # Counter fidelity: beatport_id is stamped by the first branch, so the row
        # still counts as enriched even with the artwork path neutralised.
        assert stats["enriched"] == 1
        # And the spy is restored after the run (guard's finally).
        assert ImageService.upload_from_url is spy

    def test_apply_calls_upload(self, sync_session, monkeypatch):
        from services.image_service import ImageService

        spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_from_url", spy)

        entry = _cat(sync_session)
        record = {
            "catalog_id": entry.id,
            "status": "found",
            "bp_track": self._BP_WITH_IMAGE,
        }

        stats = import_matches(sync_session, [record], apply=True, now=NOW)

        # In --apply the guard is a no-op, so the cover uploads normally.
        assert spy.call_count == 1
        cover_url = spy.call_args.args[0]
        assert cover_url == "https://cdn.beatport.com/500x500.jpg"
        assert stats["enriched"] == 1

    def test_counts_identical_dry_run_vs_apply(self, sync_engine):
        from sqlalchemy.orm import Session

        record = lambda cid: {  # noqa: E731
            "catalog_id": cid,
            "status": "found",
            "bp_track": dict(self._BP_WITH_IMAGE, id="900"),
        }

        with Session(sync_engine) as s:
            e = _cat(s)
            dry = import_matches(s, [record(e.id)], apply=False, now=NOW)
            s.rollback()
            apply = import_matches(s, [record(e.id)], apply=True, now=NOW)

        # Suppressing the upload in dry-run does not change any counter.
        assert dry == apply
        assert dry["enriched"] == 1


class TestReadNdjson:
    def test_parses_lines_skips_blank_and_flags_bad_json(self):
        import io

        stream = io.StringIO(
            '{"catalog_id": 1, "status": "not_found", "bp_track": null}\n'
            "\n"  # blank line skipped
            "   \n"  # whitespace-only skipped
            "not json at all\n"
            '{"catalog_id": 2, "status": "found", "bp_track": {"id": "x"}}\n'
        )

        out = list(_read_ndjson(stream))

        assert len(out) == 3
        assert out[0] == {"catalog_id": 1, "status": "not_found", "bp_track": None}
        assert out[1] is _MALFORMED
        assert out[2] == {"catalog_id": 2, "status": "found", "bp_track": {"id": "x"}}
