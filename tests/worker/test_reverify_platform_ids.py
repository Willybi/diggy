"""Tests for the X3.c OPS repair script (scripts/reverify_platform_ids).

Exercises the testable core ``reverify_by_column`` (extracted from ``main`` so it
runs without the CLI) against a real sync SQLite session (``sync_session``
fixture). Builds small groups sharing a platform id and asserts that ONLY groups
spanning DISTINCT recordings (an id shared by a remix + its original, an EP id
shared by distinct tracks) are flagged suspect and get their id + E1 search state
cleared — while TRUE-duplicate groups (a single recording under the id) are left
untouched (that is ``dedup_catalog.py``'s job, not this script's). Same
import/path pattern as test_catalog_merge_script.py.
"""
import itertools
import os
import sys
from datetime import datetime

from sqlalchemy import select

# Make the workers package importable (same pattern as test_catalog_merge_script.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import CatalogEntry  # noqa: E402

from scripts.reverify_platform_ids import reverify_by_column  # noqa: E402

_nk = itertools.count(1)
_SEARCHED = datetime(2026, 1, 1)


def _cat(session, *, commit=True, **fields):
    """Insert a CatalogEntry with a unique normalized_key; return it."""
    n = next(_nk)
    entry = CatalogEntry(
        title=fields.pop("title", f"Track {n}"),
        artist=fields.pop("artist", f"Artist {n}"),
        normalized_key=fields.pop("normalized_key", f"nk-{n}"),
        **fields,
    )
    session.add(entry)
    session.commit() if commit else session.flush()
    return entry


class TestSuspectGroups:
    def test_remix_and_original_sharing_id_are_suspect(self, sync_session):
        # A remix inherited the original's deezer_id (Deezer hits[0] bug): distinct
        # recordings under one id → both rows suspect.
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZ1",
            isrc="ISRC-ORIG",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=2,
        )
        remix = _cat(
            sync_session,
            title="Meridian (Julian Muller Remix)",
            deezer_id="DZ1",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=False)

        assert stats["suspect_groups"] == 1
        assert stats["clean_groups"] == 0
        assert stats["suspect_rows"] == 2
        assert stats["reset"] == 0  # dry-run
        assert stats["examples"] == [
            ("DZ1", [(orig.id, "Meridian"), (remix.id, "Meridian (Julian Muller Remix)")])
        ]

    def test_apply_clears_id_and_resets_search_state(self, sync_session):
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZ2",
            isrc="ISRC-ORIG",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=2,
            # beatport state must be left alone by the deezer pass.
            beatport_id="BP-keep",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=3,
        )
        remix = _cat(
            sync_session,
            title="Meridian (Julian Muller Remix)",
            deezer_id="DZ2",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["suspect_rows"] == 2
        assert stats["reset"] == 2

        for row_id in (orig.id, remix.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.deezer_id is None
            assert row.deezer_searched_at is None
            assert row.deezer_search_attempts == 0
        # The deezer pass must not touch the beatport columns.
        keeper = sync_session.get(CatalogEntry, orig.id)
        assert keeper.beatport_id == "BP-keep"
        assert keeper.beatport_searched_at == _SEARCHED
        assert keeper.beatport_search_attempts == 3

    def test_apply_is_idempotent(self, sync_session):
        _cat(sync_session, title="Meridian", deezer_id="DZ3", isrc="ISRC-A")
        _cat(sync_session, title="Meridian (Shed Remix)", deezer_id="DZ3")

        first = reverify_by_column(sync_session, "deezer_id", apply=True)
        assert first["suspect_groups"] == 1 and first["reset"] == 2

        # The cleared ids are NULL, so nothing is shared any more → 0 suspect.
        second = reverify_by_column(sync_session, "deezer_id", apply=True)
        assert second == {
            "suspect_groups": 0,
            "clean_groups": 0,
            "suspect_rows": 0,
            "reset": 0,
            "examples": [],
        }

    def test_mixed_group_clears_even_the_true_duplicate_pair(self, sync_session):
        # An ambiguous group holding a TRUE-duplicate pair AND a distinct remix:
        # the whole group is suspect, so EVERY row (incl. the duplicate pair) is
        # cleared — the assumed X3.c design decision (no row keeps a maybe-wrong id).
        dup_a = _cat(sync_session, title="Meridian", deezer_id="DZ4", isrc="ISRC-A")
        dup_b = _cat(sync_session, title="Meridian", deezer_id="DZ4")  # same recording
        remix = _cat(sync_session, title="Meridian (Shed Remix)", deezer_id="DZ4")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["suspect_rows"] == 3
        assert stats["reset"] == 3
        for row_id in (dup_a.id, dup_b.id, remix.id):
            assert sync_session.get(CatalogEntry, row_id).deezer_id is None

    def test_beatport_column_uses_its_own_search_state(self, sync_session):
        # Same mechanism on the beatport column: an EP beatport_id shared by two
        # distinct remixes → both suspect, beatport state reset.
        remix_a = _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP1",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=2,
        )
        remix_b = _cat(
            sync_session,
            title="Funk Solo (Shed Remix)",
            beatport_id="EP1",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "beatport_id", apply=True)

        assert stats["suspect_groups"] == 1 and stats["reset"] == 2
        for row_id in (remix_a.id, remix_b.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.beatport_id is None
            assert row.beatport_searched_at is None
            assert row.beatport_search_attempts == 0


class TestTrueDuplicatesLeftIntact:
    def test_true_duplicate_group_not_flagged(self, sync_session):
        # Two rows, same title, same deezer_id → a single same-recording cluster.
        # That is dedup_catalog's job, NOT this script's: counted clean, left as-is.
        a = _cat(
            sync_session,
            title="Same Track",
            deezer_id="DZ5",
            isrc="ISRC-A",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )
        b = _cat(sync_session, title="Same Track", deezer_id="DZ5")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 0
        assert stats["clean_groups"] == 1
        assert stats["suspect_rows"] == 0
        assert stats["reset"] == 0
        # Both rows keep their id and (for a) their search state untouched.
        assert sync_session.get(CatalogEntry, a.id).deezer_id == "DZ5"
        assert sync_session.get(CatalogEntry, a.id).deezer_searched_at == _SEARCHED
        assert sync_session.get(CatalogEntry, a.id).deezer_search_attempts == 1
        assert sync_session.get(CatalogEntry, b.id).deezer_id == "DZ5"

    def test_unique_id_and_null_id_ignored(self, sync_session):
        # A row with a solo id and a row with no id at all are never candidates.
        solo = _cat(sync_session, title="Solo", deezer_id="DZ6")
        none = _cat(sync_session, title="NoId")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats == {
            "suspect_groups": 0,
            "clean_groups": 0,
            "suspect_rows": 0,
            "reset": 0,
            "examples": [],
        }
        assert sync_session.get(CatalogEntry, solo.id).deezer_id == "DZ6"
        assert sync_session.get(CatalogEntry, none.id).deezer_id is None


class TestDryRun:
    def test_dry_run_modifies_nothing(self, sync_session):
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZ7",
            isrc="ISRC-A",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=2,
        )
        remix = _cat(
            sync_session,
            title="Meridian (Shed Remix)",
            deezer_id="DZ7",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=False)
        assert stats["suspect_groups"] == 1 and stats["reset"] == 0

        # Nothing changed: ids and search state intact on both rows.
        for row_id, attempts in ((orig.id, 2), (remix.id, 1)):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.deezer_id == "DZ7"
            assert row.deezer_searched_at == _SEARCHED
            assert row.deezer_search_attempts == attempts
