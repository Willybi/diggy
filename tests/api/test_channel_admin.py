"""Tests for /api/admin/channels endpoints (C14.b, L3 — admin back)."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from models import Artist, ArtistCohort, Channel, DJSet, SetArtist, TrackIdIndex
from services import channel_service
from sqlalchemy import select


class _RaisingRedis:
    """A Redis stand-in whose every op raises — exercises the fail-open branches."""

    async def get(self, *a, **k):
        raise RuntimeError("redis down")

    async def set(self, *a, **k):
        raise RuntimeError("redis down")


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


async def _set(db, title="A set", *, channel_canonical=None):
    s = DJSet(source="youtube", title=title, channel_canonical=channel_canonical)
    db.add(s)
    await db.flush()
    return s


async def _tid(db, channel, trackid_id, *, set_id=None):
    row = TrackIdIndex(trackid_id=trackid_id, channel=channel, set_id=set_id)
    db.add(row)
    await db.flush()
    return row


async def _link_set_artist(db, set_id, artist_id, *, role="dj"):
    db.add(SetArtist(set_id=set_id, artist_id=artist_id, role=role))
    await db.flush()


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

    async def test_ranks_by_cohort_relevance(self, admin_client, db):
        # 🅰: rank by the number of watch-cohort DJs on the channel's sets, NOT by
        # raw volume. "Cohort Rich" has ONE linked set featuring 2 cohort DJs;
        # "Big Volume" has 5 indexed sets but none feature a cohort artist.
        rich = await _set(db, "rich set")
        a1 = await _artist(db, "Cohort DJ One", deezer_id="9001")
        a2 = await _artist(db, "Cohort DJ Two", deezer_id="9002")
        await _cohort(db, a1, tier=1)
        await _cohort(db, a2, tier=1)
        await _link_set_artist(db, rich.id, a1.id)
        await _link_set_artist(db, rich.id, a2.id)
        await _tid(db, "Cohort Rich", 601, set_id=rich.id)
        for i in range(5):
            await _tid(db, "Big Volume", 610 + i)
        await db.commit()

        r = await admin_client.get("/api/admin/channels/candidates")
        assert r.status_code == 200
        items = r.json()["items"]
        names = [i["name"] for i in items]
        # Relevance dominates raw volume, even though Big Volume has more indexed sets.
        assert names.index("Cohort Rich") < names.index("Big Volume")
        rich_item = next(i for i in items if i["name"] == "Cohort Rich")
        assert rich_item["trackid_count"] == 1
        assert rich_item["set_count"] == 1
        big_item = next(i for i in items if i["name"] == "Big Volume")
        assert big_item["trackid_count"] == 5
        assert big_item["set_count"] == 0

    async def test_includes_channel_seen_only_via_set_canonical(
        self, admin_client, db
    ):
        # 🅲: a channel present ONLY through a set's channel_canonical (never indexed
        # in trackid_index) still surfaces as a candidate.
        await _set(db, "yt only set", channel_canonical="Only In Sets")
        await _tid(db, "Indexed Channel", 700)
        await db.commit()

        items = (
            await admin_client.get("/api/admin/channels/candidates")
        ).json()["items"]
        by_name = {i["name"]: i for i in items}
        assert "Only In Sets" in by_name
        only = by_name["Only In Sets"]
        # Not in trackid_index → zero informative coverage counts.
        assert only["trackid_count"] == 0
        assert only["set_count"] == 0

    async def test_set_only_channel_with_cohort_outranks_volume(
        self, admin_client, db
    ):
        # 🅲 + 🅰: a set-only channel featuring a cohort DJ beats a big trackid
        # channel with no cohort relevance, despite having zero indexed volume.
        s = await _set(db, "cohort yt set", channel_canonical="Cohort Venue")
        a = await _artist(db, "Venue Resident", deezer_id="9100")
        await _cohort(db, a, tier=1)
        await _link_set_artist(db, s.id, a.id)
        for i in range(4):
            await _tid(db, "Plain Big", 800 + i)
        await db.commit()

        items = (
            await admin_client.get("/api/admin/channels/candidates")
        ).json()["items"]
        names = [i["name"] for i in items]
        assert names.index("Cohort Venue") < names.index("Plain Big")

    async def test_excluded_cohort_artist_does_not_count(self, admin_client, db):
        # An EXCLUDED cohort artist is not a relevance signal → the channel falls
        # back to a plain 0-relevance candidate (behind a real cohort channel).
        excl_set = await _set(db, "excluded cohort set")
        excl = await _artist(db, "Excluded DJ", deezer_id="9200")
        await _cohort(db, excl, tier=1, excluded=True)
        await _link_set_artist(db, excl_set.id, excl.id)
        await _tid(db, "Excluded Chan", 900, set_id=excl_set.id)

        rich_set = await _set(db, "real cohort set")
        real = await _artist(db, "Real DJ", deezer_id="9201")
        await _cohort(db, real, tier=1)
        await _link_set_artist(db, rich_set.id, real.id)
        await _tid(db, "Real Chan", 901, set_id=rich_set.id)
        await db.commit()

        items = (
            await admin_client.get("/api/admin/channels/candidates")
        ).json()["items"]
        names = [i["name"] for i in items]
        # Real Chan (relevance 1) ranks before Excluded Chan (relevance 0).
        assert names.index("Real Chan") < names.index("Excluded Chan")

    async def _virtual_parent(self, db, *, channel_canonical=None, unreliable=False):
        parent = DJSet(
            source="virtual",
            is_virtual=True,
            title="Parent",
            channel_canonical=channel_canonical,
            unreliable=unreliable,
        )
        db.add(parent)
        await db.flush()
        return parent

    async def _child(self, db, parent, title):
        child = DJSet(source="trackid", title=title, parent_set_id=parent.id)
        db.add(child)
        await db.flush()
        return child

    async def test_attached_trackid_set_counts_through_its_root(self, db):
        # The parent has no channel_canonical and the DJ sits on the parent only:
        # the sole path from the channel to that DJ is child → root.
        parent = await self._virtual_parent(db)
        dj = await _artist(db, "Parent DJ", deezer_id="9300")
        await _cohort(db, dj, tier=1)
        await _link_set_artist(db, parent.id, dj.id)
        child = await self._child(db, parent, "attached child")
        await _tid(db, "Z Attached Chan", 1000, set_id=child.id)

        plain = await _set(db, "plain set")
        await _tid(db, "A Plain Chan", 1001, set_id=plain.id)
        await db.commit()

        items = (await channel_service.list_candidates(db))["items"]

        # Relevance 1 beats the alphabetical tie-break that favours the plain one.
        assert [i["name"] for i in items] == ["Z Attached Chan", "A Plain Chan"]

    async def test_set_counts_once_per_channel_across_paths(self, db):
        # Three paths to one root: two attached children + the parent's canonical.
        parent = await self._virtual_parent(db, channel_canonical="A Attached")
        first = await self._child(db, parent, "child one")
        second = await self._child(db, parent, "child two")
        await _tid(db, "A Attached", 1010, set_id=first.id)
        await _tid(db, "A Attached", 1011, set_id=second.id)

        # Same indexed volume, but two genuinely distinct sets.
        for i in range(2):
            plain = await _set(db, f"plain {i}")
            await _tid(db, "B Two Sets", 1012 + i, set_id=plain.id)
        await db.commit()

        items = (await channel_service.list_candidates(db))["items"]

        # Set volume 1 vs 2 decides, against the alphabetical tie-break.
        assert [i["name"] for i in items] == ["B Two Sets", "A Attached"]
        attached = items[1]
        assert attached["trackid_count"] == 2  # indexed rows, not sets
        assert attached["set_count"] == 1
        assert items[0]["set_count"] == 2

    async def test_attached_set_follows_reliability_of_its_root(self, db):
        # A reliable child under an unreliable parent is not attributed to the
        # channel: the reliability filter applies to the root. The channel still
        # exists through trackid_index, with zero relevance.
        parent = await self._virtual_parent(db, unreliable=True)
        dj = await _artist(db, "Hidden DJ", deezer_id="9301")
        await _cohort(db, dj, tier=1)
        await _link_set_artist(db, parent.id, dj.id)
        child = await self._child(db, parent, "reliable child")
        await _tid(db, "Hidden Root Chan", 1020, set_id=child.id)

        visible = await _set(db, "visible set")
        await _tid(db, "A Plain Chan", 1021, set_id=visible.id)
        await db.commit()

        items = (await channel_service.list_candidates(db))["items"]

        # Were the child reliable on its own account, relevance 1 would rank it first.
        assert [i["name"] for i in items] == ["A Plain Chan", "Hidden Root Chan"]

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


# A YouTube channel search hit shared by the resolve/preselect tests.
_RESOLVE_HITS = [
    {
        "channel_id": "UCabc1234567890abcdef12",
        "title": "Boiler Room",
        "description": "Music broadcaster",
        "thumbnail_url": "https://i.ytimg.com/def.jpg",
    },
]


class TestChannelCandidatePreselect:
    """list_candidates annotates each candidate with its cached YouTube
    pre-selection, READ-ONLY — it NEVER runs a search on listing render."""

    async def test_preselect_read_from_cache_no_search(
        self, admin_client, db, fake_redis, mocker
    ):
        await _tid(db, "Boiler Room", 501)
        await db.commit()
        fake_redis._store[
            channel_service._candidate_cache_key("Boiler Room")
        ] = json.dumps(_RESOLVE_HITS)
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )

        r = await admin_client.get("/api/admin/channels/candidates")
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["name"] == "Boiler Room"
        assert item["preselect"][0]["channel_id"] == "UCabc1234567890abcdef12"
        assert item["preselect"][0]["title"] == "Boiler Room"
        # INVARIANT: annotating the listing never triggers a YouTube search.
        search.assert_not_called()

    async def test_preselect_none_when_cache_empty_no_search(
        self, admin_client, db, mocker
    ):
        await _tid(db, "Uncached", 502)
        await db.commit()
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )

        r = await admin_client.get("/api/admin/channels/candidates")
        item = r.json()["items"][0]
        assert item["name"] == "Uncached"
        assert item["preselect"] is None
        search.assert_not_called()

    async def test_redis_none_leaves_preselect_none(self, db, mocker):
        # Legacy signature (redis=None) → no preselect, no error, no search.
        await _tid(db, "NoRedis", 503)
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )
        out = await channel_service.list_candidates(db, redis=None)
        assert out["items"][0]["name"] == "NoRedis"
        assert out["items"][0]["preselect"] is None
        search.assert_not_called()

    async def test_failopen_on_raising_redis(self, db, mocker):
        # A Redis that raises on read → fail-open: no exception, preselect None.
        await _tid(db, "Boom", 504)
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )
        out = await channel_service.list_candidates(db, redis=_RaisingRedis())
        assert out["items"][0]["name"] == "Boom"
        assert out["items"][0]["preselect"] is None
        search.assert_not_called()

    async def test_hides_candidate_whose_resolved_channel_already_curated(
        self, admin_client, db, fake_redis
    ):
        # The suggested resolved channel (UCabc…) is already curated under a
        # DIFFERENT name → the name-based exclusion missed it; the resolved-channel-id
        # exclusion must hide the candidate so it does not reappear.
        await _tid(db, "Boiler Room", 511)
        await _channel(
            db,
            "Boiler Room Official YT Title",
            external_id="UCabc1234567890abcdef12",
            watched=True,
        )
        await db.commit()
        fake_redis._store[
            channel_service._candidate_cache_key("Boiler Room")
        ] = json.dumps(_RESOLVE_HITS)

        r = await admin_client.get("/api/admin/channels/candidates")
        assert "Boiler Room" not in [i["name"] for i in r.json()["items"]]


class TestChannelCandidateResolve:
    async def test_requires_auth(self, client):
        r = await client.get("/api/admin/channels/candidates/resolve?name=boiler")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get(
            "/api/admin/channels/candidates/resolve?name=boiler"
        )
        assert r.status_code == 403

    async def test_miss_searches_and_caches(self, admin_client, fake_redis, mocker):
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )
        r = await admin_client.get(
            "/api/admin/channels/candidates/resolve?name=Boiler Room"
        )
        assert r.status_code == 200
        assert r.json()["items"][0]["channel_id"] == "UCabc1234567890abcdef12"
        search.assert_called_once()
        # The hits are cached under the EXACT-name key for later cache hits.
        key = channel_service._candidate_cache_key("Boiler Room")
        assert key in fake_redis._store
        assert (
            json.loads(fake_redis._store[key])[0]["channel_id"]
            == "UCabc1234567890abcdef12"
        )

    async def test_hit_returns_cache_without_searching(
        self, admin_client, fake_redis, mocker
    ):
        fake_redis._store[
            channel_service._candidate_cache_key("Cached One")
        ] = json.dumps(_RESOLVE_HITS)
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=[],
        )
        r = await admin_client.get(
            "/api/admin/channels/candidates/resolve?name=Cached One"
        )
        assert r.status_code == 200
        assert r.json()["items"][0]["channel_id"] == "UCabc1234567890abcdef12"
        # INVARIANT: a cache hit spends ZERO quota — no search.
        search.assert_not_called()

    async def test_short_name_no_search(self, admin_client, mocker):
        # search_youtube gates names < 2 chars → resolve returns empty, no call.
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )
        r = await admin_client.get(
            "/api/admin/channels/candidates/resolve?name=%20a%20"
        )
        assert r.status_code == 200
        assert r.json() == {"items": []}
        search.assert_not_called()

    async def test_redis_none_failopen(self, mocker):
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )
        out = await channel_service.resolve_candidate("Somebody", None)
        assert out["cached"] is False
        assert out["items"][0]["channel_id"] == "UCabc1234567890abcdef12"
        search.assert_called_once()

    async def test_failopen_on_raising_redis(self, mocker):
        # get() raises → live search; set() raises → swallowed. No exception.
        search = mocker.patch(
            "services.channel_service.search_channels",
            new_callable=AsyncMock,
            return_value=_RESOLVE_HITS,
        )
        out = await channel_service.resolve_candidate("Somebody", _RaisingRedis())
        assert out["cached"] is False
        assert out["items"][0]["channel_id"] == "UCabc1234567890abcdef12"
        search.assert_called_once()


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


# ── Artist candidates (C14.b 🅱, L2) ──────────────────────────────────────────


async def _artist(db, name, *, deezer_id=None):
    a = Artist(name=name, normalized_name=name.lower(), deezer_id=deezer_id)
    db.add(a)
    await db.flush()
    return a


async def _cohort(db, artist, *, tier=1, excluded=False, signals=None):
    row = ArtistCohort(
        artist_id=artist.id,
        tier=tier,
        computed_tier=tier,
        excluded=excluded,
        signals=signals or {},
    )
    db.add(row)
    await db.flush()
    return row


class TestArtistCandidatesAuth:
    async def test_list_requires_auth(self, client):
        r = await client.get("/api/admin/channels/artist-candidates")
        assert r.status_code == 401

    async def test_list_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/channels/artist-candidates")
        assert r.status_code == 403

    async def test_resolve_requires_auth(self, client):
        r = await client.get(
            "/api/admin/channels/artist-candidates/resolve?name=boris"
        )
        assert r.status_code == 401

    async def test_resolve_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get(
            "/api/admin/channels/artist-candidates/resolve?name=boris"
        )
        assert r.status_code == 403


class TestArtistCandidatesGate:
    """The 3-guard « real artist » gate (brief §5)."""

    async def test_keeps_real_deezer_linked_dj(self, admin_client, db):
        a = await _artist(db, "Boris Brejcha", deezer_id="123")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 2, "nb_lib": 1})
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["artist_id"] == a.id
        assert item["name"] == "Boris Brejcha"
        assert item["tier"] == 1
        assert item["nb_sets"] == 2
        assert item["nb_lib"] == 1
        assert item["preselect"] is None

    async def test_rejects_denylisted_media_name(self, admin_client, db):
        # "Boiler Room" folds into MEDIA_TITLE_KEYS — a radio/broadcaster, never a DJ.
        a = await _artist(db, "Boiler Room", deezer_id="999")
        await _cohort(db, a, tier=1, signals={"nb_catalog": 50, "nb_sets_12m": 9})
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["total"] == 0

    async def test_rejects_two_char_name(self, admin_client, db):
        a = await _artist(db, "DJ", deezer_id="7")
        await _cohort(db, a, tier=1, signals={"nb_catalog": 99, "nb_sets_12m": 9})
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["total"] == 0

    async def test_rejects_generic_mono_token(self, admin_client, db):
        a = await _artist(db, "Various", deezer_id="8")
        await _cohort(db, a, tier=1, signals={"nb_catalog": 99, "nb_sets_12m": 9})
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["total"] == 0

    async def test_rejects_artist_without_signal(self, admin_client, db):
        # No Deezer id, thin catalog, no recent set → no real-artist signal.
        # tier_max=2 so the T2 member is IN SCOPE and it's the GATE (not the Lot-2
        # default T1-only scoping) that rejects it.
        a = await _artist(db, "Some Unlinked Name", deezer_id=None)
        await _cohort(
            db, a, tier=2, signals={"nb_catalog": 1, "nb_sets_12m": 0, "nb_lib": 0}
        )
        await db.commit()

        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?tier_max=2"
        )
        assert r.json()["total"] == 0

    async def test_not_found_sentinel_is_not_a_signal(self, admin_client, db):
        # tier_max=2: the T2 member is in scope; the gate rejects the NOT_FOUND id.
        a = await _artist(db, "Ghost Producer", deezer_id="NOT_FOUND")
        await _cohort(db, a, tier=2, signals={"nb_catalog": 0, "nb_sets_12m": 0})
        await db.commit()

        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?tier_max=2"
        )
        assert r.json()["total"] == 0

    async def test_catalog_depth_alone_qualifies(self, admin_client, db):
        # No Deezer link, but deep catalog (>= threshold) is a real-artist signal.
        # tier_max=2 so the T2 member is in scope (default scope is T1-only, Lot 2).
        a = await _artist(db, "Deep Cataloguer", deezer_id=None)
        await _cohort(db, a, tier=2, signals={"nb_catalog": 25, "nb_sets_12m": 0})
        await db.commit()

        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?tier_max=2"
        )
        assert r.json()["total"] == 1

    async def test_recent_set_alone_qualifies(self, admin_client, db):
        # No Deezer link, thin catalog, but a recent DJ set is a real-artist signal.
        # tier_max=2 so the T2 member is in scope (default scope is T1-only, Lot 2).
        a = await _artist(db, "Fresh Set Player", deezer_id=None)
        await _cohort(db, a, tier=2, signals={"nb_catalog": 0, "nb_sets_12m": 1})
        await db.commit()

        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?tier_max=2"
        )
        assert r.json()["total"] == 1


class TestArtistCandidatesExclusionAndRank:
    async def test_excludes_already_curated_artist(self, admin_client, db):
        a = await _artist(db, "Already Curated", deezer_id="1")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 5})
        # A channels row already links this artist → not proposed again.
        db.add(
            Channel(
                platform="youtube",
                external_id="UCcur1234567890abcdef12",
                name="Already Curated",
                channel_type="artist",
                artist_id=a.id,
            )
        )
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["total"] == 0

    async def test_a_null_artist_channel_does_not_exclude(self, admin_client, db):
        # A curated channel with NO artist_id (a venue/organiser) must not blank out
        # a legitimate artist candidate (NOT IN over a NULL list).
        a = await _artist(db, "Untouched Artist", deezer_id="1")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 5})
        db.add(
            Channel(
                platform="youtube",
                external_id="UCorg1234567890abcdef12",
                name="Some Venue",
                channel_type="organizer",
                artist_id=None,
            )
        )
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["total"] == 1

    async def test_excludes_excluded_cohort_row(self, admin_client, db):
        a = await _artist(db, "Excluded One", deezer_id="2")
        await _cohort(db, a, tier=1, excluded=True, signals={"nb_sets_12m": 5})
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["total"] == 0

    async def test_ranked_by_personal_relevance_not_volume(self, admin_client, db):
        # Ranking key: tier asc, then followed first, then nb_lib, nb_likes,
        # nb_sets_12m, nb_catalog (desc). Personal relevance beats raw set volume.
        followed_low = await _artist(db, "Followed Low", deezer_id="10")
        await _cohort(
            db,
            followed_low,
            tier=1,
            signals={"followed": True, "nb_lib": 0, "nb_likes": 0, "nb_sets_12m": 1},
        )
        big_lib = await _artist(db, "Unfollowed Big Lib", deezer_id="11")
        await _cohort(
            db,
            big_lib,
            tier=1,
            signals={"followed": False, "nb_lib": 50, "nb_likes": 0, "nb_sets_12m": 100},
        )
        more_likes = await _artist(db, "Unfollowed More Likes", deezer_id="12")
        await _cohort(
            db,
            more_likes,
            tier=1,
            signals={"followed": False, "nb_lib": 10, "nb_likes": 99, "nb_sets_12m": 100},
        )
        fewer_likes = await _artist(db, "Unfollowed Fewer Likes", deezer_id="13")
        await _cohort(
            db,
            fewer_likes,
            tier=1,
            signals={"followed": False, "nb_lib": 10, "nb_likes": 1, "nb_sets_12m": 100},
        )
        tier_two = await _artist(db, "Tier Two Big", deezer_id="14")
        await _cohort(
            db,
            tier_two,
            tier=2,
            signals={"followed": False, "nb_lib": 100, "nb_sets_12m": 100},
        )
        await db.commit()

        # tier_max=2 so "Tier Two Big" is in scope and the tier-dominance of the
        # ranking is observable (default scope is T1-only since Lot 2).
        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?tier_max=2"
        )
        names = [i["name"] for i in r.json()["items"]]
        # A followed artist with FEW sets outranks unfollowed artists with MANY sets;
        # among the unfollowed, deeper library first, then more likes; tier dominates.
        assert names == [
            "Followed Low",
            "Unfollowed Big Lib",
            "Unfollowed More Likes",
            "Unfollowed Fewer Likes",
            "Tier Two Big",
        ]

    async def test_pagination(self, admin_client, db):
        for i in range(5):
            a = await _artist(db, f"Artist Number {i}", deezer_id=str(100 + i))
            await _cohort(db, a, tier=1, signals={"nb_sets_12m": i})
        await db.commit()

        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?limit=2&page=1"
        )
        data = r.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

        r2 = await admin_client.get(
            "/api/admin/channels/artist-candidates?limit=2&page=3"
        )
        assert r2.json()["total"] == 5
        assert len(r2.json()["items"]) == 1

    async def test_hides_candidate_whose_resolved_channel_already_curated(
        self, admin_client, db, fake_redis
    ):
        # Marlon case: the artist's resolved channel is already curated under a
        # DUPLICATE artist row → the per-artist_id exclusion missed it; the
        # resolved-channel-id exclusion must hide the candidate.
        a = await _artist(db, "Marlon Hoffstadt", deezer_id="3926781")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        dup = await _artist(db, "DJ Daddy Trance", deezer_id="99999")
        db.add(
            Channel(
                platform="youtube",
                external_id="UCwAvPX7WsgigWWzW5ck8EvA",
                name="Marlon Hoffstadt aka DJ Daddy Trance",
                channel_type="artist",
                artist_id=dup.id,
                watched=True,
            )
        )
        await db.commit()
        fake_redis._store[
            channel_service._artist_resolve_cache_key("Marlon Hoffstadt")
        ] = json.dumps(
            {
                "channel_id": "UCwAvPX7WsgigWWzW5ck8EvA",
                "channel_title": "Marlon Hoffstadt aka DJ Daddy Trance",
                "method": "search",
                "confidence": "NEEDS_VERIFY",
            }
        )

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        data = r.json()
        assert "Marlon Hoffstadt" not in [i["name"] for i in data["items"]]
        assert data["total"] == 0


_ARTIST_RESOLVE_PAYLOAD = {
    "channel_id": "UCartist1234567890abcde",
    "channel_title": "Cached Artist",
    "url": "https://youtube.com/channel/UCartist1234567890abcde",
    "method": "wikidata",
    "confidence": "high",
    "has_soundcloud": True,
}


class TestArtistCandidatesPreselect:
    """list_artist_candidates annotates preselect from the Redis cache ONLY —
    it NEVER resolves an artist (a resolution spends 100 quota units)."""

    async def test_preselect_read_from_cache_no_resolution(
        self, admin_client, db, fake_redis, mocker
    ):
        a = await _artist(db, "Cached Artist", deezer_id="55")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()
        fake_redis._store[
            channel_service._artist_resolve_cache_key("Cached Artist")
        ] = json.dumps(_ARTIST_RESOLVE_PAYLOAD)
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=_ARTIST_RESOLVE_PAYLOAD,
        )

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        item = r.json()["items"][0]
        assert item["preselect"]["channel_id"] == "UCartist1234567890abcde"
        assert item["preselect"]["method"] == "wikidata"
        # INVARIANT: annotating the listing never resolves (0 quota).
        resolve.assert_not_called()

    async def test_preselect_none_when_cache_empty_no_resolution(
        self, admin_client, db, mocker
    ):
        a = await _artist(db, "Uncached Artist", deezer_id="56")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        assert r.json()["items"][0]["preselect"] is None
        resolve.assert_not_called()

    async def test_redis_none_leaves_preselect_none(self, db, mocker):
        a = await _artist(db, "No Redis Artist", deezer_id="57")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.flush()
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )

        out = await channel_service.list_artist_candidates(db, redis=None)
        assert out["items"][0]["name"] == "No Redis Artist"
        assert out["items"][0]["preselect"] is None
        resolve.assert_not_called()

    async def test_failopen_on_raising_redis(self, db, mocker):
        a = await _artist(db, "Boom Artist", deezer_id="58")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.flush()
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )

        out = await channel_service.list_artist_candidates(db, redis=_RaisingRedis())
        assert out["items"][0]["name"] == "Boom Artist"
        assert out["items"][0]["preselect"] is None
        resolve.assert_not_called()


class TestArtistCandidateResolve:
    async def test_resolves_and_caches(self, admin_client, fake_redis, mocker):
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=_ARTIST_RESOLVE_PAYLOAD,
        )
        r = await admin_client.get(
            "/api/admin/channels/artist-candidates/resolve?name=Cached Artist"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["channel_id"] == "UCartist1234567890abcde"
        assert data["method"] == "wikidata"
        assert data["has_soundcloud"] is True
        resolve.assert_called_once()
        # Cached under the artist-resolve key for later 0-quota hits.
        key = channel_service._artist_resolve_cache_key("Cached Artist")
        assert key in fake_redis._store

    async def test_cache_hit_no_resolution(self, admin_client, fake_redis, mocker):
        fake_redis._store[
            channel_service._artist_resolve_cache_key("Warm Artist")
        ] = json.dumps(_ARTIST_RESOLVE_PAYLOAD)
        resolve = mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )
        r = await admin_client.get(
            "/api/admin/channels/artist-candidates/resolve?name=Warm Artist"
        )
        assert r.status_code == 200
        assert r.json()["channel_id"] == "UCartist1234567890abcde"
        # INVARIANT: a cache hit spends ZERO quota — no resolution.
        resolve.assert_not_called()

    async def test_unresolved_returns_empty_shape(self, admin_client, mocker):
        mocker.patch(
            "services.channel_service.resolve_artist_channel",
            new_callable=AsyncMock,
            return_value=None,
        )
        r = await admin_client.get(
            "/api/admin/channels/artist-candidates/resolve?name=Nobody Here"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["channel_id"] is None
        assert data["has_soundcloud"] is False


class TestChannelAddArtist:
    async def test_add_with_artist_id_creates_artist_channel(
        self, admin_client, db, mocker
    ):
        a = await _artist(db, "Confirmed Artist", deezer_id="321")
        await db.commit()
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCconfirm1234567890abcd",
        )
        r = await admin_client.post(
            "/api/admin/channels",
            json={
                "url": "UCconfirm1234567890abcd",
                "name": "Confirmed Artist",
                "channel_type": "artist",
                "artist_id": a.id,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["channel_type"] == "artist"
        assert data["artist_id"] == a.id
        assert data["name"] == "Confirmed Artist"

    async def test_readd_reassigns_artist_on_existing_channel(
        self, admin_client, db, mocker
    ):
        # Marlon case: the suggested channel already exists linked to ANOTHER artist
        # row (a duplicate of the same person). Confirming the candidate must
        # reassign the channel's artist_id so the confirmed artist is excluded.
        a1 = await _artist(db, "DJ Daddy Trance", deezer_id="2704x")
        a2 = await _artist(db, "Marlon Hoffstadt", deezer_id="432x")
        db.add(
            Channel(
                platform="youtube",
                external_id="UCwAvPX7WsgigWWzW5ck8EvA",
                name="Marlon aka DJ Daddy Trance",
                channel_type="artist",
                artist_id=a1.id,
                watched=True,
            )
        )
        await db.commit()
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCwAvPX7WsgigWWzW5ck8EvA",
        )
        r = await admin_client.post(
            "/api/admin/channels",
            json={
                "url": "UCwAvPX7WsgigWWzW5ck8EvA",
                "name": "Marlon Hoffstadt",
                "channel_type": "artist",
                "artist_id": a2.id,
            },
        )
        assert r.status_code == 200
        assert r.json()["artist_id"] == a2.id

    async def test_add_without_artist_id_unchanged(self, admin_client, mocker):
        # The two new fields are optional — the legacy add path is untouched.
        mocker.patch(
            "services.channel_service.resolve_channel_id",
            new_callable=AsyncMock,
            return_value="UCplain1234567890abcdef",
        )
        r = await admin_client.post(
            "/api/admin/channels",
            json={"url": "u-plain", "name": "Plain Channel"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["artist_id"] is None
        assert data["name"] == "Plain Channel"


class TestArtistCandidateDismiss:
    """« Aucune chaîne à associer » — an artist candidate with no watchable channel
    is marked dismissed (placeholder excluded marker) so it stops being proposed,
    WITHOUT leaving the Deezer-watch cohort."""

    async def test_requires_auth(self, client):
        r = await client.post("/api/admin/channels/artist-candidates/1/dismiss")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post("/api/admin/channels/artist-candidates/1/dismiss")
        assert r.status_code == 403

    async def test_404_unknown_artist(self, admin_client):
        r = await admin_client.post(
            "/api/admin/channels/artist-candidates/999999/dismiss"
        )
        assert r.status_code == 404

    async def test_dismiss_drops_from_candidates_keeps_cohort(self, admin_client, db):
        a = await _artist(db, "No Channel DJ", deezer_id="700")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        before = await admin_client.get("/api/admin/channels/artist-candidates")
        assert before.json()["total"] == 1

        r = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["artist_id"] == a.id
        assert data["external_id"] is None
        assert data["channel_type"] == "artist"
        assert data["excluded"] is True
        assert data["watched"] is False

        # Gone from the candidates seed...
        after = await admin_client.get("/api/admin/channels/artist-candidates")
        assert after.json()["total"] == 0

        # ...but the cohort row is untouched (still watched for Deezer releases).
        cohort = (
            await db.execute(
                select(ArtistCohort).where(ArtistCohort.artist_id == a.id)
            )
        ).scalar_one()
        assert cohort.excluded is False

    async def test_marker_hidden_from_channels_list(self, admin_client, db):
        a = await _artist(db, "Hidden Marker DJ", deezer_id="701")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        await admin_client.post(f"/api/admin/channels/artist-candidates/{a.id}/dismiss")

        # The placeholder marker is bookkeeping, not a real channel → not listed.
        listing = await admin_client.get("/api/admin/channels")
        assert listing.json() == {"total": 0, "items": []}

    async def test_idempotent(self, admin_client, db):
        a = await _artist(db, "Twice DJ", deezer_id="702")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        first = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        second = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        assert first.status_code == 200
        assert second.status_code == 200

        markers = (
            await db.execute(
                select(Channel).where(
                    Channel.artist_id == a.id, Channel.external_id.is_(None)
                )
            )
        ).scalars().all()
        assert len(markers) == 1

    async def test_writes_audit_log(self, admin_client, db):
        a = await _artist(db, "Audited Dismiss DJ", deezer_id="703")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        r = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e
            for e in audit.json()["items"]
            if e["action"] == "channel_artist_dismiss"
        ]
        assert len(entries) == 1
        assert entries[0]["target_id"] == a.id


# ── Tier scope (C14.b Lot 2) ──────────────────────────────────────────────────


class TestArtistCandidatesTierScope:
    """The artist-candidate list is SCOPED to tier_max (default 1 = T1 only — the
    full cohort is ~28k artists and must not be served whole)."""

    async def test_default_scope_is_tier1_only(self, admin_client, db):
        t1 = await _artist(db, "Tier One DJ", deezer_id="2001")
        await _cohort(db, t1, tier=1, signals={"nb_sets_12m": 2})
        t2 = await _artist(db, "Tier Two DJ", deezer_id="2002")
        await _cohort(db, t2, tier=2, signals={"nb_catalog": 40})
        await db.commit()

        r = await admin_client.get("/api/admin/channels/artist-candidates")
        data = r.json()
        names = [i["name"] for i in data["items"]]
        assert names == ["Tier One DJ"]
        assert data["total"] == 1

    async def test_tier_max_2_includes_tier2(self, admin_client, db):
        t1 = await _artist(db, "Tier One DJ", deezer_id="2001")
        await _cohort(db, t1, tier=1, signals={"nb_sets_12m": 2})
        t2 = await _artist(db, "Tier Two DJ", deezer_id="2002")
        await _cohort(db, t2, tier=2, signals={"nb_catalog": 40})
        await db.commit()

        r = await admin_client.get(
            "/api/admin/channels/artist-candidates?tier_max=2"
        )
        data = r.json()
        names = {i["name"] for i in data["items"]}
        assert names == {"Tier One DJ", "Tier Two DJ"}
        assert data["total"] == 2
        # tier asc ⇒ the T1 member is first.
        assert data["items"][0]["name"] == "Tier One DJ"

    async def test_tier_max_none_includes_all_via_service(self, db):
        # The service's tier_max=None (no HTTP equivalent) widens to the full cohort.
        t1 = await _artist(db, "Tier One DJ", deezer_id="2001")
        await _cohort(db, t1, tier=1, signals={"nb_sets_12m": 2})
        t2 = await _artist(db, "Tier Two DJ", deezer_id="2002")
        await _cohort(db, t2, tier=2, signals={"nb_catalog": 40})
        await db.flush()

        out = await channel_service.list_artist_candidates(db, tier_max=None)
        assert {i["name"] for i in out["items"]} == {"Tier One DJ", "Tier Two DJ"}


# ── The two dismissal kinds + time-box (C14.b Lot 2) ──────────────────────────


class TestArtistDismissKind:
    """« Pas de chaîne » writes a permanent no_channel marker."""

    async def test_dismiss_writes_no_channel_signal(self, admin_client, db):
        a = await _artist(db, "No Channel DJ", deezer_id="3001")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        r = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        assert r.status_code == 200

        marker = (
            await db.execute(
                select(Channel).where(
                    Channel.artist_id == a.id, Channel.external_id.is_(None)
                )
            )
        ).scalar_one()
        assert marker.signals == {"dismiss_kind": "no_channel"}

    async def test_no_channel_masks_forever(self, db):
        a = await _artist(db, "Gone DJ", deezer_id="3002")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.flush()

        await channel_service.dismiss_artist_candidate(db, a.id)
        # Even 10 years later the no_channel marker keeps hiding the artist.
        far = datetime(2036, 1, 1, tzinfo=timezone.utc)
        out = await channel_service.list_artist_candidates(db, now=far)
        assert out["total"] == 0


class TestArtistCandidateDefer:
    """« Ne pas suivre » defers a candidate reversibly for a time-boxed window."""

    async def test_requires_auth(self, client):
        r = await client.post("/api/admin/channels/artist-candidates/1/defer")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post("/api/admin/channels/artist-candidates/1/defer")
        assert r.status_code == 403

    async def test_404_unknown_artist(self, admin_client):
        r = await admin_client.post(
            "/api/admin/channels/artist-candidates/999999/defer"
        )
        assert r.status_code == 404

    async def test_defer_writes_deferred_signal(self, admin_client, db):
        a = await _artist(db, "Deferred DJ", deezer_id="3100")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        r = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/defer"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["artist_id"] == a.id
        assert data["external_id"] is None
        assert data["excluded"] is True

        marker = (
            await db.execute(
                select(Channel).where(
                    Channel.artist_id == a.id, Channel.external_id.is_(None)
                )
            )
        ).scalar_one()
        assert marker.signals["dismiss_kind"] == "deferred"
        assert marker.signals["dismissed_at"]  # ISO timestamp present

    async def test_defer_hides_then_resurfaces(self, db):
        # Time-box via an INJECTED clock (no real wall-clock): a recently deferred
        # candidate is hidden within the window, and re-surfaces once it elapses.
        a = await _artist(db, "Resurfacing DJ", deezer_id="3101")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.flush()

        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await channel_service.defer_artist_candidate(db, a.id, now=t0)

        within = await channel_service.list_artist_candidates(
            db, now=t0 + timedelta(days=10)
        )
        assert within["total"] == 0  # still within the resurface window → hidden

        after = await channel_service.list_artist_candidates(
            db, now=t0 + timedelta(days=400)
        )
        assert after["total"] == 1  # window elapsed → re-surfaces
        assert after["items"][0]["name"] == "Resurfacing DJ"

    async def test_defer_keeps_cohort_row(self, admin_client, db):
        a = await _artist(db, "Still Watched DJ", deezer_id="3102")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/defer"
        )
        cohort = (
            await db.execute(
                select(ArtistCohort).where(ArtistCohort.artist_id == a.id)
            )
        ).scalar_one()
        assert cohort.excluded is False

    async def test_defer_then_dismiss_transitions_to_no_channel(
        self, admin_client, db
    ):
        # Re-dismissing a deferred candidate upgrades the marker to no_channel.
        a = await _artist(db, "Transition DJ", deezer_id="3103")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/defer"
        )
        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )

        markers = (
            await db.execute(
                select(Channel).where(
                    Channel.artist_id == a.id, Channel.external_id.is_(None)
                )
            )
        ).scalars().all()
        assert len(markers) == 1  # idempotent — the same marker is reused
        assert markers[0].signals == {"dismiss_kind": "no_channel"}

    async def test_writes_audit_log(self, admin_client, db):
        a = await _artist(db, "Audited Defer DJ", deezer_id="3104")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        r = await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/defer"
        )
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e
            for e in audit.json()["items"]
            if e["action"] == "channel_artist_defer"
        ]
        assert len(entries) == 1
        assert entries[0]["target_id"] == a.id


# ── Org candidate dismissal (C14.b Lot 2) ─────────────────────────────────────


class TestOrgCandidateDismiss:
    """« Pas de chaîne » for an ORG candidate (a raw name, no artist_id)."""

    async def test_requires_auth(self, client):
        r = await client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "x"}
        )
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "x"}
        )
        assert r.status_code == 403

    async def test_dismiss_hides_from_candidates(self, admin_client, db):
        await _tid(db, "Shady Promoter", 1001)
        await _tid(db, "Legit Venue", 1002)
        await db.commit()

        before = await admin_client.get("/api/admin/channels/candidates")
        assert "Shady Promoter" in [i["name"] for i in before.json()["items"]]

        r = await admin_client.post(
            "/api/admin/channels/candidates/dismiss",
            json={"name": "Shady Promoter"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Shady Promoter"
        assert data["external_id"] is None
        assert data["excluded"] is True
        assert data["artist_id"] is None

        after = await admin_client.get("/api/admin/channels/candidates")
        names = [i["name"] for i in after.json()["items"]]
        assert "Shady Promoter" not in names
        assert "Legit Venue" in names

    async def test_marker_carries_no_channel_signal(self, admin_client, db):
        await _tid(db, "Org Name", 1003)
        await db.commit()

        await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Org Name"}
        )
        marker = (
            await db.execute(
                select(Channel).where(Channel.name == "Org Name")
            )
        ).scalar_one()
        assert marker.signals == {"dismiss_kind": "no_channel"}

    async def test_marker_hidden_from_channels_list(self, admin_client, db):
        await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Hidden Org"}
        )
        listing = await admin_client.get("/api/admin/channels")
        assert listing.json() == {"total": 0, "items": []}

    async def test_blank_name_400(self, admin_client):
        r = await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "   "}
        )
        assert r.status_code == 400

    async def test_idempotent(self, admin_client, db):
        first = await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Twice Org"}
        )
        second = await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Twice Org"}
        )
        assert first.status_code == 200
        assert second.status_code == 200

        markers = (
            await db.execute(
                select(Channel).where(Channel.name == "Twice Org")
            )
        ).scalars().all()
        assert len(markers) == 1

    async def test_writes_audit_log(self, admin_client, db):
        r = await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Audited Org"}
        )
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e for e in audit.json()["items"] if e["action"] == "channel_org_dismiss"
        ]
        assert len(entries) == 1
        assert entries[0]["details"]["name"] == "Audited Org"


# ── The « Écartés » tab + reinstate (C14.b Lot 2) ─────────────────────────────


class TestDismissedList:
    async def test_requires_auth(self, client):
        r = await client.get("/api/admin/channels/dismissed")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/channels/dismissed")
        assert r.status_code == 403

    async def test_empty(self, admin_client):
        r = await admin_client.get("/api/admin/channels/dismissed")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "items": []}

    async def test_lists_artists_and_orgs_with_kind(self, admin_client, db):
        dismissed = await _artist(db, "Dismissed DJ", deezer_id="4001")
        await _cohort(db, dismissed, tier=1, signals={"nb_sets_12m": 3})
        deferred = await _artist(db, "Deferred DJ", deezer_id="4002")
        await _cohort(db, deferred, tier=1, signals={"nb_sets_12m": 2})
        await db.commit()

        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{dismissed.id}/dismiss"
        )
        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{deferred.id}/defer"
        )
        await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Dismissed Org"}
        )

        r = await admin_client.get("/api/admin/channels/dismissed")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 3
        by_name = {i["name"]: i for i in data["items"]}

        assert by_name["Dismissed DJ"]["kind"] == "artist"
        assert by_name["Dismissed DJ"]["dismiss_kind"] == "no_channel"
        assert by_name["Dismissed DJ"]["dismissed_at"] is None
        assert by_name["Dismissed DJ"]["tier"] == 1

        assert by_name["Deferred DJ"]["kind"] == "artist"
        assert by_name["Deferred DJ"]["dismiss_kind"] == "deferred"
        assert by_name["Deferred DJ"]["dismissed_at"] is not None

        assert by_name["Dismissed Org"]["kind"] == "org"
        assert by_name["Dismissed Org"]["artist_id"] is None
        assert by_name["Dismissed Org"]["dismiss_kind"] == "no_channel"

    async def test_artists_ranked_by_relevance_then_orgs(self, admin_client, db):
        low = await _artist(db, "Low Relevance DJ", deezer_id="4101")
        await _cohort(db, low, tier=1, signals={"nb_lib": 1})
        high = await _artist(db, "High Relevance DJ", deezer_id="4102")
        await _cohort(db, high, tier=1, signals={"nb_lib": 50})
        await db.commit()

        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{low.id}/dismiss"
        )
        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{high.id}/dismiss"
        )
        await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Aaa Org"}
        )

        r = await admin_client.get("/api/admin/channels/dismissed")
        names = [i["name"] for i in r.json()["items"]]
        # Artists first, ranked by cohort relevance (deeper library first), org last.
        assert names == ["High Relevance DJ", "Low Relevance DJ", "Aaa Org"]


class TestChannelReinstate:
    async def test_requires_auth(self, client):
        r = await client.post("/api/admin/channels/1/reinstate")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.post("/api/admin/channels/1/reinstate")
        assert r.status_code == 403

    async def test_404_unknown(self, admin_client):
        r = await admin_client.post("/api/admin/channels/999999/reinstate")
        assert r.status_code == 404

    async def test_reinstate_artist_marker_recandidates(self, admin_client, db):
        a = await _artist(db, "Comeback DJ", deezer_id="5001")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()

        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        assert (
            await admin_client.get("/api/admin/channels/artist-candidates")
        ).json()["total"] == 0

        marker = (
            await db.execute(
                select(Channel).where(
                    Channel.artist_id == a.id, Channel.external_id.is_(None)
                )
            )
        ).scalar_one()

        r = await admin_client.post(
            f"/api/admin/channels/{marker.id}/reinstate"
        )
        assert r.status_code == 200

        # Marker gone, artist is a candidate again.
        gone = (
            await db.execute(select(Channel).where(Channel.id == marker.id))
        ).scalar_one_or_none()
        assert gone is None
        assert (
            await admin_client.get("/api/admin/channels/artist-candidates")
        ).json()["total"] == 1

    async def test_reinstate_org_marker_recandidates(self, admin_client, db):
        await _tid(db, "Returning Org", 5100)
        await db.commit()
        await admin_client.post(
            "/api/admin/channels/candidates/dismiss", json={"name": "Returning Org"}
        )
        marker = (
            await db.execute(
                select(Channel).where(Channel.name == "Returning Org")
            )
        ).scalar_one()

        r = await admin_client.post(
            f"/api/admin/channels/{marker.id}/reinstate"
        )
        assert r.status_code == 200

        after = await admin_client.get("/api/admin/channels/candidates")
        assert "Returning Org" in [i["name"] for i in after.json()["items"]]

    async def test_refuses_to_delete_real_channel(self, admin_client, db):
        # A real curated channel (external_id non-NULL) is NEVER deletable via
        # reinstate — even if excluded. 404, and the row survives.
        c = await _channel(db, "Real Chan", external_id="UCreal", excluded=True)
        await db.commit()

        r = await admin_client.post(f"/api/admin/channels/{c.id}/reinstate")
        assert r.status_code == 404

        survivor = (
            await db.execute(select(Channel).where(Channel.id == c.id))
        ).scalar_one_or_none()
        assert survivor is not None

    async def test_writes_audit_log(self, admin_client, db):
        a = await _artist(db, "Audited Reinstate DJ", deezer_id="5002")
        await _cohort(db, a, tier=1, signals={"nb_sets_12m": 3})
        await db.commit()
        await admin_client.post(
            f"/api/admin/channels/artist-candidates/{a.id}/dismiss"
        )
        marker = (
            await db.execute(
                select(Channel).where(
                    Channel.artist_id == a.id, Channel.external_id.is_(None)
                )
            )
        ).scalar_one()

        r = await admin_client.post(f"/api/admin/channels/{marker.id}/reinstate")
        assert r.status_code == 200

        audit = await admin_client.get("/api/admin/audit-log")
        entries = [
            e for e in audit.json()["items"] if e["action"] == "channel_reinstate"
        ]
        assert len(entries) == 1
        assert entries[0]["target_id"] == marker.id
