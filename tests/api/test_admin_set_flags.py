"""Tests for admin set-flag endpoints (L6)."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from models import DJSet, SetFlag, SetFlagStatus, SetFlagType
from services.set_service import list_source_urls


def _now():
    return datetime.now(timezone.utc)


def _set(title="Set A", source="trackid"):
    return DJSet(source=source, title=title)


def _flag(set_a, set_b, flag_type=SetFlagType.duplicate_candidate, confidence=0.84):
    return SetFlag(
        set_id_a=set_a.id,
        set_id_b=set_b.id,
        flag_type=flag_type,
        confidence=confidence,
        status=SetFlagStatus.pending,
        created_at=_now(),
    )


def _twin_sets():
    """A YouTube set and a TrackID set with no shared track (neither has any)."""
    youtube = DJSet(
        source="youtube",
        title="Ana @ Boiler Room",
        channel="Boiler Room",
        duration_ms=3_600_000,
        source_url="https://www.youtube.com/watch?v=abc",
        played_date=date(2026, 6, 21),
    )
    trackid = DJSet(
        source="trackid",
        title="Ana b2b Aya @ Boiler Room",
        channel="Boiler Room Official",
        duration_ms=3_660_000,
        source_url="https://trackid.net/audiostream/ana",
        played_date=date(2026, 6, 22),
    )
    return youtube, trackid


def _twin_flag(set_a, set_b):
    return SetFlag(
        set_id_a=set_a.id,
        set_id_b=set_b.id,
        flag_type=SetFlagType.duplicate_candidate,
        confidence=None,
        signals={
            "dd": 0.0164,
            "twin_rule": "date",
            "reason": "collaboration marker in one title only: ['b2b']",
        },
        status=SetFlagStatus.pending,
        created_at=_now(),
    )


class TestListSetFlags:
    async def test_returns_pending_flags(self, admin_client, db):
        s1 = _set("Set Alpha")
        s2 = _set("Set Beta")
        db.add(s1)
        db.add(s2)
        await db.flush()
        db.add(_flag(s1, s2))
        await db.commit()

        r = await admin_client.get("/api/admin/set-flags")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["title_a"] == "Set Alpha"
        assert item["title_b"] == "Set Beta"
        assert item["confidence"] == pytest.approx(0.84)
        assert item["status"] == "pending"
        assert item["flag_type"] == "duplicate_candidate"

    async def test_filters_by_status(self, admin_client, db):
        s1 = _set("S1")
        s2 = _set("S2")
        s3 = _set("S3")
        db.add(s1)
        db.add(s2)
        db.add(s3)
        await db.flush()
        f1 = _flag(s1, s2)
        db.add(f1)
        await db.flush()
        f1.status = SetFlagStatus.rejected
        f1.resolved_at = _now()
        f2 = _flag(s1, s3)
        db.add(f2)
        await db.commit()

        r_pending = await admin_client.get("/api/admin/set-flags?status=pending")
        assert r_pending.json()["total"] == 1

        r_rejected = await admin_client.get("/api/admin/set-flags?status=rejected")
        assert r_rejected.json()["total"] == 1

        r_attached = await admin_client.get("/api/admin/set-flags?status=attached")
        assert r_attached.json()["total"] == 0

    async def test_orders_by_confidence_desc(self, admin_client, db):
        """Flags surface by confidence DESC (created_at only breaks ties), so the
        most-confident candidate comes first regardless of how old it is."""
        s1 = _set("S1")
        s2 = _set("S2")
        s3 = _set("S3")
        db.add(s1)
        db.add(s2)
        db.add(s3)
        await db.flush()
        # High confidence created EARLIER, low confidence created LATER: a
        # created_at-only sort would rank the low one first — confidence must win.
        high = _flag(s1, s2, confidence=0.92)
        high.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        low = _flag(s1, s3, confidence=0.40)
        low.created_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
        db.add(high)
        db.add(low)
        await db.commit()

        r = await admin_client.get("/api/admin/set-flags?status=pending")
        assert r.status_code == 200
        confidences = [i["confidence"] for i in r.json()["items"]]
        assert confidences == pytest.approx([0.92, 0.40])

    async def test_null_confidence_sorts_last(self, admin_client, db):
        """A flag with no confidence is pushed to the end (nulls_last), even when
        it is the most recently created."""
        s1 = _set("S1")
        s2 = _set("S2")
        s3 = _set("S3")
        db.add(s1)
        db.add(s2)
        db.add(s3)
        await db.flush()
        scored = _flag(s1, s2, confidence=0.30)
        scored.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        unscored = _flag(s1, s3, confidence=None)
        unscored.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        db.add(scored)
        db.add(unscored)
        await db.commit()

        items = (await admin_client.get("/api/admin/set-flags?status=pending")).json()[
            "items"
        ]
        assert items[0]["confidence"] == pytest.approx(0.30)
        assert items[1]["confidence"] is None

    async def test_pagination(self, admin_client, db):
        s1 = _set("S1")
        s2 = _set("S2")
        s3 = _set("S3")
        db.add(s1)
        db.add(s2)
        db.add(s3)
        await db.flush()
        db.add(_flag(s1, s2))
        await db.flush()
        db.add(
            SetFlag(
                set_id_a=s1.id,
                set_id_b=s3.id,
                flag_type=SetFlagType.duplicate_candidate,
                status=SetFlagStatus.pending,
                created_at=_now(),
            )
        )
        await db.commit()

        r = await admin_client.get("/api/admin/set-flags?limit=1&offset=0")
        data = r.json()
        assert data["total"] == 2
        assert len(data["items"]) == 1

    async def test_exposes_pairwise_event_dates(self, admin_client, db):
        """C13.e: a pairwise flag carries each set's event_date (the admin
        disambiguator shown next to the titles)."""
        s1 = DJSet(source="trackid", title="Set Alpha", event_date=date(2026, 6, 20))
        s2 = DJSet(source="trackid", title="Set Beta", event_date=date(2026, 7, 5))
        db.add(s1)
        db.add(s2)
        await db.flush()
        db.add(_flag(s1, s2))
        await db.commit()

        item = (await admin_client.get("/api/admin/set-flags")).json()["items"][0]
        assert item["event_date_a"] == "2026-06-20"
        assert item["event_date_b"] == "2026-07-05"

    async def test_event_dates_null_when_absent(self, admin_client, db):
        """A set without an event_date reports null, not an error."""
        s1 = _set("Set Alpha")
        s2 = _set("Set Beta")
        db.add(s1)
        db.add(s2)
        await db.flush()
        db.add(_flag(s1, s2))
        await db.commit()

        item = (await admin_client.get("/api/admin/set-flags")).json()["items"][0]
        assert item["event_date_a"] is None
        assert item["event_date_b"] is None

    async def test_exposes_group_member_event_dates(self, admin_client, db):
        """A group flag carries member_event_dates aligned with member_set_ids."""
        s1 = DJSet(source="trackid", title="Part 1", event_date=date(2026, 3, 1))
        s2 = DJSet(source="trackid", title="Part 2", event_date=None)
        s3 = DJSet(source="trackid", title="Part 3", event_date=date(2026, 3, 2))
        db.add(s1)
        db.add(s2)
        db.add(s3)
        await db.flush()
        db.add(
            SetFlag(
                set_id_a=min(s1.id, s2.id, s3.id),
                set_id_b=None,
                group_key="the base title",
                member_set_ids=[s1.id, s2.id, s3.id],
                flag_type=SetFlagType.part_candidate,
                confidence=0.9,
                status=SetFlagStatus.pending,
                created_at=_now(),
            )
        )
        await db.commit()

        item = (await admin_client.get("/api/admin/set-flags")).json()["items"][0]
        assert item["member_event_dates"] == ["2026-03-01", None, "2026-03-02"]

    async def test_exposes_pair_set_context(self, admin_client, db):
        """A pair flag carries each set's channel, duration, link, date and source."""
        s1, s2 = _twin_sets()
        db.add(s1)
        db.add(s2)
        await db.flush()
        db.add(_twin_flag(s1, s2))
        await db.commit()

        item = (await admin_client.get("/api/admin/set-flags")).json()["items"][0]
        assert item["source_a"] == "youtube"
        assert item["source_b"] == "trackid"
        assert item["channel_a"] == "Boiler Room"
        assert item["channel_b"] == "Boiler Room Official"
        assert item["duration_ms_a"] == 3_600_000
        assert item["duration_ms_b"] == 3_660_000
        assert item["source_url_a"] == "https://www.youtube.com/watch?v=abc"
        assert item["source_url_b"] == "https://trackid.net/audiostream/ana"
        assert item["played_date_a"] == "2026-06-21"
        assert item["played_date_b"] == "2026-06-22"
        assert item["signals"]["twin_rule"] == "date"

    async def test_pair_set_context_null_when_absent(self, admin_client, db):
        s1 = _set("Set Alpha")
        s2 = _set("Set Beta")
        db.add(s1)
        db.add(s2)
        await db.flush()
        db.add(_flag(s1, s2))
        await db.commit()

        item = (await admin_client.get("/api/admin/set-flags")).json()["items"][0]
        assert item["source_a"] == "trackid"
        for key in ("channel", "duration_ms", "source_url", "played_date"):
            assert item[f"{key}_a"] is None
            assert item[f"{key}_b"] is None

    async def test_group_flag_gets_no_pair_set_context(self, admin_client, db):
        """A group flag's set_id_a is only its lowest member: nothing leaks from it."""
        s1 = DJSet(
            source="trackid",
            title="Part 1",
            channel="Boiler Room",
            duration_ms=1_800_000,
            source_url="https://trackid.net/audiostream/part-1",
            played_date=date(2026, 3, 1),
        )
        s2 = _set("Part 2")
        db.add(s1)
        db.add(s2)
        await db.flush()
        db.add(
            SetFlag(
                set_id_a=min(s1.id, s2.id),
                set_id_b=None,
                group_key="the base title",
                member_set_ids=[s1.id, s2.id],
                flag_type=SetFlagType.part_candidate,
                confidence=0.9,
                status=SetFlagStatus.pending,
                created_at=_now(),
            )
        )
        await db.commit()

        item = (await admin_client.get("/api/admin/set-flags")).json()["items"][0]
        assert item["member_titles"] == ["Part 1", "Part 2"]
        for key in ("channel", "duration_ms", "source_url", "played_date", "source"):
            assert item[f"{key}_a"] is None
            assert item[f"{key}_b"] is None

    async def test_requires_admin(self, client):
        r = await client.get("/api/admin/set-flags")
        assert r.status_code in (401, 403)

    async def test_non_admin_gets_403(self, auth_client):
        r = await auth_client.get("/api/admin/set-flags")
        assert r.status_code == 403


class TestAttachSetFlag:
    async def test_creates_virtual_parent_and_attaches(self, admin_client, db):
        s1 = _set("Long Title For Set A")
        s2 = _set("Short")
        db.add(s1)
        db.add(s2)
        await db.flush()
        f = _flag(s1, s2)
        db.add(f)
        await db.commit()
        s1_id, s2_id = s1.id, s2.id  # capture before expire_all

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/attach")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        parent_id = data["parent_id"]
        assert isinstance(parent_id, int)

        # Verify flag is now "attached" via list endpoint
        r2 = await admin_client.get("/api/admin/set-flags?status=attached")
        assert r2.json()["total"] == 1

        # Verify virtual parent in DB
        db.expire_all()
        parent = (
            await db.execute(select(DJSet).where(DJSet.id == parent_id))
        ).scalar_one_or_none()
        assert parent is not None
        assert parent.is_virtual is True
        # Most-descriptive title chosen (more significant tokens), not the shortest
        assert parent.title == "Long Title For Set A"

        # Both sets attached
        set_a = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        set_b = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert set_a.parent_set_id == parent_id
        assert set_b.parent_set_id == parent_id

    async def test_attaches_to_existing_parent(self, admin_client, db):
        parent = DJSet(source="virtual", title="Parent", is_virtual=True)
        s1 = _set("Child A")
        s2 = _set("Child B")
        db.add(parent)
        db.add(s1)
        db.add(s2)
        await db.flush()
        s1.parent_set_id = parent.id
        f = _flag(s1, s2)
        db.add(f)
        await db.commit()
        parent_id, s2_id = parent.id, s2.id  # capture before expire_all

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/attach")
        assert r.status_code == 200
        assert r.json()["parent_id"] == parent_id

        # s2 should now be attached to the same parent
        db.expire_all()
        set_b = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert set_b.parent_set_id == parent_id

    async def test_already_resolved_returns_404(self, admin_client, db):
        s1 = _set("Set X")
        s2 = _set("Set Y")
        db.add(s1)
        db.add(s2)
        await db.flush()
        f = _flag(s1, s2)
        db.add(f)
        await db.flush()
        f.status = SetFlagStatus.rejected
        f.resolved_at = _now()
        await db.commit()

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/attach")
        assert r.status_code == 404

    async def test_missing_flag_returns_404(self, admin_client):
        r = await admin_client.post("/api/admin/set-flags/9999/attach")
        assert r.status_code == 404


class TestTwinRuleFlagResolution:
    """A twin_rule pair shares no track and has no confidence: both actions must work."""

    async def test_attach_keeps_the_links_of_both_sets(self, admin_client, db):
        youtube, trackid = _twin_sets()
        db.add(youtube)
        db.add(trackid)
        await db.flush()
        f = _twin_flag(youtube, trackid)
        db.add(f)
        await db.commit()
        youtube_id, trackid_id = youtube.id, trackid.id

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/attach")
        assert r.status_code == 200
        parent_id = r.json()["parent_id"]

        db.expire_all()
        for set_id, url in (
            (youtube_id, "https://www.youtube.com/watch?v=abc"),
            (trackid_id, "https://trackid.net/audiostream/ana"),
        ):
            child = await db.get(DJSet, set_id)
            assert child.parent_set_id == parent_id
            assert child.source_url == url

        pending = await admin_client.get("/api/admin/set-flags?status=pending")
        assert pending.json()["total"] == 0
        assert await list_source_urls(db, parent_id) == [
            "https://www.youtube.com/watch?v=abc",
            "https://trackid.net/audiostream/ana",
        ]

    async def test_attach_refuses_two_different_parents(self, admin_client, db):
        """A video already in another family is a real review reason: attaching must
        not report success while leaving the other set in its own family."""
        parent_a = DJSet(source="virtual", title="Parent A", is_virtual=True)
        parent_b = DJSet(source="virtual", title="Parent B", is_virtual=True)
        db.add(parent_a)
        db.add(parent_b)
        await db.flush()
        youtube, trackid = _twin_sets()
        youtube.parent_set_id = parent_a.id
        trackid.parent_set_id = parent_b.id
        db.add(youtube)
        db.add(trackid)
        await db.flush()
        f = _twin_flag(youtube, trackid)
        db.add(f)
        await db.commit()
        flag_id, parent_b_id, trackid_id = f.id, parent_b.id, trackid.id

        r = await admin_client.post(f"/api/admin/set-flags/{flag_id}/attach")
        assert r.status_code == 400

        db.expire_all()
        assert (await db.get(DJSet, trackid_id)).parent_set_id == parent_b_id
        assert (await db.get(SetFlag, flag_id)).status == SetFlagStatus.pending

    async def test_reject_leaves_both_sets_alone(self, admin_client, db):
        youtube, trackid = _twin_sets()
        db.add(youtube)
        db.add(trackid)
        await db.flush()
        f = _twin_flag(youtube, trackid)
        db.add(f)
        await db.commit()
        youtube_id, trackid_id = youtube.id, trackid.id

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/reject")
        assert r.status_code == 200

        db.expire_all()
        assert (await db.get(DJSet, youtube_id)).parent_set_id is None
        assert (await db.get(DJSet, trackid_id)).parent_set_id is None
        rejected = await admin_client.get("/api/admin/set-flags?status=rejected")
        assert rejected.json()["total"] == 1


class TestRejectSetFlag:
    async def test_rejects_pending_flag(self, admin_client, db):
        s1 = _set("Set M")
        s2 = _set("Set N")
        db.add(s1)
        db.add(s2)
        await db.flush()
        f = _flag(s1, s2)
        db.add(f)
        await db.commit()

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/reject")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Verify via list endpoint
        r2 = await admin_client.get("/api/admin/set-flags?status=rejected")
        assert r2.json()["total"] == 1
        r3 = await admin_client.get("/api/admin/set-flags?status=pending")
        assert r3.json()["total"] == 0

    async def test_already_resolved_returns_404(self, admin_client, db):
        s1 = _set("Set P")
        s2 = _set("Set Q")
        db.add(s1)
        db.add(s2)
        await db.flush()
        f = _flag(s1, s2)
        db.add(f)
        await db.flush()
        f.status = SetFlagStatus.attached
        f.resolved_at = _now()
        await db.commit()

        r = await admin_client.post(f"/api/admin/set-flags/{f.id}/reject")
        assert r.status_code == 404

    async def test_missing_flag_returns_404(self, admin_client):
        r = await admin_client.post("/api/admin/set-flags/9999/reject")
        assert r.status_code == 404


class TestDetachSet:
    async def test_detaches_and_removes_parent_when_one_sibling(
        self, admin_client, db
    ):
        parent = DJSet(source="virtual", title="Parent", is_virtual=True)
        s1 = _set("Child 1")
        s2 = _set("Child 2")
        db.add(parent)
        db.add(s1)
        db.add(s2)
        await db.flush()
        s1.parent_set_id = parent.id
        s2.parent_set_id = parent.id
        await db.commit()
        s1_id, s2_id, parent_id = s1.id, s2.id, parent.id  # capture before expire_all

        r = await admin_client.post(f"/api/admin/sets/{s1_id}/detach")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        db.expire_all()
        # s1 detached
        child1 = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        assert child1.parent_set_id is None

        # s2 also detached (only remaining sibling → parent deleted)
        child2 = (await db.execute(select(DJSet).where(DJSet.id == s2_id))).scalar_one()
        assert child2.parent_set_id is None

        # parent deleted
        p = (
            await db.execute(select(DJSet).where(DJSet.id == parent_id))
        ).scalar_one_or_none()
        assert p is None

    async def test_detaches_keeps_parent_with_multiple_siblings(
        self, admin_client, db
    ):
        parent = DJSet(source="virtual", title="Parent", is_virtual=True)
        s1 = _set("Child 1")
        s2 = _set("Child 2")
        s3 = _set("Child 3")
        db.add(parent)
        db.add(s1)
        db.add(s2)
        db.add(s3)
        await db.flush()
        s1.parent_set_id = parent.id
        s2.parent_set_id = parent.id
        s3.parent_set_id = parent.id
        await db.commit()
        s1_id, parent_id = s1.id, parent.id  # capture before expire_all

        r = await admin_client.post(f"/api/admin/sets/{s1_id}/detach")
        assert r.status_code == 200

        db.expire_all()
        child1 = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        assert child1.parent_set_id is None

        # Parent still exists (2 siblings remain)
        p = (
            await db.execute(select(DJSet).where(DJSet.id == parent_id))
        ).scalar_one_or_none()
        assert p is not None

    async def test_detach_never_deletes_a_real_parent(self, admin_client, db):
        """Only a VIRTUAL parent is collapsed when its last child detaches — a
        real set (and its set_tracks) must never be deleted (invariant #4)."""
        parent = DJSet(source="trackid", title="Real Parent", is_virtual=False)
        s1 = _set("Child 1")
        s2 = _set("Child 2")
        db.add(parent)
        db.add(s1)
        db.add(s2)
        await db.flush()
        s1.parent_set_id = parent.id
        s2.parent_set_id = parent.id
        await db.commit()
        s1_id, parent_id = s1.id, parent.id  # capture before expire_all

        # Detaching s1 leaves a single sibling → the <=1 collapse branch fires.
        r = await admin_client.post(f"/api/admin/sets/{s1_id}/detach")
        assert r.status_code == 200

        db.expire_all()
        child1 = (await db.execute(select(DJSet).where(DJSet.id == s1_id))).scalar_one()
        assert child1.parent_set_id is None

        # The real parent survives even though the collapse branch ran.
        p = (
            await db.execute(select(DJSet).where(DJSet.id == parent_id))
        ).scalar_one_or_none()
        assert p is not None
        assert p.is_virtual is False

    async def test_set_without_parent_returns_400(self, admin_client, db):
        s = _set("Orphan")
        db.add(s)
        await db.commit()

        r = await admin_client.post(f"/api/admin/sets/{s.id}/detach")
        assert r.status_code == 400
        assert "parent" in r.json()["detail"].lower()

    async def test_missing_set_returns_404(self, admin_client):
        r = await admin_client.post("/api/admin/sets/9999/detach")
        assert r.status_code == 404
