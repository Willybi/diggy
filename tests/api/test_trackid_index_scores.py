"""Tests for the TrackID index score-update mode (C12 / lot L6).

Two layers, both self-contained:
  - ``parse_scores_row`` is PURE (no DB) — exercised directly.
  - ``run_score_update`` is driven against an OWN in-memory SQLite engine holding
    only the trackid_index table (mirrors test_trackid_index_model.py), so it does
    NOT touch the PG conftest harness and stays parallel-safe. The DB path is
    dialect-neutral (existence SELECT + a JSON-typed targeted UPDATE).
"""
import json

from models.trackid_index import TrackIdIndex
from scripts.import_trackid_index import parse_scores_row, run_score_update
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# ── pure parsing / validation ──────────────────────────────────────────────────


def test_parse_scores_row_valid():
    assert parse_scores_row(
        {"trackid_id": 7, "score": 12.5, "score_components": {"phase": 0, "has_lib": True}}
    ) == (7, 12.5, {"phase": 0, "has_lib": True})


def test_parse_scores_row_integer_score_coerced_to_float():
    assert parse_scores_row({"trackid_id": 1, "score": 3}) == (1, 3.0, None)


def test_parse_scores_row_components_optional():
    # A missing score_components is permitted (None), a present non-object is not.
    assert parse_scores_row({"trackid_id": 1, "score": 2.0})[2] is None
    assert parse_scores_row({"trackid_id": 1, "score": 2.0, "score_components": [1, 2]}) is None


def test_parse_scores_row_invalid_rows():
    assert parse_scores_row({"score": 2.5}) is None  # no trackid_id
    assert parse_scores_row({"trackid_id": "x", "score": 2.5}) is None  # non-int id
    assert parse_scores_row({"trackid_id": True, "score": 2.5}) is None  # bool id
    assert parse_scores_row({"trackid_id": 1, "score": "hi"}) is None  # non-numeric
    assert parse_scores_row({"trackid_id": 1, "score": True}) is None  # bool score
    assert parse_scores_row({"trackid_id": 1}) is None  # no score


# ── DB path (own SQLite engine, single table) ───────────────────────────────────


def _seed_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    TrackIdIndex.__table__.create(engine)
    with Session(engine) as session:
        session.add_all(
            [
                TrackIdIndex(trackid_id=1, title="a"),
                TrackIdIndex(trackid_id=2, title="b"),
            ]
        )
        session.commit()
    return engine


def _write_ndjson(tmp_path, objs):
    path = tmp_path / "scores.ndjson"
    path.write_text("\n".join(json.dumps(o) for o in objs), encoding="utf-8")
    return str(path)


def test_run_score_update_apply_writes_known_rows(tmp_path):
    engine = _seed_engine()
    path = _write_ndjson(
        tmp_path,
        [
            {"trackid_id": 1, "score": 12.5, "score_components": {"phase": 0, "has_lib": True}},
            {"trackid_id": 999, "score": 3.0, "score_components": {"phase": 3}},  # unknown
            {"trackid_id": 2, "score": 0.0, "score_components": {"phase": 2, "channel_prio": "reste"}},
        ],
    )

    with Session(engine) as session:
        stats = run_score_update(session, path, apply=True, limit=None, batch_size=1000)

    assert stats == {"read": 3, "invalid": 0, "known": 2, "unknown": 1, "written": 2}

    with Session(engine) as session:
        r1 = session.query(TrackIdIndex).filter_by(trackid_id=1).one()
        assert r1.score == 12.5
        assert r1.score_components == {"phase": 0, "has_lib": True}
        r2 = session.query(TrackIdIndex).filter_by(trackid_id=2).one()
        assert r2.score == 0.0
        assert r2.score_components == {"phase": 2, "channel_prio": "reste"}


def test_run_score_update_dry_run_writes_nothing(tmp_path):
    engine = _seed_engine()
    path = _write_ndjson(
        tmp_path, [{"trackid_id": 1, "score": 9.0, "score_components": {"phase": 1}}]
    )

    with Session(engine) as session:
        stats = run_score_update(session, path, apply=False, limit=None, batch_size=1000)

    assert stats["known"] == 1
    assert stats["written"] == 0
    with Session(engine) as session:
        row = session.query(TrackIdIndex).filter_by(trackid_id=1).one()
        assert row.score is None
        assert row.score_components is None


def test_run_score_update_is_idempotent_and_batches(tmp_path):
    engine = _seed_engine()
    path = _write_ndjson(
        tmp_path,
        [
            {"trackid_id": 1, "score": 5.0, "score_components": {"phase": 0}},
            {"trackid_id": 2, "score": 6.0, "score_components": {"phase": 1}},
        ],
    )

    with Session(engine) as session:
        run_score_update(session, path, apply=True, limit=None, batch_size=1)
    # Re-run converges to the same state (idempotent), small batch size crosses flushes.
    with Session(engine) as session:
        stats = run_score_update(session, path, apply=True, limit=None, batch_size=1)

    assert stats["written"] == 2
    with Session(engine) as session:
        r1 = session.query(TrackIdIndex).filter_by(trackid_id=1).one()
        assert r1.score == 5.0 and r1.score_components == {"phase": 0}


def test_run_score_update_skips_invalid_lines(tmp_path):
    engine = _seed_engine()
    path = _write_ndjson(
        tmp_path,
        [
            {"trackid_id": 1, "score": 5.0, "score_components": {"phase": 0}},
            {"trackid_id": "bad", "score": 5.0},  # invalid
            {"score": 5.0},  # invalid
        ],
    )

    with Session(engine) as session:
        stats = run_score_update(session, path, apply=True, limit=None, batch_size=1000)

    assert stats["read"] == 3
    assert stats["invalid"] == 2
    assert stats["known"] == 1
    assert stats["written"] == 1
