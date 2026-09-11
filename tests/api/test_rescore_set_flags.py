"""Tests for scripts/rescore_set_flags — re-scoring of pending duplicate flags.

Exercises the core ``rescore_flags`` coroutine directly (not via subprocess),
building real ``sets`` / ``set_tracks`` so ``score_pair`` computes genuine signals.
Covers: under-threshold NOTHING → auto-reject; under-threshold but FLAG (date guard)
→ kept; above-threshold → kept; recomputed AUTO_ATTACH → kept without attaching;
group flag left intact; a set gone virtual → non-rescorable & intact; dry-run writes
nothing.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from models import DJSet, SetFlag, SetFlagStatus, SetFlagType, SetTrack
from scripts.rescore_set_flags import (
    DECISION_AUTO_ATTACHED,
    DECISION_EPISODE_REJECTED,
    DECISION_EVENT_REJECTED,
    DECISION_KEPT,
    DECISION_REJECTED,
    DECISION_UNSCORABLE,
    RescoreOutcome,
    _episode_number,
    rescore_flags,
)
from services.set_dedup_service import MatchVerdict


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_set(
    db,
    title="Test Set",
    *,
    normalized_title=None,
    source="trackid",
    part_number=None,
    played_date=None,
    event_date=None,
    is_virtual=False,
):
    s = DJSet(
        title=title,
        source=source,
        normalized_title=normalized_title,
        part_number=part_number,
        played_date=played_date,
        event_date=event_date,
        is_virtual=is_virtual,
    )
    db.add(s)
    await db.flush()
    return s


async def _add_tracks(db, set_id, mtids):
    """Add identified tracks (ordered) with the given mtids."""
    for pos, mtid in enumerate(mtids, start=1):
        db.add(
            SetTrack(
                set_id=set_id,
                position=pos,
                timecode_ms=pos * 1000,
                raw_title=f"Track {mtid}",
                raw_artist="DJ",
                is_id=False,
                trackid_music_track_id=mtid,
            )
        )
    await db.flush()


async def _make_pair_flag(db, set_a, set_b, *, confidence, signals):
    """A pending duplicate_candidate PAIR flag in canonical (min, max) order."""
    f = SetFlag(
        set_id_a=min(set_a, set_b),
        set_id_b=max(set_a, set_b),
        flag_type=SetFlagType.duplicate_candidate,
        confidence=confidence,
        signals=dict(signals),
        status=SetFlagStatus.pending,
        created_at=_now(),
    )
    db.add(f)
    await db.flush()
    return f


# ---------------------------------------------------------------------------
# Auto-reject: under threshold + verdict NOTHING
# ---------------------------------------------------------------------------


class TestAutoReject:
    async def test_low_confidence_nothing_is_rejected(self, db):
        """Two unrelated sets sharing 3 anthems → NOTHING, low conf → auto-rejected."""
        a = await _make_set(db, "Set A", normalized_title="alpha beta gamma")
        b = await _make_set(db, "Set B", normalized_title="delta epsilon zeta")
        # shared {1,2,3}; overlap 3/8 = 0.375; first tracks differ; order shuffled
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5, 6, 7, 8])
        await _add_tracks(db, b.id, [9, 3, 10, 1, 11, 2, 12, 13])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=0.9, signals={"overlap": 0.9}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        assert len(outcomes) == 1
        o = outcomes[0]
        assert o.decision == DECISION_REJECTED
        assert o.verdict == MatchVerdict.NOTHING
        assert o.new_confidence < 0.30
        # Flag mutated: status flipped, marker added, confidence + signals rewritten
        assert flag.status == SetFlagStatus.rejected
        assert flag.signals["auto_rejected"] is True
        assert flag.confidence == pytest.approx(o.new_confidence)
        assert flag.signals["overlap"] == pytest.approx(0.375)
        # Full signals dict written (not just the legacy raw overlap)
        assert set(flag.signals) >= {
            "overlap",
            "title_sim",
            "weighted_overlap",
            "date_gap_days",
            "order_corr",
        }


# ---------------------------------------------------------------------------
# Event-date divergence (L1/L2): NOTHING verdict → rejected regardless of conf
# ---------------------------------------------------------------------------


class TestEventDateSeparated:
    async def test_divergent_event_dates_are_rejected_even_at_high_confidence(
        self, db
    ):
        """Identical tracklists but two RELIABLE event_dates 2 days apart →
        decide_verdict returns NOTHING (distinct performances, L1). The composite
        confidence is HIGH (old cut would KEEP it) yet the flag is rejected and
        counted under the dedicated event-date decision."""
        a = await _make_set(
            db,
            "Artist Live",
            normalized_title="artist live",
            event_date=date(2026, 6, 20),
        )
        b = await _make_set(
            db,
            "Artist Live (2)",
            normalized_title="artist live",
            event_date=date(2026, 6, 22),  # 2 days apart → gap > 1
        )
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5])
        await _add_tracks(db, b.id, [1, 2, 3, 4, 5])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        o = outcomes[0]
        assert o.decision == DECISION_EVENT_REJECTED
        assert o.verdict == MatchVerdict.NOTHING
        assert o.new_confidence >= 0.30  # high confidence, yet rejected
        # Dedicated counter: exactly one event-date rejection
        assert sum(1 for x in outcomes if x.decision == DECISION_EVENT_REJECTED) == 1
        # Flag mutated: rejected + both markers
        assert flag.status == SetFlagStatus.rejected
        assert flag.signals["auto_rejected"] is True
        assert flag.signals["event_date_separated"] is True


# ---------------------------------------------------------------------------
# Kept despite low confidence: date-guard FLAG
# ---------------------------------------------------------------------------


class TestKeptDateGuard:
    async def test_low_confidence_but_flag_verdict_is_kept(self, db):
        """High overlap + similar title + 40-day gap → verdict FLAG at low composite
        confidence. The date guard makes it a LEGIT flag; the script must keep it."""
        a = await _make_set(
            db,
            "Artist X Live Set",
            normalized_title="artist x live set",
            played_date=date(2024, 1, 1),
        )
        b = await _make_set(
            db,
            "Artist X Live",
            normalized_title="artist x live",
            played_date=date(2024, 2, 10),  # 40 days later
        )
        # shared {1,2,3,4}; overlap 4/5 = 0.8; same order
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5])
        await _add_tracks(db, b.id, [1, 2, 3, 4, 6])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=0.8, signals={"overlap": 0.8}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        o = outcomes[0]
        assert o.decision == DECISION_KEPT
        assert o.verdict == MatchVerdict.FLAG
        assert o.new_confidence < 0.30  # genuinely below the cutoff yet kept
        # Kept flags are STILL updated (confidence + signals), status untouched
        assert flag.status == SetFlagStatus.pending
        assert flag.confidence == pytest.approx(o.new_confidence)
        assert "auto_rejected" not in flag.signals
        assert flag.signals["overlap"] == pytest.approx(0.8)
        assert flag.signals["date_gap_days"] == 40


# ---------------------------------------------------------------------------
# Kept above threshold + AUTO_ATTACH never attaches
# ---------------------------------------------------------------------------


class TestKeptAboveThreshold:
    async def test_high_confidence_flag_is_kept_and_updated(self, db):
        """Identical tracklists, 10-day gap → FLAG, composite well above cutoff."""
        a = await _make_set(
            db,
            "Big Room Anthems",
            normalized_title="big room anthems",
            played_date=date(2024, 1, 1),
        )
        b = await _make_set(
            db,
            "Big Room Anthems (reupload)",
            normalized_title="big room anthems",
            played_date=date(2024, 1, 11),  # 10 days → FLAG, not auto-attach
        )
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5])
        await _add_tracks(db, b.id, [1, 2, 3, 4, 5])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        o = outcomes[0]
        assert o.decision == DECISION_KEPT
        assert o.verdict == MatchVerdict.FLAG
        assert o.new_confidence >= 0.30
        assert flag.status == SetFlagStatus.pending
        assert flag.confidence == pytest.approx(o.new_confidence)

    async def test_recomputed_auto_attach_is_kept_never_attached(self, db):
        """Same-day identical sets recompute to AUTO_ATTACH — kept, but the script
        NEVER attaches (no virtual parent created)."""
        d = date(2024, 3, 1)
        a = await _make_set(
            db, "Same Day", normalized_title="same day set", played_date=d
        )
        b = await _make_set(
            db, "Same Day (mirror)", normalized_title="same day set", played_date=d
        )
        a_id, b_id = a.id, b.id
        await _add_tracks(db, a_id, [1, 2, 3, 4, 5])
        await _add_tracks(db, b_id, [1, 2, 3, 4, 5])
        flag = await _make_pair_flag(
            db, a_id, b_id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        o = outcomes[0]
        assert o.verdict == MatchVerdict.AUTO_ATTACH
        assert o.decision == DECISION_KEPT
        assert flag.status == SetFlagStatus.pending
        # No attach happened: neither set got a parent
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        b_ref = (await db.execute(select(DJSet).where(DJSet.id == b_id))).scalar_one()
        assert a_ref.parent_set_id is None
        assert b_ref.parent_set_id is None
        # No virtual parent row created
        virtuals = (
            await db.execute(select(DJSet).where(DJSet.is_virtual.is_(True)))
        ).scalars().all()
        assert virtuals == []


# ---------------------------------------------------------------------------
# Out of scope by default: group flags (only touched with --auto-attach)
# ---------------------------------------------------------------------------


async def _make_group_flag(
    db,
    member_ids,
    *,
    flag_type=SetFlagType.part_candidate,
    group_key="some base title",
    confidence=0.92,
    signals=None,
):
    """A pending GROUP flag (set_id_b NULL, members in member_set_ids)."""
    f = SetFlag(
        set_id_a=min(member_ids),
        set_id_b=None,
        group_key=group_key,
        member_set_ids=list(member_ids),
        flag_type=flag_type,
        confidence=confidence,
        signals=dict(signals or {"member_count": len(member_ids)}),
        status=SetFlagStatus.pending,
        created_at=_now(),
    )
    db.add(f)
    await db.flush()
    return f


class TestGroupFlagIntact:
    async def test_group_flag_is_never_touched(self, db):
        """Without --auto-attach a part_candidate group flag is never re-scored."""
        a = await _make_set(db, "Part 1", part_number=1)
        b = await _make_set(db, "Part 2", part_number=2)
        group_flag = await _make_group_flag(db, [a.id, b.id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        # Not re-scored at all
        assert all(o.flag_id != gf_id for o in outcomes)
        db.expire_all()
        gf = (await db.execute(select(SetFlag).where(SetFlag.id == gf_id))).scalar_one()
        assert gf.flag_type == SetFlagType.part_candidate
        assert gf.confidence == pytest.approx(0.92)
        assert gf.signals == {"member_count": 2}
        assert gf.status == SetFlagStatus.pending


# ---------------------------------------------------------------------------
# Opt-in --auto-attach: part_candidate GROUP flags (structural, no confidence gate)
# ---------------------------------------------------------------------------


class TestGroupAutoAttach:
    async def test_coherent_dates_group_is_attached(self, db):
        """« … PART 1 » + « … PART 2 », same event_date → coherent → attached under a
        shared virtual parent with --auto-attach, no confidence gate."""
        a = await _make_set(
            db, "Boiler Room PART 1", part_number=1, event_date=date(2026, 6, 20)
        )
        b = await _make_set(
            db, "Boiler Room PART 2", part_number=2, event_date=date(2026, 6, 20)
        )
        a_id, b_id = a.id, b.id
        group_flag = await _make_group_flag(db, [a_id, b_id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        group_outcomes = [o for o in outcomes if o.flag_id == gf_id]
        assert len(group_outcomes) == 1
        o = group_outcomes[0]
        assert o.decision == DECISION_AUTO_ATTACHED
        assert o.member_set_ids == [a_id, b_id]
        assert o.set_id_b is None and o.verdict is None
        # attach_flag flipped the status in-session (the caller's commit flushes it —
        # like the pairwise attach test, assert on the live object before expiring).
        assert group_flag.status == SetFlagStatus.attached
        # Members now hang under a shared (new) virtual parent (flushed by attach_flag)
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        b_ref = (await db.execute(select(DJSet).where(DJSet.id == b_id))).scalar_one()
        assert a_ref.parent_set_id is not None
        assert a_ref.parent_set_id == b_ref.parent_set_id
        parent = (
            await db.execute(select(DJSet).where(DJSet.id == a_ref.parent_set_id))
        ).scalar_one()
        assert parent.is_virtual is True

    async def test_coherent_group_without_auto_attach_stays_pending(self, db):
        """The SAME coherent group, but WITHOUT --auto-attach → untouched (pending)."""
        a = await _make_set(
            db, "Boiler Room PART 1", part_number=1, event_date=date(2026, 6, 20)
        )
        b = await _make_set(
            db, "Boiler Room PART 2", part_number=2, event_date=date(2026, 6, 20)
        )
        a_id = a.id
        group_flag = await _make_group_flag(db, [a.id, b.id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        assert all(o.flag_id != gf_id for o in outcomes)
        db.expire_all()
        gf = (
            await db.execute(select(SetFlag).where(SetFlag.id == gf_id))
        ).scalar_one()
        assert gf.status == SetFlagStatus.pending
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_divergent_event_dates_group_left_pending(self, db):
        """Two « parts » with DISTINCT reliable event_dates → divergent → left pending
        (not attached) even with --auto-attach (distinct episodes, invariant #4)."""
        a = await _make_set(
            db, "Show PART 1", part_number=1, event_date=date(2026, 6, 20)
        )
        b = await _make_set(
            db, "Show PART 2", part_number=2, event_date=date(2026, 7, 4)
        )
        a_id = a.id
        group_flag = await _make_group_flag(db, [a.id, b.id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = next(o for o in outcomes if o.flag_id == gf_id)
        assert o.decision == DECISION_KEPT
        assert o.member_set_ids == [a_id, b.id]
        db.expire_all()
        gf = (
            await db.execute(select(SetFlag).where(SetFlag.id == gf_id))
        ).scalar_one()
        assert gf.status == SetFlagStatus.pending  # never attached
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_part_overlap_anomaly_group_is_never_attached(self, db):
        """A part_overlap_anomaly group flag is out of scope → never attached even
        with --auto-attach (only part_candidate groups are surfaced)."""
        a = await _make_set(
            db, "Anomaly PART 1", part_number=1, event_date=date(2026, 6, 20)
        )
        b = await _make_set(
            db, "Anomaly PART 2", part_number=2, event_date=date(2026, 6, 20)
        )
        a_id = a.id
        group_flag = await _make_group_flag(
            db, [a.id, b.id], flag_type=SetFlagType.part_overlap_anomaly
        )
        gf_id = group_flag.id

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        assert all(o.flag_id != gf_id for o in outcomes)
        db.expire_all()
        gf = (
            await db.execute(select(SetFlag).where(SetFlag.id == gf_id))
        ).scalar_one()
        assert gf.status == SetFlagStatus.pending
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_coherent_group_dry_run_previews_without_attaching(self, db):
        """Dry-run: a coherent group is previewed AUTO-ATTACH but nothing is written."""
        a = await _make_set(
            db, "Fest PART 1", part_number=1, event_date=date(2026, 6, 20)
        )
        b = await _make_set(
            db, "Fest PART 2", part_number=2, event_date=date(2026, 6, 20)
        )
        a_id = a.id
        group_flag = await _make_group_flag(db, [a.id, b.id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=False, auto_attach=True
        )

        o = next(o for o in outcomes if o.flag_id == gf_id)
        assert o.decision == DECISION_AUTO_ATTACHED
        db.expire_all()
        gf = (
            await db.execute(select(SetFlag).where(SetFlag.id == gf_id))
        ).scalar_one()
        assert gf.status == SetFlagStatus.pending  # dry-run wrote nothing
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None


# ---------------------------------------------------------------------------
# Non-rescorable: a set became virtual
# ---------------------------------------------------------------------------


class TestNonRescorable:
    async def test_virtual_set_flag_reported_and_untouched(self, db):
        """score_pair returns None when a member set is virtual → the flag is
        reported NON-RESCORABLE and left byte-for-byte intact."""
        a = await _make_set(db, "Physical", normalized_title="physical set")
        b = await _make_set(db, "Now Virtual", is_virtual=True)
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=0.77, signals={"overlap": 0.77}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        assert len(outcomes) == 1
        o = outcomes[0]
        assert o.decision == DECISION_UNSCORABLE
        assert o.new_confidence is None
        assert o.verdict is None
        # Untouched
        assert flag.confidence == pytest.approx(0.77)
        assert flag.signals == {"overlap": 0.77}
        assert flag.status == SetFlagStatus.pending


# ---------------------------------------------------------------------------
# Opt-in --auto-attach: identical ordered tracklist → attached under virtual parent
# ---------------------------------------------------------------------------


class TestAutoAttach:
    async def test_identical_tracklist_is_attached_with_auto_attach(self, db):
        """overlap ~1.0 / order ~1.0 / 10 shared tracks / 400-day upload gap → verdict
        FLAG (dates far apart) but tracklist identical. With --auto-attach the pair is
        MERGED under a virtual parent."""
        a = await _make_set(
            db,
            "Marathon Mix",
            normalized_title="marathon mix",
            played_date=date(2023, 1, 1),
        )
        b = await _make_set(
            db,
            "Marathon Mix (reupload)",
            normalized_title="marathon mix",
            played_date=date(2024, 2, 5),  # ~400 days later → FLAG, not AUTO_ATTACH
        )
        a_id, b_id = a.id, b.id
        tracks = list(range(1, 11))  # 10 identical tracks, same order
        await _add_tracks(db, a_id, tracks)
        await _add_tracks(db, b_id, tracks)
        flag = await _make_pair_flag(
            db, a_id, b_id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = outcomes[0]
        assert o.decision == DECISION_AUTO_ATTACHED
        assert o.verdict == MatchVerdict.FLAG  # dates far apart, yet attached on V2
        assert flag.status == SetFlagStatus.attached
        # Both sets now hang under a (new) virtual parent
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        b_ref = (await db.execute(select(DJSet).where(DJSet.id == b_id))).scalar_one()
        assert a_ref.parent_set_id is not None
        assert b_ref.parent_set_id is not None
        assert a_ref.parent_set_id == b_ref.parent_set_id
        parent = (
            await db.execute(
                select(DJSet).where(DJSet.id == a_ref.parent_set_id)
            )
        ).scalar_one()
        assert parent.is_virtual is True

    async def test_same_pair_without_auto_attach_stays_kept(self, db):
        """The IDENTICAL pair, but WITHOUT --auto-attach → still just KEPT (pending),
        nothing attached — default behaviour unchanged."""
        a = await _make_set(
            db,
            "Marathon Mix",
            normalized_title="marathon mix",
            played_date=date(2023, 1, 1),
        )
        b = await _make_set(
            db,
            "Marathon Mix (reupload)",
            normalized_title="marathon mix",
            played_date=date(2024, 2, 5),
        )
        a_id, b_id = a.id, b.id
        tracks = list(range(1, 11))
        await _add_tracks(db, a_id, tracks)
        await _add_tracks(db, b_id, tracks)
        flag = await _make_pair_flag(
            db, a_id, b_id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        assert outcomes[0].decision == DECISION_KEPT
        assert flag.status == SetFlagStatus.pending
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None
        virtuals = (
            await db.execute(select(DJSet).where(DJSet.is_virtual.is_(True)))
        ).scalars().all()
        assert virtuals == []

    async def test_identical_but_too_few_shared_is_not_attached(self, db):
        """Identical ordered tracklist but only 3 shared tracks (< floor of 6) and a
        far-apart upload date → verdict FLAG, NOT attached even with --auto-attach."""
        a = await _make_set(
            db,
            "Short Set",
            normalized_title="short set",
            played_date=date(2023, 1, 1),
        )
        b = await _make_set(
            db,
            "Short Set (mirror)",
            normalized_title="short set",
            played_date=date(2024, 2, 5),  # far apart → FLAG, not AUTO_ATTACH
        )
        a_id, b_id = a.id, b.id
        await _add_tracks(db, a_id, [1, 2, 3])
        await _add_tracks(db, b_id, [1, 2, 3])
        flag = await _make_pair_flag(
            db, a_id, b_id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = outcomes[0]
        assert o.decision != DECISION_AUTO_ATTACHED
        assert o.decision == DECISION_KEPT
        assert flag.status == SetFlagStatus.pending
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_divergent_event_dates_reject_takes_precedence_over_attach(self, db):
        """Identical ordered tracklist but two RELIABLE event_dates apart → REJET-DATES
        even WITH --auto-attach (a bad merge costs more than an unmerged duplicate)."""
        a = await _make_set(
            db,
            "Artist Live",
            normalized_title="artist live",
            event_date=date(2026, 6, 20),
        )
        b = await _make_set(
            db,
            "Artist Live (2)",
            normalized_title="artist live",
            event_date=date(2026, 6, 25),  # 5 days apart → distinct performances
        )
        a_id, b_id = a.id, b.id
        tracks = list(range(1, 11))
        await _add_tracks(db, a_id, tracks)
        await _add_tracks(db, b_id, tracks)
        flag = await _make_pair_flag(
            db, a_id, b_id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = outcomes[0]
        assert o.decision == DECISION_EVENT_REJECTED
        assert flag.status == SetFlagStatus.rejected
        assert flag.signals["event_date_separated"] is True
        # No attach happened
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_low_confidence_noise_still_rejected_with_auto_attach(self, db):
        """Non-regression: the low-confidence NOTHING noise cut is unaffected by
        --auto-attach (nothing to attach → still auto-rejected)."""
        a = await _make_set(db, "Set A", normalized_title="alpha beta gamma")
        b = await _make_set(db, "Set B", normalized_title="delta epsilon zeta")
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5, 6, 7, 8])
        await _add_tracks(db, b.id, [9, 3, 10, 1, 11, 2, 12, 13])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=0.9, signals={"overlap": 0.9}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = outcomes[0]
        assert o.decision == DECISION_REJECTED
        assert flag.status == SetFlagStatus.rejected
        assert flag.signals["auto_rejected"] is True


# ---------------------------------------------------------------------------
# Opt-in --reject-episodes: episode-number extraction + divergent-episode reject
# ---------------------------------------------------------------------------


class TestEpisodeNumber:
    """Pure unit tests of the _episode_number extractor (no DB)."""

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Spectrum Radio 200 by Joris Voorn", ("marker", 200)),
            ("Global DJ Broadcast Vol. 71", ("marker", 71)),
            ("Anjunadeep Edition #676", ("marker", 676)),
            ("Transitions Episode 512", ("marker", 512)),
            ("KISS Dance 2024-08-11", ("trailing", 11)),  # bare trailing (date)
            ("Group Therapy 500", ("trailing", 500)),  # bare trailing number
            ("Awakenings ADE 2024", None),  # 4-digit year, not an episode
            ("Boiler Room London Part 2", None),  # part marker → group path
            ("Live at Tomorrowland pt. 3", None),  # part marker
            ("Sunset Session", None),  # no number
            ("", None),
            (None, None),
        ],
    )
    def test_extraction(self, title, expected):
        assert _episode_number(title) == expected


class TestRejectEpisodes:
    async def test_divergent_episodes_are_rejected(self, db):
        """Two episodes of the same show with strong overlap → REJET-ÉPISODE (not a
        duplicate) when --reject-episodes is on, regardless of overlap."""
        a = await _make_set(
            db, "Spectrum Radio 200", normalized_title="spectrum radio 200"
        )
        b = await _make_set(
            db, "Spectrum Radio 251", normalized_title="spectrum radio 251"
        )
        # High overlap / identical order to prove the episode number wins over it.
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, reject_episodes=True
        )

        o = outcomes[0]
        assert o.decision == DECISION_EPISODE_REJECTED
        assert flag.status == SetFlagStatus.rejected
        assert flag.signals["auto_rejected"] is True
        assert flag.signals["episode_separated"] is True

    async def test_same_episode_number_is_not_rejected(self, db):
        """Same episode number on both sides → NOT an episode divergence (attached
        with --auto-attach on an identical tracklist, or kept)."""
        a = await _make_set(
            db, "Spectrum Radio 200", normalized_title="spectrum radio 200"
        )
        b = await _make_set(
            db,
            "Spectrum Radio 200 (reupload)",
            normalized_title="spectrum radio 200",
        )
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, reject_episodes=True
        )

        assert outcomes[0].decision != DECISION_EPISODE_REJECTED
        assert flag.status != SetFlagStatus.rejected

    async def test_marker_vs_trailing_is_not_rejected(self, db):
        """A marker number (BBC Radio 1) vs a trailing date component (…2025-03-22
        → 22) is NOT an episode divergence — same show, must stay a duplicate
        candidate (the two prod false positives this fixes)."""
        a = await _make_set(
            db,
            "Perel - Essential Mix - BBC Radio 1",
            normalized_title="perel essential mix bbc radio 1",
        )
        b = await _make_set(
            db,
            "Perel - Essential Mix 2025-03-22",
            normalized_title="perel essential mix 2025 03 22",
        )
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, reject_episodes=True
        )

        assert outcomes[0].decision != DECISION_EPISODE_REJECTED
        assert flag.status != SetFlagStatus.rejected

    async def test_two_markers_are_rejected(self, db):
        """Two genuine episodes (Sugar Radio 544 vs 548) → marker/marker → rejected."""
        a = await _make_set(
            db, "Sugar Radio 544", normalized_title="sugar radio 544"
        )
        b = await _make_set(
            db, "Sugar Radio 548", normalized_title="sugar radio 548"
        )
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, reject_episodes=True
        )

        assert outcomes[0].decision == DECISION_EPISODE_REJECTED
        assert flag.status == SetFlagStatus.rejected

    async def test_marker_and_hash_are_rejected(self, db):
        """A keyword marker (JATS Podcast 676) vs a '#' marker (Nocturna #42) →
        both "marker" class → rejected (# counts as a marker)."""
        a = await _make_set(
            db, "JATS Podcast 676", normalized_title="jats podcast 676"
        )
        b = await _make_set(db, "Nocturna #42", normalized_title="nocturna 42")
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, reject_episodes=True
        )

        assert outcomes[0].decision == DECISION_EPISODE_REJECTED
        assert flag.status == SetFlagStatus.rejected

    async def test_divergent_episodes_without_flag_is_unchanged(self, db):
        """Without --reject-episodes the same divergent-episode pair keeps its
        default behaviour (KEPT here — identical tracklist, verdict AUTO_ATTACH)."""
        a = await _make_set(
            db, "Spectrum Radio 200", normalized_title="spectrum radio 200"
        )
        b = await _make_set(
            db, "Spectrum Radio 251", normalized_title="spectrum radio 251"
        )
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(db, threshold=0.30, apply=True)

        assert outcomes[0].decision != DECISION_EPISODE_REJECTED
        assert flag.status != SetFlagStatus.rejected


# ---------------------------------------------------------------------------
# L3e-b: divergent TITLE dates (order-agnostic) → reject / leave pending even when
# the stored event_date is NULL (C13.e parser abstained on the ambiguous title)
# ---------------------------------------------------------------------------


class TestTitleDateDivergence:
    async def test_pair_divergent_title_dates_is_rejected(self, db):
        """« Helmo (24.09.2022) » vs « Helmo (08.10.2022) » — both titles carry a full
        date and they differ, yet one event_date is NULL (parser abstained). The
        title-date rule makes decide_verdict return NOTHING → REJET-DATES even with
        --auto-attach on an identical ordered tracklist."""
        a = await _make_set(
            db,
            "Helmo (24.09.2022)",
            normalized_title="helmo",
            event_date=date(2022, 9, 24),
        )
        b = await _make_set(
            db,
            "Helmo (08.10.2022)",
            normalized_title="helmo",
            event_date=None,  # parser abstained → stored event_date missing
        )
        a_id, b_id = a.id, b.id
        tracks = list(range(1, 11))
        await _add_tracks(db, a_id, tracks)
        await _add_tracks(db, b_id, tracks)
        flag = await _make_pair_flag(
            db, a_id, b_id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db,
            threshold=0.30,
            apply=True,
            auto_attach=True,
            reject_episodes=True,
        )

        o = outcomes[0]
        assert o.decision == DECISION_EVENT_REJECTED
        assert o.verdict == MatchVerdict.NOTHING
        assert flag.status == SetFlagStatus.rejected
        assert flag.signals["auto_rejected"] is True
        assert flag.signals["event_date_separated"] is True
        # No attach happened despite the identical tracklist
        db.expire_all()
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_group_divergent_title_dates_left_pending(self, db):
        """A part_candidate group whose two members carry DIFFERENT title dates while
        the stored event_date is NULL on both → incoherent → left pending (no attach)
        even with --auto-attach."""
        a = await _make_set(
            db, "Show PART 1 (24.09.2022)", part_number=1, event_date=None
        )
        b = await _make_set(
            db, "Show PART 2 (08.10.2022)", part_number=2, event_date=None
        )
        a_id = a.id
        group_flag = await _make_group_flag(db, [a.id, b.id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = next(o for o in outcomes if o.flag_id == gf_id)
        assert o.decision == DECISION_KEPT  # divergent title dates → pending
        db.expire_all()
        gf = (
            await db.execute(select(SetFlag).where(SetFlag.id == gf_id))
        ).scalar_one()
        assert gf.status == SetFlagStatus.pending  # never attached
        a_ref = (await db.execute(select(DJSet).where(DJSet.id == a_id))).scalar_one()
        assert a_ref.parent_set_id is None

    async def test_pair_identical_title_dates_not_rejected(self, db):
        """Non-regression: identical title dates on both sides are NOT a divergence —
        an identical ordered tracklist is still attached with --auto-attach."""
        a = await _make_set(
            db,
            "Helmo (24.09.2022)",
            normalized_title="helmo",
            event_date=date(2022, 9, 24),
        )
        b = await _make_set(
            db,
            "Helmo (24.09.2022) reupload",
            normalized_title="helmo",
            event_date=date(2022, 9, 24),
        )
        tracks = list(range(1, 11))
        await _add_tracks(db, a.id, tracks)
        await _add_tracks(db, b.id, tracks)
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=1.0, signals={"overlap": 1.0}
        )

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = outcomes[0]
        assert o.decision == DECISION_AUTO_ATTACHED
        assert flag.status == SetFlagStatus.attached

    async def test_group_identical_title_dates_is_attached(self, db):
        """Non-regression: a part_candidate group whose members carry the SAME title
        date (event_date NULL) stays coherent → attached with --auto-attach."""
        a = await _make_set(
            db, "Show PART 1 (24.09.2022)", part_number=1, event_date=None
        )
        b = await _make_set(
            db, "Show PART 2 (24.09.2022)", part_number=2, event_date=None
        )
        group_flag = await _make_group_flag(db, [a.id, b.id])
        gf_id = group_flag.id

        outcomes = await rescore_flags(
            db, threshold=0.30, apply=True, auto_attach=True
        )

        o = next(o for o in outcomes if o.flag_id == gf_id)
        assert o.decision == DECISION_AUTO_ATTACHED
        assert group_flag.status == SetFlagStatus.attached


# ---------------------------------------------------------------------------
# Dry-run writes nothing
# ---------------------------------------------------------------------------


class TestDryRun:
    async def test_dry_run_makes_no_db_changes(self, db):
        a = await _make_set(db, "Set A", normalized_title="alpha beta gamma")
        b = await _make_set(db, "Set B", normalized_title="delta epsilon zeta")
        await _add_tracks(db, a.id, [1, 2, 3, 4, 5, 6, 7, 8])
        await _add_tracks(db, b.id, [9, 3, 10, 1, 11, 2, 12, 13])
        flag = await _make_pair_flag(
            db, a.id, b.id, confidence=0.9, signals={"overlap": 0.9}
        )
        flag_id = flag.id

        outcomes = await rescore_flags(db, threshold=0.30, apply=False)

        # The decision is computed (would be a reject) but NOT applied
        assert outcomes[0].decision == DECISION_REJECTED
        assert isinstance(outcomes[0], RescoreOutcome)

        db.expire_all()
        fresh = (
            await db.execute(select(SetFlag).where(SetFlag.id == flag_id))
        ).scalar_one()
        assert fresh.confidence == pytest.approx(0.9)
        assert fresh.signals == {"overlap": 0.9}
        assert fresh.status == SetFlagStatus.pending
