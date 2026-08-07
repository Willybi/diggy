"""Unit tests for the PURE orchestrator logic (no Essentia, no network, no SSH).

Deliberately placed in the package, NOT under ``tests/``: CI has no Essentia and
must not depend on this local-tooling package. Run standalone from the repo root:

    pytest worker/bpm_backfill/test_backfill_bpm.py -q
"""

from worker.bpm_backfill.backfill_bpm import (
    REMOTE_PSQL_APPLY,
    apply_or_plan,
    build_pull_query,
    build_update_batches,
    eligible_updates,
    filter_new,
    load_checkpoint,
    parse_candidates,
    parse_update_count,
    reject_ids,
)


def test_build_pull_query_no_limit():
    sql = build_pull_query()
    assert "COPY (" in sql
    assert "has_preview = true" in sql
    assert "bpm IS NULL" in sql
    assert "deezer_id IS NOT NULL" in sql
    assert "deezer_id <> 'NOT_FOUND'" in sql
    assert "LIMIT" not in sql
    # beatport_id is deliberately NOT filtered (product decision)
    assert "beatport_id" not in sql


def test_build_pull_query_limit():
    assert "LIMIT 20" in build_pull_query(20)


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
    return [
        {"id": "1", "bpm": "128.0", "conf": "3.12", "status": "ok"},
        {"id": "2", "bpm": "174.1", "conf": "2.0", "status": "ok"},  # boundary
        {"id": "3", "bpm": "", "conf": "1.4", "status": "low_conf"},
        {"id": "4", "bpm": "", "conf": "", "status": "no_preview"},
        {"id": "5", "bpm": "", "conf": "", "status": "error:RuntimeError"},
        # defensive: "ok" but below the gate must NOT be written
        {"id": "6", "bpm": "90.0", "conf": "1.9", "status": "ok"},
        # defensive: "ok" but empty bpm must NOT be written
        {"id": "7", "bpm": "", "conf": "2.5", "status": "ok"},
    ]


def test_eligible_updates_gate():
    pairs = eligible_updates(_results(), min_conf=2.0)
    assert pairs == [(1, 128.0), (2, 174.1)]  # conf >= 2.0 inclusive


def test_reject_ids_final_statuses_only():
    # low_conf / no_preview / error:* are final; "ok" rows are not rejects
    assert reject_ids(_results()) == ["3", "4", "5"]


def test_build_update_batches_sql_shape():
    batches = build_update_batches([(1, 128.0), (2, 174.12)])
    assert len(batches) == 1
    sql, ids = batches[0]
    assert "bpm_source = 'analysis'" in sql
    assert "WHERE c.id = v.id AND c.bpm IS NULL" in sql  # idempotence/race guard
    assert "(1, 128.0)" in sql
    assert "(2, 174.1)" in sql  # bpm rendered at 1 decimal
    assert ids == ["1", "2"]


def test_build_update_batches_batching_and_empty():
    pairs = [(i, 120.0) for i in range(1, 8)]
    batches = build_update_batches(pairs, batch_size=3)
    assert [len(ids) for _sql, ids in batches] == [3, 3, 1]
    assert batches[2][1] == ["7"]
    assert build_update_batches([]) == []


def test_parse_update_count():
    assert parse_update_count("UPDATE 500\nUPDATE 12\n") == 512
    assert parse_update_count("") == 0
    assert parse_update_count("SET\nTimings on\n") == 0


def test_checkpoint_roundtrip(tmp_path):
    path = tmp_path / "processed_ids.txt"
    assert load_checkpoint(str(path)) == set()
    counters = apply_or_plan(
        _results(), apply=False, checkpoint_path=str(path), runner=None
    )
    assert counters["eligible"] == 2
    # dry-run: rejects checkpointed, eligible ids NOT (they still need writing)
    assert load_checkpoint(str(path)) == {"3", "4", "5"}


def test_apply_or_plan_dry_run_never_calls_runner(tmp_path):
    calls = []

    def runner(cmd, sql):
        calls.append((cmd, sql))
        return "UPDATE 999\n"

    counters = apply_or_plan(
        _results(),
        apply=False,
        checkpoint_path=str(tmp_path / "cp.txt"),
        runner=runner,
    )
    assert calls == []
    assert counters["written"] == 0
    assert counters["eligible"] == 2
    assert counters["low_conf"] == 1
    assert counters["no_preview"] == 1
    assert counters["errors"] == 1


def test_apply_or_plan_apply_runs_batches_and_checkpoints(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(cmd, sql):
        calls.append((cmd, sql))
        return "UPDATE 1\n"

    counters = apply_or_plan(
        _results(),
        apply=True,
        checkpoint_path=str(path),
        batch_size=1,  # 2 eligible rows -> 2 batches
        runner=runner,
    )
    assert len(calls) == 2
    assert all(cmd == REMOTE_PSQL_APPLY for cmd, _sql in calls)
    assert "AND c.bpm IS NULL" in calls[0][1]
    assert counters["written"] == 2  # 1 per fake batch
    # written ids AND rejects both checkpointed after apply
    assert load_checkpoint(str(path)) == {"1", "2", "3", "4", "5"}
