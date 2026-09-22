"""Tests for /api/admin/cohort endpoints (C14.a, L3 — admin back)."""
from models import Artist, ArtistCohort


async def _artist(db, name, deezer_id=None):
    a = Artist(name=name, normalized_name=name.lower(), deezer_id=deezer_id)
    db.add(a)
    await db.flush()
    return a


async def _cohort(
    db,
    artist,
    *,
    tier,
    computed_tier=None,
    forced_tier=None,
    pinned=False,
    excluded=False,
    last_checked_at=None,
    signals=None,
):
    row = ArtistCohort(
        artist_id=artist.id,
        tier=tier,
        computed_tier=computed_tier,
        forced_tier=forced_tier,
        pinned=pinned,
        excluded=excluded,
        last_checked_at=last_checked_at,
        signals=signals,
    )
    db.add(row)
    await db.flush()
    return row


class TestCohortAuth:
    async def test_list_requires_auth(self, client):
        r = await client.get("/api/admin/cohort")
        assert r.status_code == 401

    async def test_list_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/cohort")
        assert r.status_code == 403

    async def test_patch_rejected_for_non_admin(self, auth_client):
        r = await auth_client.patch("/api/admin/cohort/1", json={"pinned": True})
        assert r.status_code == 403

    async def test_recompute_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post("/api/admin/cohort/recompute")
        assert r.status_code == 403


class TestCohortList:
    async def test_lists_with_artist_fields(self, admin_client, db):
        a = await _artist(db, "Schrotthagen", deezer_id="42")
        await _cohort(
            db, a, tier=1, computed_tier=1, signals={"nb_lib": 5, "nb_catalog": 12}
        )
        await db.commit()

        r = await admin_client.get("/api/admin/cohort")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["artist_id"] == a.id
        assert item["name"] == "Schrotthagen"
        assert item["deezer_id"] == "42"
        assert item["tier"] == 1
        assert item["computed_tier"] == 1
        assert item["signals"] == {"nb_lib": 5, "nb_catalog": 12}

    async def test_orders_tier_asc(self, admin_client, db):
        a1 = await _artist(db, "Tier Two A")
        a2 = await _artist(db, "Tier One")
        a3 = await _artist(db, "Tier Two B")
        await _cohort(db, a1, tier=2, computed_tier=2)
        await _cohort(db, a2, tier=1, computed_tier=1)
        await _cohort(db, a3, tier=2, computed_tier=2)
        await db.commit()

        r = await admin_client.get("/api/admin/cohort")
        tiers = [i["tier"] for i in r.json()["items"]]
        assert tiers == [1, 2, 2]

    async def test_filter_by_tier(self, admin_client, db):
        a1 = await _artist(db, "One")
        a2 = await _artist(db, "Two")
        await _cohort(db, a1, tier=1, computed_tier=1)
        await _cohort(db, a2, tier=2, computed_tier=2)
        await db.commit()

        r = await admin_client.get("/api/admin/cohort?tier=2")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["artist_id"] == a2.id

    async def test_filter_by_override_pinned(self, admin_client, db):
        a1 = await _artist(db, "Pinned")
        a2 = await _artist(db, "Plain")
        await _cohort(db, a1, tier=1, computed_tier=1, pinned=True)
        await _cohort(db, a2, tier=1, computed_tier=1)
        await db.commit()

        r = await admin_client.get("/api/admin/cohort?override=pinned")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["artist_id"] == a1.id
        assert data["items"][0]["pinned"] is True

    async def test_filter_by_override_excluded(self, admin_client, db):
        a1 = await _artist(db, "Excluded")
        a2 = await _artist(db, "Kept")
        await _cohort(db, a1, tier=1, computed_tier=1, excluded=True)
        await _cohort(db, a2, tier=1, computed_tier=1)
        await db.commit()

        r = await admin_client.get("/api/admin/cohort?override=excluded")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["artist_id"] == a1.id
        assert data["items"][0]["excluded"] is True

    async def test_pagination_bounds_items(self, admin_client, db):
        for i in range(5):
            a = await _artist(db, f"Artist {i}")
            await _cohort(db, a, tier=1, computed_tier=1)
        await db.commit()

        r = await admin_client.get("/api/admin/cohort?page=1&page_size=2")
        data = r.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

        r2 = await admin_client.get("/api/admin/cohort?page=3&page_size=2")
        assert r2.json()["total"] == 5
        assert len(r2.json()["items"]) == 1


class TestCohortOverride:
    async def test_force_tier_updates_effective_tier(self, admin_client, db):
        a = await _artist(db, "Forced")
        await _cohort(db, a, tier=2, computed_tier=2)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"forced_tier": 1}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["forced_tier"] == 1
        assert data["computed_tier"] == 2
        # Effective tier = forced override.
        assert data["tier"] == 1

    async def test_force_tier_2_sets_effective_tier(self, admin_client, db):
        # (a) An explicit forced_tier=2 drives the effective tier to 2.
        a = await _artist(db, "Force2")
        await _cohort(db, a, tier=1, computed_tier=1)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"forced_tier": 2}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["forced_tier"] == 2
        assert data["tier"] == 2

    async def test_unforce_clears_forced_tier_back_to_computed(self, admin_client, db):
        # (b) An explicit forced_tier=null UN-forces → effective falls to computed.
        a = await _artist(db, "Unforce")
        await _cohort(db, a, tier=1, computed_tier=2, forced_tier=1)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"forced_tier": None}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["forced_tier"] is None
        assert data["computed_tier"] == 2
        assert data["tier"] == 2

    async def test_unforce_falls_back_to_pin_floor(self, admin_client, db):
        # Un-forcing a pinned row with no computed tier lands on the pin floor (T1).
        a = await _artist(db, "UnforcePinned")
        await _cohort(db, a, tier=3, computed_tier=None, forced_tier=3, pinned=True)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"forced_tier": None}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["forced_tier"] is None
        assert data["tier"] == 1

    async def test_pin_without_forced_tier_leaves_force_untouched(
        self, admin_client, db
    ):
        # (c) A PATCH that omits forced_tier must NOT clear an existing force
        # (absent key = unchanged, distinct from an explicit null).
        a = await _artist(db, "KeepForce")
        await _cohort(db, a, tier=2, computed_tier=1, forced_tier=2)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"pinned": True}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["pinned"] is True
        assert data["forced_tier"] == 2
        assert data["tier"] == 2

    async def test_pin_floors_tier_when_no_computed(self, admin_client, db):
        # An override-only row (computed_tier NULL) pinned → effective T1.
        a = await _artist(db, "PinnedFloor")
        await _cohort(db, a, tier=2, computed_tier=None)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"pinned": True}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["pinned"] is True
        assert data["tier"] == 1

    async def test_exclude_keeps_computed_tier(self, admin_client, db):
        a = await _artist(db, "Excluded2")
        await _cohort(db, a, tier=2, computed_tier=2)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"excluded": True}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["excluded"] is True
        # Effective tier still resolves to the computed tier.
        assert data["tier"] == 2

    async def test_creates_row_for_artist_outside_cohort(self, admin_client, db):
        # An artist with no cohort row can be pinned in — the row is created.
        a = await _artist(db, "Outsider")
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"pinned": True}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["artist_id"] == a.id
        assert data["pinned"] is True
        assert data["tier"] == 1

        # Verify persistence through the API (avoids reading the shared in-memory
        # connection from the setup session after the endpoint committed on it).
        listing = await admin_client.get("/api/admin/cohort")
        rows = {i["artist_id"]: i for i in listing.json()["items"]}
        assert a.id in rows
        assert rows[a.id]["pinned"] is True

    async def test_writes_audit_log(self, admin_client, db):
        a = await _artist(db, "Audited")
        await _cohort(db, a, tier=2, computed_tier=2)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"forced_tier": 1}
        )
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e for e in audit.json()["items"] if e["action"] == "cohort_override"
        ]
        assert len(entries) == 1
        assert entries[0]["target_id"] == a.id
        assert entries[0]["details"]["forced_tier"] == 1

    async def test_404_for_unknown_artist(self, admin_client):
        r = await admin_client.patch(
            "/api/admin/cohort/999999", json={"pinned": True}
        )
        assert r.status_code == 404

    async def test_rejects_out_of_range_forced_tier(self, admin_client, db):
        a = await _artist(db, "BadTier")
        await _cohort(db, a, tier=1, computed_tier=1)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/cohort/{a.id}", json={"forced_tier": 9}
        )
        assert r.status_code == 422


class TestCohortRecompute:
    async def test_fires_task(self, admin_client, mocker):
        send = mocker.patch(
            "routers.admin.celery.send_task",
            return_value=mocker.Mock(id="rc-task-id"),
        )
        r = await admin_client.post("/api/admin/cohort/recompute")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "queued"
        assert data["task_id"] == "rc-task-id"
        send.assert_called_once_with("workers.tasks.recompute_artist_cohort")

    async def test_audits_recompute(self, admin_client, mocker):
        mocker.patch(
            "routers.admin.celery.send_task",
            return_value=mocker.Mock(id="rc-task-id"),
        )
        r = await admin_client.post("/api/admin/cohort/recompute")
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e for e in audit.json()["items"] if e["action"] == "cohort_recompute"
        ]
        assert len(entries) == 1
        assert entries[0]["details"]["task_id"] == "rc-task-id"
