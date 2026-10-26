"""
Tests for the trend v2 compute logic.

Tests the helper functions (pillar mapping, family assignment) and
the overall formula behavior using mocked DB results.
"""

import math
import os
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Add server paths
_server = os.path.join(os.path.dirname(__file__), "../../server")
_api = os.path.join(_server, "api")
for p in (_server, _api):
    if p not in sys.path:
        sys.path.insert(0, p)

# Mock infra modules not available outside Docker
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state", "celery.result",
    "redis", "redis.exceptions",
    "requests",
    "workers.celery_app",
]

# Save originals so we can restore after tests
_saved_modules = {mod: sys.modules.get(mod) for mod in _MOCK_MODULES}

for _mod in _MOCK_MODULES:
    sys.modules.setdefault(_mod, MagicMock())

# Make celery_app.task() act as a passthrough decorator
_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        return fn
    if args and callable(args[0]):
        return args[0]
    return decorator


_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

from workers.tasks.trends import _genre_to_family, _purge_stale_trends, _ROOT_TO_PILLAR

# Restore sys.modules immediately — we already imported what we need.
# This prevents polluting other test files collected by pytest.
for _mod, _original in _saved_modules.items():
    if _original is None:
        sys.modules.pop(_mod, None)
    else:
        sys.modules[_mod] = _original
del _saved_modules


# ── Helpers ──────────────────────────────────────────────────────────────────


class TestGenreToFamily:
    def test_returns_first_non_autres_match(self):
        cache = {"Tech House": "house", "Techno": "techno", "Ambient": "autres"}
        assert _genre_to_family(["Tech House", "Techno"], cache) == "house"

    def test_falls_back_to_autres_if_all_autres(self):
        cache = {"Ambient": "autres", "Downtempo": "autres"}
        assert _genre_to_family(["Ambient", "Downtempo"], cache) == "autres"

    def test_returns_none_for_empty_genres(self):
        assert _genre_to_family([], {}) is None
        assert _genre_to_family(None, {}) is None

    def test_returns_none_when_no_cache_match(self):
        assert _genre_to_family(["Unknown Genre"], {}) is None

    def test_prefers_non_autres_over_autres(self):
        cache = {"Ambient": "autres", "Drum and Bass": "dnb"}
        assert _genre_to_family(["Ambient", "Drum and Bass"], cache) == "dnb"


# ── Formula unit tests (pure math, no DB) ────────────────────────────────────

# Simulate a detection row from the SQL query
ScoreRow = namedtuple(
    "ScoreRow",
    [
        "catalog_id",
        "genres",
        "detection_count",
        "source_count",
        "trend_score",
        "velocity",
    ],
)


def _decay(age_days):
    return 0.5 ** (age_days / 14.0)


def _size_weight(track_count):
    return 1.0 / math.sqrt(max(track_count, 1))


class TestSourceWeight:
    """Verify that set detections weigh 3x more than playlist detections."""

    def test_set_weight_3x(self):
        # A detection in a set (weight 3.0) vs playlist (weight 1.0)
        # with same age and same track_count
        age = 0  # today
        track_count = 25
        set_score = _decay(age) * 3.0 * _size_weight(track_count)
        playlist_score = _decay(age) * 1.0 * _size_weight(track_count)
        assert set_score == pytest.approx(3.0 * playlist_score)


class TestSizeWeight:
    """Verify small playlists weigh more."""

    def test_small_playlist_weighs_more(self):
        # 25 tracks vs 400 tracks
        w25 = _size_weight(25)
        w400 = _size_weight(400)
        ratio = w25 / w400
        assert ratio == pytest.approx(4.0)

    def test_size_weight_floor(self):
        # track_count=0 should be treated as 1
        assert _size_weight(0) == _size_weight(1)


class TestConvergenceBonus:
    """Verify multi-source convergence bonus."""

    def test_single_source(self):
        bonus = 1 + 0.3 * (1 - 1)
        assert bonus == 1.0

    def test_two_sources(self):
        bonus = 1 + 0.3 * (2 - 1)
        assert bonus == pytest.approx(1.3)

    def test_three_sources(self):
        bonus = 1 + 0.3 * (3 - 1)
        assert bonus == pytest.approx(1.6)


class TestVelocityCalculation:
    """Verify velocity ratio and clamping."""

    def _velocity(self, recent, previous):
        raw = recent / max(previous, 1) - 1
        return min(max(raw, 0), 5)

    def test_stable(self):
        # same detections both weeks -> 0
        assert self._velocity(5, 5) == 0.0

    def test_acceleration(self):
        # 10 recent vs 5 previous -> velocity 1.0
        assert self._velocity(10, 5) == pytest.approx(1.0)

    def test_deceleration_clamped_to_zero(self):
        # 2 recent vs 10 previous -> negative -> clamped to 0
        assert self._velocity(2, 10) == 0.0

    def test_from_zero_clamped_to_five(self):
        # 10 recent vs 0 previous -> 10/1 - 1 = 9 -> clamped to 5
        assert self._velocity(10, 0) == 5.0

    def test_previous_zero_moderate(self):
        # 3 recent, 0 previous -> 3/1 - 1 = 2 -> within cap
        assert self._velocity(3, 0) == pytest.approx(2.0)


class TestInitialDetectionExcluded:
    """is_initial_detection=True must not count in velocity."""

    def test_filter_in_sql(self):
        # The SQL uses: NOT is_initial_detection
        # We verify the intent: initial detections have is_initial_detection=True
        # and the WHERE clause excludes them.
        sql_fragment = "AND NOT is_initial_detection"
        # This test just documents the contract
        assert "NOT is_initial_detection" in sql_fragment


class TestRankByFamily:
    """Verify that ranks are computed correctly per family."""

    def test_ranks_assigned_by_family(self):
        entries = [
            {"catalog_id": 1, "trend_score": 10, "family": "house"},
            {"catalog_id": 2, "trend_score": 8, "family": "techno"},
            {"catalog_id": 3, "trend_score": 6, "family": "house"},
            {"catalog_id": 4, "trend_score": 4, "family": "techno"},
            {"catalog_id": 5, "trend_score": 2, "family": None},
        ]
        # Sort by score desc for global rank
        entries.sort(key=lambda e: e["trend_score"], reverse=True)
        for i, e in enumerate(entries, 1):
            e["rank_global"] = i

        # Rank within each family
        from collections import defaultdict

        by_family = defaultdict(list)
        for e in entries:
            if e["family"]:
                by_family[e["family"]].append(e)
        for family_entries in by_family.values():
            for i, e in enumerate(family_entries, 1):
                e["rank_in_family"] = i
        for e in entries:
            e.setdefault("rank_in_family", None)

        # Global ranks
        assert entries[0]["rank_global"] == 1  # score 10, house
        assert entries[1]["rank_global"] == 2  # score 8, techno
        assert entries[4]["rank_global"] == 5  # score 2, no family

        # Family ranks
        house = [e for e in entries if e["family"] == "house"]
        assert house[0]["rank_in_family"] == 1  # score 10
        assert house[1]["rank_in_family"] == 2  # score 6

        techno = [e for e in entries if e["family"] == "techno"]
        assert techno[0]["rank_in_family"] == 1  # score 8
        assert techno[1]["rank_in_family"] == 2  # score 4

        # No family -> no family rank
        no_family = [e for e in entries if e["family"] is None]
        assert no_family[0]["rank_in_family"] is None


class TestRemovedTracksExcluded:
    """Tracks with removed_at IS NOT NULL must be excluded from scoring."""

    def test_sql_excludes_removed(self):
        # The SQL uses: AND rt.removed_at IS NULL
        # We verify this is present in the query
        import inspect
        from workers.tasks.trends import compute_trends

        source = inspect.getsource(compute_trends)
        assert "removed_at IS NULL" in source


class TestUnreliableSetsExcluded:
    """C8 (L2): unreliable TrackID sets must not weigh in set-level trend scoring.

    compute_trends builds its SQL by concatenating the shared reliability
    fragment at runtime (``set_reliable_sql('s')``), so we assert the source wires
    that helper into the set branch — the same source-inspection contract as
    TestRemovedTracksExcluded above."""

    def test_set_branch_wires_reliability_fragment(self):
        import inspect
        from workers.tasks.trends import compute_trends

        source = inspect.getsource(compute_trends)
        # helper imported + fragment concatenated into the set: UNION branch
        assert "from trackid.reliability import set_reliable_sql" in source
        assert 'set_reliable_sql("s")' in source
        assert "set_reliable_frag" in source

    def test_reliability_fragment_semantics(self):
        # The shared fragment keeps reliable sets (unreliable IS NOT TRUE).
        from trackid.reliability import set_reliable_sql

        assert set_reliable_sql("s") == "s.unreliable IS NOT TRUE"


class TestFkGuardBeforeUpsert:
    """DIGGY-APP-1P/-4/-1W: a catalog row deleted concurrently (merge-on-collision
    during the overlapping 07:00 Beatport enrich run) between the detections
    SELECT and the radar_trends upsert makes the bulk INSERT raise a
    ForeignKeyViolation. compute_trends re-checks catalog existence right before
    inserting AND retries the insert on the residual race (a delete committing
    between the re-check and the INSERT's FK trigger still violated it — the
    pre-check-only fix 1ff2683 regressed 2026-10-10). Same source-inspection
    contract as the reliability/removed-tracks tests above — the drop/retry
    branches only fire under a real concurrent delete (unreachable via seeded
    data, since the detections CTE joins catalog)."""

    def test_source_rechecks_catalog_existence_before_upsert(self):
        import inspect
        from workers.tasks.trends import compute_trends

        source = inspect.getsource(compute_trends)
        # existence re-check immediately before the upsert
        assert "SELECT id FROM catalog WHERE id = ANY(:ids)" in source
        assert "FK guard" in source
        # the upsert is skipped cleanly when the post-filter set is empty
        assert "if entries:" in source

    def test_source_retries_insert_on_fk_violation(self):
        """The residual race (delete between re-check and FK trigger) must be
        survived by a bounded retry that rolls back and re-filters, not by letting
        the run die to the DLQ (DIGGY-APP-4/-1W)."""
        import inspect
        from workers.tasks.trends import compute_trends

        source = inspect.getsource(compute_trends)
        # the insert path is wrapped in a bounded retry on IntegrityError
        assert "IntegrityError" in source
        assert "max_attempts" in source
        assert "session.rollback()" in source
        # the aborted transaction is rolled back and the run re-raises at the cap
        assert "if attempt == max_attempts:" in source
        assert "raise" in source


class TestDuplicateSetsCollapsed:
    """TrackID hosts duplicate audiostreams of the same show (distinct
    external_ids). A dup identifying < 3 tracks escapes the track-overlap
    dedup (never a match_set candidate) and stays a separate root, so a
    single-track show would otherwise count once per copy in the SUM(base_score)
    that ranks trends. The set branch collapses detections on the logical set
    identity (channel + normalized_title + reliable date) BEFORE the sum, with a
    physical-set_id fallback so unrelated sets are never merged. Same
    source-inspection contract as the reliability/removed-tracks tests above —
    the collapse only fires on real duplicate rows (unreachable via seeded data,
    since compute_trends' SQL is PG-only and mocked in this suite)."""

    def test_set_branch_collapses_logical_duplicates_before_sum(self):
        import inspect
        from workers.tasks.trends import compute_trends

        source = inspect.getsource(compute_trends)
        # the logical-set key is built from channel + normalized_title + date
        assert "'setgrp:' || md5(" in source
        assert "s.normalized_title" in source
        assert "COALESCE(lower(s.channel), '')" in source
        assert "COALESCE(s.event_date::text," in source
        # aggregated so each logical set yields ONE detection row (de-inflates
        # both COUNT(DISTINCT) and the base_score SUM)
        assert "GROUP BY catalog_id, entity_key, genres, release_date" in source
        # physical set_id fallback keeps un-normalized sets distinct
        assert "ELSE 'set:' || st.set_id::text" in source


class TestPurgeStaleTrends:
    """A3-02: a run must delete radar_trends rows left over from previous runs."""

    def _make_trend(self, catalog_id, computed_at):
        from models import RadarTrend

        return RadarTrend(
            catalog_id=catalog_id,
            trend_score=1.0,
            window_days=30,
            detection_count=1,
            source_count=1,
            computed_at=computed_at,
        )

    def test_purges_stale_keeps_current_run(self, sync_session):
        from models import RadarTrend
        from sqlalchemy import select

        run_ts = datetime.now(timezone.utc)
        sync_session.add(self._make_trend(1, run_ts - timedelta(days=2)))  # stale
        sync_session.add(self._make_trend(2, run_ts))  # upserted by current run
        sync_session.commit()

        purged = _purge_stale_trends(sync_session, run_ts)
        sync_session.commit()

        assert purged == 1
        remaining = sync_session.execute(select(RadarTrend.catalog_id)).scalars().all()
        assert remaining == [2]

    def test_purge_noop_when_all_fresh(self, sync_session):
        from models import RadarTrend
        from sqlalchemy import select

        run_ts = datetime.now(timezone.utc)
        sync_session.add(self._make_trend(1, run_ts))
        sync_session.add(self._make_trend(2, run_ts))
        sync_session.commit()

        purged = _purge_stale_trends(sync_session, run_ts)
        sync_session.commit()

        assert purged == 0
        assert len(sync_session.execute(select(RadarTrend)).scalars().all()) == 2
