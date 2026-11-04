"""Tests for the twin control at the entry of the sets funnel (set_twin_service)."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from models import DJSet, SetFlag, SetFlagStatus, SetFlagType, SetTrack
from services import set_twin_service
from services.set_twin_rules import (
    CHANNEL_STEP_MAX_DURATION_GAP,
    DATE_STEP_MAX_DURATION_GAP,
)
from services.set_twin_service import (
    REASON_ALREADY_IN_FAMILY,
    REASON_AMBIGUOUS,
    REASON_YOUTUBE_SIDE_TRUNCATED,
    _duration_window,
    reconcile_twins_for_set,
)
from sqlalchemy import func, select
from trackid.importer import import_audiostream
from workers.youtube import upsert_youtube_set, watch_url

HOUR = 3_600_000
CHANNEL = "Cercle"
# Contained in the two titles below: a channel-step ATTACH with no date to rely on.
BASE_TITLE = "Peggy Gou Forest Gathering"
EPISODE_A = f"{BASE_TITLE} Sunrise"
EPISODE_B = f"{BASE_TITLE} Sunset"
PUBLISHED = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)


async def _make_set(db, title=BASE_TITLE, source="trackid", **fields):
    fields.setdefault("duration_ms", HOUR)
    fields.setdefault("channel", CHANNEL)
    fields.setdefault("channel_canonical", fields["channel"])
    dj_set = DJSet(title=title, source=source, **fields)
    db.add(dj_set)
    await db.flush()
    return dj_set


async def _make_family(db, *children):
    parent = DJSet(title="Family", source="virtual", is_virtual=True)
    db.add(parent)
    await db.flush()
    for child in children:
        child.parent_set_id = parent.id
    await db.flush()
    return parent


async def _make_flag(db, id_1, id_2, status):
    flag = SetFlag(
        set_id_a=min(id_1, id_2),
        set_id_b=max(id_1, id_2),
        flag_type=SetFlagType.duplicate_candidate,
        status=status,
        created_at=PUBLISHED,
    )
    db.add(flag)
    await db.flush()
    return flag


async def _flags(db):
    return (await db.execute(select(SetFlag))).scalars().all()


def _mock_client(detail):
    client = MagicMock()
    client.merge_tracklist = MagicMock(
        return_value=[
            {
                "title": "Track",
                "artist": "DJ",
                "startTime": "00:00:00.0000000",
                "musicTrackId": 1,
            }
        ]
    )
    return client, detail


def _detail(ext_id, title=BASE_TITLE, url=None, channel=CHANNEL):
    return {
        "id": ext_id,
        "slug": f"set-{ext_id}",
        "title": title,
        "url": url or f"https://www.mixcloud.com/set-{ext_id}/",
        "duration": "01:00:00.0000000",
        "createdOn": "2024-01-15T20:00:00Z",
        "channel": channel,
    }


async def _import(db, detail):
    client, detail = _mock_client(detail)
    return await import_audiostream(
        db, client, detail, prefetched_detail=detail, min_age_hours=0
    )


class TestYoutubeIncoming:
    async def test_same_video_attaches_whatever_the_titles_say(self, db):
        twin = await _make_set(
            db,
            "Completely different title",
            channel="Elsewhere",
            duration_ms=None,
            source_url=watch_url("VID"),
        )
        twin_id = twin.id

        dj_set, created = await upsert_youtube_set(
            db,
            video={
                "video_id": "VID",
                "title": BASE_TITLE,
                "published": PUBLISHED,
                "duration_ms": HOUR,
            },
            channel_name=CHANNEL,
        )

        assert created is True
        assert dj_set.source == "youtube"
        assert dj_set.parent_set_id is not None
        assert (await db.get(DJSet, twin_id)).parent_set_id == dj_set.parent_set_id

        flag = (await _flags(db))[0]
        assert flag.status == SetFlagStatus.attached
        assert flag.flag_type == SetFlagType.duplicate_candidate
        assert flag.resolved_at is not None
        assert flag.confidence is None
        assert flag.set_id_a == min(twin_id, dj_set.id)
        assert flag.signals["twin_rule"] == "video"
        assert flag.signals["reason"] == "same video id"
        assert "same_channel" in flag.signals

    async def test_same_video_as_a_child_joins_its_family(self, db):
        child = await _make_set(db, "Another title", source_url=watch_url("VID"))
        sibling = await _make_set(db, "Yet another title")
        parent = await _make_family(db, child, sibling)
        parent_id = parent.id

        dj_set, _ = await upsert_youtube_set(
            db,
            video={
                "video_id": "VID",
                "title": BASE_TITLE,
                "published": PUBLISHED,
                "duration_ms": HOUR,
            },
            channel_name=CHANNEL,
        )

        assert dj_set.parent_set_id == parent_id
        assert (await _flags(db))[0].status == SetFlagStatus.attached

    async def test_video_wins_over_an_episode_of_the_channel(self, db):
        episode = await _make_set(db, EPISODE_A)
        video = await _make_set(
            db, "Unrelated title", channel="Elsewhere", source_url=watch_url("Y1")
        )
        yt = await _make_set(db, source="youtube", external_id="Y1")
        video_id, episode_id = video.id, episode.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attached"] == 1
        assert (await db.get(DJSet, video_id)).parent_set_id == yt.parent_set_id
        assert (await db.get(DJSet, episode_id)).parent_set_id is None

    async def test_two_channel_episodes_flag_the_closest_without_attaching(self, db):
        far = await _make_set(db, EPISODE_A, duration_ms=HOUR - 50_000)
        near = await _make_set(db, EPISODE_B, duration_ms=HOUR + 10_000)
        yt = await _make_set(db, source="youtube", external_id="Y1")
        far_id, near_id, yt_id = far.id, near.id, yt.id

        counts = await reconcile_twins_for_set(db, yt_id)

        assert counts["attached"] == 0
        assert counts["flagged"] == 1
        assert yt.parent_set_id is None
        flags = await _flags(db)
        assert len(flags) == 1
        assert {flags[0].set_id_a, flags[0].set_id_b} == {near_id, yt_id}
        assert far_id not in (flags[0].set_id_a, flags[0].set_id_b)
        assert flags[0].status == SetFlagStatus.pending
        assert flags[0].signals["reason"] == REASON_AMBIGUOUS

    async def test_two_episodes_under_one_parent_count_as_one(self, db):
        episode_a = await _make_set(db, EPISODE_A)
        episode_b = await _make_set(db, EPISODE_B)
        parent = await _make_family(db, episode_a, episode_b)
        yt = await _make_set(db, source="youtube", external_id="Y1")

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attached"] == 1
        assert yt.parent_set_id == parent.id

    async def test_several_date_matches_attach_to_the_lowest_id(self, db):
        day = date(2024, 5, 20)
        first = await _make_set(db, BASE_TITLE, channel="A", event_date=day)
        second = await _make_set(db, BASE_TITLE, channel="B", event_date=day)
        yt = await _make_set(
            db, BASE_TITLE, source="youtube", external_id="Y1", channel="C", event_date=day
        )
        first_id, second_id = first.id, second.id

        await reconcile_twins_for_set(db, yt.id)

        assert (await db.get(DJSet, first_id)).parent_set_id == yt.parent_set_id
        assert (await db.get(DJSet, second_id)).parent_set_id is None

    async def test_review_flags_without_attaching(self, db):
        # A number in one title only leaves a channel match to a human.
        other = await _make_set(db, f"{BASE_TITLE} 2")
        yt = await _make_set(db, source="youtube", external_id="Y1")
        other_id = other.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["flagged"] == 1
        assert yt.parent_set_id is None
        assert (await db.get(DJSet, other_id)).parent_set_id is None
        flag = (await _flags(db))[0]
        assert flag.status == SetFlagStatus.pending
        assert flag.resolved_at is None
        assert flag.signals["twin_rule"] == "channel"

    async def test_upload_date_comes_from_the_youtube_played_date(self, db):
        # Published two years before the event: another episode of a recurring show.
        await _make_set(db, EPISODE_A, event_date=date(2024, 6, 1))
        yt = await _make_set(
            db, source="youtube", external_id="Y1", played_date=date(2022, 6, 1)
        )

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["candidates"] == 0
        assert await _flags(db) == []

    async def test_trackid_played_date_is_not_an_upload_date(self, db):
        # The publication window only reads the YouTube side.
        trackid = await _make_set(
            db, EPISODE_A, played_date=date(2010, 1, 1), event_date=date(2024, 6, 1)
        )
        yt = await _make_set(
            db, source="youtube", external_id="Y1", played_date=date(2024, 6, 2)
        )
        trackid_id = trackid.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attached"] == 1
        assert (await db.get(DJSet, trackid_id)).parent_set_id == yt.parent_set_id


class TestTrackidIncoming:
    async def test_import_attaches_an_existing_youtube_set(self, db):
        yt = await _make_set(db, "YT title", source="youtube", external_id="VID")
        yt_id = yt.id

        dj_set, track_count = await _import(
            db, _detail(501, url="https://youtu.be/VID", channel="Elsewhere")
        )

        assert track_count == 1
        assert dj_set.parent_set_id is not None
        assert (await db.get(DJSet, yt_id)).parent_set_id == dj_set.parent_set_id
        assert (await _flags(db))[0].signals["twin_rule"] == "video"

    async def test_two_youtube_sets_on_one_set_stay_apart(self, db):
        y1 = await _make_set(db, EPISODE_A, source="youtube", external_id="Y1")
        y2 = await _make_set(db, EPISODE_B, source="youtube", external_id="Y2")
        trackid = await _make_set(db)
        y1_id, y2_id = y1.id, y2.id

        counts = await reconcile_twins_for_set(db, trackid.id)

        assert counts["attached"] == 0
        assert counts["flagged"] == 1
        assert trackid.parent_set_id is None
        assert (await db.get(DJSet, y1_id)).parent_set_id is None
        assert (await db.get(DJSet, y2_id)).parent_set_id is None
        assert (await _flags(db))[0].signals["reason"] == REASON_AMBIGUOUS

    async def test_video_match_still_wins_over_another_youtube_set(self, db):
        same_video = await _make_set(
            db, "Unrelated title", source="youtube", external_id="VID", channel="B"
        )
        await _make_set(db, EPISODE_A, source="youtube", external_id="Y2")
        await _make_set(db, EPISODE_B, source="youtube", external_id="Y3")
        trackid = await _make_set(db, source_url=watch_url("VID"))
        same_video_id = same_video.id

        counts = await reconcile_twins_for_set(db, trackid.id)

        assert counts["attached"] == 1
        assert (await db.get(DJSet, same_video_id)).parent_set_id == trackid.parent_set_id

    async def test_recrawl_of_one_episode_does_not_settle_an_ambiguous_video(self, db):
        episode_a = await _make_set(db, EPISODE_A)
        episode_b = await _make_set(db, EPISODE_B, duration_ms=HOUR + 10_000)
        yt = await _make_set(db, source="youtube", external_id="Y1")
        await reconcile_twins_for_set(db, yt.id)  # flags the pair with episode_a

        counts = await reconcile_twins_for_set(db, episode_b.id)

        assert counts["attached"] == 0
        assert yt.parent_set_id is None
        assert episode_a.parent_set_id is None
        assert episode_b.parent_set_id is None

    async def test_video_already_in_a_family_does_not_drag_the_set_in(self, db):
        first = await _make_set(db, EPISODE_A)
        yt = await _make_set(db, source="youtube", external_id="Y1")
        await _make_family(db, first, yt)
        second = await _make_set(db, EPISODE_B)

        counts = await reconcile_twins_for_set(db, second.id)

        assert counts["attached"] == 0
        assert second.parent_set_id is None
        flags = await _flags(db)
        assert len(flags) == 1
        assert flags[0].signals["reason"] == REASON_ALREADY_IN_FAMILY

    async def test_reimport_is_idempotent(self, db):
        await _make_set(db, "YT title", source="youtube", external_id="VID")
        detail = _detail(502, url=watch_url("VID"), channel="Elsewhere")

        first, _ = await _import(db, detail)
        parent_id = first.parent_set_id
        sets_before = (
            await db.execute(select(func.count()).select_from(DJSet))
        ).scalar_one()
        second, _ = await _import(db, detail)

        assert second.id == first.id
        assert second.parent_set_id == parent_id
        assert len(await _flags(db)) == 1
        sets_after = (
            await db.execute(select(func.count()).select_from(DJSet))
        ).scalar_one()
        assert sets_after == sets_before

    async def test_import_survives_a_reconcile_failure(self, db, monkeypatch):
        async def boom(session, set_id):
            row = await session.get(DJSet, set_id)
            row.title = "Changed before the failure"
            await session.flush()
            raise RuntimeError("simulated reconcile failure")

        monkeypatch.setattr(set_twin_service, "reconcile_twins_for_set", boom)

        dj_set, track_count = await _import(db, _detail(503))

        assert track_count == 1
        # Still readable after the savepoint rollback, its change undone.
        assert dj_set.title == BASE_TITLE
        tracks = await db.execute(
            select(func.count()).select_from(SetTrack).where(SetTrack.set_id == dj_set.id)
        )
        assert tracks.scalar_one() == 1


class TestNothingToDo:
    async def test_unreliable_twin_is_ignored(self, db):
        await _make_set(db, source_url=watch_url("Y1"), unreliable=True)
        yt = await _make_set(db, source="youtube", external_id="Y1")

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["candidates"] == 0
        assert yt.parent_set_id is None
        assert await _flags(db) == []

    async def test_unreliable_incoming_trackid_set_is_ignored(self, db):
        await _make_set(db, source="youtube", external_id="Y1")
        trackid = await _make_set(db, source_url=watch_url("Y1"), unreliable=True)

        counts = await reconcile_twins_for_set(db, trackid.id)

        assert counts["candidates"] == 0
        assert await _flags(db) == []

    async def test_virtual_set_is_ignored(self, db):
        virtual = await _make_set(
            db, source="virtual", is_virtual=True, source_url=watch_url("Y1")
        )
        await _make_set(db, source="youtube", external_id="Y1")

        assert (await reconcile_twins_for_set(db, virtual.id))["candidates"] == 0

    async def test_virtual_parent_is_not_a_candidate(self, db):
        await _make_set(
            db, source="virtual", is_virtual=True, source_url=watch_url("Y1")
        )
        yt = await _make_set(db, source="youtube", external_id="Y1")

        assert (await reconcile_twins_for_set(db, yt.id))["candidates"] == 0

    async def test_missing_set_is_ignored(self, db):
        assert (await reconcile_twins_for_set(db, 999_999))["candidates"] == 0

    async def test_rejected_flag_is_never_undone(self, db):
        twin = await _make_set(db, source_url=watch_url("Y1"))
        yt = await _make_set(db, source="youtube", external_id="Y1")
        flag = await _make_flag(db, twin.id, yt.id, SetFlagStatus.rejected)

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["decided"] == 1
        assert yt.parent_set_id is None
        assert flag.status == SetFlagStatus.rejected
        assert len(await _flags(db)) == 1

    async def test_detached_pair_is_not_attached_again(self, db):
        twin = await _make_set(db, source_url=watch_url("Y1"))
        yt = await _make_set(db, source="youtube", external_id="Y1")
        await _make_flag(db, twin.id, yt.id, SetFlagStatus.attached)

        await reconcile_twins_for_set(db, twin.id)

        assert yt.parent_set_id is None
        assert twin.parent_set_id is None

    async def test_rejection_is_not_undone_through_a_sibling(self, db):
        rejected = await _make_set(db, "Rejected child", channel="Elsewhere")
        sibling = await _make_set(db, source_url=watch_url("Y1"))
        await _make_family(db, rejected, sibling)
        yt = await _make_set(db, source="youtube", external_id="Y1")
        await _make_flag(db, rejected.id, yt.id, SetFlagStatus.rejected)

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["decided"] == 1
        assert yt.parent_set_id is None

    async def test_different_parents_are_counted_without_raising(self, db):
        trackid = await _make_set(db, source_url=watch_url("Y1"))
        await _make_family(db, trackid, await _make_set(db, "Sibling A"))
        yt = await _make_set(db, source="youtube", external_id="Y1")
        await _make_family(db, yt, await _make_set(db, "Sibling B", source="youtube"))
        parent_id = yt.parent_set_id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attach_errors"] == 1
        assert counts["attached"] == 0
        assert yt.parent_set_id == parent_id
        assert await _flags(db) == []

    async def test_set_already_in_the_family_is_left_alone(self, db):
        twin = await _make_set(db, source_url=watch_url("Y1"))
        yt = await _make_set(db, source="youtube", external_id="Y1")
        await _make_family(db, twin, yt)

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["candidates"] == 0
        assert await _flags(db) == []


class TestProlificChannel:
    """A channel list is read whole: no candidate is lost to a cap on proximity."""

    async def test_twin_beyond_fifty_candidates_is_found(self, db):
        for i in range(59):
            await _make_set(db, f"Unrelated Artist {i} Night")
        twin = await _make_set(db, duration_ms=HOUR + 60_000)
        yt = await _make_set(db, source="youtube", external_id="Y1")
        twin_id = twin.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attached"] == 1
        assert counts["channel_truncated"] == 0
        assert (await db.get(DJSet, twin_id)).parent_set_id == yt.parent_set_id

    async def test_two_episodes_beyond_fifty_candidates_stay_ambiguous(self, db):
        for i in range(58):
            await _make_set(db, f"Unrelated Artist {i} Night")
        await _make_set(db, EPISODE_A, duration_ms=HOUR + 30_000)
        await _make_set(db, EPISODE_B, duration_ms=HOUR + 40_000)
        yt = await _make_set(db, source="youtube", external_id="Y1")

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attached"] == 0
        assert counts["flagged"] == 1
        assert yt.parent_set_id is None
        flags = await _flags(db)
        assert len(flags) == 1
        assert flags[0].signals["reason"] == REASON_AMBIGUOUS

    async def test_cap_ignores_the_whole_channel_list(self, db, monkeypatch):
        monkeypatch.setattr(set_twin_service, "TWIN_CHANNEL_CANDIDATE_CAP", 2)
        twin = await _make_set(db)
        await _make_set(db, "Unrelated Artist One")
        await _make_set(db, "Unrelated Artist Two")
        yt = await _make_set(db, source="youtube", external_id="Y1")
        twin_id = twin.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["channel_truncated"] == 1
        assert counts["candidates"] == 0
        assert counts["attached"] == 0
        assert yt.parent_set_id is None
        assert (await db.get(DJSet, twin_id)).parent_set_id is None
        assert await _flags(db) == []

    async def test_list_at_the_cap_is_still_read(self, db, monkeypatch):
        monkeypatch.setattr(set_twin_service, "TWIN_CHANNEL_CANDIDATE_CAP", 2)
        await _make_set(db)
        await _make_set(db, "Unrelated Artist One")
        yt = await _make_set(db, source="youtube", external_id="Y1")

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["channel_truncated"] == 0
        assert counts["attached"] == 1

    async def test_video_match_survives_the_cap(self, db, monkeypatch):
        monkeypatch.setattr(set_twin_service, "TWIN_CHANNEL_CANDIDATE_CAP", 2)
        for i in range(3):
            await _make_set(db, f"Unrelated Artist {i} Night")
        video = await _make_set(
            db, "Other title", channel="Elsewhere", source_url=watch_url("Y1")
        )
        yt = await _make_set(db, source="youtube", external_id="Y1")
        video_id = video.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["channel_truncated"] == 1
        assert counts["attached"] == 1
        assert (await db.get(DJSet, video_id)).parent_set_id == yt.parent_set_id

    async def test_date_match_on_the_same_channel_survives_the_cap(self, db, monkeypatch):
        monkeypatch.setattr(set_twin_service, "TWIN_CHANNEL_CANDIDATE_CAP", 2)
        day = date(2024, 5, 20)
        for i in range(3):
            await _make_set(db, f"Unrelated Artist {i} Night")
        dated = await _make_set(db, event_date=day)
        yt = await _make_set(db, source="youtube", external_id="Y1", event_date=day)
        dated_id = dated.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["channel_truncated"] == 1
        assert counts["attached"] == 1
        assert (await db.get(DJSet, dated_id)).parent_set_id == yt.parent_set_id

    async def test_three_percent_gap_without_date_is_not_a_channel_match(self, db):
        other = await _make_set(db, duration_ms=HOUR + 110_000)
        yt = await _make_set(db, source="youtube", external_id="Y1")
        other_id = other.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["candidates"] == 0
        assert counts["attached"] == 0
        assert (await db.get(DJSet, other_id)).parent_set_id is None
        assert await _flags(db) == []

    async def test_three_percent_gap_with_the_same_date_still_attaches(self, db):
        day = date(2024, 5, 20)
        other = await _make_set(db, duration_ms=HOUR + 110_000, event_date=day)
        yt = await _make_set(db, source="youtube", external_id="Y1", event_date=day)
        other_id = other.id

        counts = await reconcile_twins_for_set(db, yt.id)

        assert counts["attached"] == 1
        assert (await db.get(DJSet, other_id)).parent_set_id == yt.parent_set_id

    async def test_trackid_channel_match_flags_when_the_youtube_list_is_cut(
        self, db, monkeypatch
    ):
        monkeypatch.setattr(set_twin_service, "TWIN_CHANNEL_CANDIDATE_CAP", 2)
        for i in range(2):
            await _make_set(db, f"Unrelated Artist {i} Night")
        yt = await _make_set(db, source="youtube", external_id="Y1")
        trackid = await _make_set(db)
        yt_id = yt.id

        counts = await reconcile_twins_for_set(db, trackid.id)

        assert counts["channel_truncated"] == 0
        assert counts["attached"] == 0
        assert counts["flagged"] == 1
        assert trackid.parent_set_id is None
        assert (await db.get(DJSet, yt_id)).parent_set_id is None
        flag = (await _flags(db))[0]
        assert flag.status == SetFlagStatus.pending
        assert flag.signals["reason"] == REASON_YOUTUBE_SIDE_TRUNCATED

    async def test_trackid_date_match_flags_when_the_youtube_list_is_cut(
        self, db, monkeypatch
    ):
        # The video's own date search would pick this set: the cut still objects.
        monkeypatch.setattr(set_twin_service, "TWIN_CHANNEL_CANDIDATE_CAP", 2)
        day = date(2024, 5, 20)
        for i in range(2):
            await _make_set(db, f"Unrelated Artist {i} Night")
        yt = await _make_set(db, source="youtube", external_id="Y1", event_date=day)
        trackid = await _make_set(db, event_date=day)

        counts = await reconcile_twins_for_set(db, trackid.id)

        assert counts["attached"] == 0
        assert counts["flagged"] == 1
        assert yt.parent_set_id is None
        flag = (await _flags(db))[0]
        assert flag.signals["reason"] == REASON_YOUTUBE_SIDE_TRUNCATED


class TestDurationWindow:
    @pytest.mark.parametrize(
        "max_gap", [DATE_STEP_MAX_DURATION_GAP, CHANNEL_STEP_MAX_DURATION_GAP]
    )
    def test_covers_the_gap_decide_twin_accepts_on_both_sides(self, max_gap):
        low, high = _duration_window(HOUR, max_gap)
        assert abs(low - HOUR) / HOUR <= max_gap
        assert abs(low - 1 - HOUR) / HOUR > max_gap
        # The bound is rounded up: the last whole value below it is still within the
        # gap of the longest duration, the bound itself just past it.
        assert abs(high - 1 - HOUR) / (high - 1) <= max_gap
        assert abs(high - HOUR) / high > max_gap
