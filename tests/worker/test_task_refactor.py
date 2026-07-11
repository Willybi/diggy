"""
Tests for the refactored workers/tasks/ package.
Covers failure scenarios, orchestration fan-out, retry behavior,
and import compatibility.
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call
import importlib

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Artist,
    ArtistAlias,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetTrack,
    User,
    UserFollow,
    WatchedEntity,
)
from utils import make_normalized_key, normalize

# Path so workers package is importable in tests
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# Mock infra that isn't available outside Docker
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "requests",
    "workers.celery_app",
]
_mocks = {}
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        _mocks[_mod] = MagicMock()
        sys.modules[_mod] = _mocks[_mod]

# Make celery_app.celery_app a proper mock with .task() returning a decorator
_celery_mock = MagicMock()
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
        # called without arguments: @celery_app.task
        fn = args[0]
        fn.name = getattr(fn, "__name__", "")
        fn.autoretry_for = ()
        fn.bind = False
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    return decorator

_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)


# ── Import compatibility ──────────────────────────────────────────────


class TestImportCompatibility:
    """Ensure re-exports from workers.tasks are compatible with existing code."""

    def _import_tasks(self):
        # Force a fresh import by cleaning up cached modules
        mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
        for m in mods_to_clear:
            del sys.modules[m]
        import workers.tasks as wt
        return wt

    def test_package_has_all_13_tasks(self):
        wt = self._import_tasks()
        expected = [
            "crawl_radar", "crawl_single_playlist",
            "enrich_catalog", "enrich_catalog_beatport",
            "resolve_set_tracks", "enrich_set_tracks", "recrawl_incomplete_sets",
            "sync_artists", "fetch_artist_artworks", "link_set_artists",
            "reclassify_genres_chunk", "reclassify_all_genres",
            "compute_trends",
        ]
        for name in expected:
            assert hasattr(wt, name), f"workers.tasks.{name} not found"

    def test_all_tasks_have_explicit_name(self):
        """All tasks must have explicit name= to preserve beat schedule compatibility."""
        wt = self._import_tasks()
        expected_prefix = "workers.tasks."
        task_names = [
            "crawl_radar", "crawl_single_playlist",
            "enrich_catalog", "enrich_catalog_beatport",
            "resolve_set_tracks", "enrich_set_tracks", "recrawl_incomplete_sets",
            "sync_artists", "fetch_artist_artworks", "link_set_artists",
            "reclassify_genres_chunk", "reclassify_all_genres", "compute_trends",
        ]
        for tname in task_names:
            task = getattr(wt, tname)
            assert task.name.startswith(expected_prefix), (
                f"Task {task.name} must start with '{expected_prefix}'"
            )

    def test_submodule_exports_match_package_exports(self):
        """Tasks imported from submodules must match re-exports from package."""
        wt = self._import_tasks()
        import workers.tasks.radar as radar
        import workers.tasks.catalog as catalog
        import workers.tasks.sets as sets_mod
        import workers.tasks.artists as artists
        import workers.tasks.genres as genres
        import workers.tasks.trends as trends

        assert wt.crawl_radar is radar.crawl_radar
        assert wt.enrich_catalog is catalog.enrich_catalog
        assert wt.resolve_set_tracks is sets_mod.resolve_set_tracks
        assert wt.sync_artists is artists.sync_artists
        assert wt.reclassify_genres_chunk is genres.reclassify_genres_chunk
        assert wt.compute_trends is trends.compute_trends


# ── Retry policy verification ─────────────────────────────────────────


class TestRetryPolicies:
    """Verify retry configuration on all tasks."""

    def _get_tasks(self):
        mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
        for m in mods_to_clear:
            del sys.modules[m]
        import workers.tasks as wt
        return wt

    def test_non_orchestrators_have_autoretry(self):
        wt = self._get_tasks()
        non_orchestrators = [
            "crawl_single_playlist",
            "enrich_catalog", "enrich_catalog_beatport",
            "resolve_set_tracks", "enrich_set_tracks", "recrawl_incomplete_sets",
            "sync_artists", "fetch_artist_artworks", "link_set_artists",
            "reclassify_genres_chunk", "compute_trends",
        ]
        for tname in non_orchestrators:
            task = getattr(wt, tname)
            assert task.autoretry_for, (
                f"Task {task.name} should have autoretry_for set"
            )
            assert Exception in task.autoretry_for, (
                f"Task {task.name} should autoretry on Exception"
            )

    def test_all_tasks_are_bound(self):
        wt = self._get_tasks()
        for tname in [
            "crawl_radar", "crawl_single_playlist",
            "enrich_catalog", "enrich_catalog_beatport",
            "resolve_set_tracks", "enrich_set_tracks", "recrawl_incomplete_sets",
            "sync_artists", "fetch_artist_artworks", "link_set_artists",
            "reclassify_genres_chunk", "reclassify_all_genres", "compute_trends",
        ]:
            task = getattr(wt, tname)
            assert task.bind is True, f"Task {task.name} should be bind=True"

    def test_task_names_match_beat_schedule_format(self):
        """Beat schedule references tasks by name; verify all match expected format."""
        wt = self._get_tasks()
        expected_names = {
            "crawl_radar": "workers.tasks.crawl_radar",
            "recrawl_incomplete_sets": "workers.tasks.recrawl_incomplete_sets",
            "enrich_catalog": "workers.tasks.enrich_catalog",
            "enrich_catalog_beatport": "workers.tasks.enrich_catalog_beatport",
            "compute_trends": "workers.tasks.compute_trends",
        }
        for attr, expected_name in expected_names.items():
            task = getattr(wt, attr)
            assert task.name == expected_name, (
                f"Expected {attr}.name == '{expected_name}', got '{task.name}'"
            )


# ── Time limits vs broker visibility_timeout ──────────────────────────


def _read_visibility_timeout():
    """Parse visibility_timeout from celery_app.py source.

    workers.celery_app is mocked in this test env, so the value is read
    from source instead of the imported module.
    """
    import re

    path = os.path.join(_SERVER_PATH, "workers", "celery_app.py")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"\"visibility_timeout\":\s*(\d+)", source)
    return int(match.group(1)) if match else None


class TestTimeLimits:
    """Long tasks must finish before the broker re-delivers them.

    Redis re-delivers unacked tasks after visibility_timeout; with
    task_acks_late=True a task outliving it runs twice concurrently
    (root cause of the 2026-07-08 enrich_beatport deadlocks).
    """

    def _get_tasks(self):
        mods_to_clear = [k for k in sys.modules if k.startswith("workers.tasks")]
        for m in mods_to_clear:
            del sys.modules[m]
        import workers.tasks as wt
        return wt

    def test_visibility_timeout_is_configured(self):
        assert _read_visibility_timeout() is not None, (
            "broker_transport_options visibility_timeout missing from celery_app.py"
        )

    def test_resolve_set_tracks_has_dedicated_limits(self):
        """Inline enrichment after big imports needs more than the global 1800s."""
        wt = self._get_tasks()
        assert wt.resolve_set_tracks.soft_time_limit == 7200
        assert wt.resolve_set_tracks.time_limit == 7500

    def test_enrich_catalog_beatport_keeps_long_limits(self):
        wt = self._get_tasks()
        assert wt.enrich_catalog_beatport.soft_time_limit == 25200
        assert wt.enrich_catalog_beatport.time_limit == 28800

    def test_recrawl_incomplete_sets_has_dedicated_limits(self):
        wt = self._get_tasks()
        assert wt.recrawl_incomplete_sets.soft_time_limit == 3600
        assert wt.recrawl_incomplete_sets.time_limit == 3900

    def test_all_task_time_limits_below_visibility_timeout(self):
        visibility_timeout = _read_visibility_timeout()
        wt = self._get_tasks()
        task_names = [
            "crawl_radar", "crawl_single_playlist",
            "enrich_catalog", "enrich_catalog_beatport",
            "resolve_set_tracks", "enrich_set_tracks", "recrawl_incomplete_sets",
            "sync_artists", "fetch_artist_artworks", "link_set_artists",
            "reclassify_genres_chunk", "reclassify_all_genres", "compute_trends",
        ]
        for tname in task_names:
            task = getattr(wt, tname)
            time_limit = task.time_limit
            if time_limit is None:
                # Falls back to the global CELERY_TIME_LIMIT default (3600)
                time_limit = 3600
            assert time_limit < visibility_timeout, (
                f"Task {tname} time_limit={time_limit} >= visibility_timeout="
                f"{visibility_timeout}: the broker would re-deliver it mid-run"
            )


# crawl_followed_sets eligibility tests removed with the task (C6.b): the
# replacement recrawl_incomplete_sets is covered in test_tasks_recrawl_sets.py


# ── link_set_artists logic ────────────────────────────────────────────


def _link_set_artists(session):
    """Replicate core matching logic of link_set_artists."""
    norm_to_id = {}
    for a in session.execute(select(Artist)).scalars().all():
        norm_to_id[normalize(a.name)] = a.id
    for al in session.execute(select(ArtistAlias)).scalars().all():
        if al.normalized_alias not in norm_to_id:
            norm_to_id[al.normalized_alias] = al.artist_id

    sorted_names = sorted(norm_to_id.keys(), key=len, reverse=True)
    sets = session.execute(select(DJSet)).scalars().all()
    linked = 0
    skipped = 0

    for dj_set in sets:
        title = dj_set.title or ""
        is_b2b = "b2b" in title.lower()
        matched_ids = set()
        title_norm = normalize(title)
        title_norm_clean = title_norm.replace("_", " ")

        for norm_name in sorted_names:
            if len(norm_name) < 3:
                continue
            if norm_name in title_norm or norm_name in title_norm_clean:
                aid = norm_to_id[norm_name]
                if aid not in matched_ids:
                    matched_ids.add(aid)

        existing = {
            r[0] for r in session.execute(
                select(SetArtist.artist_id).where(SetArtist.set_id == dj_set.id)
            ).all()
        }

        for aid in matched_ids:
            if aid in existing:
                skipped += 1
                continue
            role = "b2b" if is_b2b else "dj"
            session.add(SetArtist(set_id=dj_set.id, artist_id=aid, role=role, position=0))
            linked += 1

        session.commit()

    return {"linked": linked, "skipped": skipped}


class TestLinkSetArtistsAdditional:
    def test_underscore_title_matching(self, sync_session):
        """Artist names in underscore-separated titles should be matched."""
        s = sync_session
        a = Artist(name="Moderat", normalized_name="moderat")
        s.add(a)
        dj = DJSet(source="trackid", title="Moderat_Live_at_Coachella")
        s.add(dj)
        s.commit()
        result = _link_set_artists(s)
        assert result["linked"] == 1

    def test_no_artists_no_link(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Unknown DJ at a party")
        s.add(dj)
        s.commit()
        result = _link_set_artists(s)
        assert result["linked"] == 0

    def test_multiple_sets_independent_linking(self, sync_session):
        s = sync_session
        a1 = Artist(name="ANNA", normalized_name="anna")
        a2 = Artist(name="Moderat", normalized_name="moderat")
        s.add_all([a1, a2])
        dj1 = DJSet(source="trackid", title="ANNA at Berghain")
        dj2 = DJSet(source="trackid", title="Moderat Live")
        s.add_all([dj1, dj2])
        s.commit()
        result = _link_set_artists(s)
        assert result["linked"] == 2

    def test_idempotent_on_double_run(self, sync_session):
        s = sync_session
        a = Artist(name="ANNA", normalized_name="anna")
        s.add(a)
        dj = DJSet(source="trackid", title="ANNA at Club")
        s.add(dj)
        s.commit()
        r1 = _link_set_artists(s)
        r2 = _link_set_artists(s)
        assert r1["linked"] == 1
        assert r2["linked"] == 0
        assert r2["skipped"] == 1


# ── resolve_set_tracks core logic ─────────────────────────────────────


def _resolve_set_tracks(session):
    """Replicate core logic of resolve_set_tracks (no Celery)."""
    resolved = 0
    tracks = session.execute(
        select(SetTrack).where(
            SetTrack.catalog_id.is_(None),
            SetTrack.is_id == False,  # noqa: E712
            SetTrack.raw_title.isnot(None),
        )
    ).scalars().all()

    if not tracks:
        return {"resolved": 0}

    track_dicts = [{"title": st.raw_title, "artist": st.raw_artist} for st in tracks]

    # Simple inline version of bulk_get_or_create_catalog
    for st in tracks:
        nk = make_normalized_key(st.raw_title, st.raw_artist)
        entry = session.execute(
            select(CatalogEntry).where(CatalogEntry.normalized_key == nk)
        ).scalar_one_or_none()
        if not entry:
            entry = CatalogEntry(
                title=st.raw_title, artist=st.raw_artist, normalized_key=nk
            )
            session.add(entry)
            session.flush()
        st.catalog_id = entry.id
        resolved += 1

    session.commit()
    return {"resolved": resolved}


class TestResolveSetTracksAdditional:
    def test_empty_set_tracks_returns_zero(self, sync_session):
        result = _resolve_set_tracks(sync_session)
        assert result["resolved"] == 0

    def test_is_id_tracks_skipped(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="S")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="ID", raw_artist="ID", is_id=True))
        s.commit()
        result = _resolve_set_tracks(s)
        assert result["resolved"] == 0

    def test_already_resolved_tracks_skipped(self, sync_session):
        s = sync_session
        cat = CatalogEntry(
            title="Cola", artist="CamelPhat",
            normalized_key=make_normalized_key("Cola", "CamelPhat")
        )
        s.add(cat)
        dj = DJSet(source="trackid", title="S")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola",
                       raw_artist="CamelPhat", catalog_id=cat.id))
        s.commit()
        result = _resolve_set_tracks(s)
        assert result["resolved"] == 0

    def test_resolves_to_existing_catalog_entry(self, sync_session):
        s = sync_session
        nk = make_normalized_key("Cola", "CamelPhat")
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key=nk)
        s.add(cat)
        dj = DJSet(source="trackid", title="S")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()
        result = _resolve_set_tracks(s)
        assert result["resolved"] == 1
        track = s.execute(select(SetTrack)).scalar_one()
        assert track.catalog_id == cat.id


# ── _load_crawlable_playlists (C6.e: crawl the whole watchlist, no follow filter) ──


class TestLoadCrawlablePlaylists:
    def _radar(self):
        import workers.tasks.radar as radar_mod
        return radar_mod

    def _make_user(self, session):
        u = User(email="x@x.com", username="x", google_id="gx", is_active=True)
        session.add(u)
        session.flush()
        return u

    def _make_entity(self, session, external_id="dz-1", last_crawled_at=None):
        e = WatchedEntity(
            external_id=external_id,
            source="deezer",
            title="PL",
            last_crawled_at=last_crawled_at,
        )
        session.add(e)
        session.flush()
        return e

    def test_followed_playlist_is_returned(self, sync_session):
        s = sync_session
        u = self._make_user(s)
        e = self._make_entity(
            s, last_crawled_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        )
        s.add(UserFollow(user_id=u.id, entity_id=e.id,
                         followed_at=datetime.now(timezone.utc)))
        s.commit()

        playlists = self._radar()._load_crawlable_playlists(s)

        assert len(playlists) == 1
        pl = playlists[0]
        assert set(pl) == {
            "id", "source", "external_id", "last_crawled_at",
            "has_followers", "last_changed_at", "created_at",
        }
        assert pl["id"] == e.id
        assert pl["source"] == "deezer"
        assert pl["external_id"] == "dz-1"
        assert pl["has_followers"] is True
        # ISO string, same contract as the former HTTP JSON payload
        assert isinstance(pl["last_crawled_at"], str)
        assert pl["last_crawled_at"].startswith("2026-07-01T12:00:00")

    def test_unfollowed_playlist_is_returned_with_flag(self, sync_session):
        """C6.e: an orphan playlist (no follower) is now crawled too, flagged
        has_followers=False (used only as a crawl-priority signal)."""
        s = sync_session
        u = self._make_user(s)
        followed = self._make_entity(s, external_id="dz-followed")
        self._make_entity(s, external_id="dz-orphan")
        s.add(UserFollow(user_id=u.id, entity_id=followed.id,
                         followed_at=datetime.now(timezone.utc)))
        s.commit()

        playlists = self._radar()._load_crawlable_playlists(s)

        by_ext = {pl["external_id"]: pl for pl in playlists}
        assert set(by_ext) == {"dz-followed", "dz-orphan"}
        assert by_ext["dz-followed"]["has_followers"] is True
        assert by_ext["dz-orphan"]["has_followers"] is False

    def test_never_crawled_playlist_has_none_last_crawled_at(self, sync_session):
        s = sync_session
        self._make_entity(s, last_crawled_at=None)
        s.commit()

        playlists = self._radar()._load_crawlable_playlists(s)

        # returned even without any follower, last_crawled_at kept as None
        assert playlists[0]["last_crawled_at"] is None
        assert playlists[0]["has_followers"] is False


# ── _crawl_decision (C6.e adaptive cadence) ─────────────────────────────────────


class TestCrawlDecision:
    NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    def _radar(self):
        import workers.tasks.radar as radar_mod
        return radar_mod

    def _decide(
        self, has_followers, changed_days_ago, crawled_days_ago,
        created_days_ago=None,
    ):
        def _ago(days):
            return self.NOW - timedelta(days=days) if days is not None else None

        return self._radar()._crawl_decision(
            self.NOW,
            has_followers,
            _ago(changed_days_ago),
            _ago(created_days_ago),
            _ago(crawled_days_ago),
        )

    def test_followed_stable_90d_keeps_daily_floor(self):
        # followed → daily floor whatever the stability age; effective threshold
        # is 0.75d (min_days 1.0 − CADENCE_SLACK_DAYS)
        assert self._decide(True, 90, 19 / 24) == "crawl"
        assert self._decide(True, 90, 17 / 24) == "wait"

    def test_unfollowed_changed_5d_is_daily(self):
        # daily tier, effective threshold 0.75d (1.0 − slack)
        assert self._decide(False, 5, 19 / 24) == "crawl"
        assert self._decide(False, 5, 17 / 24) == "wait"

    def test_unfollowed_changed_30d_is_weekly(self):
        assert self._decide(False, 30, 8) == "crawl"
        assert self._decide(False, 30, 6) == "wait"

    def test_unfollowed_changed_90d_is_monthly(self):
        assert self._decide(False, 90, 31) == "crawl"
        assert self._decide(False, 90, 29) == "wait"

    def test_never_crawled_is_due(self):
        assert self._decide(False, 5, None) == "crawl"
        assert self._decide(True, None, None, created_days_ago=1) == "crawl"

    def test_no_stability_reference_is_due(self):
        # unfollowed, last_changed_at AND created_at both None → always crawl
        assert self._decide(False, None, 100) == "crawl"

    def test_created_at_used_when_never_changed(self):
        # no last_changed_at → stability age falls back to created_at (weekly)
        assert self._decide(False, None, 8, created_days_ago=30) == "crawl"
        assert self._decide(False, None, 6, created_days_ago=30) == "wait"

    def test_naive_datetimes_accepted(self):
        """SQLite returns naive datetimes; they must be treated as UTC."""
        changed = (self.NOW - timedelta(days=5)).replace(tzinfo=None)
        crawled = (self.NOW - timedelta(days=2)).replace(tzinfo=None)
        assert self._radar()._crawl_decision(
            self.NOW, False, changed, None, crawled
        ) == "crawl"

    def test_nightly_beat_scenario_just_under_24h_is_due(self):
        """Beat fires 24h apart but last_crawled_at is stamped at crawl END:
        a playlist crawled last night (~23h55) must stay due, not wait a whole
        extra day. This is exactly what CADENCE_SLACK_DAYS protects against."""
        assert self._decide(True, 90, 1 - 5 / 1440) == "crawl"


# ── _select_crawl_batch (C6.e cadence filter + priority sort + cap) ─────────────


class TestSelectCrawlBatch:
    NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    def _radar(self):
        import workers.tasks.radar as radar_mod
        return radar_mod

    def _pl(
        self, pid, *, has_followers=False, changed_days_ago=None,
        created_days_ago=1.0, crawled_days_ago=None,
    ):
        def _ago(days):
            return self.NOW - timedelta(days=days) if days is not None else None

        crawled = _ago(crawled_days_ago)
        return {
            "id": pid,
            "source": "deezer",
            "external_id": f"ext-{pid}",
            "last_crawled_at": crawled.isoformat() if crawled else None,
            "has_followers": has_followers,
            "last_changed_at": _ago(changed_days_ago),
            "created_at": _ago(created_days_ago),
        }

    def test_wait_playlists_dropped_from_batch(self):
        wait = self._pl(1, has_followers=True, crawled_days_ago=0.5)  # <1d → wait
        due = self._pl(2, has_followers=True, crawled_days_ago=2.0)
        batch, skipped_cadence, dropped = self._radar()._select_crawl_batch(
            [wait, due], self.NOW, 200
        )
        assert [pl["id"] for pl in batch] == [2]
        assert skipped_cadence == 1
        assert dropped == 0

    def test_cap_keeps_followed_over_recent_orphan(self):
        # cap 1: a followed playlist wins the slot even though the unfollowed
        # one changed more recently
        followed = self._pl(
            1, has_followers=True, changed_days_ago=10, crawled_days_ago=5
        )
        recent_orphan = self._pl(
            2, has_followers=False, changed_days_ago=1, crawled_days_ago=5
        )
        batch, skipped_cadence, dropped = self._radar()._select_crawl_batch(
            [recent_orphan, followed], self.NOW, 1
        )
        assert [pl["id"] for pl in batch] == [1]
        assert dropped == 1
        assert skipped_cadence == 0

    def test_recency_orders_within_same_follower_status(self):
        older = self._pl(
            1, has_followers=False, changed_days_ago=10, crawled_days_ago=5
        )
        newer = self._pl(
            2, has_followers=False, changed_days_ago=2, crawled_days_ago=5
        )
        batch, _, _ = self._radar()._select_crawl_batch(
            [older, newer], self.NOW, 200
        )
        assert [pl["id"] for pl in batch] == [2, 1]


# ── _is_initial_crawl (C6.e trend-velocity guard on reawakened playlists) ───────


class TestIsInitialCrawl:
    NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    def _radar(self):
        import workers.tasks.radar as radar_mod
        return radar_mod

    def test_never_crawled_is_initial(self):
        assert self._radar()._is_initial_crawl(None, self.NOW) is True

    def test_dormant_over_30d_is_initial(self):
        assert self._radar()._is_initial_crawl(
            self.NOW - timedelta(days=40), self.NOW
        ) is True

    def test_recent_crawl_is_not_initial(self):
        assert self._radar()._is_initial_crawl(
            self.NOW - timedelta(days=10), self.NOW
        ) is False

    def test_naive_datetime_accepted(self):
        naive = (self.NOW - timedelta(days=40)).replace(tzinfo=None)
        assert self._radar()._is_initial_crawl(naive, self.NOW) is True
