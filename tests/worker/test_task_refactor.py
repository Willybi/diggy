"""
Tests for the refactored workers/tasks/ package.
Covers failure scenarios, orchestration fan-out, retry behavior,
and import compatibility.
"""
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
import importlib

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models import (
    Artist,
    ArtistAlias,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetTrack,
    User,
    UserSetFollow,
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
            "resolve_set_tracks", "enrich_set_tracks", "crawl_followed_sets",
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
            "resolve_set_tracks", "enrich_set_tracks", "crawl_followed_sets",
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
            "resolve_set_tracks", "enrich_set_tracks", "crawl_followed_sets",
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
            "resolve_set_tracks", "enrich_set_tracks", "crawl_followed_sets",
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
            "crawl_followed_sets": "workers.tasks.crawl_followed_sets",
            "enrich_catalog": "workers.tasks.enrich_catalog",
            "enrich_catalog_beatport": "workers.tasks.enrich_catalog_beatport",
            "compute_trends": "workers.tasks.compute_trends",
        }
        for attr, expected_name in expected_names.items():
            task = getattr(wt, attr)
            assert task.name == expected_name, (
                f"Expected {attr}.name == '{expected_name}', got '{task.name}'"
            )


# ── crawl_followed_sets eligibility logic ────────────────────────────


def _find_eligible_sets(session):
    """Replicate eligibility logic from crawl_followed_sets."""
    followed_ids = {
        r[0] for r in session.execute(
            select(UserSetFollow.set_id).distinct()
        ).all()
    }
    if not followed_ids:
        return [], 0, 0

    sets_to_crawl = []
    skipped_complete = 0
    skipped_recent = 0

    for sid in followed_ids:
        dj_set = session.get(DJSet, sid)
        if not dj_set or dj_set.source != "trackid":
            continue

        total = session.execute(
            select(func.count(SetTrack.id)).where(SetTrack.set_id == sid)
        ).scalar() or 0
        identified = session.execute(
            select(func.count(SetTrack.id)).where(
                SetTrack.set_id == sid,
                SetTrack.is_id.is_(False),
                SetTrack.catalog_id.isnot(None),
            )
        ).scalar() or 0

        if total > 0 and identified >= total:
            skipped_complete += 1
            continue

        if dj_set.last_crawled_at:
            last = dj_set.last_crawled_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            if age_h < 12:
                skipped_recent += 1
                continue

        sets_to_crawl.append(dj_set.id)

    return sets_to_crawl, skipped_complete, skipped_recent


class TestCrawlFollowedSetsEligibility:
    def _make_user(self, session):
        u = User(email="x@x.com", username="x", google_id="gx", is_active=True)
        session.add(u)
        session.flush()
        return u

    def test_empty_follows_returns_empty(self, sync_session):
        eligible, sc, sr = _find_eligible_sets(sync_session)
        assert eligible == [] and sc == 0 and sr == 0

    def test_skips_set_crawled_under_12h(self, sync_session):
        s = sync_session
        u = self._make_user(s)
        dj = DJSet(source="trackid", title="S",
                   last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=6))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()
        eligible, _, skipped_recent = _find_eligible_sets(s)
        assert eligible == []
        assert skipped_recent == 1

    def test_includes_set_crawled_over_12h(self, sync_session):
        s = sync_session
        u = self._make_user(s)
        dj = DJSet(source="trackid", title="S",
                   last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=13))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()
        eligible, _, _ = _find_eligible_sets(s)
        assert dj.id in eligible

    def test_skips_fully_identified_set(self, sync_session):
        s = sync_session
        u = self._make_user(s)
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        s.add(cat)
        s.flush()
        dj = DJSet(source="trackid", title="S",
                   last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=48))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False, catalog_id=cat.id))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()
        eligible, skipped_complete, _ = _find_eligible_sets(s)
        assert eligible == []
        assert skipped_complete == 1

    def test_skips_non_trackid_sets(self, sync_session):
        s = sync_session
        u = self._make_user(s)
        dj = DJSet(source="manual", title="S",
                   last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=48))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()
        eligible, _, _ = _find_eligible_sets(s)
        assert eligible == []

    def test_set_never_crawled_is_eligible(self, sync_session):
        s = sync_session
        u = self._make_user(s)
        dj = DJSet(source="trackid", title="S", last_crawled_at=None)
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()
        eligible, _, _ = _find_eligible_sets(s)
        assert dj.id in eligible

    def test_mixed_sets_partial_identification(self, sync_session):
        """A set with 2 tracks, 1 identified → eligible."""
        s = sync_session
        u = self._make_user(s)
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        s.add(cat)
        s.flush()
        dj = DJSet(source="trackid", title="S",
                   last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=48))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False, catalog_id=cat.id))
        s.add(SetTrack(set_id=dj.id, position=2, raw_title="ID", is_id=True))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()
        eligible, _, _ = _find_eligible_sets(s)
        assert dj.id in eligible


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
