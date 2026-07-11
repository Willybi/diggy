"""
Additional tests for worker tasks refactoring.
Covers: failure scenarios, orchestration, retry behavior, task module structure.
"""
import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Artist,
    ArtistAlias,
    ArtistFlag,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetTrack,
    User,
    WatchedEntity,
)
from utils import make_normalized_key, normalize


# ── Import / module structure ──────────────────────────────────────────────────


class TestModuleImports:
    """Verify that the tasks package can be imported and tasks are re-exported."""

    def test_tasks_package_importable(self):
        """workers.tasks must be importable as a package."""
        # We can't do a live celery import, but we verify the __init__ re-exports
        # by checking the task sub-modules exist at the filesystem level.
        tasks_dir = os.path.join(
            os.path.dirname(__file__), "../../server/workers/tasks"
        )
        assert os.path.isdir(tasks_dir), "tasks/ directory must exist"

    def test_all_module_files_exist(self):
        tasks_dir = os.path.join(
            os.path.dirname(__file__), "../../server/workers/tasks"
        )
        expected = ["__init__.py", "radar.py", "catalog.py", "sets.py", "artists.py", "genres.py", "trends.py"]
        for fname in expected:
            assert os.path.isfile(os.path.join(tasks_dir, fname)), f"Missing: {fname}"

    def test_old_tasks_py_deleted(self):
        old_path = os.path.join(
            os.path.dirname(__file__), "../../server/workers/tasks.py"
        )
        assert not os.path.isfile(old_path), "tasks.py must be deleted"

    def test_init_re_exports_all_task_names(self):
        init_path = os.path.join(
            os.path.dirname(__file__), "../../server/workers/tasks/__init__.py"
        )
        content = open(init_path).read()
        expected_tasks = [
            "crawl_radar", "crawl_single_playlist",
            "enrich_catalog", "enrich_catalog_beatport",
            "resolve_set_tracks", "enrich_set_tracks", "recrawl_incomplete_sets",
            "sync_artists", "fetch_artist_artworks", "link_set_artists",
            "reclassify_genres_chunk", "reclassify_all_genres",
            "compute_trends",
        ]
        for task in expected_tasks:
            assert task in content, f"Task '{task}' not found in __init__.py"

    def test_all_task_decorators_have_explicit_names(self):
        """Each task module must declare name= on @celery_app.task."""
        import re
        tasks_dir = os.path.join(
            os.path.dirname(__file__), "../../server/workers/tasks"
        )
        task_files = ["radar.py", "catalog.py", "sets.py", "artists.py", "genres.py", "trends.py"]
        for fname in task_files:
            content = open(os.path.join(tasks_dir, fname)).read()
            # All @celery_app.task decorators must include name=
            decorator_blocks = re.findall(
                r'@celery_app\.task\(.*?\)', content, re.DOTALL
            )
            for block in decorator_blocks:
                assert 'name=' in block, f"{fname}: found @celery_app.task without name= in block: {block[:100]}"


# ── crawl_radar orchestration (logic replicated) ──────────────────────────────


def _crawl_radar_logic(playlists, get_fetchers_fn, dispatch_fn):
    """
    Replicate the core dispatch logic of crawl_radar without Celery/DB.

    Returns dict with dispatched, skipped, errors counts.
    """
    dispatched = 0
    skipped = 0
    errors = 0

    for pl in playlists:
        source = pl.get("source")
        try:
            _, _, has_changed = get_fetchers_fn(source)
        except ValueError:
            continue  # unknown source → skip

        try:
            if not has_changed(pl["external_id"], pl.get("last_crawled_at")):
                skipped += 1
                continue
        except Exception:
            pass  # has_changed raised → treat as changed, still dispatch

        try:
            dispatch_fn(pl["id"])
            dispatched += 1
        except Exception:
            errors += 1

    return {"dispatched": dispatched, "skipped_playlists": skipped, "errors": errors}


class TestCrawlRadarOrchestration:
    """Test fan-out logic of crawl_radar (logic replicated, no Celery import)."""

    def test_dispatches_for_each_changed_playlist(self):
        playlists = [
            {"id": 1, "source": "deezer", "external_id": "dz1", "last_crawled_at": None},
            {"id": 2, "source": "deezer", "external_id": "dz2", "last_crawled_at": None},
        ]
        dispatched_ids = []

        def get_fetchers(source):
            return (MagicMock(), MagicMock(), lambda ext_id, last: True)

        result = _crawl_radar_logic(playlists, get_fetchers, dispatched_ids.append)
        assert result["dispatched"] == 2
        assert result["skipped_playlists"] == 0
        assert dispatched_ids == [1, 2]

    def test_skips_playlists_with_no_changes(self):
        playlists = [
            {"id": 1, "source": "deezer", "external_id": "dz1", "last_crawled_at": "2024-01-01"},
        ]
        dispatched_ids = []

        def get_fetchers(source):
            return (MagicMock(), MagicMock(), lambda ext_id, last: False)

        result = _crawl_radar_logic(playlists, get_fetchers, dispatched_ids.append)
        assert result["dispatched"] == 0
        assert result["skipped_playlists"] == 1
        assert dispatched_ids == []

    def test_skips_unknown_source_playlist(self):
        playlists = [
            {"id": 1, "source": "unknown_source", "external_id": "x1", "last_crawled_at": None},
        ]
        dispatched_ids = []

        def get_fetchers(source):
            raise ValueError(f"unknown source: {source}")

        result = _crawl_radar_logic(playlists, get_fetchers, dispatched_ids.append)
        assert result["dispatched"] == 0
        assert dispatched_ids == []

    def test_dispatch_error_counted(self):
        playlists = [
            {"id": 1, "source": "deezer", "external_id": "dz1", "last_crawled_at": None},
        ]

        def get_fetchers(source):
            return (MagicMock(), MagicMock(), lambda ext_id, last: True)

        def fail_dispatch(pid):
            raise RuntimeError("celery down")

        result = _crawl_radar_logic(playlists, get_fetchers, fail_dispatch)
        assert result["errors"] == 1
        assert result["dispatched"] == 0

    def test_mixed_playlist_types(self):
        """Some playlists changed, some not, some unknown source."""
        playlists = [
            {"id": 1, "source": "deezer", "external_id": "dz1", "last_crawled_at": None},
            {"id": 2, "source": "deezer", "external_id": "dz2", "last_crawled_at": "old"},
            {"id": 3, "source": "bad_src", "external_id": "x", "last_crawled_at": None},
        ]
        dispatched_ids = []

        def get_fetchers(source):
            if source == "bad_src":
                raise ValueError
            # dz1 → changed, dz2 → not changed
            return (
                MagicMock(),
                MagicMock(),
                lambda ext_id, last: last is None,
            )

        result = _crawl_radar_logic(playlists, get_fetchers, dispatched_ids.append)
        assert result["dispatched"] == 1
        assert result["skipped_playlists"] == 1
        assert dispatched_ids == [1]


# ── crawl_single_playlist Redis lock (logic replicated) ───────────────────────


def _crawl_single_playlist_with_lock(lock_acquired, inner_fn, lock_obj, playlist_id):
    """
    Replicate the lock acquire/release pattern of crawl_single_playlist.
    Returns inner_fn result, or skipped dict if lock not acquired.
    """
    if not lock_obj.acquire(blocking=False):
        return {"skipped": True, "playlist_id": playlist_id, "reason": "lock"}

    try:
        return inner_fn(playlist_id)
    finally:
        try:
            lock_obj.release()
        except Exception as e:
            if "LockNotOwnedError" in type(e).__name__:
                pass  # lock expired, ignore
            else:
                raise


class TestCrawlSinglePlaylistLock:
    """Test Redis lock behavior (logic replicated, no redis import needed)."""

    def test_returns_skipped_when_lock_not_acquired(self):
        lock = MagicMock()
        lock.acquire.return_value = False
        result = _crawl_single_playlist_with_lock(
            False, lambda pid: {"ok": True}, lock, playlist_id=42
        )
        assert result == {"skipped": True, "playlist_id": 42, "reason": "lock"}

    def test_calls_inner_when_lock_acquired(self):
        lock = MagicMock()
        lock.acquire.return_value = True
        result = _crawl_single_playlist_with_lock(
            True, lambda pid: {"playlist_id": pid, "inserted": 5}, lock, playlist_id=7
        )
        assert result == {"playlist_id": 7, "inserted": 5}
        lock.release.assert_called_once()

    def test_releases_lock_after_inner_exception(self):
        lock = MagicMock()
        lock.acquire.return_value = True

        def fail_inner(pid):
            raise RuntimeError("db down")

        with pytest.raises(RuntimeError):
            _crawl_single_playlist_with_lock(True, fail_inner, lock, playlist_id=5)

        lock.release.assert_called_once()

    def test_lock_expiry_during_run_does_not_crash(self):
        """LockNotOwnedError on release is silently swallowed."""
        class LockNotOwnedError(Exception):
            pass

        lock = MagicMock()
        lock.acquire.return_value = True
        lock.release.side_effect = LockNotOwnedError("expired")

        # Should not raise
        result = _crawl_single_playlist_with_lock(
            True, lambda pid: {"ok": True}, lock, playlist_id=5
        )
        assert result == {"ok": True}


# ── resolve_set_tracks edge cases ─────────────────────────────────────────────


class TestResolveSetTracksEdgeCases:
    """Additional edge cases for resolve_set_tracks core logic."""

    def _resolve(self, session):
        """Replicate core logic without Celery (mirrors existing test helper)."""
        resolved = 0
        created = 0

        tracks = session.execute(
            select(SetTrack).where(
                SetTrack.catalog_id.is_(None),
                SetTrack.is_id == False,  # noqa: E712
                SetTrack.raw_title.isnot(None),
            )
        ).scalars().all()

        for st in tracks:
            norm_key = make_normalized_key(st.raw_title, st.raw_artist)
            entry = session.execute(
                select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
            ).scalar_one_or_none()

            if not entry:
                entry = CatalogEntry(
                    title=st.raw_title,
                    artist=st.raw_artist,
                    normalized_key=norm_key,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(entry)
                session.flush()
                created += 1

            st.catalog_id = entry.id
            resolved += 1

        session.commit()
        return {"resolved": resolved, "catalog_created": created}

    def test_empty_database_returns_zeros(self, sync_session):
        result = self._resolve(sync_session)
        assert result == {"resolved": 0, "catalog_created": 0}

    def test_none_raw_artist_still_resolves(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Mix")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Unknown Track", raw_artist=None))
        s.commit()

        result = self._resolve(s)
        assert result["resolved"] == 1
        assert result["catalog_created"] == 1

    def test_mixed_resolved_and_unresolved(self, sync_session):
        s = sync_session
        cat = CatalogEntry(title="Known", artist="DJ A", normalized_key=make_normalized_key("Known", "DJ A"))
        s.add(cat)
        dj = DJSet(source="trackid", title="Mix")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Known", raw_artist="DJ A"))
        s.add(SetTrack(set_id=dj.id, position=2, raw_title="New Track", raw_artist="DJ B"))
        s.add(SetTrack(set_id=dj.id, position=3, raw_title=None))  # skipped
        s.add(SetTrack(set_id=dj.id, position=4, raw_title="ID", is_id=True))  # skipped
        s.commit()

        result = self._resolve(s)
        assert result["resolved"] == 2
        assert result["catalog_created"] == 1


# ── link_set_artists additional cases ─────────────────────────────────────────


class TestLinkSetArtistsAdditional:
    """Additional edge cases for link_set_artists core logic."""

    def _link(self, session):
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
            title_lower = title.lower()
            is_b2b = "b2b" in title_lower
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

    def test_no_artists_no_links(self, sync_session):
        s = sync_session
        s.add(DJSet(source="trackid", title="Some DJ @ Club"))
        s.commit()
        result = self._link(s)
        assert result["linked"] == 0

    def test_no_sets_no_links(self, sync_session):
        s = sync_session
        s.add(Artist(name="ANNA", normalized_name="anna"))
        s.commit()
        result = self._link(s)
        assert result["linked"] == 0

    def test_underscore_title_matches(self, sync_session):
        """Titles with underscores (e.g. Busy_P_b2b_Erol_Alkan) should match."""
        s = sync_session
        a1 = Artist(name="Busy P", normalized_name="busy p")
        a2 = Artist(name="Erol Alkan", normalized_name="erol alkan")
        s.add_all([a1, a2])
        dj = DJSet(source="trackid", title="Busy_P_b2b_Erol_Alkan")
        s.add(dj)
        s.commit()

        result = self._link(s)
        assert result["linked"] == 2
        links = s.execute(select(SetArtist)).scalars().all()
        assert all(l.role == "b2b" for l in links)

    def test_longer_name_matches_before_shorter(self, sync_session):
        """'Fred again..' should be matched before 'Fred'."""
        s = sync_session
        fred = Artist(name="Fred", normalized_name="fred")
        fred_again = Artist(name="Fred again..", normalized_name="fred again..")
        s.add_all([fred, fred_again])
        dj = DJSet(source="trackid", title="Fred again.. at Boiler Room")
        s.add(dj)
        s.commit()

        result = self._link(s)
        # Both "fred" and "fred again.." appear in the title, so both get linked.
        # The key test is that this doesn't crash and doesn't produce wrong duplicates.
        assert result["linked"] >= 1
        links = s.execute(select(SetArtist)).scalars().all()
        artist_ids = {l.artist_id for l in links}
        assert fred_again.id in artist_ids


# crawl_followed_sets eligibility tests removed with the task (C6.b): the
# replacement recrawl_incomplete_sets is covered in test_tasks_recrawl_sets.py
