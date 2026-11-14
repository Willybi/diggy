"""DIGGY-APP-22/1Y/1N/23/H — a concurrent write at the per-batch commit of the
enrich drains costs ONE batch, never the whole run.

`_commit_batch_or_discard` wraps `_commit_with_deadlock_retry`: on a
StaleDataError (row deleted mid-batch by a concurrent merge), a
PendingRollbackError (deadlock swallowed during an autoflush, Session poisoned)
or an exhausted 40P01 deadlock it rolls back and returns False; any other
OperationalError propagates unchanged.

Unit tests use a mock session (pattern of test_commit_deadlock_retry.py); the
driven drain test reuses the harness of test_deadline_exit.py as-is.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy.orm.exc import StaleDataError

# Reuse the deadline-exit harness (sys.modules mocks, fixtures, fake clock)
# without refactoring it: importing it installs the same broker mocks.
from tests.worker.test_deadline_exit import (  # noqa: F401
    _NEVER,
    _FakeClock,
    _mock_enrichment,
    catalog_mod,
    fake_redis,
    fake_self,
    run_env,
)


def _op_error(pgcode):
    orig = MagicMock()
    orig.pgcode = pgcode
    return OperationalError("UPDATE catalog ...", {}, orig)


@pytest.fixture
def cat(catalog_mod, monkeypatch):  # noqa: F811
    """The catalog task module with the deadlock backoff patched to 0."""
    # Backoff 0 → time.sleep(0): no need to patch the (global) time module.
    monkeypatch.setattr(catalog_mod, "COMMIT_DEADLOCK_BACKOFF", 0)
    return catalog_mod


class TestCommitBatchOrDiscard:
    def test_commit_ok_returns_true(self, cat):
        session = MagicMock()

        assert cat._commit_batch_or_discard(session, label="t", batch_len=3) is True
        session.commit.assert_called_once()
        session.rollback.assert_not_called()

    def test_stale_data_discards_batch(self, cat):
        session = MagicMock()
        session.commit.side_effect = StaleDataError("row vanished")

        assert cat._commit_batch_or_discard(session, label="t", batch_len=3) is False
        session.rollback.assert_called_once()

    def test_pending_rollback_discards_batch(self, cat):
        session = MagicMock()
        session.commit.side_effect = PendingRollbackError("poisoned session")

        assert cat._commit_batch_or_discard(session, label="t", batch_len=3) is False
        session.rollback.assert_called()

    def test_non_deadlock_operational_error_propagates(self, cat):
        session = MagicMock()
        session.commit.side_effect = _op_error("57P01")

        with pytest.raises(OperationalError) as exc:
            cat._commit_batch_or_discard(session, label="t", batch_len=3)
        assert exc.value.orig.pgcode == "57P01"
        assert session.commit.call_count == 1

    def test_exhausted_deadlock_discards_batch(self, cat):
        session = MagicMock()
        session.commit.side_effect = [
            _op_error("40P01") for _ in range(cat.COMMIT_DEADLOCK_MAX_RETRIES)
        ]

        assert cat._commit_batch_or_discard(session, label="t", batch_len=3) is False
        assert session.commit.call_count == cat.COMMIT_DEADLOCK_MAX_RETRIES
        session.rollback.assert_called()

    def test_no_retry_mode_discards_deadlock_at_once(self, cat):
        session = MagicMock()
        session.commit.side_effect = _op_error("40P01")

        assert (
            cat._commit_batch_or_discard(
                session, label="t", batch_len=3, retry_deadlock=False
            )
            is False
        )
        assert session.commit.call_count == 1


class TestDrainSurvivesDiscardedBatch:
    def test_deezer_first_batch_stale_second_committed(
        self, cat, run_env, fake_redis, fake_self, monkeypatch  # noqa: F811
    ):
        # 200 candidates → 2 batches of 100; the 1st commit hits StaleDataError.
        enrichment = _mock_enrichment(
            monkeypatch, 200, {"enriched": 9, "errors": 1, "merged": 2}
        )
        monkeypatch.setattr(cat, "time", _FakeClock(_NEVER))
        run_env.session.commit.side_effect = [StaleDataError("gone"), None]

        result = cat.enrich_catalog(fake_self)

        assert enrichment.enrich_deezer_batch.await_count == 2
        assert run_env.session.commit.call_count == 2
        run_env.session.rollback.assert_called_once()
        # Only the 2nd batch's success stats count; the 1st counts as 100 errors.
        assert result["enriched"] == 9
        assert result["merged"] == 2
        assert result["errors"] == 100 + 1
        run_env.clog.set_stats.assert_called_once_with(result)
        fake_redis.delete.assert_called_once_with("lock:enrich_deezer")

    def test_beatport_first_batch_pending_rollback_second_committed(
        self, cat, run_env, fake_redis, fake_self, monkeypatch  # noqa: F811
    ):
        # 100 candidates → 2 batches of 50; the 1st commit finds a poisoned Session.
        enrichment = _mock_enrichment(
            monkeypatch, 100,
            {"enriched": 7, "not_found": 1, "errors": 0, "merged": 0},
        )
        monkeypatch.setattr(cat, "time", _FakeClock(_NEVER))
        run_env.session.commit.side_effect = [PendingRollbackError("x"), None]

        result = cat.enrich_catalog_beatport(fake_self)

        assert enrichment.enrich_beatport_batch.await_count == 2
        assert result["enriched"] == 7
        assert result["not_found"] == 1
        assert result["errors"] == 50
        assert result["soft_limit_hit"] is False
