"""Tests for the C14.b auto-link task (workers/tasks/channels).

Two session types, same conventions as test_tasks_youtube.py:

  * the single-instance Redis lock in the task WRAPPER (SET NX EX + conditional
    release) — driven with a celery/redis sys.modules mock harness (celery is not
    installed in the test env), ``_run_autolink_official_channels`` stubbed;
  * the async CORE ``_autolink_channels`` — driven end-to-end over an OWN in-memory
    aiosqlite engine (StaticPool) via ``asyncio.run``, with the Deezer-id resolver
    (:func:`workers.artist_channel_resolve.resolve_channel_by_deezer_id`) STUBBED
    and a dict-backed fake Redis, so we exercise cohort selection + idempotent
    channel upsert + the per-run cap + the Redis dedup against a real DB.

The clock for the AV9 deadline test is faked by replacing the task module's
``time`` attribute (never the global — asyncio's loop reads ``time.monotonic``
internally and would consume the fake sequence; the AV9 pitfall). Parallel-safe:
each test builds its own engine; no shared module state is mutated beyond
monkeypatch (auto-restored).
"""
import asyncio
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


# _run_autolink_official_channels does `from celery.exceptions import
# SoftTimeLimitExceeded` and uses it in an `except` — needs a real Exception
# subclass, not a MagicMock attribute (same technique as test_tasks_youtube).
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
def channels_task(monkeypatch):
    """Import the real task module with celery mocked (fresh workers.tasks init)."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.tasks.channels as channels_task

    return channels_task


# ── Task wrapper: single-instance Redis lock ──────────────────────────────────


@pytest.fixture
def lock_redis(monkeypatch):
    """Controllable redis client; defaults acquire + cleanly release the lock."""
    client = MagicMock()
    client.set.return_value = True
    client.get.return_value = "task-al"
    redis_mod = MagicMock()
    redis_mod.from_url.return_value = client
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    return client


@pytest.fixture
def lock_self():
    task_self = MagicMock()
    task_self.request.id = "task-al"
    return task_self


class TestAutolinkChannelsLock:
    """Same SET NX EX + conditional-release pattern as the other crawl tasks."""

    def test_skips_when_lock_held(
        self, channels_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock()
        monkeypatch.setattr(channels_task, "_run_autolink_official_channels", run)
        lock_redis.set.return_value = False  # nx=True: lock already held
        lock_redis.get.return_value = "task-other"

        result = channels_task.autolink_official_channels(lock_self)

        assert result == {"skipped": "already_running", "holder": "task-other"}
        run.assert_not_called()
        lock_redis.delete.assert_not_called()

    def test_acquires_runs_and_releases(
        self, channels_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock(return_value={"created": 3})
        monkeypatch.setattr(channels_task, "_run_autolink_official_channels", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-al"  # still owns the lock

        result = channels_task.autolink_official_channels(lock_self)

        assert result == {"created": 3}
        run.assert_called_once_with(lock_self)
        _, kwargs = lock_redis.set.call_args
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == channels_task.CHANNEL_AUTOLINK_LOCK_TTL
        lock_redis.delete.assert_called_once_with("lock:autolink_official_channels")

    def test_does_not_release_lock_it_no_longer_owns(
        self, channels_task, lock_redis, lock_self, monkeypatch
    ):
        run = MagicMock(return_value={})
        monkeypatch.setattr(channels_task, "_run_autolink_official_channels", run)
        lock_redis.set.return_value = True
        lock_redis.get.return_value = "task-newer"  # someone else owns it now

        channels_task.autolink_official_channels(lock_self)

        lock_redis.delete.assert_not_called()

    def test_lock_ttl_strictly_covers_time_limit(self, channels_task):
        # The TTL must exceed the hard time_limit so the lock can't expire mid-run;
        # both must reference the shared module constants (one source of truth).
        assert (
            channels_task.CHANNEL_AUTOLINK_LOCK_TTL
            > channels_task.CHANNEL_AUTOLINK_TIME_LIMIT
        )
        assert (
            channels_task.autolink_official_channels.soft_time_limit
            == channels_task.CHANNEL_AUTOLINK_SOFT_TIME_LIMIT
        )
        assert (
            channels_task.autolink_official_channels.time_limit
            == channels_task.CHANNEL_AUTOLINK_TIME_LIMIT
        )
        # No autoretry (SoftTimeLimitExceeded IS an Exception).
        assert channels_task.autolink_official_channels.autoretry_for == ()
        # Margin leaves an actual working window.
        assert (
            0
            < channels_task.CHANNEL_AUTOLINK_DEADLINE_MARGIN
            < channels_task.CHANNEL_AUTOLINK_SOFT_TIME_LIMIT
        )


# ── Async core: _autolink_channels over an in-memory aiosqlite engine ─────────


class _FakeRedis:
    """Dict-backed sync Redis stand-in (decode_responses semantics: str values)."""

    def __init__(self, preset=None):
        self.store = dict(preset or {})
        self.set_calls = []

    def mget(self, keys):
        return [self.store.get(k) for k in keys]

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.set_calls.append((key, value, ex))
        return True


class _FakeClock:
    """Deterministic time.monotonic stand-in (same shape as test_tasks_youtube):
    pops the sequence one call at a time, then keeps returning the last value."""

    def __init__(self, values):
        self._values = list(values)

    def monotonic(self):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


def _make_resolve(hit_map, *, calls=None):
    """Async stub for resolve_channel_by_deezer_id: returns a hit dict for every id
    present in ``hit_map`` ({deezer_id: (channel_id, title)}), else absent."""

    async def _resolve(ids, *, wiki_client, yt_client, api_key):
        if calls is not None:
            calls.append(list(ids))
        out = {}
        for d in ids:
            if d in hit_map:
                cid, title = hit_map[d]
                out[d] = {
                    "channel_id": cid,
                    "channel_title": title,
                    "url": f"https://www.youtube.com/channel/{cid}",
                    "method": "wikidata_deezer",
                    "confidence": "high",
                }
        return out

    return _resolve


def _seed_artist(session, *, aid, name, deezer_id):
    from models import Artist

    session.add(
        Artist(id=aid, name=name, normalized_name=name.lower(), deezer_id=deezer_id)
    )


def _seed_cohort(session, *, aid, tier=1, excluded=False):
    from models import ArtistCohort

    session.add(ArtistCohort(artist_id=aid, tier=tier, excluded=excluded))


def _seed_channel(
    session, *, external_id, name="Existing", artist_id=None, watched=True,
    excluded=False,
):
    from models import Channel

    session.add(
        Channel(
            platform="youtube",
            external_id=external_id,
            name=name,
            artist_id=artist_id,
            watched=watched,
            excluded=excluded,
        )
    )


def _run_core(
    monkeypatch,
    *,
    seed_fn,
    read_fn,
    resolve_stub,
    fake_redis,
    api_key="KEY",
    deadline=float("inf"),
    max_per_run=200,
    fake_clock=None,
):
    """Own in-memory aiosqlite engine (StaticPool → one shared conn), schema
    created, ``seed_fn(session)`` seeded, ``_autolink_channels`` run against it with
    the resolver stubbed + a fake Redis, then ``read_fn(session)`` snapshotted — ALL
    under a SINGLE event loop (the StaticPool aiosqlite connection is bound to its
    creating loop). Returns ``{"stats", "snapshot"}`` (mirrors test_tasks_youtube)."""
    import workers.artist_channel_resolve as acr
    import workers.tasks.channels as channels_task
    from database import Base
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    monkeypatch.setattr(acr, "resolve_channel_by_deezer_id", resolve_stub)
    if fake_clock is not None:
        monkeypatch.setattr(channels_task, "time", fake_clock)

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

        stats = await channels_task._autolink_channels(
            factory,
            fake_redis,
            object(),
            object(),
            api_key=api_key,
            deadline=deadline,
            max_per_run=max_per_run,
        )

        async with factory() as db:
            snapshot = await db.run_sync(read_fn)

        await engine.dispose()
        return {"stats": stats, "snapshot": snapshot}

    return asyncio.run(_go())


def _dedup_key(deezer_id):
    return f"yt:autolink:deezer:{deezer_id}"


class TestAutolinkChannelsCore:
    def test_creates_channels_for_hits(self, channels_task, monkeypatch):
        def _seed(session):
            _seed_artist(session, aid=1, name="Peggy Gou", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)
            _seed_artist(session, aid=2, name="Adam Beyer", deezer_id="d2")
            _seed_cohort(session, aid=2, tier=2)

        def _read(session):
            from models import Channel

            rows = session.query(Channel).order_by(Channel.artist_id).all()
            return [
                {
                    "external_id": r.external_id,
                    "artist_id": r.artist_id,
                    "watched": r.watched,
                    "channel_type": r.channel_type,
                    "name": r.name,
                    "signals": r.signals,
                }
                for r in rows
            ]

        fake_redis = _FakeRedis()
        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve(
                {"d1": ("UC1", "Peggy Gou"), "d2": ("UC2", "Adam Beyer")}
            ),
            fake_redis=fake_redis,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["candidates"] == 2
        assert stats["pending"] == 2
        assert stats["resolved"] == 2
        assert stats["created"] == 2
        assert {r["external_id"] for r in snap} == {"UC1", "UC2"}
        for r in snap:
            assert r["watched"] is True
            assert r["channel_type"] == "artist"
            assert r["signals"]["method"] == "wikidata_deezer"
        # Both resolutions were cached for dedup.
        assert fake_redis.get(_dedup_key("d1")) is not None
        assert fake_redis.get(_dedup_key("d2")) is not None

    def test_filters_ineligible_candidates(self, channels_task, monkeypatch):
        resolve_calls = []

        def _seed(session):
            # Eligible.
            _seed_artist(session, aid=10, name="Ok", deezer_id="ok")
            _seed_cohort(session, aid=10, tier=1)
            # Excluded cohort row → filtered.
            _seed_artist(session, aid=11, name="Excl", deezer_id="ex")
            _seed_cohort(session, aid=11, tier=1, excluded=True)
            # No deezer_id → filtered.
            _seed_artist(session, aid=12, name="NoDz", deezer_id=None)
            _seed_cohort(session, aid=12, tier=1)
            # NOT_FOUND sentinel → filtered.
            _seed_artist(session, aid=13, name="NF", deezer_id="NOT_FOUND")
            _seed_cohort(session, aid=13, tier=1)
            # Already curated (a channel already linked to this artist) → filtered.
            _seed_artist(session, aid=14, name="Cur", deezer_id="cur")
            _seed_cohort(session, aid=14, tier=1)
            _seed_channel(session, external_id="UCcur", artist_id=14)
            # Not in the cohort at all → filtered (no artist_cohort row).
            _seed_artist(session, aid=15, name="Outsider", deezer_id="out")

        def _read(session):
            from models import Channel

            new = (
                session.query(Channel)
                .filter(Channel.external_id != "UCcur")
                .all()
            )
            return {"new_ext": sorted(r.external_id for r in new)}

        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve(
                {
                    "ok": ("UCok", "Ok"),
                    "ex": ("UCex", "Excl"),
                    "cur": ("UCcur2", "Cur"),
                    "out": ("UCout", "Outsider"),
                },
                calls=resolve_calls,
            ),
            fake_redis=_FakeRedis(),
        )
        stats, snap = out["stats"], out["snapshot"]

        # Only the single eligible artist is a candidate / resolved / created.
        assert stats["candidates"] == 1
        assert stats["created"] == 1
        assert snap["new_ext"] == ["UCok"]
        # The resolver was only ever asked about the eligible id.
        assert resolve_calls == [["ok"]]

    def test_cap_limits_created_and_leaves_overflow_untried(
        self, channels_task, monkeypatch
    ):
        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)
            _seed_artist(session, aid=2, name="A2", deezer_id="d2")
            _seed_cohort(session, aid=2, tier=1)

        def _read(session):
            from models import Channel

            return sorted(r.external_id for r in session.query(Channel).all())

        fake_redis = _FakeRedis()
        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve(
                {"d1": ("UC1", "A1"), "d2": ("UC2", "A2")}
            ),
            fake_redis=fake_redis,
            max_per_run=1,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["created"] == 1
        assert snap == ["UC1"]  # the first (lower-id) artist wins the single slot
        # The overflow HIT is left un-marked so a later run creates its channel.
        assert fake_redis.get(_dedup_key("d1")) is not None
        assert fake_redis.get(_dedup_key("d2")) is None

    def test_max_per_run_zero_is_noop(self, channels_task, monkeypatch):
        resolve_calls = []

        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)

        def _read(session):
            from models import Channel

            return session.query(Channel).count()

        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1")}, calls=resolve_calls),
            fake_redis=_FakeRedis(),
            max_per_run=0,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats == {
            "candidates": 0,
            "pending": 0,
            "resolved": 0,
            "created": 0,
            "backfills_dispatched": 0,
            "deadline_hit": False,
        }
        assert snap == 0
        assert resolve_calls == []  # early no-op: nothing even loaded/resolved

    def test_dedup_skips_already_tried(self, channels_task, monkeypatch):
        resolve_calls = []

        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)

        def _read(session):
            from models import Channel

            return session.query(Channel).count()

        # d1 already has a dedup key (a prior miss) → skipped before any query.
        fake_redis = _FakeRedis(preset={_dedup_key("d1"): "none"})
        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1")}, calls=resolve_calls),
            fake_redis=fake_redis,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["candidates"] == 1
        assert stats["pending"] == 0
        assert stats["created"] == 0
        assert snap == 0
        assert resolve_calls == []  # the already-tried id is never re-queried

    def test_miss_is_cached(self, channels_task, monkeypatch):
        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)

        def _read(session):
            from models import Channel

            return session.query(Channel).count()

        fake_redis = _FakeRedis()
        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve({}),  # a miss (no hit returned)
            fake_redis=fake_redis,
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["resolved"] == 0
        assert stats["created"] == 0
        assert snap == 0
        # The definitive miss is cached so Wikidata is not re-queried next night.
        assert fake_redis.get(_dedup_key("d1")) == "none"

    def test_idempotent_existing_channel_links_artist(
        self, channels_task, monkeypatch
    ):
        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)
            # A channel row for the resolved id already exists, unlinked + unwatched.
            _seed_channel(
                session, external_id="UC1", name="Pre", artist_id=None,
                watched=False,
            )

        def _read(session):
            from models import Channel

            rows = session.query(Channel).all()
            r = rows[0]
            return {
                "count": len(rows),
                "artist_id": r.artist_id,
                "watched": r.watched,
                "name": r.name,
            }

        fake_redis = _FakeRedis()
        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1")}),
            fake_redis=fake_redis,
        )
        stats, snap = out["stats"], out["snapshot"]

        # No NEW row (created stays 0), but the existing row is linked + re-watched.
        assert stats["resolved"] == 1
        assert stats["created"] == 0
        assert snap["count"] == 1
        assert snap["artist_id"] == 1
        assert snap["watched"] is True
        assert snap["name"] == "Pre"  # existing name untouched
        assert fake_redis.get(_dedup_key("d1")) is not None

    def test_deadline_stops_before_first_batch(self, channels_task, monkeypatch):
        resolve_calls = []

        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1, tier=1)

        def _read(session):
            from models import Channel

            return session.query(Channel).count()

        # Deadline passed by the caller (100.0); the loop's first check reads 1e9
        # (>= 100 → break). Fake ONLY the module's `time` (never the global — the
        # event loop reads time.monotonic internally; AV9 pitfall).
        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=_read,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1")}, calls=resolve_calls),
            fake_redis=_FakeRedis(),
            deadline=100.0,
            fake_clock=_FakeClock([10**9]),
        )
        stats, snap = out["stats"], out["snapshot"]

        assert stats["deadline_hit"] is True
        assert stats["created"] == 0
        assert snap == 0
        assert resolve_calls == []  # broke before issuing any query


class TestAutolinkBackfillDispatch:
    """A created channel must also get its historical backfill (RSS = ~15 uploads)."""

    @staticmethod
    def _seed_two(session):
        _seed_artist(session, aid=1, name="A1", deezer_id="d1")
        _seed_cohort(session, aid=1)
        _seed_artist(session, aid=2, name="A2", deezer_id="d2")
        _seed_cohort(session, aid=2)

    @staticmethod
    def _read_ids(session):
        from models import Channel

        return sorted(r.id for r in session.query(Channel).all())

    def test_created_channels_get_a_staggered_backfill(
        self, channels_task, monkeypatch
    ):
        celery = MagicMock()
        monkeypatch.setattr(channels_task, "celery_app", celery)
        monkeypatch.setattr(channels_task, "CHANNEL_AUTOLINK_BACKFILL_STAGGER", 30)

        out = _run_core(
            monkeypatch,
            seed_fn=self._seed_two,
            read_fn=self._read_ids,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1"), "d2": ("UC2", "A2")}),
            fake_redis=_FakeRedis(),
        )
        stats, ids = out["stats"], out["snapshot"]

        assert stats["backfills_dispatched"] == 2
        calls = celery.send_task.call_args_list
        assert [c.args[0] for c in calls] == [
            "workers.tasks.backfill_youtube_channel"
        ] * 2
        assert [c.kwargs["args"] for c in calls] == [[ids[0]], [ids[1]]]
        assert [c.kwargs["countdown"] for c in calls] == [0, 30]

    def test_stagger_continues_across_batches(self, channels_task, monkeypatch):
        celery = MagicMock()
        monkeypatch.setattr(channels_task, "celery_app", celery)
        monkeypatch.setattr(channels_task, "CHANNEL_AUTOLINK_BATCH", 1)
        monkeypatch.setattr(channels_task, "CHANNEL_AUTOLINK_BACKFILL_STAGGER", 30)

        _run_core(
            monkeypatch,
            seed_fn=self._seed_two,
            read_fn=self._read_ids,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1"), "d2": ("UC2", "A2")}),
            fake_redis=_FakeRedis(),
        )

        countdowns = [c.kwargs["countdown"] for c in celery.send_task.call_args_list]
        assert countdowns == [0, 30]

    def test_existing_channel_is_not_backfilled(self, channels_task, monkeypatch):
        celery = MagicMock()
        monkeypatch.setattr(channels_task, "celery_app", celery)

        def _seed(session):
            _seed_artist(session, aid=1, name="A1", deezer_id="d1")
            _seed_cohort(session, aid=1)
            _seed_channel(session, external_id="UC1", artist_id=None)

        out = _run_core(
            monkeypatch,
            seed_fn=_seed,
            read_fn=self._read_ids,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1")}),
            fake_redis=_FakeRedis(),
        )

        assert out["stats"]["resolved"] == 1
        assert out["stats"]["backfills_dispatched"] == 0
        celery.send_task.assert_not_called()

    def test_dispatch_failure_does_not_fail_the_run(self, channels_task, monkeypatch):
        celery = MagicMock()
        celery.send_task.side_effect = ConnectionError("broker down")
        monkeypatch.setattr(channels_task, "celery_app", celery)

        out = _run_core(
            monkeypatch,
            seed_fn=self._seed_two,
            read_fn=self._read_ids,
            resolve_stub=_make_resolve({"d1": ("UC1", "A1"), "d2": ("UC2", "A2")}),
            fake_redis=_FakeRedis(),
        )

        assert out["stats"]["created"] == 2  # the channels are committed anyway
        assert len(out["snapshot"]) == 2
        assert out["stats"]["backfills_dispatched"] == 0
