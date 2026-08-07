"""Integration tests for get_match_candidates + score_pair (L3) — requires DB (SQLite in CI)."""

from datetime import date

import pytest
import pytest_asyncio

from services.set_dedup_service import (
    compute_confidence,
    get_match_candidates,
    match_set,
    score_pair,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_set(db, title="Test Set", source="trackid"):
    from models import DJSet

    s = DJSet(title=title, source=source)
    db.add(s)
    await db.flush()
    return s


async def _add_tracks(db, set_id, mtids, is_id=False):
    """Add SetTrack rows for each mtid, at consecutive positions."""
    from models import SetTrack

    for pos, mtid in enumerate(mtids):
        t = SetTrack(
            set_id=set_id,
            position=pos,
            is_id=is_id,
            trackid_music_track_id=mtid,
        )
        db.add(t)
    await db.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_found_with_four_shared(db, clean_db):
    """set_b shares 4 identified tracks with set_a → returned as candidate."""
    set_a = await _make_set(db, title="Set A")
    set_b = await _make_set(db, title="Set B")

    await _add_tracks(db, set_a.id, [10, 20, 30, 40, 50])
    await _add_tracks(db, set_b.id, [10, 20, 30, 40, 60])

    candidates = await get_match_candidates(db, set_a.id, [10, 20, 30, 40, 50])

    assert len(candidates) == 1
    assert candidates[0].set_id == set_b.id
    assert candidates[0].shared_count == 4
    assert candidates[0].total_identified == 5


@pytest.mark.asyncio
async def test_candidate_not_found_below_threshold(db, clean_db):
    """2 shared tracks is below the 3-track threshold → no candidates."""
    set_a = await _make_set(db, title="Set A")
    set_b = await _make_set(db, title="Set B")

    await _add_tracks(db, set_a.id, [10, 20, 70, 80])
    await _add_tracks(db, set_b.id, [10, 20, 90, 100])

    candidates = await get_match_candidates(db, set_a.id, [10, 20, 70, 80])

    assert candidates == []


@pytest.mark.asyncio
async def test_empty_incoming_mtids_returns_empty(db, clean_db):
    """Fewer than 3 incoming_mtids → short-circuit, no DB query."""
    set_a = await _make_set(db, title="Set A")
    candidates = await get_match_candidates(db, set_a.id, [])
    assert candidates == []

    candidates = await get_match_candidates(db, set_a.id, [10, 20])
    assert candidates == []


@pytest.mark.asyncio
async def test_set_not_matched_to_itself(db, clean_db):
    """The source set is excluded from its own candidates."""
    set_a = await _make_set(db, title="Set A")
    await _add_tracks(db, set_a.id, [10, 20, 30, 40, 50])

    candidates = await get_match_candidates(db, set_a.id, [10, 20, 30, 40, 50])
    assert all(c.set_id != set_a.id for c in candidates)


@pytest.mark.asyncio
async def test_virtual_set_excluded(db, clean_db):
    """Virtual sets (is_virtual=True) are not returned as candidates."""
    from models import DJSet

    set_a = await _make_set(db, title="Set A")
    set_v = DJSet(title="Virtual", source="trackid", is_virtual=True)
    db.add(set_v)
    await db.flush()

    await _add_tracks(db, set_a.id, [1, 2, 3, 4])
    await _add_tracks(db, set_v.id, [1, 2, 3, 4])

    candidates = await get_match_candidates(db, set_a.id, [1, 2, 3, 4])
    assert all(c.set_id != set_v.id for c in candidates)


@pytest.mark.asyncio
async def test_is_id_tracks_excluded_from_matching(db, clean_db):
    """Tracks with is_id=True (unidentified) are not counted as shared."""
    set_a = await _make_set(db, title="Set A")
    set_b = await _make_set(db, title="Set B")

    # set_a: 3 identified + 2 ID tracks (same mtids)
    await _add_tracks(db, set_a.id, [10, 20, 30], is_id=False)
    await _add_tracks(db, set_b.id, [10, 20, 30], is_id=True)  # all unidentified

    candidates = await get_match_candidates(db, set_a.id, [10, 20, 30])
    # set_b tracks are is_id=True → excluded from the WHERE clause → 0 shared
    assert candidates == []


@pytest.mark.asyncio
async def test_multiple_candidates(db, clean_db):
    """Two sets both sharing >= 3 tracks are both returned."""
    set_a = await _make_set(db, title="Set A")
    set_b = await _make_set(db, title="Set B")
    set_c = await _make_set(db, title="Set C")

    await _add_tracks(db, set_a.id, [1, 2, 3, 4, 5])
    await _add_tracks(db, set_b.id, [1, 2, 3, 99])
    await _add_tracks(db, set_c.id, [1, 2, 3, 100, 101])

    candidates = await get_match_candidates(db, set_a.id, [1, 2, 3, 4, 5])
    candidate_ids = {c.set_id for c in candidates}

    assert set_b.id in candidate_ids
    assert set_c.id in candidate_ids
    assert len(candidates) == 2


# ---------------------------------------------------------------------------
# score_pair (re-score entry point)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_pair_returns_signals_and_confidence(db, clean_db):
    """score_pair loads both sets + df from DB and returns (signals, confidence)."""
    from models import DJSet

    today = date(2026, 5, 10)
    set_a = DJSet(
        title="Set A", source="trackid", played_date=today,
        normalized_title="dj alpha @ berlin",
    )
    set_b = DJSet(
        title="Set B", source="trackid", played_date=today,
        normalized_title="dj alpha @ berlin",
    )
    db.add(set_a)
    db.add(set_b)
    await db.flush()

    await _add_tracks(db, set_a.id, [10, 20, 30, 40])
    await _add_tracks(db, set_b.id, [10, 20, 30, 99])

    scored = await score_pair(db, set_a.id, set_b.id)
    assert scored is not None
    signals, confidence = scored

    assert signals.overlap == pytest.approx(0.75)
    assert signals.title_sim == 1.0
    assert signals.date_gap_days == 0
    assert signals.first_track_match is True
    # shared tracks appear in BOTH sets → df=2 → weight 1/log2(3) ≈ 0.631
    assert signals.weighted_overlap == pytest.approx(0.654, abs=1e-3)
    assert confidence == compute_confidence(signals)


@pytest.mark.asyncio
async def test_score_pair_df_lowers_anthem_weight(db, clean_db):
    """A shared anthem (high df in DB) yields a lower weighted_overlap than a
    shared rare track, at identical raw overlap."""
    # Pair 1 shares mtid 10, a genre anthem present in 6 more sets (df=8)
    set_a = await _make_set(db, title="Set A")
    set_b = await _make_set(db, title="Set B")
    await _add_tracks(db, set_a.id, [10, 20, 30])
    await _add_tracks(db, set_b.id, [10, 40, 50])
    for i in range(6):
        other = await _make_set(db, title=f"Other {i}")
        await _add_tracks(db, other.id, [10])

    # Pair 2 shares mtid 60, present in these two sets only (df=2)
    set_c = await _make_set(db, title="Set C")
    set_d = await _make_set(db, title="Set D")
    await _add_tracks(db, set_c.id, [60, 21, 31])
    await _add_tracks(db, set_d.id, [60, 41, 51])

    scored_anthem = await score_pair(db, set_a.id, set_b.id)
    scored_rare = await score_pair(db, set_c.id, set_d.id)
    assert scored_anthem is not None and scored_rare is not None
    signals_anthem, _ = scored_anthem
    signals_rare, _ = scored_rare

    # Same raw overlap (1 shared / 3), but the anthem weighs far less
    assert signals_anthem.overlap == pytest.approx(signals_rare.overlap)
    # anthem: w(df=8)/(w(df=8) + 2) ≈ 0.136 ; rare: w(df=2)/(w(df=2) + 2) ≈ 0.240
    assert signals_anthem.weighted_overlap == pytest.approx(0.136, abs=1e-3)
    assert signals_rare.weighted_overlap == pytest.approx(0.240, abs=1e-3)
    assert signals_anthem.weighted_overlap < signals_rare.weighted_overlap


@pytest.mark.asyncio
async def test_score_pair_missing_set_returns_none(db, clean_db):
    set_a = await _make_set(db, title="Set A")
    assert await score_pair(db, set_a.id, 999999) is None
    assert await score_pair(db, 999999, set_a.id) is None


@pytest.mark.asyncio
async def test_score_pair_virtual_set_returns_none(db, clean_db):
    from models import DJSet

    set_a = await _make_set(db, title="Set A")
    virtual = DJSet(title="Virtual", source="virtual", is_virtual=True)
    db.add(virtual)
    await db.flush()

    assert await score_pair(db, set_a.id, virtual.id) is None


@pytest.mark.asyncio
async def test_match_set_results_carry_confidence(db, clean_db):
    """match_set computes the composite confidence once per pair result."""
    from models import DJSet

    today = date(2026, 5, 10)
    set_a = DJSet(
        title="Set A", source="trackid", played_date=today,
        normalized_title="dj alpha @ berlin",
    )
    set_b = DJSet(
        title="Set B", source="trackid", played_date=today,
        normalized_title="dj alpha @ berlin",
    )
    db.add(set_a)
    db.add(set_b)
    await db.flush()
    await _add_tracks(db, set_a.id, [10, 20, 30, 40])
    await _add_tracks(db, set_b.id, [10, 20, 30, 99])

    pair_results, _ = await match_set(db, set_a.id)
    assert len(pair_results) == 1
    result = pair_results[0]
    assert result.confidence == compute_confidence(result.signals)
    assert result.confidence > 0.0
