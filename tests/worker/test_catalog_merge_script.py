"""Tests for the one-shot dedup script (scripts/dedup_catalog).

Exercises the testable core ``dedup_by_column`` (extracted from ``main`` so it
runs without the CLI) against a real sync SQLite session (``sync_session``
fixture). Builds small duplicate graphs sharing a platform id, plus FK children
on the losers, and asserts a single canonical row survives with every reference
repointed. Same import/path pattern as test_catalog_merge.py.
"""
import itertools
import os
import sys
from datetime import datetime

from sqlalchemy import select

# Make the workers package importable (same pattern as test_catalog_merge.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import (  # noqa: E402
    CatalogArtist,
    CatalogEntry,
    SetTrack,
    UserTrack,
)

from scripts.dedup_catalog import dedup_by_column  # noqa: E402

_nk = itertools.count(1)


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


class TestDryRun:
    def test_dry_run_reports_without_modifying(self, sync_session):
        # Two rows share a deezer_id: dry-run should count 1 group / 1 loser and
        # leave BOTH rows in place.
        a = _cat(sync_session, deezer_id="DZ1", isrc="ISRC-A")  # ISRC => canonical
        b = _cat(sync_session, deezer_id="DZ1")

        stats = dedup_by_column(sync_session, "deezer_id", apply=False)

        assert stats["groups"] == 1
        assert stats["losers"] == 1
        assert stats["examples"] == [("DZ1", a.id, [b.id])]
        # Nothing removed.
        rows = sync_session.execute(select(CatalogEntry)).scalars().all()
        assert {r.id for r in rows} == {a.id, b.id}


class TestApply:
    def test_apply_collapses_group_and_repoints_fks(self, sync_session):
        # 3 rows share a deezer_id; the ISRC-bearing one is the canonical winner.
        canon = _cat(sync_session, deezer_id="DZ2", isrc="ISRC-CANON")
        loser1 = _cat(sync_session, deezer_id="DZ2")
        loser2 = _cat(sync_session, deezer_id="DZ2")
        # FK children hang off the losers — they must survive, repointed.
        sync_session.add(
            CatalogArtist(catalog_id=loser1.id, artist_id=7, role="main", position=0)
        )
        sync_session.add(UserTrack(user_id=3, catalog_id=loser1.id, avis="love"))
        sync_session.add(SetTrack(set_id=1, catalog_id=loser2.id, position=0))
        sync_session.commit()

        stats = dedup_by_column(sync_session, "deezer_id", apply=True)

        assert stats["groups"] == 1
        assert stats["losers"] == 2
        assert stats["deleted"] == 2

        # Exactly one row left for that deezer_id, and it is the canonical.
        survivors = (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.deezer_id == "DZ2")
            )
            .scalars()
            .all()
        )
        assert [s.id for s in survivors] == [canon.id]
        assert sync_session.get(CatalogEntry, loser1.id) is None
        assert sync_session.get(CatalogEntry, loser2.id) is None

        # Every FK child repointed to the canonical.
        assert sync_session.execute(select(CatalogArtist)).scalar_one().catalog_id == (
            canon.id
        )
        ut = sync_session.execute(select(UserTrack)).scalar_one()
        assert ut.catalog_id == canon.id and ut.avis == "love"
        assert sync_session.execute(select(SetTrack)).scalar_one().catalog_id == (
            canon.id
        )

    def test_apply_is_idempotent(self, sync_session):
        _cat(sync_session, deezer_id="DZ3", isrc="ISRC-K")
        _cat(sync_session, deezer_id="DZ3")

        first = dedup_by_column(sync_session, "deezer_id", apply=True)
        assert first["groups"] == 1

        # A second run finds nothing to do.
        second = dedup_by_column(sync_session, "deezer_id", apply=True)
        assert second == {
            "groups": 0,
            "losers": 0,
            "deleted": 0,
            "examples": [],
        }

    def test_deezer_pass_then_beatport_pass_sequential(self, sync_session):
        # r1/r2/r3 all share a deezer_id; r2 & r3 ALSO share a beatport_id.
        # The deezer pass collapses all three; the later beatport pass must
        # re-query the up-to-date state and touch NO deleted row.
        r1 = _cat(
            sync_session, deezer_id="DZ4", isrc="ISRC-R1", created_at=datetime(2019, 1, 1)
        )  # oldest + ISRC => canonical
        _cat(sync_session, deezer_id="DZ4", beatport_id="BP4")
        _cat(sync_session, deezer_id="DZ4", beatport_id="BP4")

        dz = dedup_by_column(sync_session, "deezer_id", apply=True)
        assert dz["groups"] == 1
        assert dz["deleted"] == 2

        # Deezer merge already united everything → the beatport group is gone.
        bp = dedup_by_column(sync_session, "beatport_id", apply=True)
        assert bp["groups"] == 0
        assert bp["deleted"] == 0

        # A single row remains, and it kept both platform ids (null-filled).
        rows = sync_session.execute(select(CatalogEntry)).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == r1.id
        assert rows[0].deezer_id == "DZ4"
        assert rows[0].beatport_id == "BP4"

    def test_beatport_group_independent_of_deezer(self, sync_session):
        # A pure beatport duplicate (no shared deezer_id) is folded by the
        # beatport pass alone.
        canon = _cat(sync_session, beatport_id="BP5", isrc="ISRC-B")
        loser = _cat(sync_session, beatport_id="BP5")

        dz = dedup_by_column(sync_session, "deezer_id", apply=True)
        assert dz["groups"] == 0

        bp = dedup_by_column(sync_session, "beatport_id", apply=True)
        assert bp["groups"] == 1 and bp["deleted"] == 1

        survivors = sync_session.execute(select(CatalogEntry)).scalars().all()
        assert [s.id for s in survivors] == [canon.id]
        assert sync_session.get(CatalogEntry, loser.id) is None
