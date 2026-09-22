"""Tests for the C14.b L5 nightly YouTube DJ-set watch task.

Two session types, same conventions as test_tasks_link_set_artists.py:

  * the single-instance Redis lock in the task WRAPPER (SET NX EX + conditional
    release) — driven with a celery/redis sys.modules mock harness (celery is not
    installed in the test env), ``_run_crawl_youtube_channels`` stubbed;
  * the async CORE ``_crawl_channels`` — driven end-to-end over an OWN in-memory
    aiosqlite engine (StaticPool) via ``asyncio.run``, with the L2 youtube client
    (feed + durations) MOCKED and the duration gate + ``upsert_youtube_set`` REAL,
    so we exercise set creation + last_checked_at stamping against a real DB.

The clock for the AV9 deadline test is faked by replacing the task module's
``time`` attribute (never the global ``time`` — asyncio's loop reads
``time.monotonic`` internally and would consume the fake sequence; the AV9 pitfall).
Parallel-safe: each test builds its own engine; no shared module state is mutated
beyond monkeypatch (auto-restored).
"""
import asyncio
import datetime
import os
import sys
from unittest.mock import MagicMock

import pytest

# Make the workers package importable (same pattern as test_tasks_link_set_artists).
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


# _run_crawl_youtube_channels does `from celery.exceptions import
# SoftTimeLimitExceeded` and uses it in an `except` — needs a real Exception
# subclass, not a MagicMock attribute (same technique as test_deadline_exit).
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


# ── Task wrapper: single-instance Redis lock ──────────────────────────────────


@pytest.fixture
def lock_redis(monkeypatch):
    """Controllable redis client; defaults acquire + cleanly release the lock."""
    client = MagicMock()
    client.set.return_value = True
    client.get.return_value = "task-yt"
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def lock_self():
    task_self = MagicMock()
    task_self.request.id = "task-yt"
    return task_self


class TestCrawlYoutubeChannelsLock:
    """Same SET NX EX + conditional-release pattern as the other crawl tasks."""

    def test_skips_when_lock_held(
        self, youtube_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock()
        monkeypatch.setattr(youtube_task, "_run_crawl_youtube_channels", run)
        lock_redis.set.return_value = False  # nx=True: lock already held
        lock_redis.get.return_value = "task-other"

        result = youtube_task.crawl_youtube_channels(lock_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        lock_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, youtube_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock(return_value={"channels": 1, "sets_created": 2})
        monkeypatch.setattr(youtube_task, "_run_crawl_youtube_channels", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-yt"  # still owns the lock

        result = youtube_task.crawl_youtube_channels(lock_self)

        assert result == {"channels": 1, "sets_created": 2}
        run.assert_called_once_with(lock_self)
        _, kwargs = lock_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == youtube_task.YOUTUBE_CRAWL_LOCK_TTL
        lock_redis.delete.assert_called_once_with("lock:crawl_youtube_channels")

    def test_does_not_release_lock_it_no_longer_owns(
        self, youtube_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock(return_value={})
        monkeypatch.setattr(youtube_task, "_run_crawl_youtube_channels", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-newer"  # someone else owns it now

        youtube_task.crawl_youtube_channels(lock_self)

        lock_redis.delete.assert_not_called()

    def test_lock_ttl_strictly_covers_time_limit(self, youtube_task):
        # The TTL must exceed the hard time_limit so the lock can't expire mid-run;
        # both must reference the shared module constants (one source of truth).
        assert (
            youtube_task.YOUTUBE_CRAWL_LOCK_TTL
            > youtube_task.YOUTUBE_CRAWL_TIME_LIMIT
        )
        assert (
            youtube_task.crawl_youtube_channels.soft_time_limit
            == youtube_task.YOUTUBE_CRAWL_SOFT_TIME_LIMIT
        )
        assert (
            youtube_task.crawl_youtube_channels.time_limit
            == youtube_task.YOUTUBE_CRAWL_TIME_LIMIT
        )
        # No autoretry (SoftTimeLimitExceeded IS an Exception).
        assert youtube_task.crawl_youtube_channels.autoretry_for == ()
        # Margin leaves an actual working window.
        assert (
            0
            < youtube_task.YOUTUBE_CRAWL_DEADLINE_MARGIN
            < youtube_task.YOUTUBE_CRAWL_SOFT_TIME_LIMIT
        )


# ── Async core: _crawl_channels over an in-memory aiosqlite engine ────────────

D = datetime.date
_PUB = datetime.datetime(2020, 2, 1, 12, 0, tzinfo=datetime.timezone.utc)


class _FakeAsyncCM:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeLimiter:
    """RateLimiter() stand-in: acquire(name) is an async CM; records the source."""

    def __init__(self):
        self.acquired = []

    def acquire(self, name):
        self.acquired.append(name)
        return _FakeAsyncCM()


class _FakeClock:
    """Deterministic time.monotonic stand-in (same shape as test_deadline_exit):
    pops the sequence one call at a time, then keeps returning the last value."""

    def __init__(self, values):
        self._values = list(values)

    def monotonic(self):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


def _video(video_id, title, *, published=_PUB, thumbnail_url=None):
    # Shape emitted by workers.youtube.parse_channel_feed (no duration_ms — the
    # task injects it from the durations map before calling upsert_youtube_set).
    return {
        "video_id": video_id,
        "title": title,
        "published": published,
        "thumbnail_url": thumbnail_url,
    }


def _install_youtube_client_mocks(monkeypatch, feed_by_channel, durations):
    """Mock the L2 client's network cores (feed + durations); the gate +
    upsert_youtube_set stay REAL. Returns a call recorder."""
    from workers import youtube as yt

    calls = {"feed": [], "durations": []}

    async def _fetch_channel_feed(client, channel_id):
        calls["feed"].append(channel_id)
        return list(feed_by_channel.get(channel_id, []))

    async def _fetch_video_durations(client, video_ids, api_key):
        calls["durations"].append(list(video_ids))
        if not api_key:
            return {}
        return {v: durations[v] for v in video_ids if v in durations}

    monkeypatch.setattr(yt, "fetch_channel_feed", _fetch_channel_feed)
    monkeypatch.setattr(yt, "fetch_video_durations", _fetch_video_durations)
    return calls


def _run_core(seed_fn, read_fn, *, api_key, deadline):
    """Own in-memory aiosqlite engine (StaticPool → one shared conn), schema
    created, ``seed_fn(session)`` seeded, then ``_crawl_channels`` run against it,
    then ``read_fn(session)`` snapshotted — ALL under a SINGLE event loop (the
    StaticPool aiosqlite connection is bound to its creating loop, so reads must
    stay in it). Returns ``{"stats", "snapshot"}``. Mirrors test_youtube.py /
    test_import_trackid_clean's self-contained pattern."""
    import workers.tasks.youtube as youtube_task
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

        async with factory() as db:
            await db.run_sync(seed_fn)
            await db.commit()

        stats = await youtube_task._crawl_channels(
            factory, object(), _FakeLimiter(), api_key=api_key, deadline=deadline
        )

        async with factory() as db:
            snapshot = await db.run_sync(read_fn)

        await engine.dispose()
        return {"stats": stats, "snapshot": snapshot}

    return asyncio.run(_go())


def _seed_channel(session, *, external_id, name="Boiler Room", watched=True,
                  excluded=False, last_checked_at=None):
    from models import Channel

    session.add(
        Channel(
            platform="youtube",
            external_id=external_id,
            name=name,
            watched=watched,
            excluded=excluded,
            last_checked_at=last_checked_at,
        )
    )


class TestCrawlChannelsCore:
    def test_creates_set_and_stamps_last_checked_at(self, youtube_task, monkeypatch):
        _install_youtube_client_mocks(
            monkeypatch,
            feed_by_channel={
                "UC_boiler": [
                    _video("VID_LONG", "Peggy Gou live set"),
                    _video("VID_SHORT", "Teaser clip"),
                ]
            },
            durations={"VID_LONG": 3600, "VID_SHORT": 600},
        )

        def _read(session):
            from models import Channel, DJSet

            sets = session.query(DJSet).all()
            chan = session.query(Channel).one()
            return {
                "n_sets": len(sets),
                "ext": sets[0].external_id if sets else None,
                "source": sets[0].source if sets else None,
                "dur_ms": sets[0].duration_ms if sets else None,
                "last_checked": chan.last_checked_at,
            }

        out = _run_core(
            lambda s: _seed_channel(s, external_id="UC_boiler"),
            _read,
            api_key="KEY",
            deadline=float("inf"),
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["channels"] == 1
        assert stats["videos_seen"] == 2
        assert stats["sets_created"] == 1  # only the long video clears the gate
        assert stats["deadline_hit"] is False

        assert snap["n_sets"] == 1
        assert snap["ext"] == "VID_LONG"
        assert snap["source"] == "youtube"
        assert snap["dur_ms"] == 3600 * 1000  # seconds → ms, from the durations map
        assert snap["last_checked"] is not None

    def test_no_api_key_is_graceful_noop(self, youtube_task, monkeypatch):
        calls = _install_youtube_client_mocks(
            monkeypatch,
            feed_by_channel={"UC_boiler": [_video("VID_LONG", "Long set")]},
            durations={"VID_LONG": 3600},
        )

        def _read(session):
            from models import Channel, DJSet

            return {
                "n_sets": session.query(DJSet).count(),
                "last_checked": session.query(Channel).one().last_checked_at,
            }

        out = _run_core(
            lambda s: _seed_channel(s, external_id="UC_boiler"),
            _read,
            api_key="",  # no Data-API key
            deadline=float("inf"),
        )
        stats, snap = out["stats"], out["snapshot"]

        # No crash; nothing created; the channel is NOT stamped (stays due).
        assert stats == {
            "channels": 0,
            "videos_seen": 0,
            "sets_created": 0,
            "deadline_hit": False,
        }
        assert calls["feed"] == []  # early no-op, no feed fetched
        assert snap["n_sets"] == 0
        assert snap["last_checked"] is None

    def test_deadline_stops_before_next_channel(self, youtube_task, monkeypatch):
        _install_youtube_client_mocks(
            monkeypatch,
            feed_by_channel={
                "UC_a": [_video("VID_A", "Set A")],
                "UC_b": [_video("VID_B", "Set B")],
            },
            durations={"VID_A": 3600, "VID_B": 3600},
        )
        # Clock: deadline is passed by the CALLER (100.0). The first channel's
        # check reads 0.0 (< 100 → processed); the second reads 1e9 (>= 100 →
        # break). Fake ONLY the module's `time` (never the global — the event loop
        # reads time.monotonic internally; AV9 pitfall).
        monkeypatch.setattr(youtube_task, "time", _FakeClock([0.0, 10**9]))

        def _seed(session):
            _seed_channel(session, external_id="UC_a", name="A")
            _seed_channel(session, external_id="UC_b", name="B")

        def _read(session):
            from models import Channel, DJSet

            stamped = (
                session.query(Channel)
                .filter(Channel.last_checked_at.isnot(None))
                .count()
            )
            return {"n_sets": session.query(DJSet).count(), "stamped": stamped}

        out = _run_core(_seed, _read, api_key="KEY", deadline=100.0)
        stats, snap = out["stats"], out["snapshot"]

        # Exactly one channel processed; the loop broke cleanly before the second.
        assert stats["channels"] == 1
        assert stats["sets_created"] == 1
        assert stats["deadline_hit"] is True
        assert snap["n_sets"] == 1
        assert snap["stamped"] == 1  # only the processed channel was stamped

    def test_already_known_video_is_skipped(self, youtube_task, monkeypatch):
        _install_youtube_client_mocks(
            monkeypatch,
            feed_by_channel={"UC_boiler": [_video("VID_LONG", "Long set")]},
            durations={"VID_LONG": 3600},
        )

        def _seed(session):
            from models import DJSet

            _seed_channel(session, external_id="UC_boiler")
            # A youtube set already exists for this video → filtered out.
            session.add(
                DJSet(
                    external_id="VID_LONG",
                    source="youtube",
                    title="Long set",
                    created_at=_PUB,
                )
            )

        def _read(session):
            from models import DJSet

            return session.query(DJSet).filter_by(source="youtube").count()

        out = _run_core(_seed, _read, api_key="KEY", deadline=float("inf"))
        stats, snap = out["stats"], out["snapshot"]

        assert stats["channels"] == 1
        assert stats["videos_seen"] == 1
        assert stats["sets_created"] == 0  # the only video was already known
        assert snap == 1  # still just the pre-existing one

    def test_feed_http_error_skips_channel_without_stamping(
        self, youtube_task, monkeypatch
    ):
        from workers import youtube as yt

        async def _boom_feed(client, channel_id):
            if channel_id == "UC_bad":
                raise yt.YouTubeHTTPError(503, f"feed:{channel_id}")
            return [_video("VID_OK", "Good set")]

        async def _durations(client, video_ids, api_key):
            return {v: 3600 for v in video_ids}

        monkeypatch.setattr(yt, "fetch_channel_feed", _boom_feed)
        monkeypatch.setattr(yt, "fetch_video_durations", _durations)

        def _seed(session):
            # Both watched; the outage channel must not fail the other one.
            _seed_channel(session, external_id="UC_bad", name="Bad")
            _seed_channel(session, external_id="UC_good", name="Good")

        def _read(session):
            from models import Channel

            bad = session.query(Channel).filter_by(external_id="UC_bad").one()
            good = session.query(Channel).filter_by(external_id="UC_good").one()
            return {
                "bad_stamped": bad.last_checked_at is not None,
                "good_stamped": good.last_checked_at is not None,
            }

        out = _run_core(_seed, _read, api_key="KEY", deadline=float("inf"))
        stats, snap = out["stats"], out["snapshot"]

        # The outage channel is skipped (not counted, not stamped); the other runs.
        assert stats["channels"] == 1
        assert stats["sets_created"] == 1
        assert snap["bad_stamped"] is False  # outage → NOT stamped, retried later
        assert snap["good_stamped"] is True

    def test_excluded_and_unwatched_channels_are_ignored(
        self, youtube_task, monkeypatch
    ):
        _install_youtube_client_mocks(
            monkeypatch,
            feed_by_channel={"UC_ok": [_video("VID_OK", "Set")]},
            durations={"VID_OK": 3600},
        )

        def _seed(session):
            _seed_channel(session, external_id="UC_ok", name="Watched")
            _seed_channel(
                session, external_id="UC_excl", name="Excluded", excluded=True
            )
            _seed_channel(
                session, external_id="UC_off", name="Unwatched", watched=False
            )
            # A watched channel with no resolved external_id must be skipped too.
            _seed_channel(session, external_id=None, name="Unresolved")

        out = _run_core(
            _seed, lambda s: None, api_key="KEY", deadline=float("inf")
        )
        stats = out["stats"]

        assert stats["channels"] == 1  # only the single watched, resolved channel
        assert stats["sets_created"] == 1
