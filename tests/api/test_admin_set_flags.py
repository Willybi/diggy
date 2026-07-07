"""Tests for admin set-flag endpoints (L6)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import DJSet, SetFlag, SetFlagStatus, SetFlagType


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
        # Shorter title chosen
        assert parent.title == "Short"

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
