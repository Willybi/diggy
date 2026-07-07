"""Tests for L4: merge/materialisation + orchestration (set_dedup_service)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import DJSet, SetFlag, SetFlagStatus, SetFlagType, SetTrack
from services.set_dedup_service import (
    GroupMatchResult,
    MatchResult,
    MatchSignals,
    MatchVerdict,
    _validate_part_group,
    apply_match_results,
    find_or_create_virtual_parent,
    get_part_candidates,
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


# ---------------------------------------------------------------------------
# C6.1 — Part group validation (unit-level, no DB)
# ---------------------------------------------------------------------------


class TestValidatePartGroup:
    def test_valid_group(self):
        members = [
            {"id": 1, "part_number": 1, "part_total": 7},
            {"id": 2, "part_number": 2, "part_total": 7},
            {"id": 3, "part_number": 3, "part_total": 7},
        ]
        assert _validate_part_group(members) is True

    def test_duplicate_part_numbers_rejected(self):
        members = [
            {"id": 1, "part_number": 1, "part_total": 7},
            {"id": 2, "part_number": 1, "part_total": 7},
        ]
        assert _validate_part_group(members) is False

    def test_inconsistent_part_totals_rejected(self):
        members = [
            {"id": 1, "part_number": 1, "part_total": 7},
            {"id": 2, "part_number": 2, "part_total": 8},
        ]
        assert _validate_part_group(members) is False

    def test_none_part_totals_ok(self):
        members = [
            {"id": 1, "part_number": 1, "part_total": None},
            {"id": 2, "part_number": 2, "part_total": None},
        ]
        assert _validate_part_group(members) is True

    def test_mixed_none_and_value_ok(self):
        """If some members have no part_total, only check consistency of non-None values."""
        members = [
            {"id": 1, "part_number": 1, "part_total": 7},
            {"id": 2, "part_number": 2, "part_total": None},
        ]
        assert _validate_part_group(members) is True


# ---------------------------------------------------------------------------
# C6.1 — get_part_candidates (integration, SQLite)
# ---------------------------------------------------------------------------


async def _make_part_set(
    db, title, normalized_title, part_number, part_total=None, source="trackid"
):
    s = DJSet(
        title=title,
        source=source,
        part_number=part_number,
        part_total=part_total,
        normalized_title=normalized_title,
        is_virtual=False,
    )
    db.add(s)
    await db.flush()
    return s


class TestGetPartCandidates:
    async def test_finds_folamour_parts(self, db):
        base = "folamour - the very best of folamour - home party series"
        p1 = await _make_part_set(db, "Folamour 1/7", f"{base} 1/7", 1, 7)
        p2 = await _make_part_set(db, "Folamour 2/7", f"{base} 2/7", 2, 7)
        p3 = await _make_part_set(db, "Folamour 3/7", f"{base} 3/7", 3, 7)
        await db.flush()

        # From p1's perspective, should find p2 and p3
        candidates = await get_part_candidates(db, p1.id, 1, f"{base} 1/7")
        candidate_ids = [c["id"] for c in candidates]
        assert p2.id in candidate_ids
        assert p3.id in candidate_ids
        assert p1.id not in candidate_ids

    async def test_no_candidates_without_part_number(self, db):
        """Sets without part_number are excluded even with matching base_title."""
        base = "some set title"
        s = await _make_part_set(db, "Some Set", base, part_number=None)
        # s has no part_number
        s2 = await _make_part_set(db, "Some Set 1/3", f"{base} 1/3", 1, 3)
        await db.flush()

        candidates = await get_part_candidates(db, s2.id, 1, f"{base} 1/3")
        assert not any(c["id"] == s.id for c in candidates)

    async def test_different_base_title_excluded(self, db):
        """Sets from a completely different set are not returned."""
        p1 = await _make_part_set(db, "Folamour 1/7", "folamour series 1/7", 1, 7)
        other = await _make_part_set(
            db, "Other Artist 1/7", "other artist completely different 1/7", 1, 7
        )
        await db.flush()

        candidates = await get_part_candidates(db, p1.id, 1, "folamour series 1/7")
        assert not any(c["id"] == other.id for c in candidates)


# ---------------------------------------------------------------------------
# C6.1 — apply_match_results with group flags (flag lifecycle)
# ---------------------------------------------------------------------------


class TestApplyGroupFlags:
    async def test_creates_group_flag(self, db):
        s1 = await _make_set(db, "Set Part 1", part_number=1)
        s2 = await _make_set(db, "Set Part 2", part_number=2)
        await db.flush()
        s1_id, s2_id = s1.id, s2.id

        gr = GroupMatchResult(
            group_key="set",
            member_set_ids=sorted([s1_id, s2_id]),
            signals={"member_count": 2, "part_numbers": [1, 2], "part_total": None,
                     "pairwise_overlaps_max": 0.0, "title_sim_min": 0.95,
                     "date_span_days": 0, "group_key": "set"},
            confidence=0.95,
            flag_type="part_candidate",
        )

        counts = await apply_match_results(db, s1_id, [], [gr])
        assert counts["flagged"] == 1

        flag = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "set"))
        ).scalar_one_or_none()
        assert flag is not None
        assert flag.flag_type == SetFlagType.part_candidate
        assert flag.set_id_b is None
        assert set(flag.member_set_ids) == {s1_id, s2_id}

    async def test_extends_pending_group_flag(self, db):
        s1 = await _make_set(db, "Set Part 1", part_number=1)
        s2 = await _make_set(db, "Set Part 2", part_number=2)
        s3 = await _make_set(db, "Set Part 3", part_number=3)
        await db.flush()

        # Create initial flag for s1+s2
        existing = SetFlag(
            set_id_a=min(s1.id, s2.id),
            set_id_b=None,
            group_key="folamour",
            member_set_ids=[s1.id, s2.id],
            flag_type=SetFlagType.part_candidate,
            confidence=0.92,
            signals={"member_count": 2},
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
        db.add(existing)
        await db.flush()

        # Now s3 arrives and extends to 3 members
        gr = GroupMatchResult(
            group_key="folamour",
            member_set_ids=sorted([s1.id, s2.id, s3.id]),
            signals={"member_count": 3, "part_numbers": [1, 2, 3]},
            confidence=0.94,
            flag_type="part_candidate",
        )
        counts = await apply_match_results(db, s3.id, [], [gr])
        assert counts["flagged"] == 1

        db.expire_all()
        flag = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "folamour"))
        ).scalar_one()
        assert len(flag.member_set_ids) == 3
        assert flag.confidence == 0.94

    async def test_rejected_flag_not_recreated(self, db):
        s1 = await _make_set(db, "Set Part 1", part_number=1)
        s2 = await _make_set(db, "Set Part 2", part_number=2)
        await db.flush()

        rejected = SetFlag(
            set_id_a=min(s1.id, s2.id),
            set_id_b=None,
            group_key="rejected-group",
            member_set_ids=[s1.id, s2.id],
            flag_type=SetFlagType.part_candidate,
            confidence=0.9,
            signals={},
            status=SetFlagStatus.rejected,
            created_at=_now(),
        )
        db.add(rejected)
        await db.flush()

        gr = GroupMatchResult(
            group_key="rejected-group",
            member_set_ids=[s1.id, s2.id],
            signals={},
            confidence=0.9,
            flag_type="part_candidate",
        )
        counts = await apply_match_results(db, s1.id, [], [gr])
        assert counts["nothing"] == 1
        # Still only one flag
        all_flags = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "rejected-group"))
        ).scalars().all()
        assert len(all_flags) == 1


# ---------------------------------------------------------------------------
# C6.1 — Admin endpoint: attach group flag
# ---------------------------------------------------------------------------


class TestAttachGroupFlag:
    async def test_attach_group_flag_creates_parent(self, db, admin_client):
        p1 = await _make_part_set(db, "DJ Set Part 1", "dj set 1/3", 1, 3)
        p2 = await _make_part_set(db, "DJ Set Part 2", "dj set 2/3", 2, 3)
        p3 = await _make_part_set(db, "DJ Set Part 3", "dj set 3/3", 3, 3)
        await db.flush()
        p1_id, p2_id, p3_id = p1.id, p2.id, p3.id

        flag = SetFlag(
            set_id_a=p1_id,
            set_id_b=None,
            group_key="dj set",
            member_set_ids=[p1_id, p2_id, p3_id],
            flag_type=SetFlagType.part_candidate,
            confidence=0.95,
            signals={"part_numbers": [1, 2, 3], "part_total": 3},
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
        db.add(flag)
        await db.commit()
        flag_id = flag.id

        r = await admin_client.post(f"/api/admin/set-flags/{flag_id}/attach")
        assert r.status_code == 200
        parent_id = r.json()["parent_id"]

        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        assert parent.is_virtual is True
        assert parent.title == "dj set"

        for pid in (p1_id, p2_id, p3_id):
            member = (await db.execute(select(DJSet).where(DJSet.id == pid))).scalar_one()
            assert member.parent_set_id == parent_id

        flag_ref = (await db.execute(select(SetFlag).where(SetFlag.id == flag_id))).scalar_one()
        assert flag_ref.status == SetFlagStatus.attached
