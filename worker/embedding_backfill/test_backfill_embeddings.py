"""Unit tests for the PURE orchestrator logic (no Essentia, no network, no SSH).

Deliberately placed in the package, NOT under ``tests/``: CI has no Essentia and
must not depend on this local-tooling package. Run standalone from the repo root:

    pytest worker/embedding_backfill/test_backfill_embeddings.py -q
"""

import argparse
import json

import pytest

from worker.embedding_backfill import backfill_embeddings as bf
from worker.embedding_backfill.backfill_embeddings import (
    MODEL_NAME,
    MODEL_VERSION,
    REMOTE_PSQL_APPLY,
    PassResult,
    apply_or_plan,
    build_insert_batches,
    build_pull_query,
    eligible_inserts,
    filter_new,
    format_vector_literal,
    load_checkpoint,
    parse_candidates,
    parse_insert_count,
    reject_ids,
)


def _loop_args(tmp_path, **over):
    base = dict(
        workdir=str(tmp_path),
        reuse_results=False,
        loop=True,
        after_id=0,
        limit=10,
        workers=2,
        batch_size=200,
        apply=False,
        max_rounds=3,
        retry_cooldown=0,
    )
    base.update(over)
    return argparse.Namespace(**base)


def test_build_pull_query_no_limit():
    sql = build_pull_query()
    assert "COPY (" in sql
    assert "FROM catalog c" in sql
    assert "LEFT JOIN track_embeddings te" in sql
    assert f"te.model_name = '{MODEL_NAME}'" in sql
    assert f"te.model_version = '{MODEL_VERSION}'" in sql
    assert "te.id IS NULL" in sql  # only rows without an embedding yet
    assert "has_preview = true" in sql
    assert "deezer_id IS NOT NULL" in sql
    assert "deezer_id <> 'NOT_FOUND'" in sql
    assert "ORDER BY c.id" in sql
    assert "LIMIT" not in sql
    assert "c.id >" not in sql  # no after-id clause by default


def test_build_pull_query_limit_and_after_id():
    sql = build_pull_query(limit=20, after_id=1234)
    assert "LIMIT 20" in sql
    assert "AND c.id > 1234" in sql


def test_parse_candidates():
    rows = parse_candidates("id,deezer_id\n1,111\n2,222\n")
    assert rows == [
        {"id": "1", "deezer_id": "111"},
        {"id": "2", "deezer_id": "222"},
    ]


def test_filter_new_skips_checkpointed():
    candidates = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert filter_new(candidates, {"2"}) == [{"id": "1"}, {"id": "3"}]
    assert filter_new(candidates, set()) == candidates


def _results():
    v3 = json.dumps([0.1, 0.2, 0.3])
    return [
        {"id": "1", "status": "ok", "dim": "3", "emb": v3},
        {"id": "2", "status": "ok", "dim": "3", "emb": json.dumps([1.0, 2.0, 3.0])},
        {"id": "3", "status": "no_preview", "dim": "", "emb": ""},
        {"id": "4", "status": "error:RuntimeError", "dim": "", "emb": ""},
        # defensive: "ok" but wrong dim must NOT be written
        {"id": "5", "status": "ok", "dim": "2", "emb": json.dumps([0.5, 0.6])},
        # defensive: "ok" but empty/garbage emb must NOT be written
        {"id": "6", "status": "ok", "dim": "3", "emb": ""},
        {"id": "7", "status": "ok", "dim": "3", "emb": "not-json"},
    ]


def test_eligible_inserts_dim_gate():
    pairs = eligible_inserts(_results(), dim=3)
    assert pairs == [(1, [0.1, 0.2, 0.3]), (2, [1.0, 2.0, 3.0])]


def test_reject_ids_final_statuses_only():
    # only no_preview is final: "ok" rows are not rejects, error:* stays retryable
    assert reject_ids(_results()) == ["3"]


def test_reject_ids_keeps_rate_limited_rows_retryable():
    results = [
        {"id": "1", "status": "error:HTTP429"},
        {"id": "2", "status": "error:HTTPError"},
    ]
    assert reject_ids(results) == []


def test_format_vector_literal():
    lit = format_vector_literal([0.1, 2.0, -3.5])
    assert lit.startswith("'[")
    assert lit.endswith("]'::vector")
    assert lit == "'[0.1,2.0,-3.5]'::vector"


def test_build_insert_batches_sql_shape():
    batches = build_insert_batches([(1, [0.1, 0.2, 0.3]), (2, [1.0, 2.0, 3.0])])
    assert len(batches) == 1
    sql, ids = batches[0]
    assert "INSERT INTO track_embeddings" in sql
    assert "(catalog_id, model_name, model_version, embedding, created_at)" in sql
    assert (
        "ON CONFLICT (catalog_id, model_name, model_version) DO NOTHING" in sql
    )  # idempotence guard
    assert f"'{MODEL_NAME}'" in sql
    assert f"'{MODEL_VERSION}'" in sql
    assert "'[0.1,0.2,0.3]'::vector" in sql
    assert "now()" in sql
    assert ids == ["1", "2"]


def test_build_insert_batches_batching_and_empty():
    pairs = [(i, [float(i)]) for i in range(1, 8)]
    batches = build_insert_batches(pairs, batch_size=3)
    assert [len(ids) for _sql, ids in batches] == [3, 3, 1]
    assert batches[2][1] == ["7"]
    assert build_insert_batches([]) == []


def test_parse_insert_count():
    assert parse_insert_count("INSERT 0 200\nINSERT 0 12\n") == 212
    assert parse_insert_count("") == 0
    assert parse_insert_count("SET\nTimings on\n") == 0


def test_checkpoint_roundtrip(tmp_path):
    path = tmp_path / "processed_ids.txt"
    assert load_checkpoint(str(path)) == set()
    counters = apply_or_plan(
        _results(), apply=False, checkpoint_path=str(path), dim=3, runner=None
    )
    assert counters["eligible"] == 2
    # dry-run: no_preview checkpointed; eligible (to write) and error (to retry) NOT
    assert load_checkpoint(str(path)) == {"3"}


def test_apply_or_plan_dry_run_never_calls_runner(tmp_path):
    calls = []

    def runner(cmd, sql):
        calls.append((cmd, sql))
        return "INSERT 0 999\n"

    counters = apply_or_plan(
        _results(),
        apply=False,
        checkpoint_path=str(tmp_path / "cp.txt"),
        dim=3,
        runner=runner,
    )
    assert calls == []
    assert counters["written"] == 0
    assert counters["eligible"] == 2
    assert counters["no_preview"] == 1
    assert counters["errors"] == 1


def test_apply_or_plan_apply_runs_batches_and_checkpoints(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(cmd, sql):
        calls.append((cmd, sql))
        return "INSERT 0 1\n"

    counters = apply_or_plan(
        _results(),
        apply=True,
        checkpoint_path=str(path),
        dim=3,
        batch_size=1,  # 2 eligible rows -> 2 batches
        runner=runner,
    )
    assert len(calls) == 2
    assert all(cmd == REMOTE_PSQL_APPLY for cmd, _sql in calls)
    assert "ON CONFLICT (catalog_id, model_name, model_version) DO NOTHING" in calls[0][1]
    assert counters["written"] == 2  # 1 per fake batch
    # written ids AND no_preview checkpointed after apply; the error row (4) is not
    assert load_checkpoint(str(path)) == {"1", "2", "3"}


def test_error_row_is_pulled_again_on_the_next_run(tmp_path):
    path = tmp_path / "cp.txt"
    apply_or_plan(
        _results(),
        apply=True,
        checkpoint_path=str(path),
        dim=3,
        runner=lambda cmd, sql: "INSERT 0 2\n",
    )
    candidates = [{"id": "3"}, {"id": "4"}]
    assert filter_new(candidates, load_checkpoint(str(path))) == [{"id": "4"}]


def test_loop_advances_cursor_and_stops_on_drain(tmp_path, monkeypatch, capsys):
    # the 3rd scripted pass pulls nothing past the cursor
    script = iter([PassResult(10, 100, 0, 0), PassResult(10, 250, 0, 0), PassResult(0, 250, 0, 0)])
    seen = []

    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        seen.append(after_id)
        return next(script)

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    bf.main(_loop_args(tmp_path))
    # cursor advances 0 -> 100 -> 250, then the empty pass ends the round
    assert seen == [0, 100, 250]
    assert "drained" in capsys.readouterr().out


def test_loop_stops_when_cursor_stalls(tmp_path, monkeypatch):
    # a window that pulls rows but does not advance max_id must not spin forever
    script = iter([PassResult(10, 100, 0, 0), PassResult(10, 100, 0, 0)])
    seen = []

    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        seen.append(after_id)
        return next(script)

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    bf.main(_loop_args(tmp_path))
    assert seen == [0, 100]  # 2nd pass: max_id (100) <= after_id (100) -> stop


def test_loop_window_defaults_when_no_limit(tmp_path, monkeypatch):
    limits = []

    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        limits.append(limit)
        return PassResult(0, after_id, 0, 0)  # drain immediately

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    bf.main(_loop_args(tmp_path, limit=0))
    assert limits == [bf.LOOP_WINDOW_DEFAULT]


def test_loop_retries_errors_after_cooldown(tmp_path, monkeypatch, capsys):
    # round 1 leaves errors -> cooldown -> round 2 restarts from the start and clears
    script = iter(
        [
            PassResult(10, 100, 0, 3),
            PassResult(0, 100, 0, 0),
            PassResult(3, 90, 0, 0),
            PassResult(0, 90, 0, 0),
        ]
    )
    seen = []
    sleeps = []

    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        seen.append(after_id)
        return next(script)

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    monkeypatch.setattr(bf.time, "sleep", sleeps.append)
    bf.main(_loop_args(tmp_path, apply=True, retry_cooldown=77))
    assert seen == [0, 100, 0, 90]
    assert sleeps == [77]
    assert "drained" in capsys.readouterr().out


def test_loop_gives_up_after_max_rounds_without_claiming_drained(
    tmp_path, monkeypatch, capsys
):
    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        if after_id == 0:
            return PassResult(10, 100, 0, 3)
        return PassResult(0, after_id, 0, 0)

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    monkeypatch.setattr(bf.time, "sleep", lambda s: None)
    bf.main(_loop_args(tmp_path, apply=True, max_rounds=2))
    out = capsys.readouterr().out
    assert "drained" not in out
    assert "3 still in error" in out


def test_loop_reports_checkpoint_skips_instead_of_drained(tmp_path, monkeypatch, capsys):
    # the original bug: every remaining row filtered by the checkpoint, "drained" printed
    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        if after_id == 0:
            return PassResult(10, 100, 10, 0)
        return PassResult(0, after_id, 0, 0)

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    monkeypatch.setattr(bf.time, "sleep", lambda s: pytest.fail("no retry expected"))
    bf.main(_loop_args(tmp_path, apply=True))
    out = capsys.readouterr().out
    assert "drained" not in out
    assert "10 skipped by the checkpoint" in out


def test_loop_dry_run_does_not_retry_errors(tmp_path, monkeypatch):
    seen = []

    def fake_run_pass(after_id, limit, workdir, cp, rp, args):
        seen.append(after_id)
        if after_id == 0:
            return PassResult(10, 100, 0, 3)
        return PassResult(0, after_id, 0, 0)

    monkeypatch.setattr(bf, "_run_pass", fake_run_pass)
    monkeypatch.setattr(bf.time, "sleep", lambda s: pytest.fail("no cooldown in dry-run"))
    bf.main(_loop_args(tmp_path, apply=False))
    assert seen == [0, 100]
