"""Tests for scripts/reconcile_youtube_twins — catch-up of the existing YouTube sets.

Exercises the coroutines directly, on committed rows: the script rolls back between
batches and expunges its session, so a test reads the state back through ``_parent``.
"""

from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock

import pytest
from models import (
    Artist,
    ArtistActivity,
    DJSet,
    SetArtist,
    SetFlag,
    SetFlagStatus,
    SetFlagType,
    SetTrack,
    UserOpinion,
)
from scripts.reconcile_youtube_twins import (
    REASON_COLLISION,
    _parse_steps,
    apply_plans,
    demote_collisions,
    reconcile_twins,
    repair_parents,
)
from services.image_service import ImageService
from services.set_twin_rules import TwinVerdict
from services.set_twin_service import (
    TwinPlan,
    plan_twin_for_set,
    reconcile_twins_for_set,
)
from sqlalchemy import func, select
from workers.youtube import watch_url

HOUR = 3_600_000
DAY = date(2024, 5, 20)


@pytest.fixture
def copy_spy(monkeypatch):
    spy = MagicMock(return_value=True)
    monkeypatch.setattr(ImageService, "copy_object", staticmethod(spy))
    return spy


async def _make_set(db, title="Peggy Gou Forest Gathering", source="trackid", **fields):
    fields.setdefault("duration_ms", HOUR)
    fields.setdefault("channel", "Cercle")
    fields.setdefault("channel_canonical", fields["channel"])
    dj_set = DJSet(title=title, source=source, **fields)
    db.add(dj_set)
    await db.flush()
    return dj_set.id


async def _make_youtube(db, external_id, **fields):
    return await _make_set(db, source="youtube", external_id=external_id, **fields)


async def _video_pair(db, video="V1", channel="Cercle"):
    """A YouTube set and a set on the same video, nothing else in common."""
    twin = await _make_set(
        db, "Unrelated title", channel="Elsewhere", source_url=watch_url(video)
    )
    yt = await _make_youtube(db, video, channel=channel)
    return yt, twin


async def _date_pair(db, title, channel):
    twin = await _make_set(db, title, channel=channel, event_date=DAY)
    yt = await _make_youtube(db, f"yt-{title}", title=title, channel=channel, event_date=DAY)
    return yt, twin


async def _channel_pair(db, title, channel):
    twin = await _make_set(db, title, channel=channel)
    yt = await _make_youtube(db, f"yt-{title}", title=title, channel=channel)
    return yt, twin


async def _parent(db, set_id):
    return (
        await db.execute(select(DJSet.parent_set_id).where(DJSet.id == set_id))
    ).scalar_one()


async def _flags(db):
    return (await db.execute(select(SetFlag))).scalars().all()


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


class TestDryRun:
    async def test_twins_writes_nothing(self, db, copy_spy):
        yt, twin = await _video_pair(db)
        await _make_set(db, "Peggy Gou Night 2", channel="Other")
        await _make_youtube(db, "Y2", title="Peggy Gou Night", channel="Other")
        await db.commit()
        sets_before = await _count(db, DJSet)

        stats = await reconcile_twins(db, sample=5, flag_review=True)

        assert stats["would_attach"] == 1
        assert stats["would_review"] == 1
        assert stats["attached"] == stats["flagged"] == 0
        assert await _parent(db, yt) is None
        assert await _parent(db, twin) is None
        assert await _flags(db) == []
        assert await _count(db, DJSet) == sets_before
        copy_spy.assert_not_called()

    async def test_repair_parents_writes_nothing(self, db, copy_spy):
        parent = DJSet(title="Family", source="virtual", is_virtual=True)
        db.add(parent)
        await db.flush()
        parent_id = parent.id
        await _make_set(
            db,
            parent_set_id=parent_id,
            has_artwork=True,
            source_url="https://example.com/a",
            event_date=DAY,
        )
        await db.commit()

        stats = await repair_parents(db)

        assert stats["parents"] == 1
        assert stats["links_gained"] == 1
        assert stats["channels_gained"] == 1
        assert stats["dates_gained"] == 1
        assert stats["artworks_copied"] == 1
        copy_spy.assert_not_called()
        row = (
            await db.execute(
                select(
                    DJSet.source_url,
                    DJSet.channel,
                    DJSet.event_date,
                    DJSet.has_artwork,
                ).where(DJSet.id == parent_id)
            )
        ).one()
        assert row.source_url is None
        assert row.channel is None
        assert row.event_date is None
        assert not row.has_artwork
        # The patched method is back in place once the run is over.
        assert ImageService.copy_object is copy_spy


class TestSameDecisionAsTheEntry:
    @pytest.mark.parametrize(
        "make_pair", [_date_pair, _channel_pair], ids=["date", "channel"]
    )
    async def test_apply_matches_reconcile_twins_for_set(self, db, copy_spy, make_pair):
        # Unrelated titles: the second twin must not be a candidate of the first set.
        yt_entry, twin_entry = await make_pair(db, "Peggy Gou Forest Gathering", "Cercle")
        await db.commit()
        plan = await plan_twin_for_set(db, yt_entry)
        counts = await reconcile_twins_for_set(db, yt_entry)
        await db.commit()
        db.expunge_all()
        assert counts["attached"] == 1

        yt_script, twin_script = await make_pair(db, "Ben Klock Berghain Closing", "Boiler")
        await db.commit()
        stats = await reconcile_twins(db, apply=True)
        assert stats["attached"] == 1

        for yt, twin in ((yt_entry, twin_entry), (yt_script, twin_script)):
            parent = await _parent(db, yt)
            assert parent is not None
            assert await _parent(db, twin) == parent

        flags = await _flags(db)
        assert len(flags) == 2
        assert {f.status for f in flags} == {SetFlagStatus.attached}
        assert {f.flag_type for f in flags} == {SetFlagType.duplicate_candidate}
        assert flags[0].signals == flags[1].signals
        assert flags[0].signals["twin_rule"] == plan.step
        assert flags[0].signals["reason"] == plan.reason

    async def test_plan_writes_nothing_and_names_the_winner(self, db):
        yt, twin = await _video_pair(db)
        await db.commit()

        plan = await plan_twin_for_set(db, yt)

        assert plan.winner_id == twin
        assert plan.winner_family_id == twin
        assert plan.verdict == TwinVerdict.ATTACH
        assert plan.step == "video"
        assert plan.reason == "same video id"
        assert plan.signals["same_channel"] is False
        assert plan.channel_truncated is False
        assert await _flags(db) == []

    async def test_plan_without_twin_has_no_winner(self, db):
        yt = await _make_youtube(db, "Y1")
        await db.commit()

        plan = await plan_twin_for_set(db, yt)

        assert plan.winner_id is None
        assert plan.verdict is None


class TestApplyBySteps:
    async def test_video_step_leaves_date_and_channel_alone(self, db, copy_spy):
        video_yt, video_twin = await _video_pair(db)
        date_yt, _ = await _date_pair(db, "Ben Klock Berghain", "Date channel")
        channel_yt, _ = await _channel_pair(db, "Nina Kraviz Printworks", "Channel one")
        await db.commit()

        stats = await reconcile_twins(db, steps=("video",), apply=True)

        assert stats["attached"] == 1
        assert stats["other_steps"] == 2
        assert await _parent(db, video_yt) == await _parent(db, video_twin)
        assert await _parent(db, video_yt) is not None
        assert await _parent(db, date_yt) is None
        assert await _parent(db, channel_yt) is None

    async def test_steps_can_run_one_after_the_other(self, db, copy_spy):
        date_yt, _ = await _date_pair(db, "Ben Klock Berghain", "Date channel")
        channel_yt, _ = await _channel_pair(db, "Nina Kraviz Printworks", "Channel one")
        await db.commit()

        await reconcile_twins(db, steps=("date",), apply=True)
        assert await _parent(db, date_yt) is not None
        assert await _parent(db, channel_yt) is None

        await reconcile_twins(db, steps=("channel",), apply=True)
        assert await _parent(db, channel_yt) is not None

    def test_parse_steps(self):
        assert _parse_steps("video, date") == ("video", "date")
        with pytest.raises(Exception, match="steps must be among"):
            _parse_steps("video,title")


class TestIdempotence:
    async def test_second_pass_attaches_nothing(self, db, copy_spy):
        yt, _ = await _video_pair(db)
        await db.commit()

        first = await reconcile_twins(db, apply=True)
        parent = await _parent(db, yt)
        second = await reconcile_twins(db, apply=True, flag_review=True)

        assert first["attached"] == 1
        assert second["attached"] == second["flagged"] == second["would_attach"] == 0
        assert second["scanned"] == 0
        assert await _parent(db, yt) == parent
        assert len(await _flags(db)) == 1

    async def test_second_pass_does_not_flag_twice(self, db, copy_spy):
        await _make_set(db, "Peggy Gou Night 2", channel="Other")
        await _make_youtube(db, "Y2", title="Peggy Gou Night", channel="Other")
        await db.commit()

        first = await reconcile_twins(db, apply=True, flag_review=True)
        second = await reconcile_twins(db, apply=True, flag_review=True)

        assert first["flagged"] == 1
        assert second["flagged"] == 0
        assert second["excluded_existing_flag"] == 1
        assert len(await _flags(db)) == 1


class TestDecisionMemory:
    async def test_rejected_flag_is_respected(self, db, copy_spy):
        yt, twin = await _video_pair(db)
        db.add(
            SetFlag(
                set_id_a=min(yt, twin),
                set_id_b=max(yt, twin),
                flag_type=SetFlagType.duplicate_candidate,
                status=SetFlagStatus.rejected,
                created_at=func.now(),
            )
        )
        await db.commit()

        stats = await reconcile_twins(db, apply=True, flag_review=True)

        assert stats["attached"] == 0
        assert stats["excluded_existing_flag"] == 1
        assert await _parent(db, yt) is None
        flags = await _flags(db)
        assert len(flags) == 1
        assert flags[0].status == SetFlagStatus.rejected

    async def test_unreliable_twin_is_ignored(self, db, copy_spy):
        await _make_set(db, source_url=watch_url("Y1"), unreliable=True)
        yt = await _make_youtube(db, "Y1")
        await db.commit()

        stats = await reconcile_twins(db, apply=True)

        assert stats["attached"] == 0
        assert await _parent(db, yt) is None
        assert await _flags(db) == []


class TestFamilies:
    async def test_twin_child_of_a_family_brings_the_youtube_set_in(self, db, copy_spy):
        parent = DJSet(title="Family", source="virtual", is_virtual=True)
        db.add(parent)
        await db.flush()
        parent_id = parent.id
        await _make_set(
            db, "Unrelated", parent_set_id=parent_id, source_url=watch_url("Y1")
        )
        await _make_set(db, "Sibling", channel="Other", parent_set_id=parent_id)
        yt = await _make_youtube(db, "Y1")
        await db.commit()

        stats = await reconcile_twins(db, apply=True)

        assert stats["attached"] == 1
        assert await _parent(db, yt) == parent_id

    async def test_different_parents_are_counted_and_the_run_goes_on(self, db, copy_spy):
        first_parent = DJSet(title="A", source="virtual", is_virtual=True)
        other_parent = DJSet(title="B", source="virtual", is_virtual=True)
        db.add_all([first_parent, other_parent])
        await db.flush()
        first_parent_id, other_parent_id = first_parent.id, other_parent.id
        await _make_set(
            db, "Unrelated", parent_set_id=first_parent_id, source_url=watch_url("Y1")
        )
        moved = await _make_youtube(db, "Y1")
        next_yt, next_twin = await _video_pair(db, "Y2")
        await db.commit()
        plans = [
            await plan_twin_for_set(db, moved),
            await plan_twin_for_set(db, next_yt),
        ]

        # The set joined another family between the plan and the write.
        row = await db.get(DJSet, moved)
        row.parent_set_id = other_parent_id
        await db.commit()
        db.expunge_all()

        stats = await apply_plans(db, plans)

        assert stats["different_parents"] == 1
        assert stats["attached"] == 1
        assert await _parent(db, moved) == other_parent_id
        assert await _parent(db, next_yt) == await _parent(db, next_twin)

    async def test_error_rolls_back_the_pair_and_the_run_goes_on(
        self, db, copy_spy, monkeypatch
    ):
        from scripts import reconcile_youtube_twins as script

        bad_yt, _ = await _video_pair(db, "Y1")
        good_yt, _ = await _video_pair(db, "Y2")
        await db.commit()
        real_apply = script.apply_twin_plan

        async def flaky(session, plan):
            if plan.set_id == bad_yt:
                raise RuntimeError("simulated failure")
            return await real_apply(session, plan)

        monkeypatch.setattr(script, "apply_twin_plan", flaky)

        stats = await reconcile_twins(db, apply=True)

        assert stats["errors"] == 1
        assert stats["attached"] == 1
        assert await _parent(db, bad_yt) is None
        assert await _parent(db, good_yt) is not None

    async def test_plan_overtaken_by_a_new_decision_is_skipped(self, db, copy_spy):
        yt, twin = await _video_pair(db)
        await db.commit()
        plan = await plan_twin_for_set(db, yt)

        # An admin rejects the pair after the plan.
        db.add(
            SetFlag(
                set_id_a=min(yt, twin),
                set_id_b=max(yt, twin),
                flag_type=SetFlagType.duplicate_candidate,
                status=SetFlagStatus.rejected,
                created_at=func.now(),
            )
        )
        await db.commit()

        stats = await apply_plans(db, [plan])

        assert stats["stale"] == 1
        assert stats["attached"] == 0
        assert await _parent(db, yt) is None


class TestCollisions:
    async def test_two_youtube_sets_on_one_twin_outside_video_go_to_review(
        self, db, copy_spy
    ):
        twin = await _make_set(db, "Peggy Gou Forest Gathering Sunrise")
        y1 = await _make_youtube(db, "Y1")
        y2 = await _make_youtube(db, "Y2")
        await db.commit()

        stats = await reconcile_twins(db, apply=True)

        assert stats["collisions"] == 2
        assert stats["attached"] == 0
        assert stats["flagged"] == 0  # no --flag-review
        assert await _parent(db, y1) is None
        assert await _parent(db, y2) is None
        assert await _parent(db, twin) is None
        assert await _flags(db) == []

    async def test_collision_is_flagged_with_flag_review(self, db, copy_spy):
        await _make_set(db, "Peggy Gou Forest Gathering Sunrise")
        await _make_youtube(db, "Y1")
        await _make_youtube(db, "Y2")
        await db.commit()

        stats = await reconcile_twins(db, apply=True, flag_review=True)

        assert stats["attached"] == 0
        assert stats["flagged"] == 2
        flags = await _flags(db)
        assert {f.status for f in flags} == {SetFlagStatus.pending}
        assert {f.signals["reason"] for f in flags} == {REASON_COLLISION}

    async def test_collision_across_steps_holds_when_only_one_step_is_asked(
        self, db, copy_spy
    ):
        await _make_set(db, "Peggy Gou Forest Gathering Sunrise", event_date=DAY)
        by_date = await _make_youtube(db, "Y1", event_date=DAY)
        by_channel = await _make_youtube(db, "Y2")
        await db.commit()

        stats = await reconcile_twins(db, steps=("date",), apply=True)

        assert stats["attached"] == 0
        assert await _parent(db, by_date) is None
        assert await _parent(db, by_channel) is None

    async def test_two_youtube_sets_on_one_family_by_video_are_attached(
        self, db, copy_spy
    ):
        # A set holds one URL and (source, external_id) is unique: two videos can only
        # reach one family through two of its members.
        parent = DJSet(title="Family", source="virtual", is_virtual=True)
        db.add(parent)
        await db.flush()
        parent_id = parent.id
        await _make_set(
            db, "Unrelated one", channel="A", parent_set_id=parent_id,
            source_url=watch_url("V1"),
        )
        await _make_set(
            db, "Unrelated two", channel="B", parent_set_id=parent_id,
            source_url=watch_url("V2"),
        )
        y1 = await _make_youtube(db, "V1", channel="C")
        y2 = await _make_youtube(db, "V2", channel="C")
        await db.commit()

        stats = await reconcile_twins(db, apply=True)

        assert stats["collisions"] == 0
        assert stats["attached"] == 2
        assert await _parent(db, y1) == parent_id
        assert await _parent(db, y2) == parent_id

    async def test_two_video_plans_on_one_twin_do_not_collide(self):
        plan = TwinPlan(
            set_id=1, winner_id=9, winner_family_id=9,
            verdict=TwinVerdict.ATTACH, step="video",
        )

        kept = demote_collisions([plan, replace(plan, set_id=2)])

        assert [p.verdict for p in kept] == [TwinVerdict.ATTACH, TwinVerdict.ATTACH]

    async def test_review_plan_does_not_contend_with_an_attachment(self):
        attach = TwinPlan(
            set_id=1, winner_id=9, winner_family_id=9,
            verdict=TwinVerdict.ATTACH, step="channel",
        )
        review = replace(attach, set_id=2, verdict=TwinVerdict.REVIEW, reason="number")

        kept = demote_collisions([attach, review])

        assert kept == [attach, review]

    async def test_limit_on_apply_still_sees_the_collision(self, db, copy_spy):
        await _make_set(db, "Peggy Gou Forest Gathering Sunrise")
        y1 = await _make_youtube(db, "Y1")
        y2 = await _make_youtube(db, "Y2")
        await db.commit()

        stats = await reconcile_twins(db, apply=True, limit=1)

        assert stats["scanned"] == 2
        assert stats["attached"] == 0
        assert await _parent(db, y1) is None
        assert await _parent(db, y2) is None


class TestRepairParents:
    async def _family(self, db):
        parent = DJSet(
            title="Family",
            source="virtual",
            is_virtual=True,
            duration_ms=HOUR,
        )
        db.add(parent)
        await db.flush()
        parent_id = parent.id
        child = await _make_set(
            db,
            parent_set_id=parent_id,
            source_url=watch_url("V1"),
            event_date=DAY,
            has_artwork=True,
        )
        artist = Artist(name="Peggy Gou", normalized_name="peggy gou")
        db.add(artist)
        await db.flush()
        db.add(SetArtist(set_id=child, artist_id=artist.id, role="dj"))
        for position in (1, 2):
            db.add(
                SetTrack(
                    set_id=parent_id,
                    position=position,
                    raw_title=f"Track {position}",
                    raw_artist="DJ",
                )
            )
        await db.commit()
        return parent_id

    async def test_gains_metadata_without_losing_tracks(self, db, copy_spy):
        parent_id = await self._family(db)

        stats = await repair_parents(db, apply=True)

        assert stats["parents"] == 1
        assert stats["links_gained"] == 1
        assert stats["channels_gained"] == 1
        assert stats["dates_gained"] == 1
        assert stats["djs_gained"] == 1
        assert stats["artworks_copied"] == 1
        copy_spy.assert_called_once()
        row = (
            await db.execute(
                select(
                    DJSet.source_url,
                    DJSet.channel,
                    DJSet.event_date,
                    DJSet.has_artwork,
                ).where(DJSet.id == parent_id)
            )
        ).one()
        assert row.source_url == watch_url("V1")
        assert row.channel == "Cercle"
        assert row.event_date == DAY
        assert row.has_artwork
        tracks = (
            await db.execute(
                select(func.count())
                .select_from(SetTrack)
                .where(SetTrack.set_id == parent_id)
            )
        ).scalar_one()
        assert tracks == 2

    async def test_is_idempotent(self, db, copy_spy):
        await self._family(db)
        await repair_parents(db, apply=True)
        copy_spy.reset_mock()

        stats = await repair_parents(db, apply=True)

        assert stats["parents"] == 1
        assert stats["links_gained"] == stats["djs_gained"] == 0
        assert stats["artworks_copied"] == 0
        copy_spy.assert_not_called()

    async def test_counts_a_parent_turned_unreliable(self, db, copy_spy):
        parent = DJSet(title="Family", source="virtual", is_virtual=True)
        db.add(parent)
        await db.flush()
        await _make_set(db, parent_set_id=parent.id, unreliable=True)
        await db.commit()

        stats = await repair_parents(db)

        assert stats["became_unreliable"] == 1

    async def test_failed_batch_is_rolled_back_and_the_run_goes_on(
        self, db, copy_spy, monkeypatch
    ):
        from scripts import reconcile_youtube_twins as script

        parent_id = await self._family(db)
        real_sync = script.sync_parent_metadata
        calls = []

        async def flaky(session, pid):
            await real_sync(session, pid)
            calls.append(pid)
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(script, "sync_parent_metadata", flaky)

        stats = await repair_parents(db, apply=True)

        assert calls == [parent_id]
        assert stats["errors"] == 1
        assert stats["parents"] == 0
        channel = (
            await db.execute(select(DJSet.channel).where(DJSet.id == parent_id))
        ).scalar_one()
        assert channel is None

    async def test_limit(self, db, copy_spy):
        for title in ("A", "B", "C"):
            db.add(DJSet(title=title, source="virtual", is_virtual=True))
        await db.commit()

        stats = await repair_parents(db, apply=True, limit=2)

        assert stats["parents"] == 2
        assert stats["childless"] == 2


class TestFlagReview:
    async def test_review_flag_only_with_flag_review(self, db, copy_spy):
        await _make_set(db, "Peggy Gou Night 2", channel="Other")
        yt = await _make_youtube(db, "Y2", title="Peggy Gou Night", channel="Other")
        await db.commit()

        without = await reconcile_twins(db, apply=True)
        assert without["would_review"] == 1
        assert without["flagged"] == 0
        assert await _flags(db) == []

        with_flag = await reconcile_twins(db, apply=True, flag_review=True)
        assert with_flag["flagged"] == 1
        flags = await _flags(db)
        assert len(flags) == 1
        assert flags[0].status == SetFlagStatus.pending
        assert await _parent(db, yt) is None


class TestLimit:
    async def test_dry_run_caps_the_scan(self, db):
        for video in ("Y1", "Y2", "Y3"):
            await _video_pair(db, video)
        await db.commit()

        stats = await reconcile_twins(db, limit=2)

        assert stats["scanned"] == 2
        assert stats["would_attach"] == 2

    async def test_apply_caps_the_writes_and_a_rerun_finishes(self, db, copy_spy):
        for video in ("Y1", "Y2", "Y3"):
            await _video_pair(db, video)
        await db.commit()

        first = await reconcile_twins(db, apply=True, limit=2)
        assert first["attached"] == 2

        second = await reconcile_twins(db, apply=True, limit=2)
        assert second["scanned"] == 1
        assert second["attached"] == 1


class TestReport:
    async def test_counts_what_points_at_the_sets_to_attach(
        self, db, copy_spy, auth_user
    ):
        yt, _ = await _video_pair(db)
        artist = Artist(name="Peggy Gou", normalized_name="peggy gou")
        db.add(artist)
        await db.flush()
        db.add(
            ArtistActivity(
                artist_id=artist.id,
                activity_type="set",
                source="youtube",
                external_id=str(yt),
                set_id=yt,
            )
        )
        db.add(
            UserOpinion(
                user_id=auth_user.id,
                entity_type="set",
                entity_key=str(yt),
                opinion="liked",
            )
        )
        await db.commit()

        stats = await reconcile_twins(db)

        assert stats["opinions"] == 1
        assert stats["activities"] == 1
        assert await _count(db, UserOpinion) == 1

    async def test_counts_the_artworks_to_copy(self, db):
        with_cover, _ = await _video_pair(db, "Y1")
        await _video_pair(db, "Y2")
        row = await db.get(DJSet, with_cover)
        row.has_artwork = True
        await db.commit()

        stats = await reconcile_twins(db)

        assert stats["artworks_to_copy"] == 1

    async def test_sample_prints_both_sides_and_the_signals(self, db, capsys):
        yt, twin = await _video_pair(db)
        await db.commit()

        await reconcile_twins(db, sample=5)

        out = capsys.readouterr().out
        assert "sample: video / attach (1)" in out
        assert f"#{yt} [youtube]" in out
        assert f"#{twin} [trackid]" in out
        assert "upload_delta_days=" in out
        assert "reason='same video id'" in out
