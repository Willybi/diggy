"""Tests for the artist Deezer-link candidate selection tiers
(workers.tasks.artists.select_link_candidates / count_link_candidates).

Focus on the long-term RESURRECTION tier (an artist abandoned after MAX attempts is
re-searched every ARTIST_LONG_RETRY_DAYS) alongside the pre-existing tier1 (never
searched) and retry (E1 backoff) tiers, against a real sync SQLite session.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions", "requests", "curl_cffi", "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.delay = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
sys.modules["workers.celery_app"] = MagicMock(celery_app=_celery_mock)

from models import Artist  # noqa: E402

from workers.tasks.artists import (  # noqa: E402
    ARTIST_LONG_RETRY_DAYS,
    ARTIST_MAX_SEARCH_ATTEMPTS,
    count_link_candidates,
    select_link_candidates,
)

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _mk(session, name, **kw):
    a = Artist(name=name, normalized_name=name.lower(), **kw)
    session.add(a)
    session.commit()
    return a


def _names(rows):
    return {a.name for a in rows}


class TestSelectLinkCandidates:
    def test_tier1_never_searched_selected(self, sync_session):
        _mk(sync_session, "Fresh", deezer_searched_at=None)
        assert "Fresh" in _names(select_link_candidates(sync_session, 100, _NOW))

    def test_abandoned_recent_not_selected(self, sync_session):
        # >= MAX attempts but searched only 10 days ago → dormant, not yet due.
        _mk(
            sync_session, "DormantRecent",
            deezer_search_attempts=ARTIST_MAX_SEARCH_ATTEMPTS,
            deezer_searched_at=_NOW - timedelta(days=10),
        )
        assert "DormantRecent" not in _names(select_link_candidates(sync_session, 100, _NOW))

    def test_resurrected_after_long_retry(self, sync_session):
        # >= MAX attempts AND last searched beyond the long-retry window → resurrected.
        _mk(
            sync_session, "Resurrect",
            deezer_search_attempts=ARTIST_MAX_SEARCH_ATTEMPTS,
            deezer_searched_at=_NOW - timedelta(days=ARTIST_LONG_RETRY_DAYS + 5),
        )
        assert "Resurrect" in _names(select_link_candidates(sync_session, 100, _NOW))

    def test_not_found_sentinel_never_resurrected(self, sync_session):
        # deezer_id set to the sentinel (human decision) → excluded from every tier.
        _mk(
            sync_session, "Confirmed Absent",
            deezer_id="NOT_FOUND",
            deezer_search_attempts=ARTIST_MAX_SEARCH_ATTEMPTS,
            deezer_searched_at=_NOW - timedelta(days=ARTIST_LONG_RETRY_DAYS + 5),
        )
        assert "Confirmed Absent" not in _names(select_link_candidates(sync_session, 100, _NOW))

    def test_resurrect_is_lowest_priority(self, sync_session):
        # With a budget of 1, the never-searched tier1 wins over a due resurrection.
        _mk(sync_session, "Fresh", deezer_searched_at=None)
        _mk(
            sync_session, "Resurrect",
            deezer_search_attempts=ARTIST_MAX_SEARCH_ATTEMPTS,
            deezer_searched_at=_NOW - timedelta(days=ARTIST_LONG_RETRY_DAYS + 5),
        )
        picked = _names(select_link_candidates(sync_session, 1, _NOW))
        assert picked == {"Fresh"}

    def test_count_includes_resurrect(self, sync_session):
        _mk(sync_session, "Fresh", deezer_searched_at=None)
        _mk(
            sync_session, "Resurrect",
            deezer_search_attempts=ARTIST_MAX_SEARCH_ATTEMPTS,
            deezer_searched_at=_NOW - timedelta(days=ARTIST_LONG_RETRY_DAYS + 5),
        )
        _mk(
            sync_session, "DormantRecent",
            deezer_search_attempts=ARTIST_MAX_SEARCH_ATTEMPTS,
            deezer_searched_at=_NOW - timedelta(days=10),
        )
        # tier1 (Fresh) + resurrect (Resurrect); DormantRecent is not yet due.
        assert count_link_candidates(sync_session, _NOW) == 2
