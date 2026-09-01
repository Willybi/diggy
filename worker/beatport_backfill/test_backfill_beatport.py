"""Unit tests for the PURE host-orchestrator logic (no network, no ssh, no Docker).

Deliberately placed in the package, NOT under ``tests/``: CI must not depend on
this local-tooling package (and ``scrape_driver.py`` imports the server code, which
is only present inside the container). Run standalone from the repo root:

    pytest worker/beatport_backfill/test_backfill_beatport.py -q
"""

import json

import pytest

from worker.beatport_backfill.backfill_beatport import (
    PRIORITY_BASELINE,
    apply_or_plan,
    build_import_command,
    build_pull_query,
    filter_new,
    load_checkpoint,
    parse_candidates,
    parse_shard,
    summarize_matches,
)


def test_build_pull_query_defaults():
    sql = build_pull_query()
    assert "COPY (" in sql
    assert "FROM catalog c" in sql
    # fresh Tier-1 only — E1 retries stay on the VPS
    assert "c.beatport_id IS NULL" in sql
    assert "c.beatport_searched_at IS NULL" in sql
    # M2M artist aggregation + flat fallback
    assert "LEFT JOIN catalog_artists ca" in sql
    assert "LEFT JOIN artists a" in sql
    assert "string_agg(a.name, ', ' ORDER BY ca.position)" in sql
    assert "c.artist AS flat_artist" in sql
    assert "GROUP BY c.id" in sql
    # C12 priority ordering
    assert f"coalesce(c.enrich_priority, {PRIORITY_BASELINE}) DESC" in sql
    assert "c.id DESC" in sql
    # no windowing by default
    assert "LIMIT" not in sql
    assert "c.id >" not in sql
    assert "c.id %" not in sql


def test_build_pull_query_limit_after_id_shard():
    sql = build_pull_query(limit=20, after_id=1234, shard=(1, 4))
    assert "LIMIT 20" in sql
    assert "AND c.id > 1234" in sql
    assert "AND c.id % 4 = 1" in sql


def test_parse_shard():
    assert parse_shard(None) is None
    assert parse_shard("") is None
    assert parse_shard("0/4") == (0, 4)
    assert parse_shard("3/4") == (3, 4)
    for bad in ("1", "1/2/3", "4/4", "5/4", "-1/4", "1/0", "a/2"):
        with pytest.raises(ValueError):
            parse_shard(bad)


def test_parse_candidates():
    rows = parse_candidates(
        "id,title,isrc,flat_artist,m2m_artists\n"
        "1,Glue,GB123,Bicep,Bicep\n"
        "2,Kerala,,Bonobo,\n"
    )
    assert rows == [
        {
            "id": "1", "title": "Glue", "isrc": "GB123",
            "flat_artist": "Bicep", "m2m_artists": "Bicep",
        },
        {
            "id": "2", "title": "Kerala", "isrc": "",
            "flat_artist": "Bonobo", "m2m_artists": "",
        },
    ]


def test_filter_new_skips_checkpointed():
    candidates = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert filter_new(candidates, {"2"}) == [{"id": "1"}, {"id": "3"}]
    assert filter_new(candidates, set()) == candidates


def _matches_ndjson():
    return "\n".join(
        [
            json.dumps({"catalog_id": 1, "status": "found", "bp_track": {"id": 9}}),
            json.dumps({"catalog_id": 2, "status": "not_found", "bp_track": None}),
            "{ this is not json",  # malformed line
            json.dumps({"catalog_id": True, "status": "found", "bp_track": {}}),  # bool id
            json.dumps({"status": "found", "bp_track": {}}),  # missing id
            json.dumps({"catalog_id": 5, "status": "weird"}),  # bad status
            "",  # blank line skipped, not counted
        ]
    )


def test_summarize_matches():
    processed, counts = summarize_matches(_matches_ndjson())
    assert processed == ["1", "2"]
    assert counts["found"] == 1
    assert counts["not_found"] == 1
    assert counts["malformed"] == 4  # bad json + bool id + missing id + bad status
    assert counts["total"] == 6  # 6 non-blank lines; blank line not counted


def test_build_import_command():
    assert build_import_command(False).endswith("import_beatport_matches.py")
    assert build_import_command(True).endswith("import_beatport_matches.py --apply")
    assert "docker compose exec -T api" in build_import_command(False)


def test_apply_or_plan_dry_run_calls_ops_without_apply_and_no_checkpoint(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(ndjson_text, apply):
        calls.append((ndjson_text, apply))
        return "=== DRY-RUN ===\nRead 2 NDJSON record(s)\n"

    counts = apply_or_plan(
        _matches_ndjson(), apply=False, checkpoint_path=str(path), runner=runner
    )
    assert len(calls) == 1
    assert calls[0][1] is False  # OPS invoked WITHOUT --apply
    assert counts["found"] == 1
    # dry-run checkpoints NOTHING (nothing was written)
    assert load_checkpoint(str(path)) == set()


def test_apply_or_plan_apply_calls_ops_with_apply_and_checkpoints(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(ndjson_text, apply):
        calls.append((ndjson_text, apply))
        return "=== APPLY ===\nDone.\n"

    counts = apply_or_plan(
        _matches_ndjson(), apply=True, checkpoint_path=str(path), runner=runner
    )
    assert len(calls) == 1
    assert calls[0][1] is True  # OPS invoked WITH --apply
    assert counts["not_found"] == 1
    # every processed (found/not_found) id checkpointed after a successful apply
    assert load_checkpoint(str(path)) == {"1", "2"}


def test_apply_or_plan_empty_ndjson_short_circuits(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(ndjson_text, apply):
        calls.append((ndjson_text, apply))
        return ""

    counts = apply_or_plan("\n  \n", apply=True, checkpoint_path=str(path), runner=runner)
    assert calls == []  # OPS never invoked on an empty NDJSON
    assert counts["total"] == 0
    assert load_checkpoint(str(path)) == set()
