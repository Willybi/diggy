"""Tests for L4: merge/materialisation + orchestration (set_dedup_service)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import DJSet, SetFlag, SetFlagStatus, SetFlagType, SetTrack
from services.set_dedup_service import (
    MatchResult,
    MatchSignals,
    MatchVerdict,
    apply_match_results,
    find_or_create_virtual_parent,
    materialize_parent,
)


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_set(db, title="Test Set", source="trackid", part_number=None, duration_ms=None):
    s = DJSet(title=title, source=source, part_number=part_number, duration_ms=duration_ms)
    db.add(s)
    await db.flush()
    return s


async def _add_tracks(db, set_id, specs):
    """Add tracks. specs = list of (mtid, timecode_ms, title, artist) tuples."""
    for pos, (mtid, tc, title, artist) in enumerate(specs, start=1):
        db.add(
            SetTrack(
                set_id=set_id,
                position=pos,
                timecode_ms=tc,
                raw_title=title,
                raw_artist=artist,
                is_id=False,
                trackid_music_track_id=mtid,
            )
        )
    await db.flush()


# ---------------------------------------------------------------------------
# TestFindOrCreateVirtualParent
# ---------------------------------------------------------------------------


class TestFindOrCreateVirtualParent:
    async def test_creates_parent_when_neither_has_one(self, db):
        s1 = await _make_set(db, "Long Title Set A")
        s2 = await _make_set(db, "Short")
        s1_id, s2_id = s1.id, s2.id  # capture before expire_all

        parent_id, created = await find_or_create_virtual_parent(
            db, s1_id, s2_id, None, None
        )

        assert created is True
        assert isinstance(parent_id, int)

        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.is_virtual is True
        # Shorter title chosen
        assert parent.title == "Short"

        s1_ref = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s1_ref.parent_set_id == parent_id
        assert s2_ref.parent_set_id == parent_id

    async def test_reuses_existing_parent_from_set_a(self, db):
        existing_parent = DJSet(source="virtual", title="Existing", is_virtual=True)
        db.add(existing_parent)
        s1 = await _make_set(db, "Set A")
        s2 = await _make_set(db, "Set B")
        await db.flush()
        s1_id, s2_id, ep_id = s1.id, s2.id, existing_parent.id  # capture before expire_all
        s1.parent_set_id = ep_id
        await db.flush()

        parent_id, created = await find_or_create_virtual_parent(
            db, s1_id, s2_id, None, None
        )

        assert created is False
        assert parent_id == ep_id

        db.expire_all()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s2_ref.parent_set_id == ep_id

    async def test_reuses_existing_parent_from_set_b(self, db):
        existing_parent = DJSet(source="virtual", title="Existing B", is_virtual=True)
        db.add(existing_parent)
        s1 = await _make_set(db, "Set A")
        s2 = await _make_set(db, "Set B")
        await db.flush()
        s1_id, s2_id, ep_id = s1.id, s2.id, existing_parent.id  # capture before expire_all
        s2.parent_set_id = ep_id
        await db.flush()

        parent_id, created = await find_or_create_virtual_parent(
            db, s1_id, s2_id, None, None
        )

        assert created is False
        assert parent_id == ep_id

        db.expire_all()
        s1_ref = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        assert s1_ref.parent_set_id == ep_id

    async def test_uses_provided_title(self, db):
        s1 = await _make_set(db, "Set Alpha")
        s2 = await _make_set(db, "Set Beta")

        parent_id, created = await find_or_create_virtual_parent(
            db, s1.id, s2.id, None, "Custom Title"
        )

        assert created is True
        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.title == "Custom Title"


# ---------------------------------------------------------------------------
# TestMaterializeParentDoublons
# ---------------------------------------------------------------------------


class TestMaterializeParentDoublons:
    async def test_deduplicates_by_mtid(self, db):
        """Two sets with same mtids → parent has deduplicated tracks."""
        s1 = await _make_set(db, "Set A")
        s2 = await _make_set(db, "Set B")

        await _add_tracks(
            db, s1.id,
            [(10, 100, "Track One", "Artist A"),
             (20, 200, "Track Two", "Artist B"),
             (30, 300, "Track Three", "Artist C")],
        )
        # same mtids, timecodes shifted by +10ms
        await _add_tracks(
            db, s2.id,
            [(10, 110, "Track One", "Artist A"),
             (20, 210, "Track Two", "Artist B"),
             (30, 310, "Track Three", "Artist C")],
        )

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        count = await materialize_parent(db, parent_id)

        assert count == 3

        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.is_virtual is True

        tracks = (
            await db.execute(
                select(SetTrack)
                .where(SetTrack.set_id == parent_id)
                .order_by(SetTrack.position)
            )
        ).scalars().all()
        assert len(tracks) == 3
        # Positions are consecutive starting from 1
        assert [t.position for t in tracks] == [1, 2, 3]

    async def test_merges_tracks_from_both_sets(self, db):
        """One track unique to each set + shared tracks → all unique tracks kept."""
        s1 = await _make_set(db, "Set X")
        s2 = await _make_set(db, "Set Y")

        # s1: tracks 10,20,30 (shared) + 40 (unique)
        await _add_tracks(
            db, s1.id,
            [(10, 0, "T1", "A"), (20, 60000, "T2", "A"),
             (30, 120000, "T3", "A"), (40, 180000, "T4", "A")],
        )
        # s2: tracks 10,20,30 (shared) + 50 (unique)
        await _add_tracks(
            db, s2.id,
            [(10, 5000, "T1", "A"), (20, 65000, "T2", "A"),
             (30, 125000, "T3", "A"), (50, 185000, "T5", "A")],
        )

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        count = await materialize_parent(db, parent_id)

        # 4 unique mtids from s1 + 1 unique from s2 = 5
        assert count == 5

        tracks = (
            await db.execute(
                select(SetTrack)
                .where(SetTrack.set_id == parent_id)
                .order_by(SetTrack.position)
            )
        ).scalars().all()
        assert [t.position for t in tracks] == list(range(1, 6))

    async def test_is_virtual_set_to_true(self, db):
        s1 = await _make_set(db, "Set P")
        s2 = await _make_set(db, "Set Q")

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        await materialize_parent(db, parent_id)

        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.is_virtual is True

    async def test_empty_children_returns_zero(self, db):
        """Sets with no tracks → parent has 0 tracks."""
        s1 = await _make_set(db, "Empty A")
        s2 = await _make_set(db, "Empty B")

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        count = await materialize_parent(db, parent_id)

        assert count == 0


# ---------------------------------------------------------------------------
# TestMaterializeParentParties
# ---------------------------------------------------------------------------


class TestMaterializeParentParties:
    async def test_concatenates_parts_in_order(self, db):
        """Two parts → tracks concatenated with timecode offset from part 1 duration."""
        s1 = await _make_set(db, "Set Part 1", part_number=1, duration_ms=60_000)
        s2 = await _make_set(db, "Set Part 2", part_number=2, duration_ms=60_000)

        # Part 1: 3 tracks, timecodes 0 / 20000 / 40000
        await _add_tracks(
            db, s1.id,
            [(1, 0, "Track 1", "DJ"), (2, 20_000, "Track 2", "DJ"), (3, 40_000, "Track 3", "DJ")],
        )
        # Part 2: 3 distinct tracks, timecodes from 0 (will be offset by part1.duration_ms)
        await _add_tracks(
            db, s2.id,
            [(4, 0, "Track 4", "DJ"), (5, 20_000, "Track 5", "DJ"), (6, 40_000, "Track 6", "DJ")],
        )

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        count = await materialize_parent(db, parent_id)

        assert count == 6

        tracks = (
            await db.execute(
                select(SetTrack)
                .where(SetTrack.set_id == parent_id)
                .order_by(SetTrack.position)
            )
        ).scalars().all()
        assert len(tracks) == 6
        assert [t.position for t in tracks] == list(range(1, 7))

        # Part 2 timecodes offset by s1.duration_ms = 60000
        part2_start_idx = 3
        assert tracks[part2_start_idx].timecode_ms == 60_000
        assert tracks[part2_start_idx + 1].timecode_ms == 80_000
        assert tracks[part2_start_idx + 2].timecode_ms == 100_000

    async def test_boundary_dedup_removes_overlap(self, db):
        """Last track of part 1 == first track of part 2 → deduplicated."""
        s1 = await _make_set(db, "Set Pt 1", part_number=1, duration_ms=60_000)
        s2 = await _make_set(db, "Set Pt 2", part_number=2, duration_ms=60_000)

        # Part 1 ends with mtid=99
        await _add_tracks(
            db, s1.id,
            [(10, 0, "Track A", "DJ"), (99, 50_000, "Overlap Track", "DJ")],
        )
        # Part 2 starts with same mtid=99
        await _add_tracks(
            db, s2.id,
            [(99, 0, "Overlap Track", "DJ"), (20, 20_000, "Track B", "DJ")],
        )

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        count = await materialize_parent(db, parent_id)

        # 2 + 2 - 1 boundary dup = 3
        assert count == 3

    async def test_parts_duration_sum_in_parent(self, db):
        """Parent duration_ms = sum of children durations in parts case."""
        s1 = await _make_set(db, "Pt 1", part_number=1, duration_ms=120_000)
        s2 = await _make_set(db, "Pt 2", part_number=2, duration_ms=90_000)

        await _add_tracks(db, s1.id, [(1, 0, "T1", "DJ")])
        await _add_tracks(db, s2.id, [(2, 0, "T2", "DJ")])

        parent_id, _ = await find_or_create_virtual_parent(db, s1.id, s2.id, None, None)
        await materialize_parent(db, parent_id)

        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.duration_ms == 210_000


# ---------------------------------------------------------------------------
# TestApplyMatchResults
# ---------------------------------------------------------------------------


def _auto_result(candidate_id):
    return MatchResult(
        candidate_id=candidate_id,
        signals=MatchSignals(overlap=0.9, title_sim=0.8, date_match=True, first_track_match=True),
        verdict=MatchVerdict.AUTO_ATTACH,
        flag_type=None,
    )


def _flag_result(candidate_id):
    return MatchResult(
        candidate_id=candidate_id,
        signals=MatchSignals(overlap=0.6, title_sim=0.7, date_match=False, first_track_match=False),
        verdict=MatchVerdict.FLAG,
        flag_type="duplicate_candidate",
    )


def _nothing_result(candidate_id):
    return MatchResult(
        candidate_id=candidate_id,
        signals=MatchSignals(overlap=0.1, title_sim=0.1, date_match=False, first_track_match=False),
        verdict=MatchVerdict.NOTHING,
        flag_type=None,
    )


class TestApplyMatchResults:
    async def test_auto_attach_creates_virtual_parent(self, db):
        s1 = await _make_set(db, "Set Auto A")
        s2 = await _make_set(db, "Set Auto B")
        s1_id, s2_id = s1.id, s2.id  # capture before expire_all

        counts = await apply_match_results(db, s1_id, [_auto_result(s2_id)])

        assert counts["attached"] == 1
        assert counts["flagged"] == 0
        assert counts["nothing"] == 0

        db.expire_all()
        s1_ref = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s1_ref.parent_set_id is not None
        assert s1_ref.parent_set_id == s2_ref.parent_set_id

        parent = (
            await db.execute(select(DJSet).where(DJSet.id == s1_ref.parent_set_id))
        ).scalar_one()
        assert parent.is_virtual is True

    async def test_flag_inserts_set_flag(self, db):
        s1 = await _make_set(db, "Set Flag A")
        s2 = await _make_set(db, "Set Flag B")

        counts = await apply_match_results(db, s1.id, [_flag_result(s2.id)])

        assert counts["flagged"] == 1

        flags = (await db.execute(select(SetFlag))).scalars().all()
        assert len(flags) == 1
        flag = flags[0]
        assert flag.set_id_a == min(s1.id, s2.id)
        assert flag.set_id_b == max(s1.id, s2.id)
        assert flag.flag_type == SetFlagType.duplicate_candidate
        assert flag.status == SetFlagStatus.pending
        assert flag.confidence == pytest.approx(0.6)
        assert flag.signals["overlap"] == pytest.approx(0.6)
        assert flag.signals["title_sim"] == pytest.approx(0.7)
        assert flag.signals["date_match"] is False

    async def test_flag_is_idempotent(self, db):
        """Calling apply_match_results twice for the same pair inserts only 1 flag."""
        s1 = await _make_set(db, "Idem A")
        s2 = await _make_set(db, "Idem B")

        result = _flag_result(s2.id)
        counts1 = await apply_match_results(db, s1.id, [result])
        await db.flush()
        counts2 = await apply_match_results(db, s1.id, [result])

        assert counts1["flagged"] == 1
        assert counts2["flagged"] == 0  # already exists

        flags = (await db.execute(select(SetFlag))).scalars().all()
        assert len(flags) == 1

    async def test_flag_canonical_order(self, db):
        """Flag is stored with set_id_a = min(a,b) regardless of call order."""
        s1 = await _make_set(db, "Alpha")
        s2 = await _make_set(db, "Beta")

        # Call with s2 as source set
        await apply_match_results(db, s2.id, [_flag_result(s1.id)])

        flags = (await db.execute(select(SetFlag))).scalars().all()
        assert len(flags) == 1
        assert flags[0].set_id_a == min(s1.id, s2.id)
        assert flags[0].set_id_b == max(s1.id, s2.id)

    async def test_nothing_makes_no_changes(self, db):
        s1 = await _make_set(db, "Nothing A")
        s2 = await _make_set(db, "Nothing B")
        s1_id, s2_id = s1.id, s2.id  # capture before expire_all

        counts = await apply_match_results(db, s1_id, [_nothing_result(s2_id)])

        assert counts["nothing"] == 1
        assert counts["flagged"] == 0
        assert counts["attached"] == 0

        flags = (await db.execute(select(SetFlag))).scalars().all()
        assert len(flags) == 0

        db.expire_all()
        s1_ref = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s1_ref.parent_set_id is None
        assert s2_ref.parent_set_id is None

    async def test_mixed_results(self, db):
        s1 = await _make_set(db, "Source")
        s2 = await _make_set(db, "Candidate Auto")
        s3 = await _make_set(db, "Candidate Flag")
        s4 = await _make_set(db, "Candidate Nothing")

        counts = await apply_match_results(
            db,
            s1.id,
            [
                _auto_result(s2.id),
                _flag_result(s3.id),
                _nothing_result(s4.id),
            ],
        )

        assert counts == {"attached": 1, "flagged": 1, "nothing": 1}


# ---------------------------------------------------------------------------
# TestAttachSetFlagRefactor
# ---------------------------------------------------------------------------


class TestAttachSetFlagRefactor:
    async def test_parent_has_tracks_after_attach(self, admin_client, db):
        """After attach, the virtual parent must have materialized set_tracks."""
        s1 = DJSet(source="trackid", title="Long Title For Set A")
        s2 = DJSet(source="trackid", title="Short")
        db.add(s1)
        db.add(s2)
        await db.flush()

        # Add 4 tracks with same mtids to both sets
        for i, mtid in enumerate([100, 200, 300, 400]):
            db.add(
                SetTrack(
                    set_id=s1.id, position=i + 1, timecode_ms=i * 60_000,
                    raw_title=f"Track {i + 1}", raw_artist="DJ X",
                    is_id=False, trackid_music_track_id=mtid,
                )
            )
            db.add(
                SetTrack(
                    set_id=s2.id, position=i + 1, timecode_ms=i * 60_000 + 5_000,
                    raw_title=f"Track {i + 1}", raw_artist="DJ X",
                    is_id=False, trackid_music_track_id=mtid,
                )
            )

        f = SetFlag(
            set_id_a=s1.id,
            set_id_b=s2.id,
            flag_type=SetFlagType.duplicate_candidate,
            confidence=0.9,
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
        db.add(f)
        await db.commit()
        s1_id, s2_id, flag_id = s1.id, s2.id, f.id

        r = await admin_client.post(f"/api/admin/set-flags/{flag_id}/attach")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        parent_id = data["parent_id"]

        db.expire_all()

        # Parent is virtual
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.is_virtual is True
        # Shorter title
        assert parent.title == "Short"

        # Both sets attached
        for sid in (s1_id, s2_id):
            s = (await db.execute(select(DJSet).where(DJSet.id == sid))).scalar_one()
            assert s.parent_set_id == parent_id

        # Parent has materialized tracks (4 unique mtids)
        parent_tracks = (
            await db.execute(select(SetTrack).where(SetTrack.set_id == parent_id))
        ).scalars().all()
        assert len(parent_tracks) == 4

    async def test_attaches_to_existing_parent_no_rematerialise(self, admin_client, db):
        """Reusing an existing parent: created=False → materialize_parent not called again."""
        existing_parent = DJSet(source="virtual", title="Parent", is_virtual=True)
        s1 = DJSet(source="trackid", title="Child A")
        s2 = DJSet(source="trackid", title="Child B")
        db.add(existing_parent)
        db.add(s1)
        db.add(s2)
        await db.flush()
        s1.parent_set_id = existing_parent.id

        f = SetFlag(
            set_id_a=s1.id,
            set_id_b=s2.id,
            flag_type=SetFlagType.duplicate_candidate,
            confidence=0.7,
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
        db.add(f)
        await db.commit()
        parent_id_expected, s2_id, flag_id = existing_parent.id, s2.id, f.id

        r = await admin_client.post(f"/api/admin/set-flags/{flag_id}/attach")
        assert r.status_code == 200
        assert r.json()["parent_id"] == parent_id_expected

        db.expire_all()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s2_ref.parent_set_id == parent_id_expected
