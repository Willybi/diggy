"""Tests for /api/admin/channels endpoints (C14.b, L3 — admin back)."""
from unittest.mock import AsyncMock

from models import Channel, DJSet, TrackIdIndex


async def _channel(db, name, *, external_id=None, watched=True, excluded=False):
    row = Channel(
        platform="youtube",
        external_id=external_id,
        name=name,
        watched=watched,
        excluded=excluded,
    )
    db.add(row)
    await db.flush()
    return row


async def _set(db, title="A set"):
    s = DJSet(source="youtube", title=title)
    db.add(s)
    await db.flush()
    return s


async def _tid(db, channel, trackid_id, *, set_id=None):
    row = TrackIdIndex(trackid_id=trackid_id, channel=channel, set_id=set_id)
    db.add(row)
    await db.flush()
    return row


class TestChannelAuth:
    async def test_list_requires_auth(self, client):
        r = await client.get("/api/admin/channels")
        assert r.status_code == 401

    async def test_list_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/channels")
        assert r.status_code == 403

    async def test_candidates_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/channels/candidates")
        assert r.status_code == 403

    async def test_search_requires_auth(self, client):
        r = await client.get("/api/admin/channels/search?q=boiler")
        assert r.status_code == 401

    async def test_search_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/channels/search?q=boiler")
        assert r.status_code == 403

    async def test_add_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post("/api/admin/channels", json={"url": "x"})
        assert r.status_code == 403

    async def test_patch_rejected_for_non_admin(self, auth_client):
        r = await auth_client.patch("/api/admin/channels/1", json={"watched": False})
        assert r.status_code == 403


class TestChannelList:
    async def test_empty(self, admin_client):
        r = await admin_client.get("/api/admin/channels")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "items": []}

    async def test_lists_with_fields(self, admin_client, db):
        await _channel(db, "Boiler Room", external_id="UC1", watched=True)
        await db.commit()

        r = await admin_client.get("/api/admin/channels")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["name"] == "Boiler Room"
        assert item["platform"] == "youtube"
        assert item["external_id"] == "UC1"
        assert item["watched"] is True
        assert item["excluded"] is False

    async def test_filter_by_watched(self, admin_client, db):
        await _channel(db, "On", external_id="UCon", watched=True)
        await _channel(db, "Off", external_id="UCoff", watched=False)
        await db.commit()

        r = await admin_client.get("/api/admin/channels?watched=false")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Off"

    async def test_pagination_bounds_items(self, admin_client, db):
        for i in range(5):
            await _channel(db, f"Chan {i}", external_id=f"UC{i}")
        await db.commit()

        r = await admin_client.get("/api/admin/channels?page=1&page_size=2")
        data = r.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

        r2 = await admin_client.get("/api/admin/channels?page=3&page_size=2")
        assert r2.json()["total"] == 5
        assert len(r2.json()["items"]) == 1


class TestChannelCandidates:
    async def test_empty(self, admin_client):
        r = await admin_client.get("/api/admin/channels/candidates")
        assert r.status_code == 200
        assert r.json() == {"items": []}

    async def test_ranks_least_covered_first(self, admin_client, db):
        # "Untapped": 3 indexed, 0 linked → uncovered 3 (highest discovery value).
        s = await _set(db)
        await _tid(db, "Untapped", 101)
        await _tid(db, "Untapped", 102)
        await _tid(db, "Untapped", 103)
        # "Covered": 3 indexed, 2 linked → uncovered 1.
        await _tid(db, "Covered", 201, set_id=s.id)
        await _tid(db, "Covered", 202, set_id=s.id)
        await _tid(db, "Covered", 203)
        await db.commit()

        r = await admin_client.get("/api/admin/channels/candidates")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [i["name"] for i in items] == ["Untapped", "Covered"]
        untapped, covered = items
        assert untapped["trackid_count"] == 3
        assert untapped["set_count"] == 0
        assert covered["trackid_count"] == 3
        assert covered["set_count"] == 2

    async def test_excludes_already_curated_and_null_channels(self, admin_client, db):
        # A channel already in `channels` is not proposed again.
        await _channel(db, "Known", external_id="UCknown")
        await _tid(db, "Known", 301)
        await _tid(db, "Fresh", 302)
        # A NULL-channel indexed row is ignored.
        await _tid(db, None, 303)
        await db.commit()

        r = await admin_client.get("/api/admin/channels/candidates")
        names = [i["name"] for i in r.json()["items"]]
        assert names == ["Fresh"]

    async def test_limit(self, admin_client, db):
        for i in range(4):
            await _tid(db, f"C{i}", 400 + i)
        await db.commit()

        r = await admin_client.get("/api/admin/channels/candidates?limit=2")
        assert len(r.json()["items"]) == 2


class TestChannelAdd:
    async def test_creates_row(self, admin_client, mocker):
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCabc1234567890abcdef12",
        )
        r = await admin_client.post(
            "/api/admin/channels",
            json={"url": "https://youtube.com/@boiler", "name": "Boiler Room"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["external_id"] == "UCabc1234567890abcdef12"
        assert data["name"] == "Boiler Room"
        assert data["platform"] == "youtube"
        assert data["watched"] is True

        listing = await admin_client.get("/api/admin/channels")
        assert listing.json()["total"] == 1

    async def test_idempotent_on_platform_external_id(self, admin_client, mocker):
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCsame1234567890abcdef1",
        )
        first = await admin_client.post(
            "/api/admin/channels", json={"url": "u1", "name": "First"}
        )
        assert first.status_code == 200
        second = await admin_client.post(
            "/api/admin/channels", json={"url": "u1-dup", "name": "First"}
        )
        assert second.status_code == 200

        listing = await admin_client.get("/api/admin/channels")
        data = listing.json()
        assert data["total"] == 1
        assert data["items"][0]["external_id"] == "UCsame1234567890abcdef1"

    async def test_auto_fetches_title_when_no_name(self, admin_client, mocker):
        # (a) Added by URL without a name → the fetched channel title is stored.
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCtitle1234567890abcdef",
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value="Boiler Room",
        )
        r = await admin_client.post("/api/admin/channels", json={"url": "u-title"})
        assert r.status_code == 200
        assert r.json()["name"] == "Boiler Room"

    async def test_refreshes_placeholder_name_on_readd(
        self, admin_client, db, mocker
    ):
        # (b) A row whose name is still the channel id (placeholder) is refreshed
        #     to the fetched title on a re-add without an explicit name.
        cid = "UCplace1234567890abcdef"
        await _channel(db, cid, external_id=cid, watched=False)
        await db.commit()

        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value=cid,
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value="Real Title",
        )
        r = await admin_client.post("/api/admin/channels", json={"url": "u-re"})
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Real Title"
        assert data["watched"] is True  # re-watch preserved

    async def test_curated_name_not_overwritten_on_readd(
        self, admin_client, db, mocker
    ):
        # A real (non-placeholder) name is never clobbered by a nameless re-add.
        cid = "UCcur1234567890abcdef12"
        await _channel(db, "Curated Name", external_id=cid, watched=False)
        await db.commit()

        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value=cid,
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value="Different Title",
        )
        r = await admin_client.post("/api/admin/channels", json={"url": "u-cur"})
        assert r.status_code == 200
        assert r.json()["name"] == "Curated Name"

    async def test_explicit_name_wins_over_fetch(self, admin_client, mocker):
        # (c) An explicit body.name always wins — fetch_channel_title not consulted.
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCexpl1234567890abcdef1",
        )
        fetch = mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value="Fetched Title",
        )
        r = await admin_client.post(
            "/api/admin/channels",
            json={"url": "u-expl", "name": "Chosen Name"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Chosen Name"
        fetch.assert_not_called()

    async def test_falls_back_to_channel_id_when_no_name(self, admin_client, mocker):
        # (d) No body.name AND no title fetched (e.g. no API key) → channel_id.
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCnoname1234567890abcde",
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value=None,
        )
        r = await admin_client.post("/api/admin/channels", json={"url": "u"})
        assert r.status_code == 200
        assert r.json()["name"] == "UCnoname1234567890abcde"

    async def test_400_when_unresolvable(self, admin_client, mocker):
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value=None,
        )
        r = await admin_client.post(
            "/api/admin/channels", json={"url": "not-a-channel"}
        )
        assert r.status_code == 400

    async def test_writes_audit_log(self, admin_client, mocker):
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCaudit1234567890abcdef",
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value=None,
        )
        r = await admin_client.post(
            "/api/admin/channels", json={"url": "https://y/@a"}
        )
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [e for e in audit.json()["items"] if e["action"] == "channel_add"]
        assert len(entries) == 1
        assert entries[0]["details"]["url"] == "https://y/@a"

    async def test_dispatches_historical_backfill(self, admin_client, mocker):
        # L7: adding a channel fires the one-shot historical backfill task for its id.
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCback1234567890abcdef1",
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value=None,
        )
        send = mocker.patch("routers.admin.celery.send_task")
        r = await admin_client.post("/api/admin/channels", json={"url": "u-bk"})
        assert r.status_code == 200
        item_id = r.json()["id"]
        send.assert_called_once_with(
            "workers.tasks.backfill_youtube_channel", args=[item_id]
        )

    async def test_dispatch_failure_does_not_fail_add(self, admin_client, mocker):
        # Best-effort dispatch: a broker outage must not fail the add.
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCboom1234567890abcdef1",
        )
        mocker.patch(
            "services.channel_service.fetch_channel_title",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "routers.admin.celery.send_task",
            side_effect=RuntimeError("broker down"),
        )
        r = await admin_client.post("/api/admin/channels", json={"url": "u-boom"})
        assert r.status_code == 200

        listing = await admin_client.get("/api/admin/channels")
        assert listing.json()["total"] == 1


class TestChannelSearch:
    _HITS = [
        {
            "channel_id": "UCabc1234567890abcdef12",
            "title": "Boiler Room",
            "description": "Music broadcaster",
            "thumbnail_url": "https://i.ytimg.com/def.jpg",
        },
        {
            "channel_id": "UCxyz1234567890abcdef98",
            "title": "Boiler Room Berlin",
            "description": None,
            "thumbnail_url": None,
        },
    ]

    async def test_returns_items(self, admin_client, mocker):
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=self._HITS,
        )
        r = await admin_client.get("/api/admin/channels/search?q=boiler")
        assert r.status_code == 200
        data = r.json()
        assert [i["channel_id"] for i in data["items"]] == [
            "UCabc1234567890abcdef12",
            "UCxyz1234567890abcdef98",
        ]
        assert data["items"][0]["title"] == "Boiler Room"
        assert data["items"][0]["thumbnail_url"] == "https://i.ytimg.com/def.jpg"
        # The query is stripped before it reaches the worker core.
        search.assert_called_once()
        assert search.call_args.args[1] == "boiler"

    async def test_empty_query_no_network(self, admin_client, mocker):
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=self._HITS,
        )
        r = await admin_client.get("/api/admin/channels/search?q=")
        assert r.status_code == 200
        assert r.json() == {"items": []}
        search.assert_not_called()

    async def test_single_char_query_no_network(self, admin_client, mocker):
        # A 1-char query (even padded with spaces) short-circuits — quota guard.
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=self._HITS,
        )
        r = await admin_client.get("/api/admin/channels/search?q=%20a%20")
        assert r.status_code == 200
        assert r.json() == {"items": []}
        search.assert_not_called()

    async def test_limit_bounded(self, admin_client, mocker):
        mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=[],
        )
        # limit above the cap (le=10) is rejected by FastAPI validation.
        r = await admin_client.get("/api/admin/channels/search?q=boiler&limit=11")
        assert r.status_code == 422

    async def test_limit_forwarded(self, admin_client, mocker):
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=[],
        )
        r = await admin_client.get("/api/admin/channels/search?q=boiler&limit=3")
        assert r.status_code == 200
        assert search.call_args.kwargs["limit"] == 3


class TestChannelOverride:
    async def test_toggle_watched(self, admin_client, db):
        c = await _channel(db, "Toggle", external_id="UCt", watched=True)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/channels/{c.id}", json={"watched": False}
        )
        assert r.status_code == 200
        assert r.json()["watched"] is False

    async def test_toggle_excluded_leaves_watched(self, admin_client, db):
        c = await _channel(db, "Excl", external_id="UCe", watched=True)
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/channels/{c.id}", json={"excluded": True}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["excluded"] is True
        assert data["watched"] is True

    async def test_set_channel_type_and_artist(self, admin_client, db):
        c = await _channel(db, "Typed", external_id="UCty")
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/channels/{c.id}",
            json={"channel_type": "organizer", "artist_id": None},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["channel_type"] == "organizer"
        assert data["artist_id"] is None

    async def test_absent_field_left_untouched(self, admin_client, db):
        c = await _channel(db, "Keep", external_id="UCk", watched=True)
        await db.commit()

        # Only excluded is sent — watched must stay True.
        r = await admin_client.patch(
            f"/api/admin/channels/{c.id}", json={"excluded": True}
        )
        assert r.status_code == 200
        assert r.json()["watched"] is True

    async def test_404_for_unknown_channel(self, admin_client):
        r = await admin_client.patch(
            "/api/admin/channels/999999", json={"watched": False}
        )
        assert r.status_code == 404

    async def test_writes_audit_log(self, admin_client, db):
        c = await _channel(db, "Audited", external_id="UCau")
        await db.commit()

        r = await admin_client.patch(
            f"/api/admin/channels/{c.id}", json={"excluded": True}
        )
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e for e in audit.json()["items"] if e["action"] == "channel_override"
        ]
        assert len(entries) == 1
        assert entries[0]["target_id"] == c.id
        assert entries[0]["details"]["excluded"] is True
