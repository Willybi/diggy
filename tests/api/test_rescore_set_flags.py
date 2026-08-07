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
    DECISION_KEPT,
    DECISION_REJECTED,
    DECISION_UNSCORABLE,
    RescoreOutcome,
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
    is_virtual=False,
):
    s = DJSet(
        title=title,
        source=source,
        normalized_title=normalized_title,
        part_number=part_number,
        played_date=played_date,
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
# Out of scope: group flags
# ---------------------------------------------------------------------------


class TestGroupFlagIntact:
    async def test_group_flag_is_never_touched(self, db):
        a = await _make_set(db, "Part 1", part_number=1)
        b = await _make_set(db, "Part 2", part_number=2)
        group_flag = SetFlag(
            set_id_a=min(a.id, b.id),
            set_id_b=None,
            group_key="some base title",
            member_set_ids=[a.id, b.id],
            flag_type=SetFlagType.part_candidate,
            confidence=0.92,
            signals={"member_count": 2},
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
        db.add(group_flag)
        await db.flush()
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
