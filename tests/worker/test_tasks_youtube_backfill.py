"""Tests for the C14.b L7 one-shot historical YouTube backfill.

Modelled on test_tasks_youtube.py (the L5 nightly crawl):

  * ``fetch_channel_uploads`` / ``uploads_playlist_id`` — the L2 building blocks,
    exercised directly (a fake httpx client serving canned playlistItems pages);
  * the single-instance Redis lock in the task WRAPPER (SET NX EX + conditional
    release), driven with the celery/redis sys.modules mock harness;
  * the async CORE ``_backfill_channel`` — driven end-to-end over an OWN in-memory
    aiosqlite engine (StaticPool) with the L2 client (uploads + durations) MOCKED
    and the duration gate + ``upsert_youtube_set`` REAL, so we exercise set
    creation, idempotence, cross-source dedup and the AV9 deadline against a real DB.

The AV9 clock is faked by replacing the task module's ``time`` attribute (never the
global ``time`` — asyncio's loop reads ``time.monotonic`` internally and would
consume the fake sequence). Parallel-safe: each test builds its own engine; no
shared module state is mutated beyond monkeypatch (auto-restored).
"""
import asyncio
import datetime
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

# Make the workers package importable (same pattern as test_tasks_youtube).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# celery is not installed in the test env → mock the modules the task imports.
for _mod in [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions", "requests", "curl_cffi",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


class _FakeSoftTimeLimitExceeded(Exception):
    pass


_celery_exceptions = sys.modules.setdefault("celery.exceptions", MagicMock())
_celery_exceptions.SoftTimeLimitExceeded = _FakeSoftTimeLimitExceeded


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.autoretry_for = kwargs.get("autoretry_for", ())
        fn.bind = kwargs.get("bind", False)
        fn.soft_time_limit = kwargs.get("soft_time_limit")
        fn.time_limit = kwargs.get("time_limit")
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock = MagicMock()
_celery_mock.task.side_effect = _task_decorator
_celery_app_mod = MagicMock(celery_app=_celery_mock, REDIS_URL="redis://test")
sys.modules["workers.celery_app"] = _celery_app_mod


@pytest.fixture
def youtube_task(monkeypatch):
    """Import the real task module with celery mocked (fresh workers.tasks init)."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.tasks.youtube as youtube_task

    return youtube_task


# ── L2 uploads client: uploads_playlist_id + fetch_channel_uploads ────────────


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakePlaylistClient:
    """Serves canned playlistItems pages keyed by pageToken (None = first page).

    ``pages`` maps a token → payload dict; a missing token yields a 404 (so an
    unexpected extra fetch is caught). Records every request's params.
    """

    def __init__(self, pages, *, status=200):
        self._pages = pages
        self._status = status
        self.calls = []

    async def get(self, url, params=None):
        params = params or {}
        self.calls.append({"url": url, "params": params})
        if self._status != 200:
            return _FakeResponse(self._status, {})
        payload = self._pages.get(params.get("pageToken"))
        if payload is None:
            return _FakeResponse(404, {})
        return _FakeResponse(200, payload)


def _pl_item(video_id, *, title="Set", published="2020-02-01T12:00:00Z", thumbs=None):
    return {
        "snippet": {
            "resourceId": {"videoId": video_id},
            "title": title,
            "publishedAt": published,
            "thumbnails": thumbs or {"high": {"url": f"http://img/{video_id}.jpg"}},
        }
    }


_UC = "UCabc1234567890abcdef12"


class TestUploadsPlaylistId:
    def test_uc_to_uu(self):
        from workers import youtube as yt

        assert yt.uploads_playlist_id(_UC) == "UUabc1234567890abcdef12"

    def test_rejects_non_uc(self):
        from workers import youtube as yt

        for bad in ["", None, "PLsomething", "xUCabc", "uc_lower"]:
            with pytest.raises(ValueError):
                yt.uploads_playlist_id(bad)


class TestFetchChannelUploads:
    def test_paginates_and_maps_shape(self):
        from workers import youtube as yt

        pages = {
            None: {"items": [_pl_item("V1"), _pl_item("V2")], "nextPageToken": "T2"},
            "T2": {"items": [_pl_item("V3")]},  # no nextPageToken → last page
        }
        client = _FakePlaylistClient(pages)

        out = asyncio.run(
            yt.fetch_channel_uploads(client, _UC, "KEY", max_videos=500)
        )

        assert [v["video_id"] for v in out] == ["V1", "V2", "V3"]
        # Queried the UU… uploads playlist, snippet part.
        assert client.calls[0]["params"]["playlistId"] == "UU" + _UC[2:]
        assert client.calls[0]["params"]["part"] == "snippet"
        # Same dict shape as parse_channel_feed (consumed by upsert_youtube_set).
        assert set(out[0]) == {"video_id", "title", "published", "thumbnail_url"}
        assert isinstance(out[0]["published"], datetime.datetime)
        assert out[0]["thumbnail_url"] == "http://img/V1.jpg"

    def test_respects_cap_and_warns(self, caplog):
        from workers import youtube as yt

        pages = {
            None: {"items": [_pl_item("V1"), _pl_item("V2")], "nextPageToken": "T2"},
            "T2": {"items": [_pl_item("V3"), _pl_item("V4")], "nextPageToken": "T3"},
            "T3": {"items": [_pl_item("V5")]},
        }
        client = _FakePlaylistClient(pages)

        with caplog.at_level(logging.WARNING):
            out = asyncio.run(
                yt.fetch_channel_uploads(client, _UC, "KEY", max_videos=3)
            )

        assert [v["video_id"] for v in out] == ["V1", "V2", "V3"]
        # Stopped at the cap mid-page-2; page T3 was never requested.
        tokens = [c["params"].get("pageToken") for c in client.calls]
        assert tokens == [None, "T2"]
        # No silent truncation — a warning names the cap.
        assert any("max_videos" in r.getMessage() for r in caplog.records)

    def test_skips_items_without_video_id(self):
        from workers import youtube as yt

        pages = {
            None: {
                "items": [
                    {"snippet": {"title": "no resourceId"}},  # malformed → skipped
                    _pl_item("V2"),
                ]
            }
        }
        out = asyncio.run(
            yt.fetch_channel_uploads(_FakePlaylistClient(pages), _UC, "KEY")
        )
        assert [v["video_id"] for v in out] == ["V2"]

    def test_no_api_key_is_graceful_empty(self):
        from workers import youtube as yt

        client = _FakePlaylistClient({None: {"items": [_pl_item("V1")]}})
        out = asyncio.run(yt.fetch_channel_uploads(client, _UC, "", max_videos=10))
        assert out == []
        assert client.calls == []  # never touched the network

    def test_non_200_raises(self):
        from workers import youtube as yt

        client = _FakePlaylistClient({}, status=503)
        with pytest.raises(yt.YouTubeHTTPError):
            asyncio.run(yt.fetch_channel_uploads(client, _UC, "KEY"))


# ── Task wrapper: single-instance per-channel Redis lock ──────────────────────


@pytest.fixture
def lock_redis(monkeypatch):
    """Controllable redis client; defaults acquire + cleanly release the lock."""
    client = MagicMock()
    client.set.return_value = True
    client.get.return_value = "task-bf"
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def lock_self():
    task_self = MagicMock()
    task_self.request.id = "task-bf"
    return task_self


class TestBackfillLock:
    def test_skips_when_lock_held(self, youtube_task, lock_redis, lock_self, monkeypatch):
        run = MagicMock()
        monkeypatch.setattr(youtube_task, "_run_backfill_youtube_channel", run)
        lock_redis.set.return_value = False  # nx=True: lock already held
        lock_redis.get.return_value = "task-other"

        result = youtube_task.backfill_youtube_channel(lock_self, 42)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        lock_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, youtube_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock(return_value={"sets_created": 3})
        monkeypatch.setattr(youtube_task, "_run_backfill_youtube_channel", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-bf"  # still owns the lock

        result = youtube_task.backfill_youtube_channel(lock_self, 42)

        assert result == {"sets_created": 3}
        run.assert_called_once_with(lock_self, 42)
        _, kwargs = lock_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == youtube_task.YOUTUBE_BACKFILL_LOCK_TTL
        # Lock key is scoped PER CHANNEL.
        lock_redis.delete.assert_called_once_with(
            "lock:backfill_youtube_channel:42"
        )

    def test_does_not_release_lock_it_no_longer_owns(
        self, youtube_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock(return_value={})
        monkeypatch.setattr(youtube_task, "_run_backfill_youtube_channel", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-newer"  # someone else owns it now

        youtube_task.backfill_youtube_channel(lock_self, 42)

        lock_redis.delete.assert_not_called()

    def test_lock_ttl_strictly_covers_time_limit(self, youtube_task):
        assert (
            youtube_task.YOUTUBE_BACKFILL_LOCK_TTL
            > youtube_task.YOUTUBE_BACKFILL_TIME_LIMIT
        )
        assert (
            youtube_task.backfill_youtube_channel.soft_time_limit
            == youtube_task.YOUTUBE_BACKFILL_SOFT_TIME_LIMIT
        )
        assert (
            youtube_task.backfill_youtube_channel.time_limit
            == youtube_task.YOUTUBE_BACKFILL_TIME_LIMIT
        )
        # No autoretry (SoftTimeLimitExceeded IS an Exception).
        assert youtube_task.backfill_youtube_channel.autoretry_for == ()
        assert (
            0
            < youtube_task.YOUTUBE_BACKFILL_DEADLINE_MARGIN
            < youtube_task.YOUTUBE_BACKFILL_SOFT_TIME_LIMIT
        )


# ── Async core: _backfill_channel over an in-memory aiosqlite engine ──────────

_PUB = datetime.datetime(2020, 2, 1, 12, 0, tzinfo=datetime.timezone.utc)


class _FakeAsyncCM:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeLimiter:
    def __init__(self):
        self.acquired = []

    def acquire(self, name):
        self.acquired.append(name)
        return _FakeAsyncCM()


class _FakeClock:
    """Deterministic time.monotonic stand-in: pops the sequence one call at a time,
    then keeps returning the last value."""

    def __init__(self, values):
        self._values = list(values)

    def monotonic(self):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


def _video(video_id, title, *, published=_PUB, thumbnail_url=None):
    # Shape emitted by fetch_channel_uploads / parse_channel_feed (no duration_ms;
    # the task injects it from the durations map before upsert_youtube_set).
    return {
        "video_id": video_id,
        "title": title,
        "published": published,
        "thumbnail_url": thumbnail_url,
    }


def _seed_channel(
    session,
    *,
    channel_id,
    external_id=_UC,
    name="Ritter Butzke",
    platform="youtube",
    watched=True,
    excluded=False,
):
    from models import Channel

    session.add(
        Channel(
            id=channel_id,
            platform=platform,
            external_id=external_id,
            name=name,
            watched=watched,
            excluded=excluded,
        )
    )


def _count_sets(session):
    from models import DJSet

    return session.query(DJSet).count()


def _install_uploads_mocks(monkeypatch, uploads, durations):
    """Mock the L2 uploads + durations cores; the gate + upsert stay REAL."""
    from workers import youtube as yt

    async def _fetch_channel_uploads(client, channel_id, api_key, *, max_videos):
        return [] if not api_key else list(uploads)

    async def _fetch_video_durations(client, video_ids, api_key):
        if not api_key:
            return {}
        return {v: durations[v] for v in video_ids if v in durations}

    monkeypatch.setattr(yt, "fetch_channel_uploads", _fetch_channel_uploads)
    monkeypatch.setattr(yt, "fetch_video_durations", _fetch_video_durations)


async def _new_engine_factory():
    from database import Base
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def _run_backfill_core(
    seed_fn, read_fn, *, channel_id, api_key, deadline, uploads, durations, monkeypatch
):
    """Own in-memory aiosqlite engine, seeded, then ``_backfill_channel`` run and a
    ``read_fn`` snapshot — all under a SINGLE event loop (StaticPool conn is bound
    to its creating loop). Returns ``{"stats", "snapshot"}``."""
    import workers.tasks.youtube as youtube_task

    _install_uploads_mocks(monkeypatch, uploads, durations)

    async def _go():
        engine, factory = await _new_engine_factory()
        async with factory() as db:
            await db.run_sync(seed_fn)
            await db.commit()
        stats = await youtube_task._backfill_channel(
            factory,
            object(),
            _FakeLimiter(),
            channel_id=channel_id,
            api_key=api_key,
            deadline=deadline,
        )
        async with factory() as db:
            snapshot = await db.run_sync(read_fn)
        await engine.dispose()
        return {"stats": stats, "snapshot": snapshot}

    return asyncio.run(_go())


class TestBackfillCore:
    def test_creates_historical_sets_short_filtered(self, youtube_task, monkeypatch):
        # The acceptance vector: a historical full set must be captured.
        uploads = [
            _video("VID_HIST", "Schrotthagen | Full Set at Ritter Butzke"),
            _video("VID_TEASER", "Ritter Butzke Teaser"),
        ]

        def _read(session):
            from models import DJSet

            sets = session.query(DJSet).all()
            return {
                "n": len(sets),
                "ext": [s.external_id for s in sets],
                "source": sets[0].source if sets else None,
                "title": sets[0].title if sets else None,
                "dur_ms": sets[0].duration_ms if sets else None,
            }

        out = _run_backfill_core(
            lambda s: _seed_channel(s, channel_id=1, name="Ritter Butzke"),
            _read,
            channel_id=1,
            api_key="KEY",
            deadline=float("inf"),
            uploads=uploads,
            durations={"VID_HIST": 3600, "VID_TEASER": 300},
            monkeypatch=monkeypatch,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["videos_seen"] == 2
        assert stats["sets_created"] == 1  # only the long video clears the gate
        assert stats["deadline_hit"] is False
        assert snap["n"] == 1
        assert snap["ext"] == ["VID_HIST"]
        assert snap["source"] == "youtube"
        assert "Schrotthagen" in snap["title"]
        assert snap["dur_ms"] == 3600 * 1000

    def test_no_api_key_is_graceful_noop(self, youtube_task, monkeypatch):
        out = _run_backfill_core(
            lambda s: _seed_channel(s, channel_id=1),
            _count_sets,
            channel_id=1,
            api_key="",  # no Data-API key
            deadline=float("inf"),
            uploads=[_video("VID_HIST", "Long set")],
            durations={"VID_HIST": 3600},
            monkeypatch=monkeypatch,
        )
        assert out["stats"] == {
            "videos_seen": 0,
            "sets_created": 0,
            "deadline_hit": False,
        }
        assert out["snapshot"] == 0

    def test_absent_channel_is_noop(self, youtube_task, monkeypatch):
        out = _run_backfill_core(
            lambda s: None,  # seed nothing
            _count_sets,
            channel_id=999,
            api_key="KEY",
            deadline=float("inf"),
            uploads=[_video("VID_HIST", "Long set")],
            durations={"VID_HIST": 3600},
            monkeypatch=monkeypatch,
        )
        assert out["stats"]["sets_created"] == 0
        assert out["snapshot"] == 0

    def test_excluded_channel_is_noop(self, youtube_task, monkeypatch):
        out = _run_backfill_core(
            lambda s: _seed_channel(s, channel_id=1, excluded=True),
            _count_sets,
            channel_id=1,
            api_key="KEY",
            deadline=float("inf"),
            uploads=[_video("VID_HIST", "Long set")],
            durations={"VID_HIST": 3600},
            monkeypatch=monkeypatch,
        )
        assert out["stats"] == {
            "videos_seen": 0,
            "sets_created": 0,
            "deadline_hit": False,
        }
        assert out["snapshot"] == 0

    def test_rerun_is_idempotent(self, youtube_task, monkeypatch):
        _install_uploads_mocks(
            monkeypatch,
            [_video("VID_HIST", "Long historical set")],
            {"VID_HIST": 3600},
        )

        async def _go():
            engine, factory = await _new_engine_factory()
            async with factory() as db:
                await db.run_sync(lambda s: _seed_channel(s, channel_id=1))
                await db.commit()
            s1 = await youtube_task._backfill_channel(
                factory, object(), _FakeLimiter(),
                channel_id=1, api_key="KEY", deadline=float("inf"),
            )
            s2 = await youtube_task._backfill_channel(
                factory, object(), _FakeLimiter(),
                channel_id=1, api_key="KEY", deadline=float("inf"),
            )
            async with factory() as db:
                count = await db.run_sync(_count_sets)
            await engine.dispose()
            return s1, s2, count

        s1, s2, count = asyncio.run(_go())
        assert s1["sets_created"] == 1
        assert s2["sets_created"] == 0  # already stored → dedup filter, nothing new
        assert count == 1

    def test_cross_source_dedup_skips_existing_trackid_set(
        self, youtube_task, monkeypatch
    ):
        # A YouTube re-upload of a set already indexed from TrackID (same reliable
        # title date + same canonical channel + near-identical title) is NOT re-created.
        title = "Boiler Room Berlin 24.09.2022"

        def _seed(session):
            from models import Channel, DJSet

            session.add(
                Channel(
                    id=1,
                    platform="youtube",
                    external_id="UCbr1234567890abcdef123",
                    name="Boiler Room",
                    watched=True,
                    excluded=False,
                )
            )
            session.add(
                DJSet(
                    source="trackid",
                    external_id="TID1",
                    title=title,
                    channel="Boiler Room",
                    event_date=datetime.date(2022, 9, 24),
                )
            )

        def _read(session):
            from models import DJSet

            return {
                "youtube": session.query(DJSet).filter_by(source="youtube").count(),
                "total": session.query(DJSet).count(),
            }

        out = _run_backfill_core(
            _seed,
            _read,
            channel_id=1,
            api_key="KEY",
            deadline=float("inf"),
            uploads=[_video("VID_YT", title)],
            durations={"VID_YT": 3600},
            monkeypatch=monkeypatch,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["videos_seen"] == 1
        assert stats["sets_created"] == 0  # deduped against the trackid set
        assert snap["youtube"] == 0
        assert snap["total"] == 1

    def test_deadline_stops_before_next_batch(self, youtube_task, monkeypatch):
        # Batch of 1 so each video is its own batch; the deadline is checked BEFORE
        # each batch. First batch reads 0.0 (< 100 → processed), second reads 1e9
        # (>= 100 → break). Fake ONLY the module's `time` (AV9 pitfall).
        monkeypatch.setattr(youtube_task, "YOUTUBE_BACKFILL_BATCH", 1)
        monkeypatch.setattr(youtube_task, "time", _FakeClock([0.0, 10**9]))
        _install_uploads_mocks(
            monkeypatch,
            [_video("VID_A", "Set A"), _video("VID_B", "Set B")],
            {"VID_A": 3600, "VID_B": 3600},
        )

        async def _go():
            engine, factory = await _new_engine_factory()
            async with factory() as db:
                await db.run_sync(lambda s: _seed_channel(s, channel_id=1))
                await db.commit()
            stats = await youtube_task._backfill_channel(
                factory, object(), _FakeLimiter(),
                channel_id=1, api_key="KEY", deadline=100.0,
            )
            async with factory() as db:
                count = await db.run_sync(_count_sets)
            await engine.dispose()
            return stats, count

        stats, count = asyncio.run(_go())
        assert stats["sets_created"] == 1  # only the first batch processed
        assert stats["deadline_hit"] is True
        assert count == 1
