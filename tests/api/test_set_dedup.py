"""Tests for L4: merge/materialisation + orchestration (set_dedup_service)."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from models import (
    Artist,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetFlag,
    SetFlagStatus,
    SetFlagType,
    SetTrack,
)
from services.image_service import ImageService
from services.set_dedup_service import (
    FLAG_CONFIDENCE_THRESHOLD,
    GroupMatchResult,
    MatchResult,
    MatchSignals,
    MatchVerdict,
    _validate_part_group,
    apply_match_results,
    attach_pair,
    detach_set_from_parent,
    find_or_create_virtual_parent,
    get_part_candidates,
    match_set,
    materialize_parent,
    pick_best_parent_title,
    sync_parent_metadata,
)


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_set(
    db, title="Test Set", source="trackid", part_number=None, duration_ms=None,
    event_date=None,
):
    s = DJSet(
        title=title, source=source, part_number=part_number,
        duration_ms=duration_ms, event_date=event_date,
    )
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
        # Most-descriptive title chosen (more significant tokens), not the shortest
        assert parent.title == "Long Title Set A"

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

    async def test_created_parent_has_search_text(self, db):
        s1 = await _make_set(db, "Beyoncé @ Coachella [DJ Mix]")
        s2 = await _make_set(db, "Short")

        parent_id, _ = await find_or_create_virtual_parent(
            db, s1.id, s2.id, None, None
        )

        db.expire_all()
        parent = (await db.execute(select(DJSet).where(DJSet.id == parent_id))).scalar_one()
        # search_text is the folded form of the chosen title (accents stripped,
        # punctuation collapsed to spaces).
        assert parent.search_text
        assert parent.search_text == "beyonce coachella dj mix"


# ---------------------------------------------------------------------------
# TestPickBestParentTitle (pure)
# ---------------------------------------------------------------------------


class TestPickBestParentTitle:
    def test_prefers_most_descriptive_over_shortest(self):
        bcs = "BCS @ 314 Scholes, Brooklyn [DJ Mix]"
        barry = "Barry Can't Swim DJ Set (Brooklyn, NYC - 20th June 2026)"
        assert pick_best_parent_title([bcs, barry]) == barry
        # order-independent (winner has strictly more significant tokens)
        assert pick_best_parent_title([barry, bcs]) == barry

    def test_empty_list(self):
        assert pick_best_parent_title([]) == ""

    def test_all_none_or_empty(self):
        assert pick_best_parent_title([None, "", None]) == ""

    def test_ignores_none_and_empty_entries(self):
        assert pick_best_parent_title([None, "Only Real Title", ""]) == "Only Real Title"

    def test_tie_break_prefers_longer_then_first(self):
        # Same significant-token count (2 each) -> longer total length wins.
        assert pick_best_parent_title(["Set Two", "Longer Set"]) == "Longer Set"
        # Full tie (same tokens AND same length) -> stable first.
        assert pick_best_parent_title(["Alpha Bravo", "Gamma Delta"]) == "Alpha Bravo"


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
        confidence=0.95,
    )


def _flag_result(candidate_id):
    return MatchResult(
        candidate_id=candidate_id,
        signals=MatchSignals(
            overlap=0.6, title_sim=0.7, date_match=False, first_track_match=False,
            weighted_overlap=0.55, date_gap_days=12, order_corr=0.8,
        ),
        verdict=MatchVerdict.FLAG,
        flag_type="duplicate_candidate",
        confidence=0.62,
    )


def _nothing_result(candidate_id):
    return MatchResult(
        candidate_id=candidate_id,
        signals=MatchSignals(overlap=0.1, title_sim=0.1, date_match=False, first_track_match=False),
        verdict=MatchVerdict.NOTHING,
        flag_type=None,
        confidence=0.05,
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
        # Stored confidence is the composite score, no longer the raw overlap
        assert flag.confidence == pytest.approx(0.62)
        assert flag.signals["overlap"] == pytest.approx(0.6)
        assert flag.signals["title_sim"] == pytest.approx(0.7)
        assert flag.signals["date_match"] is False
        assert flag.signals["weighted_overlap"] == pytest.approx(0.55)
        assert flag.signals["date_gap_days"] == 12
        assert flag.signals["order_corr"] == pytest.approx(0.8)

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
        # Most-descriptive title (more significant tokens), not the shortest
        assert parent.title == "Long Title For Set A"

        # Both sets attached
        for sid in (s1_id, s2_id):
            s = (await db.execute(select(DJSet).where(DJSet.id == sid))).scalar_one()
            assert s.parent_set_id == parent_id

        # Parent has materialized tracks (4 unique mtids)
        parent_tracks = (
            await db.execute(select(SetTrack).where(SetTrack.set_id == parent_id))
        ).scalars().all()
        assert len(parent_tracks) == 4

    async def test_attaches_to_existing_parent_rematerialises(self, admin_client, db):
        """Reusing an existing parent re-materializes it with the new child."""
        existing_parent = DJSet(source="virtual", title="Parent", is_virtual=True)
        s1 = DJSet(source="trackid", title="Child A")
        s2 = DJSet(source="trackid", title="Child B", channel="Cercle")
        db.add(existing_parent)
        db.add(s1)
        db.add(s2)
        await db.flush()
        s1.parent_set_id = existing_parent.id
        await _add_tracks(db, s1.id, [(1, 0, "T1", "A")])
        await _add_tracks(db, s2.id, [(2, 60_000, "T2", "A")])

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

        parent = await _reload(db, parent_id_expected)
        assert parent.channel == "Cercle"
        assert len(await _parent_tracks(db, parent_id_expected)) == 2

    async def test_attach_to_real_parent_keeps_its_tracks(self, admin_client, db):
        """A real set reused as parent is not rebuilt from its children (invariant #4)."""
        real_parent = DJSet(source="trackid", title="Real Parent", is_virtual=False)
        s1 = DJSet(source="trackid", title="Child A")
        s2 = DJSet(source="trackid", title="Child B")
        db.add_all([real_parent, s1, s2])
        await db.flush()
        s1.parent_set_id = real_parent.id
        await _add_tracks(db, real_parent.id, [(9, 0, "Own Track", "A")])
        await _add_tracks(db, s2.id, [(2, 0, "T2", "A")])
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
        parent_id, flag_id = real_parent.id, f.id

        r = await admin_client.post(f"/api/admin/set-flags/{flag_id}/attach")
        assert r.status_code == 200

        tracks = await _parent_tracks(db, parent_id)
        assert [t.trackid_music_track_id for t in tracks] == [9]


# ---------------------------------------------------------------------------
# C14-dedup-yt — complete virtual parent
# ---------------------------------------------------------------------------


async def _reload(db, set_id):
    db.expire_all()
    return (await db.execute(select(DJSet).where(DJSet.id == set_id))).scalar_one()


async def _parent_tracks(db, parent_id):
    db.expire_all()
    return (
        await db.execute(
            select(SetTrack)
            .where(SetTrack.set_id == parent_id)
            .order_by(SetTrack.position)
        )
    ).scalars().all()


async def _make_family(db, *children):
    """Create a virtual parent + one child per kwargs dict. Returns (parent_id, ids)."""
    parent = DJSet(source="virtual", title="Parent Title", is_virtual=True)
    db.add(parent)
    await db.flush()
    ids = []
    for i, fields in enumerate(children):
        fields = {"source": "trackid", "title": f"Child {i}", **fields}
        child = DJSet(parent_set_id=parent.id, **fields)
        db.add(child)
        await db.flush()
        ids.append(child.id)
    return parent.id, ids


async def _make_artist(db, name):
    artist = Artist(name=name, normalized_name=name.lower())
    db.add(artist)
    await db.flush()
    return artist.id


class TestSyncParentMetadata:
    async def test_no_effect_on_real_set(self, db):
        real = DJSet(source="trackid", title="Real", channel="Mine", source_url="u")
        db.add(real)
        await db.flush()
        db.add(
            DJSet(
                source="trackid", title="C", channel="Other", parent_set_id=real.id
            )
        )
        await db.flush()

        await sync_parent_metadata(db, real.id)

        refreshed = await _reload(db, real.id)
        assert refreshed.channel == "Mine"
        assert refreshed.source_url == "u"

    async def test_no_children_overwrites_nothing(self, db):
        parent = DJSet(
            source="virtual", title="P", is_virtual=True,
            channel="Kept", source_url="kept-url", unreliable=True,
        )
        db.add(parent)
        await db.flush()

        assert await materialize_parent(db, parent.id) == 0

        refreshed = await _reload(db, parent.id)
        assert refreshed.channel == "Kept"
        assert refreshed.source_url == "kept-url"
        assert refreshed.unreliable is True

    async def test_title_and_played_date_untouched(self, db):
        parent_id, _ = await _make_family(
            db, {"title": "Much Longer Child Title", "played_date": date(2024, 1, 1)}
        )
        parent = await _reload(db, parent_id)
        parent.played_date = date(2020, 5, 5)
        await db.flush()

        await sync_parent_metadata(db, parent_id)

        refreshed = await _reload(db, parent_id)
        assert refreshed.title == "Parent Title"
        assert refreshed.played_date == date(2020, 5, 5)

    async def test_source_url_prefers_youtube_child(self, db):
        parent_id, _ = await _make_family(
            db,
            {"source_url": "https://trackid.net/audiostream/a"},
            {"source_url": "https://YouTu.be/abc"},
            {"source_url": "https://www.youtube.com/watch?v=zzz"},
        )
        await sync_parent_metadata(db, parent_id)
        assert (await _reload(db, parent_id)).source_url == "https://YouTu.be/abc"

    async def test_source_url_recognises_youtube_by_source(self, db):
        parent_id, _ = await _make_family(
            db,
            {"source_url": "https://trackid.net/audiostream/a"},
            {"source": "youtube", "source_url": "https://proxy.example/v/1"},
        )
        await sync_parent_metadata(db, parent_id)
        assert (await _reload(db, parent_id)).source_url == "https://proxy.example/v/1"

    async def test_source_url_youtube_child_without_url_falls_back(self, db):
        parent_id, _ = await _make_family(
            db,
            {"source": "youtube", "source_url": None},
            {"source_url": None},
            {"source_url": "https://trackid.net/audiostream/a"},
        )
        await sync_parent_metadata(db, parent_id)
        assert (
            (await _reload(db, parent_id)).source_url
            == "https://trackid.net/audiostream/a"
        )

    async def test_channel_most_frequent(self, db):
        parent_id, _ = await _make_family(
            db,
            {"channel": "Cercle", "channel_canonical": "Cercle"},
            {"channel": "Boiler Room", "channel_canonical": "Boiler Room"},
            {"channel": "Boiler Room", "channel_canonical": "Boiler Room"},
        )
        await sync_parent_metadata(db, parent_id)
        parent = await _reload(db, parent_id)
        assert parent.channel == "Boiler Room"
        assert parent.channel_canonical == "Boiler Room"

    async def test_channel_tie_goes_to_smallest_id(self, db):
        parent_id, _ = await _make_family(
            db,
            {"channel": "First", "channel_canonical": "first"},
            {"channel": "Second", "channel_canonical": "second"},
        )
        await sync_parent_metadata(db, parent_id)
        parent = await _reload(db, parent_id)
        assert parent.channel == "First"
        assert parent.channel_canonical == "first"

    async def test_raw_channel_id_ignored(self, db):
        raw_id = "UC" + "a1_-" * 5 + "bc"
        parent_id, _ = await _make_family(
            db,
            {"channel": raw_id, "channel_canonical": raw_id},
            {"channel": raw_id, "channel_canonical": raw_id},
            {"channel": "Real Name", "channel_canonical": "Real Name"},
        )
        await sync_parent_metadata(db, parent_id)
        parent = await _reload(db, parent_id)
        assert parent.channel == "Real Name"
        assert parent.channel_canonical == "Real Name"

    async def test_only_raw_channel_ids_leave_channel_empty(self, db):
        raw_id = "UC" + "x" * 22
        parent_id, _ = await _make_family(
            db, {"channel": raw_id, "channel_canonical": raw_id}
        )
        await sync_parent_metadata(db, parent_id)
        parent = await _reload(db, parent_id)
        assert parent.channel is None
        assert parent.channel_canonical is None

    async def test_canonical_stays_coherent_with_channel(self, db):
        """Displayed channel and filter value must name the same channel."""
        parent_id, _ = await _make_family(
            db,
            {"channel": "Cercle", "channel_canonical": "Cercle"},
            {"channel": "Boiler Room: Berlin", "channel_canonical": "Boiler Room"},
            {"channel": "Boiler Room: Paris", "channel_canonical": "Boiler Room"},
        )
        await sync_parent_metadata(db, parent_id)
        parent = await _reload(db, parent_id)
        assert parent.channel == "Cercle"
        assert parent.channel_canonical == "Cercle"

    async def test_event_date_single_value_kept(self, db):
        parent_id, _ = await _make_family(
            db, {"event_date": date(2024, 3, 2)}, {"event_date": None},
            {"event_date": date(2024, 3, 2)},
        )
        await sync_parent_metadata(db, parent_id)
        assert (await _reload(db, parent_id)).event_date == date(2024, 3, 2)

    async def test_event_date_conflict_is_none(self, db):
        parent_id, _ = await _make_family(
            db, {"event_date": date(2024, 3, 2)}, {"event_date": date(2024, 3, 9)}
        )
        parent = await _reload(db, parent_id)
        parent.event_date = date(2024, 3, 2)
        await db.flush()

        await sync_parent_metadata(db, parent_id)

        assert (await _reload(db, parent_id)).event_date is None

    async def test_styles_union_stable_without_duplicates(self, db):
        parent_id, _ = await _make_family(
            db,
            {"styles": ["House", "Techno"]},
            {"styles": None},
            {"styles": ["Techno", "Disco"]},
        )
        await sync_parent_metadata(db, parent_id)
        assert (await _reload(db, parent_id)).styles == ["House", "Techno", "Disco"]

    async def test_unreliable_only_when_all_children_are(self, db):
        some_id, _ = await _make_family(db, {"unreliable": True}, {"unreliable": False})
        all_id, _ = await _make_family(db, {"unreliable": True}, {"unreliable": True})

        await sync_parent_metadata(db, some_id)
        await sync_parent_metadata(db, all_id)

        assert (await _reload(db, some_id)).unreliable is False
        assert (await _reload(db, all_id)).unreliable is True

    async def test_artist_links_union_without_duplicate_or_removal(self, db):
        kept = await _make_artist(db, "Kept On Parent")
        shared = await _make_artist(db, "Shared")
        solo = await _make_artist(db, "Solo")
        parent_id, (c1, c2) = await _make_family(db, {}, {})
        db.add_all(
            [
                SetArtist(set_id=parent_id, artist_id=kept, role="host", position=7),
                SetArtist(set_id=c1, artist_id=shared, role="dj", position=0),
                SetArtist(set_id=c2, artist_id=shared, role="guest", position=4),
                SetArtist(set_id=c2, artist_id=solo, role="dj", position=1),
            ]
        )
        await db.flush()

        await sync_parent_metadata(db, parent_id)
        await sync_parent_metadata(db, parent_id)  # idempotent

        db.expire_all()
        links = {
            link.artist_id: (link.role, link.position)
            for link in (
                await db.execute(
                    select(SetArtist).where(SetArtist.set_id == parent_id)
                )
            ).scalars()
        }
        assert links == {
            kept: ("host", 7),
            shared: ("dj", 0),
            solo: ("dj", 1),
        }

    async def test_artwork_copied_from_first_child_having_one(self, db, monkeypatch):
        copies = []

        def fake_copy(bucket, src, dst):
            copies.append((src, dst))
            return True

        monkeypatch.setattr(ImageService, "copy_object", staticmethod(fake_copy))
        parent_id, (_, donor, _) = await _make_family(
            db, {"has_artwork": False}, {"has_artwork": True}, {"has_artwork": True}
        )

        await sync_parent_metadata(db, parent_id)

        assert (await _reload(db, parent_id)).has_artwork is True
        assert copies == [(f"{donor}.jpg", f"{parent_id}.jpg")]

    async def test_failed_artwork_copy_leaves_flag_false(self, db, monkeypatch):
        monkeypatch.setattr(
            ImageService, "copy_object", staticmethod(lambda *_: False)
        )
        parent_id, _ = await _make_family(db, {"has_artwork": True})

        await sync_parent_metadata(db, parent_id)

        assert not (await _reload(db, parent_id)).has_artwork

    async def test_existing_artwork_not_recopied(self, db, monkeypatch):
        def fail_copy(*_):
            raise AssertionError("must not copy")

        monkeypatch.setattr(ImageService, "copy_object", staticmethod(fail_copy))
        parent_id, _ = await _make_family(db, {"has_artwork": True})
        parent = await _reload(db, parent_id)
        parent.has_artwork = True
        await db.flush()

        await sync_parent_metadata(db, parent_id)

        assert (await _reload(db, parent_id)).has_artwork is True


class TestMaterializeParentComplete:
    async def test_non_virtual_set_is_left_untouched(self, db):
        real = DJSet(source="trackid", title="Real", is_virtual=False, duration_ms=5)
        db.add(real)
        await db.flush()
        await _add_tracks(db, real.id, [(9, 0, "Own", "A")])
        child = DJSet(
            source="trackid", title="C", parent_set_id=real.id, duration_ms=99
        )
        db.add(child)
        await db.flush()
        await _add_tracks(db, child.id, [(2, 0, "T2", "A")])
        real_id = real.id

        assert await materialize_parent(db, real_id) == 0

        tracks = await _parent_tracks(db, real_id)
        assert [t.trackid_music_track_id for t in tracks] == [9]
        assert (await _reload(db, real_id)).duration_ms == 5

    async def test_missing_parent_returns_zero(self, db):
        assert await materialize_parent(db, 999_999) == 0

    async def test_apply_match_results_keeps_real_parent_tracks(self, db):
        real = DJSet(source="trackid", title="Real", is_virtual=False)
        db.add(real)
        await db.flush()
        await _add_tracks(db, real.id, [(9, 0, "Own", "A")])
        s1 = DJSet(source="trackid", title="Child", parent_set_id=real.id)
        s2 = DJSet(source="trackid", title="Incoming")
        db.add_all([s1, s2])
        await db.flush()
        await _add_tracks(db, s2.id, [(2, 0, "T2", "A")])
        real_id, s1_id, s2_id = real.id, s1.id, s2.id

        counts = await apply_match_results(db, s2_id, [_auto_result(s1_id)])

        assert counts["attached"] == 1
        tracks = await _parent_tracks(db, real_id)
        assert [t.trackid_music_track_id for t in tracks] == [9]

    async def test_track_fields_preserved_through_duplicates(self, db):
        catalog = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(catalog)
        await db.flush()
        parent_id, (c1, c2) = await _make_family(db, {}, {})
        # c2's three shared tracks align with c1 at a -1000ms offset.
        for set_id, shift in ((c1, 0), (c2, 1000)):
            for pos, mtid in enumerate((1, 2, 3), start=1):
                db.add(
                    SetTrack(
                        set_id=set_id, position=pos, is_id=False,
                        trackid_music_track_id=mtid,
                        raw_title=f"T{mtid}", raw_artist="A",
                        timecode_ms=pos * 10_000 + shift,
                    )
                )
        db.add(
            SetTrack(
                set_id=c1, position=4, is_id=False, trackid_music_track_id=4,
                raw_title="T4", raw_artist="A", timecode_ms=40_000,
                end_time_ms=45_000, label="Label One", catalog_id=catalog.id,
            )
        )
        db.add(
            SetTrack(
                set_id=c2, position=4, is_id=False, trackid_music_track_id=5,
                raw_title="T5", raw_artist="A", timecode_ms=51_000,
                end_time_ms=56_000, label="Label Two",
            )
        )
        await db.flush()
        catalog_id = catalog.id

        await materialize_parent(db, parent_id)

        by_mtid = {
            t.trackid_music_track_id: t for t in await _parent_tracks(db, parent_id)
        }
        assert by_mtid[4].catalog_id == catalog_id
        assert by_mtid[4].label == "Label One"
        assert by_mtid[4].end_time_ms == 45_000
        # end_time_ms follows the alignment offset applied to the timecode.
        assert by_mtid[5].timecode_ms == 50_000
        assert by_mtid[5].end_time_ms == 55_000
        assert by_mtid[5].label == "Label Two"

    async def test_track_fields_preserved_through_parts(self, db):
        parent_id, (c1, c2) = await _make_family(
            db,
            {"part_number": 1, "duration_ms": 60_000},
            {"part_number": 2, "duration_ms": 60_000},
        )
        db.add(
            SetTrack(
                set_id=c1, position=1, is_id=False, trackid_music_track_id=1,
                raw_title="T1", raw_artist="A", timecode_ms=0,
                end_time_ms=5_000, label="L1",
            )
        )
        db.add(
            SetTrack(
                set_id=c2, position=1, is_id=False, trackid_music_track_id=2,
                raw_title="T2", raw_artist="A", timecode_ms=0,
                end_time_ms=5_000, label="L2",
            )
        )
        await db.flush()

        await materialize_parent(db, parent_id)

        tracks = await _parent_tracks(db, parent_id)
        assert [t.label for t in tracks] == ["L1", "L2"]
        assert tracks[1].timecode_ms == 60_000
        assert tracks[1].end_time_ms == 65_000

    async def test_empty_youtube_child_with_part_number_is_not_a_part(self, db):
        parent_id, (trackid_id, _) = await _make_family(
            db,
            {"duration_ms": 3_600_000},
            {"source": "youtube", "part_number": 2, "duration_ms": 3_700_000},
        )
        await _add_tracks(
            db, trackid_id, [(1, 0, "T1", "A"), (2, 60_000, "T2", "A")]
        )

        count = await materialize_parent(db, parent_id)

        assert count == 2
        tracks = await _parent_tracks(db, parent_id)
        assert [t.timecode_ms for t in tracks] == [0, 60_000]
        # Duplicates path, not the parts sum.
        assert (await _reload(db, parent_id)).duration_ms == 3_700_000

    async def test_empty_youtube_child_does_not_shift_or_inflate_parts(self, db):
        parent_id, (p1, p2, _) = await _make_family(
            db,
            {"part_number": 1, "duration_ms": 60_000},
            {"part_number": 3, "duration_ms": 60_000},
            {"source": "youtube", "part_number": 2, "duration_ms": 500_000},
        )
        await _add_tracks(db, p1, [(1, 0, "T1", "A")])
        await _add_tracks(db, p2, [(2, 0, "T2", "A")])

        await materialize_parent(db, parent_id)

        tracks = await _parent_tracks(db, parent_id)
        assert [t.timecode_ms for t in tracks] == [0, 60_000]
        assert (await _reload(db, parent_id)).duration_ms == 120_000

    async def test_all_children_empty_duration_is_max(self, db):
        parent_id, _ = await _make_family(
            db,
            {"part_number": 1, "duration_ms": 1_000},
            {"part_number": 2, "duration_ms": 3_000},
        )

        assert await materialize_parent(db, parent_id) == 0
        assert (await _reload(db, parent_id)).duration_ms == 3_000

    async def test_materialize_syncs_metadata(self, db):
        parent_id, _ = await _make_family(
            db, {"channel": "Cercle", "channel_canonical": "Cercle"}
        )
        await materialize_parent(db, parent_id)
        assert (await _reload(db, parent_id)).channel == "Cercle"


class TestDetachRematerialises:
    async def test_surviving_parent_is_rebuilt_without_the_detached_child(self, db):
        parent_id, (c1, c2, c3) = await _make_family(
            db,
            {"channel": "Gone", "channel_canonical": "Gone"},
            {"channel": "Stays", "channel_canonical": "Stays"},
            {"channel": "Stays", "channel_canonical": "Stays"},
        )
        await _add_tracks(db, c1, [(1, 0, "T1", "A")])
        await _add_tracks(db, c2, [(2, 0, "T2", "A")])
        await _add_tracks(db, c3, [(3, 0, "T3", "A")])
        await materialize_parent(db, parent_id)

        await detach_set_from_parent(db, c1)

        tracks = await _parent_tracks(db, parent_id)
        assert {t.trackid_music_track_id for t in tracks} == {2, 3}
        assert (await _reload(db, parent_id)).channel == "Stays"

    async def test_detach_keeps_artist_link_already_on_parent(self, db):
        artist_id = await _make_artist(db, "Departing DJ")
        parent_id, (c1, _, _) = await _make_family(db, {}, {}, {})
        db.add(SetArtist(set_id=c1, artist_id=artist_id, role="dj", position=0))
        await db.flush()
        await materialize_parent(db, parent_id)

        await detach_set_from_parent(db, c1)

        db.expire_all()
        links = (
            await db.execute(
                select(SetArtist.artist_id).where(SetArtist.set_id == parent_id)
            )
        ).scalars().all()
        assert links == [artist_id]

    async def test_real_parent_with_survivors_keeps_its_tracks(self, db):
        real = DJSet(source="trackid", title="Real", is_virtual=False)
        db.add(real)
        await db.flush()
        await _add_tracks(db, real.id, [(9, 0, "Own", "A")])
        children = [
            DJSet(source="trackid", title=f"C{i}", parent_set_id=real.id)
            for i in range(3)
        ]
        db.add_all(children)
        await db.flush()
        real_id, child_id = real.id, children[0].id

        await detach_set_from_parent(db, child_id)

        tracks = await _parent_tracks(db, real_id)
        assert [t.trackid_music_track_id for t in tracks] == [9]


class TestAttachPair:
    async def test_creates_parent_and_materializes(self, db):
        s1 = await _make_set(db, "Set A")
        s2 = await _make_set(db, "Set B", source="youtube")
        s2.channel = "Cercle"
        await _add_tracks(db, s1.id, [(1, 0, "T1", "A")])
        s1_id, s2_id = s1.id, s2.id

        parent_id = await attach_pair(db, s1_id, s2_id)

        parent = await _reload(db, parent_id)
        assert parent.is_virtual is True
        assert parent.channel == "Cercle"
        assert (await _reload(db, s1_id)).parent_set_id == parent_id
        assert (await _reload(db, s2_id)).parent_set_id == parent_id
        assert len(await _parent_tracks(db, parent_id)) == 1

    async def test_reuses_existing_virtual_parent(self, db):
        parent_id, (child_id,) = await _make_family(db, {})
        other = await _make_set(db, "Other", source="youtube")
        other_id = other.id

        assert await attach_pair(db, other_id, child_id) == parent_id
        assert (await _reload(db, other_id)).parent_set_id == parent_id

    async def test_same_parent_is_accepted(self, db):
        parent_id, (c1, c2) = await _make_family(db, {}, {})
        assert await attach_pair(db, c1, c2) == parent_id

    async def test_different_parents_raises_value_error(self, db):
        _, (a,) = await _make_family(db, {})
        _, (b,) = await _make_family(db, {})
        with pytest.raises(ValueError):
            await attach_pair(db, a, b)

    async def test_real_existing_parent_raises_value_error(self, db):
        real = DJSet(source="trackid", title="Real", is_virtual=False)
        db.add(real)
        await db.flush()
        child = DJSet(source="trackid", title="C", parent_set_id=real.id)
        db.add(child)
        other = await _make_set(db, "Other")
        with pytest.raises(ValueError):
            await attach_pair(db, child.id, other.id)

    async def test_missing_set_raises_lookup_error(self, db):
        s1 = await _make_set(db, "Set A")
        with pytest.raises(LookupError):
            await attach_pair(db, s1.id, 999_999)

    async def test_same_set_twice_raises_value_error(self, db):
        s1 = await _make_set(db, "Set A")
        with pytest.raises(ValueError):
            await attach_pair(db, s1.id, s1.id)

    async def test_virtual_set_raises_value_error(self, db):
        parent_id, (child_id,) = await _make_family(db, {})
        with pytest.raises(ValueError):
            await attach_pair(db, parent_id, child_id)


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
    async def test_coherent_group_attaches_directly(self, db):
        """A part_candidate with coherent dates is ATTACHED at the funnel, not flagged."""
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
        assert counts["attached"] == 1
        assert counts["flagged"] == 0

        db.expire_all()
        s1 = await db.get(DJSet, s1_id)
        s2 = await db.get(DJSet, s2_id)
        assert s1.parent_set_id is not None
        assert s1.parent_set_id == s2.parent_set_id
        parent = await db.get(DJSet, s1.parent_set_id)
        assert parent.is_virtual is True

        # No flag row is created for a direct attach (mirrors the pairwise path)
        flag = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "set"))
        ).scalar_one_or_none()
        assert flag is None

    async def test_divergent_event_dates_group_flagged(self, db):
        """>= 2 distinct event_dates among members → flagged pending, never attached."""
        s1 = await _make_set(db, "Show Part 1", part_number=1,
                             event_date=date(2014, 9, 16))
        s2 = await _make_set(db, "Show Part 2", part_number=2,
                             event_date=date(2015, 1, 20))
        await db.flush()
        s1_id, s2_id = s1.id, s2.id

        gr = GroupMatchResult(
            group_key="show",
            member_set_ids=sorted([s1_id, s2_id]),
            signals={"member_count": 2},
            confidence=0.9,
            flag_type="part_candidate",
        )
        counts = await apply_match_results(db, s1_id, [], [gr])
        assert counts["flagged"] == 1
        assert counts["attached"] == 0

        db.expire_all()
        s1 = await db.get(DJSet, s1_id)
        assert s1.parent_set_id is None
        flag = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "show"))
        ).scalar_one()
        assert flag.status == SetFlagStatus.pending

    async def test_divergent_title_dates_group_flagged(self, db):
        """Differing full dates in the RAW titles (event_date unparsed/NULL) → flagged."""
        s1 = await _make_set(db, "Show 08.10.2022 Part 1", part_number=1)
        s2 = await _make_set(db, "Show 09.10.2022 Part 2", part_number=2)
        await db.flush()
        s1_id = s1.id

        gr = GroupMatchResult(
            group_key="show 2022",
            member_set_ids=sorted([s1_id, s2.id]),
            signals={"member_count": 2},
            confidence=0.9,
            flag_type="part_candidate",
        )
        counts = await apply_match_results(db, s1_id, [], [gr])
        assert counts["flagged"] == 1
        assert counts["attached"] == 0

    async def test_overlap_anomaly_group_flagged(self, db):
        """part_overlap_anomaly is never auto-attached — human review."""
        s1 = await _make_set(db, "Set Part 1", part_number=1)
        s2 = await _make_set(db, "Set Part 2", part_number=2)
        await db.flush()
        s1_id = s1.id

        gr = GroupMatchResult(
            group_key="anomaly",
            member_set_ids=sorted([s1_id, s2.id]),
            signals={"member_count": 2, "pairwise_overlaps_max": 0.5},
            confidence=0.9,
            flag_type="part_overlap_anomaly",
        )
        counts = await apply_match_results(db, s1_id, [], [gr])
        assert counts["flagged"] == 1
        assert counts["attached"] == 0

        flag = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "anomaly"))
        ).scalar_one()
        assert flag.flag_type == SetFlagType.part_overlap_anomaly

    async def test_coherent_group_resolves_pending_flag(self, db):
        """A new part extends a pending group flag → attach + flag flipped 'attached'."""
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
        ids = [s1.id, s2.id, s3.id]

        # Now s3 arrives and extends to 3 members
        gr = GroupMatchResult(
            group_key="folamour",
            member_set_ids=sorted(ids),
            signals={"member_count": 3, "part_numbers": [1, 2, 3]},
            confidence=0.94,
            flag_type="part_candidate",
        )
        counts = await apply_match_results(db, ids[2], [], [gr])
        assert counts["attached"] == 1

        db.expire_all()
        flag = (
            await db.execute(select(SetFlag).where(SetFlag.group_key == "folamour"))
        ).scalar_one()
        assert len(flag.member_set_ids) == 3
        assert flag.confidence == 0.94
        assert flag.status == SetFlagStatus.attached
        assert flag.resolved_at is not None

        parents = set()
        for sid in ids:
            s = await db.get(DJSet, sid)
            parents.add(s.parent_set_id)
        assert len(parents) == 1 and None not in parents

    async def test_divergent_dates_group_extends_pending_flag(self, db):
        """Divergent dates keep the historical behaviour: extend the pending flag."""
        s1 = await _make_set(db, "Show Part 1", part_number=1,
                             event_date=date(2014, 9, 16))
        s2 = await _make_set(db, "Show Part 2", part_number=2,
                             event_date=date(2015, 1, 20))
        s3 = await _make_set(db, "Show Part 3", part_number=3)
        await db.flush()

        existing = SetFlag(
            set_id_a=min(s1.id, s2.id),
            set_id_b=None,
            group_key="show divergent",
            member_set_ids=[s1.id, s2.id],
            flag_type=SetFlagType.part_candidate,
            confidence=0.92,
            signals={"member_count": 2},
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
        db.add(existing)
        await db.flush()

        gr = GroupMatchResult(
            group_key="show divergent",
            member_set_ids=sorted([s1.id, s2.id, s3.id]),
            signals={"member_count": 3},
            confidence=0.94,
            flag_type="part_candidate",
        )
        counts = await apply_match_results(db, s3.id, [], [gr])
        assert counts["flagged"] == 1
        assert counts["attached"] == 0

        db.expire_all()
        flag = (
            await db.execute(
                select(SetFlag).where(SetFlag.group_key == "show divergent")
            )
        ).scalar_one()
        assert flag.status == SetFlagStatus.pending
        assert len(flag.member_set_ids) == 3

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


# ---------------------------------------------------------------------------
# C13.e — event_date in the parts path (integration via match_set)
# ---------------------------------------------------------------------------


async def _make_event_part_set(
    db, title, normalized_title, part_number, part_total, *, event_date, mtids
):
    s = DJSet(
        title=title,
        source="trackid",
        part_number=part_number,
        part_total=part_total,
        normalized_title=normalized_title,
        played_date=event_date,
        event_date=event_date,
        is_virtual=False,
    )
    db.add(s)
    await db.flush()
    for pos, mtid in enumerate(mtids, start=1):
        db.add(
            SetTrack(
                set_id=s.id,
                position=pos,
                timecode_ms=pos * 60_000,
                raw_title=f"Track {mtid}",
                raw_artist="DJ",
                is_id=False,
                trackid_music_track_id=mtid,
            )
        )
    await db.flush()
    return s


class TestPartEventDateHardRule:
    async def test_same_event_date_parts_group_kept(self, db):
        """(b) Two parts of the same set, same event_date, identical base_title →
        the part group is surfaced with a confidence above the flag threshold."""
        base = "dj set live"
        ed = date(2024, 6, 1)
        p1 = await _make_event_part_set(
            db, "DJ Set Live Part 1", f"{base} 1/2", 1, 2,
            event_date=ed, mtids=[1, 2, 3],
        )
        await _make_event_part_set(
            db, "DJ Set Live Part 2", f"{base} 2/2", 2, 2,
            event_date=ed, mtids=[4, 5, 6],
        )

        _, group_results = await match_set(db, p1.id)

        assert len(group_results) == 1
        assert group_results[0].confidence >= FLAG_CONFIDENCE_THRESHOLD
        assert group_results[0].flag_type == "part_candidate"

    async def test_event_dates_apart_no_part_group(self, db):
        """(c) Same base_title, distinct part numbers, but event_dates 14 days apart
        → confidence crushed below threshold → NO group surfaced."""
        base = "dj set live"
        p1 = await _make_event_part_set(
            db, "DJ Set Live Part 1", f"{base} 1/2", 1, 2,
            event_date=date(2024, 6, 1), mtids=[1, 2, 3],
        )
        await _make_event_part_set(
            db, "DJ Set Live Part 2", f"{base} 2/2", 2, 2,
            event_date=date(2024, 6, 15), mtids=[4, 5, 6],
        )

        _, group_results = await match_set(db, p1.id)

        assert group_results == []

    async def test_played_date_only_parts_group_kept(self, db):
        """(d) Non-regression: parts with NO event_date and played_dates 14 days
        apart are NOT crushed (played-date span only maluses beyond 60 days)."""
        base = "dj set live"
        p1 = DJSet(
            title="DJ Set Live Part 1", source="trackid", part_number=1,
            part_total=2, normalized_title=f"{base} 1/2",
            played_date=date(2024, 6, 1), is_virtual=False,
        )
        p2 = DJSet(
            title="DJ Set Live Part 2", source="trackid", part_number=2,
            part_total=2, normalized_title=f"{base} 2/2",
            played_date=date(2024, 6, 15), is_virtual=False,
        )
        db.add_all([p1, p2])
        await db.flush()
        for s, mtids in ((p1, [1, 2, 3]), (p2, [4, 5, 6])):
            for pos, mtid in enumerate(mtids, start=1):
                db.add(
                    SetTrack(
                        set_id=s.id, position=pos, timecode_ms=pos * 60_000,
                        raw_title=f"Track {mtid}", raw_artist="DJ",
                        is_id=False, trackid_music_track_id=mtid,
                    )
                )
        await db.flush()

        _, group_results = await match_set(db, p1.id)

        assert len(group_results) == 1
        assert group_results[0].confidence >= FLAG_CONFIDENCE_THRESHOLD
