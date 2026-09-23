"""Tests for the low-level YouTube client (workers/youtube, C14.b L2).

Split by session type, same conventions as the other worker tests:

  * PURE helpers (``parse_channel_feed`` / ``parse_iso8601_duration`` /
    ``is_set_duration`` / the ``resolve_channel_id`` regex fast-paths) — exercised
    directly, no network.
  * The Data-API cores (``fetch_video_durations`` / ``resolve_channel_id`` handle
    path) — driven with a tiny in-process fake ``httpx`` client (no real network).
  * ``upsert_youtube_set`` — driven end-to-end over an OWN in-memory aiosqlite
    engine (StaticPool) via ``asyncio.run``: creation, idempotence, and the
    cross-source dedup branch (a pre-existing TrackID set absorbs the YouTube one).

Same sys.path pattern as test_set_title_meta.py (import ``workers.*`` from the
server root; ``server/api`` is added by the worker conftest for ``models``/``utils``).
No fixtures are refactored.
"""
import asyncio
import datetime
import os
import sys

# Make the workers package importable (same pattern as test_set_title_meta.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

import pytest  # noqa: E402
from workers.youtube import (  # noqa: E402
    YouTubeHTTPError,
    fetch_channel_title,
    fetch_video_durations,
    find_duplicate_set,
    is_set_duration,
    parse_channel_feed,
    parse_iso8601_duration,
    resolve_channel_id,
    search_channels,
    upsert_youtube_set,
    watch_url,
)

D = datetime.date

# A realistic (trimmed) YouTube channel Atom feed: two entries, full namespaces.
_FEED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <link rel="self" href="https://www.youtube.com/feeds/videos.xml?channel_id=UCabcdefghijklmnopqrstuv"/>
  <id>yt:channel:UCabcdefghijklmnopqrstuv</id>
  <yt:channelId>UCabcdefghijklmnopqrstuv</yt:channelId>
  <title>Boiler Room</title>
  <entry>
    <id>yt:video:VIDEO0000001</id>
    <yt:videoId>VIDEO0000001</yt:videoId>
    <yt:channelId>UCabcdefghijklmnopqrstuv</yt:channelId>
    <title>Peggy Gou at Boiler Room Berlin 25.12.2021</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=VIDEO0000001"/>
    <published>2021-12-26T18:30:00+00:00</published>
    <updated>2021-12-27T09:00:00+00:00</updated>
    <media:group>
      <media:title>Peggy Gou at Boiler Room Berlin 25.12.2021</media:title>
      <media:thumbnail url="https://i.ytimg.com/vi/VIDEO0000001/hqdefault.jpg" width="480" height="360"/>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:VIDEO0000002</id>
    <yt:videoId>VIDEO0000002</yt:videoId>
    <yt:channelId>UCabcdefghijklmnopqrstuv</yt:channelId>
    <title>Short clip no thumb</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=VIDEO0000002"/>
    <published>2022-01-01T00:00:00Z</published>
    <media:group>
      <media:title>Short clip no thumb</media:title>
    </media:group>
  </entry>
</feed>
"""


# ── Pure: parse_channel_feed ──────────────────────────────────────────────────


class TestParseChannelFeed:
    def test_two_entries(self):
        videos = parse_channel_feed(_FEED_XML)
        assert len(videos) == 2

    def test_fields_first_entry(self):
        v = parse_channel_feed(_FEED_XML)[0]
        assert v["video_id"] == "VIDEO0000001"
        assert v["title"] == "Peggy Gou at Boiler Room Berlin 25.12.2021"
        assert v["thumbnail_url"] == "https://i.ytimg.com/vi/VIDEO0000001/hqdefault.jpg"
        # Aware datetime parsed from the RFC-3339 offset form.
        assert v["published"].date() == D(2021, 12, 26)
        assert v["published"].tzinfo is not None

    def test_z_suffix_and_missing_thumbnail(self):
        v = parse_channel_feed(_FEED_XML)[1]
        assert v["video_id"] == "VIDEO0000002"
        assert v["thumbnail_url"] is None
        assert v["published"].date() == D(2022, 1, 1)

    def test_entry_without_video_id_skipped(self):
        xml = b"""<?xml version="1.0"?>
        <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
              xmlns="http://www.w3.org/2005/Atom">
          <entry><title>No id here</title></entry>
        </feed>"""
        assert parse_channel_feed(xml) == []

    def test_accepts_str(self):
        assert len(parse_channel_feed(_FEED_XML.decode())) == 2


# ── Pure: parse_iso8601_duration + is_set_duration ────────────────────────────


class TestParseIsoDuration:
    @pytest.mark.parametrize(
        "iso,expected",
        [
            ("PT1H30M15S", 5415),
            ("PT45M", 2700),
            ("PT30S", 30),
            ("PT2H", 7200),
            ("PT1H", 3600),
            ("P0D", 0),
            ("P1DT2H", 93600),
            ("PT1H0M0S", 3600),
        ],
    )
    def test_forms(self, iso, expected):
        assert parse_iso8601_duration(iso) == expected

    @pytest.mark.parametrize("bad", ["1H30M", "", None, "PT1X", "garbage"])
    def test_unparseable_is_none(self, bad):
        assert parse_iso8601_duration(bad) is None


class TestIsSetDuration:
    def test_threshold(self):
        assert is_set_duration(1800) is True
        assert is_set_duration(3600) is True

    def test_below_threshold(self):
        assert is_set_duration(1799) is False
        assert is_set_duration(0) is False

    def test_none(self):
        assert is_set_duration(None) is False


# ── resolve_channel_id: regex fast-paths (no network) ─────────────────────────

_UC = "UCabcdefghijklmnopqrstuv"  # UC + 22 chars


class TestResolveChannelIdRegex:
    def test_channel_url(self):
        got = asyncio.run(
            resolve_channel_id(
                None, f"https://www.youtube.com/channel/{_UC}", api_key=""
            )
        )
        assert got == _UC

    def test_channel_url_with_trailing_path(self):
        got = asyncio.run(
            resolve_channel_id(None, f"https://www.youtube.com/channel/{_UC}/videos", "")
        )
        assert got == _UC

    def test_raw_uc(self):
        assert asyncio.run(resolve_channel_id(None, _UC, "")) == _UC

    def test_handle_without_key_returns_none(self):
        # Non-UC input + falsy key → graceful None (no network).
        assert asyncio.run(resolve_channel_id(None, "@boilerroom", "")) is None

    def test_empty_input(self):
        assert asyncio.run(resolve_channel_id(None, "", "key")) is None


# ── Data-API cores driven with a fake httpx client ────────────────────────────


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal async stand-in for httpx.AsyncClient.get, capturing calls."""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params or {}))
        return self._handler(url, params or {})


class TestFetchVideoDurations:
    def test_no_api_key_returns_empty(self):
        # Falsy key → graceful {} and NO client call.
        client = _FakeClient(lambda url, params: _FakeResp(500))
        got = asyncio.run(fetch_video_durations(client, ["a", "b"], api_key=""))
        assert got == {}
        assert client.calls == []

    def test_empty_ids_returns_empty(self):
        client = _FakeClient(lambda url, params: _FakeResp(500))
        assert asyncio.run(fetch_video_durations(client, [], api_key="k")) == {}
        assert client.calls == []

    def test_parses_durations(self):
        payload = {
            "items": [
                {"id": "v1", "contentDetails": {"duration": "PT1H"}},
                {"id": "v2", "contentDetails": {"duration": "PT30M"}},
                {"id": "v3", "contentDetails": {"duration": "bogus"}},  # dropped
            ]
        }
        client = _FakeClient(lambda url, params: _FakeResp(200, payload))
        got = asyncio.run(fetch_video_durations(client, ["v1", "v2", "v3"], "k"))
        assert got == {"v1": 3600, "v2": 1800}

    def test_http_error_raises(self):
        client = _FakeClient(lambda url, params: _FakeResp(403))
        with pytest.raises(YouTubeHTTPError):
            asyncio.run(fetch_video_durations(client, ["v1"], "k"))


class TestResolveChannelIdHandle:
    def test_handle_resolved_via_channels_list(self):
        def handler(url, params):
            assert url.endswith("/channels")
            assert params.get("forHandle") == "@boilerroom"
            return _FakeResp(200, {"items": [{"id": _UC}]})

        client = _FakeClient(handler)
        got = asyncio.run(resolve_channel_id(client, "@boilerroom", "k"))
        assert got == _UC

    def test_handle_falls_back_to_search(self):
        def handler(url, params):
            if url.endswith("/channels"):
                return _FakeResp(200, {"items": []})  # handle not found
            assert url.endswith("/search")
            return _FakeResp(200, {"items": [{"id": {"channelId": _UC}}]})

        client = _FakeClient(handler)
        got = asyncio.run(
            resolve_channel_id(client, "https://youtube.com/c/BoilerRoom", "k")
        )
        assert got == _UC


class TestFetchChannelTitle:
    def test_no_api_key_returns_none(self):
        # Falsy key → graceful None and NO client call (mirrors durations).
        client = _FakeClient(lambda url, params: _FakeResp(500))
        assert asyncio.run(fetch_channel_title(client, _UC, api_key="")) is None
        assert client.calls == []

    def test_returns_snippet_title(self):
        def handler(url, params):
            assert url.endswith("/channels")
            assert params.get("part") == "snippet"
            assert params.get("id") == _UC
            return _FakeResp(200, {"items": [{"snippet": {"title": "Boiler Room"}}]})

        client = _FakeClient(handler)
        assert asyncio.run(fetch_channel_title(client, _UC, "k")) == "Boiler Room"

    def test_empty_items_returns_none(self):
        client = _FakeClient(lambda url, params: _FakeResp(200, {"items": []}))
        assert asyncio.run(fetch_channel_title(client, _UC, "k")) is None

    def test_http_error_raises(self):
        client = _FakeClient(lambda url, params: _FakeResp(403))
        with pytest.raises(YouTubeHTTPError):
            asyncio.run(fetch_channel_title(client, _UC, "k"))


class TestSearchChannels:
    _SEARCH_PAYLOAD = {
        "items": [
            {
                "id": {"kind": "youtube#channel", "channelId": _UC},
                "snippet": {
                    "title": "Boiler Room",
                    "description": "The world's leading music broadcaster",
                    "thumbnails": {
                        "default": {"url": "https://i.ytimg.com/def.jpg"},
                        "high": {"url": "https://i.ytimg.com/high.jpg"},
                    },
                },
            },
            # A malformed item without a channelId is skipped defensively.
            {"id": {"kind": "youtube#channel"}, "snippet": {"title": "No id"}},
        ]
    }

    def test_no_api_key_returns_empty(self):
        # Falsy key → graceful [] and NO client call (mirrors durations/title).
        client = _FakeClient(lambda url, params: _FakeResp(500))
        assert asyncio.run(search_channels(client, "boiler", api_key="")) == []
        assert client.calls == []

    def test_parses_hits(self):
        def handler(url, params):
            assert url.endswith("/search")
            assert params.get("type") == "channel"
            assert params.get("q") == "boiler room"
            return _FakeResp(200, self._SEARCH_PAYLOAD)

        client = _FakeClient(handler)
        got = asyncio.run(search_channels(client, "boiler room", "k"))
        # The malformed (no channelId) item is dropped.
        assert got == [
            {
                "channel_id": _UC,
                "title": "Boiler Room",
                "description": "The world's leading music broadcaster",
                # The DEFAULT thumbnail is used.
                "thumbnail_url": "https://i.ytimg.com/def.jpg",
            }
        ]

    def test_missing_thumbnails_and_description(self):
        payload = {"items": [{"id": {"channelId": _UC}, "snippet": {"title": "T"}}]}
        client = _FakeClient(lambda url, params: _FakeResp(200, payload))
        got = asyncio.run(search_channels(client, "t", "k"))
        assert got == [
            {
                "channel_id": _UC,
                "title": "T",
                "description": None,
                "thumbnail_url": None,
            }
        ]

    def test_limit_passed_as_max_results(self):
        captured = {}

        def handler(url, params):
            captured.update(params)
            return _FakeResp(200, {"items": []})

        client = _FakeClient(handler)
        asyncio.run(search_channels(client, "q", "k", limit=3))
        assert captured.get("maxResults") == 3

    def test_http_error_raises(self):
        client = _FakeClient(lambda url, params: _FakeResp(403))
        with pytest.raises(YouTubeHTTPError):
            asyncio.run(search_channels(client, "q", "k"))


# ── upsert_youtube_set over an own aiosqlite engine ───────────────────────────


def _async_run(fn):
    """Build an OWN in-memory aiosqlite engine (StaticPool → one shared conn),
    create the schema, and run ``fn(factory)`` under a single event loop.
    Self-contained (mirrors test_import_trackid_clean's pattern)."""
    from database import Base
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    async def _go():
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            return await fn(factory)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def _video(video_id, title, published, thumbnail_url=None, duration_ms=None):
    return {
        "video_id": video_id,
        "title": title,
        "published": published,
        "thumbnail_url": thumbnail_url,
        "duration_ms": duration_ms,
    }


_PUB = datetime.datetime(2020, 2, 1, 12, 0, tzinfo=datetime.timezone.utc)


class TestFindDuplicateSet:
    def test_abstains_without_event_date(self):
        # No reliable date → never dedup across sources (invariant #4 abstention),
        # even with a perfectly matching set present.
        from models import DJSet

        async def scenario(factory):
            async with factory() as db:
                db.add(
                    DJSet(
                        external_id="TID1",
                        source="trackid",
                        title="Peggy Gou at Boiler Room Berlin",
                        channel="Boiler Room",
                        event_date=D(2021, 12, 25),
                        played_date=D(2021, 12, 25),
                        created_at=_PUB,
                    )
                )
                await db.commit()
                dup = await find_duplicate_set(
                    db,
                    "Peggy Gou at Boiler Room Berlin",
                    "Boiler Room",
                    event_date=None,
                )
                assert dup is None

        _async_run(scenario)

    def test_matches_on_played_date_fallback(self):
        # Candidate carries only played_date (no event_date) but it equals the
        # incoming reliable date → the OR fallback still matches.
        from models import DJSet

        async def scenario(factory):
            async with factory() as db:
                cand = DJSet(
                    external_id="TID2",
                    source="trackid",
                    title="Peggy Gou at Boiler Room Berlin",
                    channel="Boiler Room",
                    played_date=D(2021, 12, 25),
                    created_at=_PUB,
                )
                db.add(cand)
                await db.commit()
                cid = cand.id
                dup = await find_duplicate_set(
                    db,
                    "Peggy Gou at Boiler Room Berlin 25.12.2021",
                    "Boiler Room",
                    event_date=D(2021, 12, 25),
                )
                assert dup is not None and dup.id == cid

        _async_run(scenario)


class TestUpsertYoutubeSet:
    def test_creates_metadata_only_set(self):
        from models import DJSet, SetTrack
        from sqlalchemy import select

        async def scenario(factory):
            async with factory() as db:
                dj, created = await upsert_youtube_set(
                    db,
                    video=_video(
                        "VID1", "DJ Test Mix 25.12.2020", _PUB, duration_ms=3_600_000
                    ),
                    channel_name="Some Channel",
                )
                await db.commit()
                assert created is True
                assert dj.source == "youtube"
                assert dj.external_id == "VID1"
                assert dj.source_url == watch_url("VID1")
                # played_date comes from the feed's published timestamp...
                assert dj.played_date == D(2020, 2, 1)
                # ...event_date is the (unambiguous, >12 day) date parsed from the title
                assert dj.event_date == D(2020, 12, 25)
                assert dj.duration_ms == 3_600_000
                assert dj.channel == "Some Channel"
                assert dj.styles == []
                assert dj.search_text  # non-empty folded title
                # No SetTrack rows: metadata-only.
                n_tracks = await db.execute(
                    select(SetTrack).where(SetTrack.set_id == dj.id)
                )
                assert n_tracks.scalars().first() is None
                n_sets = await db.execute(select(DJSet))
                assert len(n_sets.scalars().all()) == 1

        _async_run(scenario)

    def test_idempotent_on_reimport(self):
        from models import DJSet
        from sqlalchemy import func, select

        async def scenario(factory):
            # A title WITHOUT a parseable date → event_date None → dedup is
            # skipped and the (external_id, source) update path is exercised.
            vid = _video("VID2", "Random Live Session", _PUB)
            async with factory() as db:
                dj1, created1 = await upsert_youtube_set(
                    db, video=vid, channel_name="My Channel"
                )
                await db.commit()
                first_id = dj1.id
            async with factory() as db:
                dj2, created2 = await upsert_youtube_set(
                    db, video=vid, channel_name="My Channel"
                )
                await db.commit()
                assert created1 is True
                assert created2 is False
                assert dj2.id == first_id
                total = await db.execute(select(func.count()).select_from(DJSet))
                assert total.scalar() == 1

        _async_run(scenario)

    def test_dedup_absorbs_into_existing_trackid_set(self):
        from models import DJSet
        from sqlalchemy import func, select

        async def scenario(factory):
            # Pre-existing TrackID set of the SAME performance: same reliable
            # event_date, same canonical channel, near-identical title.
            async with factory() as db:
                trackid_set = DJSet(
                    external_id="TID99",
                    source="trackid",
                    title="Peggy Gou at Boiler Room Berlin",
                    channel="Boiler Room",
                    event_date=D(2021, 12, 25),
                    created_at=_PUB,
                )
                db.add(trackid_set)
                await db.commit()
                tid = trackid_set.id

            async with factory() as db:
                dj, created = await upsert_youtube_set(
                    db,
                    video=_video(
                        "YTVID",
                        "Peggy Gou at Boiler Room Berlin 25.12.2021",
                        _PUB,
                    ),
                    channel_name="Boiler Room",
                )
                await db.commit()
                # Absorbed: returns the existing trackid row, creates nothing.
                assert created is False
                assert dj.id == tid
                assert dj.source == "trackid"
                total = await db.execute(select(func.count()).select_from(DJSet))
                assert total.scalar() == 1

        _async_run(scenario)

    def test_dedup_does_not_fire_on_different_channel(self):
        from models import DJSet
        from sqlalchemy import func, select

        async def scenario(factory):
            async with factory() as db:
                db.add(
                    DJSet(
                        external_id="TID100",
                        source="trackid",
                        title="Peggy Gou at Boiler Room Berlin",
                        channel="Cercle",  # DIFFERENT channel
                        event_date=D(2021, 12, 25),
                        created_at=_PUB,
                    )
                )
                await db.commit()

            async with factory() as db:
                dj, created = await upsert_youtube_set(
                    db,
                    video=_video(
                        "YTVID2",
                        "Peggy Gou at Boiler Room Berlin 25.12.2021",
                        _PUB,
                    ),
                    channel_name="Boiler Room",
                )
                await db.commit()
                # Channel differs → no dedup → a fresh youtube row is created.
                assert created is True
                assert dj.source == "youtube"
                total = await db.execute(select(func.count()).select_from(DJSet))
                assert total.scalar() == 2

        _async_run(scenario)
