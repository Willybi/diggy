"""Unit tests for the PURE host-orchestrator logic (no network, no ssh, no Docker).

In the package, NOT under ``tests/`` (CI must not depend on this local-tooling package).
Run standalone from the repo root:

    pytest worker/discography_backfill/test_backfill_discography.py -q

The container-side walk (``bundle_driver.walk_and_bundle``) is tested in
``tests/worker/test_discography_bundle_driver.py``.
"""

import json

import pytest

from worker.discography_backfill.backfill_discography import (
    _tiers_sql,
    apply_or_plan,
    build_cohort_query,
    build_import_command,
    filter_new,
    load_checkpoint,
    parse_rows,
    parse_shard,
    summarize_bundle,
)


def test_build_cohort_query_defaults():
    sql = build_cohort_query()
    assert "COPY (" in sql
    assert "TO STDOUT WITH (FORMAT csv, HEADER true)" in sql
    # same strata CTE as the benchmark + cohort Signal-3 set predicate
    assert "sa.role = 'dj'" in sql
    assert "s.unreliable IS NOT TRUE" in sql
    assert "COALESCE(s.event_date, s.played_date)" in sql
    assert "a.deezer_id IS NOT NULL AND a.deezer_id <> 'NOT_FOUND'" in sql
    # default cohort = a_lib + b_sets12m
    assert "tier IN ('a_lib', 'b_sets12m')" in sql
    assert "ORDER BY artist_id" in sql
    # no windowing by default
    assert "LIMIT" not in sql
    assert "artist_id >" not in sql
    assert "artist_id %" not in sql


def test_build_cohort_query_windowing_and_tiers():
    sql = build_cohort_query(tiers="a_lib", after_id=500, shard=(1, 4))
    assert "tier IN ('a_lib')" in sql
    assert "AND artist_id > 500" in sql
    assert "AND artist_id % 4 = 1" in sql
    # --limit is NOT in SQL (applied host-side after the checkpoint filter)
    assert "LIMIT" not in sql


def test_tiers_sql_whitelist():
    assert _tiers_sql("a_lib,b_sets12m") == "'a_lib', 'b_sets12m'"
    assert _tiers_sql(" c_catalog ") == "'c_catalog'"
    for bad in ("", "nope", "a_lib,evil"):
        with pytest.raises(ValueError):
            _tiers_sql(bad)


def test_parse_shard():
    assert parse_shard(None) is None
    assert parse_shard("0/4") == (0, 4)
    for bad in ("1", "1/2/3", "4/4", "-1/4", "1/0", "a/2"):
        with pytest.raises(ValueError):
            parse_shard(bad)


def test_parse_rows():
    rows = parse_rows(
        "tier,artist_id,name,deezer_id\n"
        "a_lib,42,Bicep,123\n"
        "b_sets12m,7,Peggy Gou,\n"
    )
    assert rows[0] == {"tier": "a_lib", "artist_id": "42", "name": "Bicep", "deezer_id": "123"}
    assert rows[1]["deezer_id"] == ""


def test_filter_new_skips_checkpointed():
    rows = [{"artist_id": "1"}, {"artist_id": "2"}, {"artist_id": "3"}]
    assert filter_new(rows, {"2"}) == [{"artist_id": "1"}, {"artist_id": "3"}]


def _bundle_ndjson():
    return "\n".join([
        json.dumps({"artist_id": 1, "deezer_id": "9", "name": "A",
                    "tracks": [{"id": 11, "title": "T1"}, {"id": 12, "title": "T2"}],
                    "error": None}),
        json.dumps({"artist_id": 2, "deezer_id": "8", "name": "B",
                    "tracks": [], "error": "albums: boom"}),   # errored, no new
        json.dumps({"artist_id": 3, "deezer_id": "7", "name": "C", "tracks": []}),
        "{ not json",                                          # malformed
        json.dumps({"artist_id": True, "tracks": []}),        # bool id → malformed
        json.dumps({"tracks": []}),                            # missing id → malformed
        json.dumps({"artist_id": 5, "tracks": "notalist"}),   # non-list → malformed
        "",                                                    # blank, not counted
    ])


def test_summarize_bundle():
    processed, counts = summarize_bundle(_bundle_ndjson())
    # artist 2 carried an error → NOT checkpointed (retries next salvo); 1 and 3 clean
    assert processed == ["1", "3"]
    assert counts["artists"] == 3
    assert counts["with_new"] == 1              # only artist 1 has tracks
    assert counts["net_new_tracks"] == 2
    assert counts["errored"] == 1              # artist 2 carried an error
    assert counts["malformed"] == 4
    assert counts["total"] == 7                 # 7 non-blank lines


def test_build_import_command():
    assert build_import_command(False).endswith("import_discography.py")
    assert build_import_command(True).endswith("import_discography.py --apply")
    assert "docker compose exec -T api" in build_import_command(False)


def test_apply_or_plan_dry_run_no_checkpoint(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append(apply)
        return "=== DRY-RUN ===\n"

    apply_or_plan(_bundle_ndjson(), apply=False, checkpoint_path=str(path), runner=runner)
    assert calls == [False]                     # OPS invoked WITHOUT --apply
    assert load_checkpoint(str(path)) == set()  # dry-run checkpoints nothing


def test_apply_or_plan_apply_checkpoints(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append(apply)
        return "=== APPLY ===\n"

    apply_or_plan(_bundle_ndjson(), apply=True, checkpoint_path=str(path), runner=runner)
    assert calls == [True]
    # clean artists checkpointed after a successful apply; errored artist 2 retries later
    assert load_checkpoint(str(path)) == {"1", "3"}


def test_apply_or_plan_empty_short_circuits(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append(apply)
        return ""

    counts = apply_or_plan("\n  \n", apply=True, checkpoint_path=str(path), runner=runner)
    assert calls == []                          # OPS never invoked on an empty bundle
    assert counts["total"] == 0
    assert load_checkpoint(str(path)) == set()
