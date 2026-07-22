"""Tests for count_enrich_backlog (workers/enrichment) — the backlog-size figures
that back the admin monitoring page.

count_enrich_backlog must be FAITHFUL to select_enrich_candidates' tier
predicates: never-tried / due-retry / cooldown / abandoned partition the
id-missing rows without overlap or gap, and total_missing == their sum. This is
the drift-prone logic, so every tier is seeded and asserted individually.
Uses a real sync SQLite session (sync_session fixture) so the tier queries run.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# Path so the workers package is importable (same pattern as test_enrich_candidates.py)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis and curl_cffi are not installed in the test env; enrichment.py imports
# them at module load. Same save/restore dance as test_enrich_candidates.py.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.enrichment import count_enrich_backlog  # noqa: E402

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl
del _saved_curl

from models import CatalogEntry  # noqa: E402

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(days):
    return NOW - timedelta(days=days)


def _make_row(session, n, **overrides):
    entry = CatalogEntry(
        title=f"Track {n}",
        artist="Artist",
        normalized_key=f"track {n} - artist",
        **overrides,
    )
    session.add(entry)
    session.commit()
    return entry


def _seed_all_deezer_tiers(session):
    """One row per tier, deezer source. Returns the expected count dict."""
    # never_tried: no id, never searched
    _make_row(session, 1)
    # due_retry — tier2: 1 attempt, searched > 30d ago
    _make_row(session, 2, deezer_searched_at=_days_ago(40), deezer_search_attempts=1)
    # due_retry — tier3: 2 attempts, searched > 90d ago
    _make_row(session, 3, deezer_searched_at=_days_ago(100), deezer_search_attempts=2)
    # cooldown — tier2: 1 attempt, searched <= 30d ago (not due yet)
    _make_row(session, 4, deezer_searched_at=_days_ago(20), deezer_search_attempts=1)
    # cooldown — tier3: 2 attempts, searched <= 90d ago (not due yet)
    _make_row(session, 5, deezer_searched_at=_days_ago(60), deezer_search_attempts=2)
    # abandoned: 3 attempts
    _make_row(session, 6, deezer_searched_at=_days_ago(400), deezer_search_attempts=3)
    # linked: already carries a deezer_id (never a backlog row)
    _make_row(session, 7, deezer_id="dz-123")
    return {
        "never_tried": 1,
        "due_retry": 2,
        "cooldown": 2,
        "abandoned": 1,
        "total_missing": 6,
        "total_linked": 1,
    }


class TestCountEnrichBacklogTiers:
    def test_each_tier_counted_exactly(self, sync_session):
        expected = _seed_all_deezer_tiers(sync_session)

        counts = count_enrich_backlog(sync_session, source="deezer", now=NOW)

        assert counts == expected

    def test_tiers_partition_total_missing(self, sync_session):
        _seed_all_deezer_tiers(sync_session)

        c = count_enrich_backlog(sync_session, source="deezer", now=NOW)

        # never + due + cooldown + abandoned must exhaust total_missing (no
        # double-count, no gap) — the invariant a naive "attempts < 3" breaks.
        assert (
            c["never_tried"] + c["due_retry"] + c["cooldown"] + c["abandoned"]
            == c["total_missing"]
        )

    def test_empty_catalog_all_zero(self, sync_session):
        c = count_enrich_backlog(sync_session, source="deezer", now=NOW)

        assert c == {
            "never_tried": 0,
            "due_retry": 0,
            "cooldown": 0,
            "abandoned": 0,
            "total_missing": 0,
            "total_linked": 0,
        }

    def test_attempt1_exactly_at_30d_is_cooldown_not_due(self, sync_session):
        # `< now - 30d` is due, `>= now - 30d` is cooldown — the boundary row
        # (searched exactly 30d ago) is NOT yet due, it is cooling down.
        _make_row(
            sync_session, 1, deezer_searched_at=_days_ago(30), deezer_search_attempts=1
        )

        c = count_enrich_backlog(sync_session, source="deezer", now=NOW)

        assert c["due_retry"] == 0
        assert c["cooldown"] == 1

    def test_abandoned_counts_beyond_max(self, sync_session):
        # attempts >= MAX (3) — 3 and 4 both abandoned, never re-selected.
        _make_row(
            sync_session, 1, deezer_searched_at=_days_ago(400), deezer_search_attempts=3
        )
        _make_row(
            sync_session, 2, deezer_searched_at=_days_ago(400), deezer_search_attempts=4
        )

        c = count_enrich_backlog(sync_session, source="deezer", now=NOW)

        assert c["abandoned"] == 2
        assert c["cooldown"] == 0
        assert c["due_retry"] == 0


class TestCountEnrichBacklogSourceIsolation:
    def test_beatport_uses_beatport_columns(self, sync_session):
        # Deezer-linked but beatport-missing: a backlog row for beatport, a
        # linked row for deezer — the two sources must not leak into each other.
        _make_row(
            sync_session,
            1,
            deezer_id="dz-1",
            beatport_searched_at=_days_ago(40),
            beatport_search_attempts=1,
        )

        deezer = count_enrich_backlog(sync_session, source="deezer", now=NOW)
        beatport = count_enrich_backlog(sync_session, source="beatport", now=NOW)

        assert deezer["total_linked"] == 1
        assert deezer["total_missing"] == 0
        assert beatport["total_linked"] == 0
        assert beatport["total_missing"] == 1
        assert beatport["due_retry"] == 1
