"""Tests for the BPM-analysis candidate predicate (E2.c, lot A) — pure model
helper, no DB. Locks the single-source backlog filter used by the future nightly
task and the admin: same conditions, .where(*...)-combinable."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from models import CatalogEntry, bpm_analysis_candidate_filter


class TestBpmAnalysisCandidateFilter:
    def test_returns_five_conditions(self):
        conditions = bpm_analysis_candidate_filter()
        assert isinstance(conditions, list)
        assert len(conditions) == 5

    def test_conditions_are_and_combinable_in_a_where(self):
        # SQLAlchemy accepts the list splat as a where() clause without error;
        # compiling proves each element is a valid boolean expression.
        from sqlalchemy import select

        stmt = select(CatalogEntry.id).where(*bpm_analysis_candidate_filter())
        rendered = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
        for token in ("has_preview", "bpm is null", "deezer_id", "bpm_analyzed_at"):
            assert token in rendered
