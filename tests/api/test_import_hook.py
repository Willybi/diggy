"""Tests for L5: import hook — title normalization + matching triggered on import."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from models import DJSet, SetFlag, SetFlagStatus, SetTrack
from services.set_dedup_service import (
    apply_match_results,
    backfill_normalized_titles,
    match_set,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_set(
    db,
    title="Test Set",
    source="trackid",
    played_date=None,
    normalized_title=None,
    is_virtual=False,
    external_id=None,
):
    s = DJSet(
        title=title,
        source=source,
        played_date=played_date,
        normalized_title=normalized_title,
        is_virtual=is_virtual,
        external_id=external_id,
    )
    db.add(s)
    await db.flush()
    return s


async def _add_tracks(db, set_id, mtids):
    """Add identified tracks with sequential mtids. mtids = list of int."""
    for pos, mtid in enumerate(mtids, start=1):
        db.add(
            SetTrack(
                set_id=set_id,
                position=pos,
                timecode_ms=pos * 60_000,
                raw_title=f"Track {mtid}",
                raw_artist="DJ X",
                is_id=False,
                trackid_music_track_id=mtid,
            )
        )
    await db.flush()


# ---------------------------------------------------------------------------
# TestImportHookNormalizesTitle
# ---------------------------------------------------------------------------


class TestImportHookNormalizesTitle:
    async def test_backfill_fills_null_normalized_title(self, db):
        """A DJSet without normalized_title gets it filled by backfill_normalized_titles."""
        s = await _make_set(db, title="Boiler Room London [Full Set HD]")
        assert s.normalized_title is None

        s_id = s.id  # capture before expire_all
        count = await backfill_normalized_titles(db)

        assert count >= 1
        db.expire_all()
        refreshed = (
            await db.execute(select(DJSet).where(DJSet.id == s_id))
        ).scalar_one()
        assert refreshed.normalized_title is not None
        assert refreshed.normalized_title != ""
        # decorative tag stripped
        assert "[full set hd]" not in refreshed.normalized_title

    async def test_backfill_skips_already_normalized(self, db):
        """DJSet with an existing normalized_title is not overwritten."""
        s = await _make_set(
            db,
            title="Raw Title",
            normalized_title="already normalized",
        )

        s_id = s.id  # capture before expire_all
        count = await backfill_normalized_titles(db)

        assert count == 0
        db.expire_all()
        refreshed = (
            await db.execute(select(DJSet).where(DJSet.id == s_id))
        ).scalar_one()
        assert refreshed.normalized_title == "already normalized"

    async def test_backfill_skips_virtual_sets(self, db):
        """Virtual sets (is_virtual=True) are excluded from backfill."""
        virtual = await _make_set(db, title="Virtual Parent", is_virtual=True)
        virtual_id = virtual.id  # capture before expire_all

        count = await backfill_normalized_titles(db)

        assert count == 0
        db.expire_all()
        refreshed = (
            await db.execute(select(DJSet).where(DJSet.id == virtual_id))
        ).scalar_one()
        assert refreshed.normalized_title is None


# ---------------------------------------------------------------------------
# TestImportHookTriggersMatching
# ---------------------------------------------------------------------------


class TestImportHookTriggersMatching:
    async def test_high_overlap_auto_attach(self, db):
        """Two sets sharing >=80% mtids + same date → AUTO_ATTACH → shared parent_set_id."""
        today = date(2024, 6, 15)
        s1 = await _make_set(
            db,
            title="Charlotte de Witte @ Awakenings",
            played_date=today,
            normalized_title="charlotte de witte @ awakenings",
        )
        # 10 shared mtids
        mtids = list(range(100, 110))
        await _add_tracks(db, s1.id, mtids)

        s2 = await _make_set(
            db,
            title="Charlotte de Witte @ Awakenings",
            played_date=today,
            normalized_title="charlotte de witte @ awakenings",
        )
        # same 10 mtids → 100% overlap
        await _add_tracks(db, s2.id, mtids)

        pair_results, group_results = await match_set(db, s2.id)
        assert pair_results, "Expected at least one match candidate"

        auto_results = [r for r in pair_results if r.verdict.value == "auto_attach"]
        assert auto_results, "Expected AUTO_ATTACH verdict"

        s1_id, s2_id = s1.id, s2.id  # capture before expire_all
        counts = await apply_match_results(db, s2_id, pair_results, group_results)
        assert counts["attached"] >= 1

        db.expire_all()
        s1_ref = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s1_ref.parent_set_id is not None
        assert s2_ref.parent_set_id is not None
        assert s1_ref.parent_set_id == s2_ref.parent_set_id


# ---------------------------------------------------------------------------
# TestImportHookFlagLowOverlap
# ---------------------------------------------------------------------------


class TestImportHookFlagLowOverlap:
    async def test_medium_overlap_inserts_flag(self, db):
        """Two sets with overlap in [0.50, 0.79) → FLAG (duplicate_candidate), not AUTO_ATTACH."""
        today = date(2024, 8, 20)

        # Set A: 10 tracks (mtids 200-209)
        s1 = await _make_set(
            db,
            title="Amelie Lens @ Tomorrowland",
            played_date=today,
            normalized_title="amelie lens @ tomorrowland",
        )
        mtids_a = list(range(200, 210))
        await _add_tracks(db, s1.id, mtids_a)

        # Set B: 6 shared tracks (overlap = 6/10 = 0.60) + 4 unique tracks
        s2 = await _make_set(
            db,
            title="Amelie Lens @ Tomorrowland",
            played_date=today,
            normalized_title="amelie lens @ tomorrowland",
        )
        # 6 shared + 4 unique (mtids 300-303)
        mtids_b = list(range(200, 206)) + list(range(300, 304))
        await _add_tracks(db, s2.id, mtids_b)

        pair_results, group_results = await match_set(db, s2.id)
        assert pair_results, "Expected at least one match candidate"

        flag_results = [r for r in pair_results if r.verdict.value == "flag"]
        assert flag_results, "Expected FLAG verdict for medium overlap"

        counts = await apply_match_results(db, s2.id, pair_results, group_results)
        assert counts["flagged"] >= 1
        assert counts["attached"] == 0

        flags = (await db.execute(select(SetFlag))).scalars().all()
        assert len(flags) >= 1
        flag = flags[0]
        assert flag.status == SetFlagStatus.pending
        # No parent assigned (FLAG, not AUTO_ATTACH)
        s2_id = s2.id  # capture before expire_all
        db.expire_all()
        s2_ref = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert s2_ref.parent_set_id is None


# ---------------------------------------------------------------------------
# TestImportHookFailSafe
# ---------------------------------------------------------------------------


def _make_mock_client(tracks=None):
    """Build a minimal TrackIDClient mock for import_audiostream tests."""
    if tracks is None:
        tracks = []
    mock_client = MagicMock()
    mock_client.get_set_detail = AsyncMock()
    mock_client.merge_tracklist = MagicMock(return_value=tracks)
    return mock_client


class TestImportHookFailSafe:
    async def test_matching_exception_does_not_abort_import(self, db):
        """If match_set raises, import_audiostream still returns (DJSet, int) normally."""
        from trackid.importer import import_audiostream

        fake_detail = {
            "id": 99999,
            "title": "FailSafe Test Set",
            "slug": "failsafe-test-set",
            "duration": "01:00:00.0000000",
            "url": "https://trackid.net/failsafe-test-set",
            "artworkUrl": None,
            "createdOn": "2024-01-15T20:00:00Z",
            "detectionProcesses": [],
        }
        two_tracks = [
            {"title": "Track One", "artist": "DJ Safe", "startTime": "00:00:00.0000000", "musicTrackId": 1},
            {"title": "Track Two", "artist": "DJ Safe", "startTime": "00:10:00.0000000", "musicTrackId": 2},
        ]
        mock_client = _make_mock_client(tracks=two_tracks)
        mock_client.get_set_detail.return_value = fake_detail

        audiostream = {"id": 99999, "slug": "failsafe-test-set"}

        with patch(
            "services.set_dedup_service.match_set",
            new=AsyncMock(side_effect=RuntimeError("simulated dedup failure")),
        ):
            dj_set, track_count = await import_audiostream(
                db, mock_client, audiostream
            )

        assert dj_set is not None
        assert isinstance(dj_set, DJSet)
        assert track_count == 2

    async def test_backfill_exception_does_not_abort_import(self, db):
        """If backfill_normalized_titles raises, import_audiostream still returns normally."""
        from trackid.importer import import_audiostream

        fake_detail = {
            "id": 88888,
            "title": "FailSafe Backfill Set",
            "slug": "failsafe-backfill-set",
            "duration": "00:30:00.0000000",
            "url": "https://trackid.net/failsafe-backfill-set",
            "artworkUrl": None,
            "createdOn": "2024-02-20T18:00:00Z",
            "detectionProcesses": [],
        }
        mock_client = _make_mock_client(tracks=[])
        mock_client.get_set_detail.return_value = fake_detail

        audiostream = {"id": 88888, "slug": "failsafe-backfill-set"}

        with patch(
            "services.set_dedup_service.backfill_normalized_titles",
            new=AsyncMock(side_effect=ValueError("simulated backfill failure")),
        ):
            dj_set, track_count = await import_audiostream(
                db, mock_client, audiostream
            )

        assert dj_set is not None
        assert isinstance(dj_set, DJSet)
        assert track_count == 0
