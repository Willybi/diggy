"""Integration tests for get_match_candidates (L3) — requires DB (SQLite in CI)."""

import pytest
import pytest_asyncio

from services.set_dedup_service import get_match_candidates


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
