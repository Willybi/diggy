"""Unit tests for the PURE host-orchestrator logic (no network, no ssh, no Docker).

Deliberately placed in the package, NOT under ``tests/``: CI must not depend on
this local-tooling package (and ``resolve_driver.py`` reuses the server code, which
is only present inside the container). Run standalone from the repo root:

    pytest worker/set_artist_backfill/test_backfill_set_artists.py -q

The container-side pure resolution (``resolve_driver.resolve_set_links``) is tested
in ``tests/worker/test_backfill_set_artists_resolve.py`` (it needs the server modules).
"""

import json

import pytest

from worker.set_artist_backfill.backfill_set_artists import (
    apply_or_plan,
    build_alias_query,
    build_artist_query,
    build_import_command,
    build_worklist_query,
    filter_new,
    load_checkpoint,
    parse_rows,
    parse_shard,
    summarize_links,
)


def test_build_worklist_query_defaults():
    sql = build_worklist_query()
    assert "COPY (" in sql
    assert "FROM sets s" in sql
    # the fil-de-l'eau selection: trackid roots with no artist link yet
    assert "s.source = 'trackid'" in sql
    assert "s.parent_set_id IS NULL" in sql
    assert "NOT EXISTS (" in sql
    assert "FROM set_artists sa WHERE sa.set_id = s.id" in sql
    assert "ORDER BY s.id" in sql
    # no windowing by default
    assert "LIMIT" not in sql
    assert "s.id >" not in sql
    assert "s.id %" not in sql


def test_build_worklist_query_limit_after_id_shard():
    sql = build_worklist_query(limit=50, after_id=1234, shard=(1, 4))
    assert "LIMIT 50" in sql
    assert "AND s.id > 1234" in sql
    assert "AND s.id % 4 = 1" in sql


def test_build_artist_and_alias_queries():
    a = build_artist_query()
    assert "SELECT a.name, a.id AS artist_id FROM artists a" in a
    al = build_alias_query()
    assert "al.normalized_alias AS name" in al
    assert "FROM artist_aliases al" in al


def test_parse_shard():
    assert parse_shard(None) is None
    assert parse_shard("") is None
    assert parse_shard("0/4") == (0, 4)
    assert parse_shard("3/4") == (3, 4)
    for bad in ("1", "1/2/3", "4/4", "5/4", "-1/4", "1/0", "a/2"):
        with pytest.raises(ValueError):
            parse_shard(bad)


def test_parse_rows():
    rows = parse_rows(
        "id,title,channel\n"
        "1,Bicep - Live,Boiler Room\n"
        "2,Some Set,\n"
    )
    assert rows == [
        {"id": "1", "title": "Bicep - Live", "channel": "Boiler Room"},
        {"id": "2", "title": "Some Set", "channel": ""},
    ]


def test_filter_new_skips_checkpointed():
    rows = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert filter_new(rows, {"2"}) == [{"id": "1"}, {"id": "3"}]
    assert filter_new(rows, set()) == rows


def _links_ndjson():
    return "\n".join(
        [
            json.dumps(
                {
                    "set_id": 1,
                    "title": "Bicep",
                    "channel": None,
                    "links": [
                        {"source": "base", "name": "Bicep", "artist_id": 10},
                        {"source": "deezer", "name": "Guest", "deezer_id": "99"},
                    ],
                }
            ),
            json.dumps({"set_id": 2, "title": "No DJ", "channel": None, "links": []}),
            "{ this is not json",  # malformed line
            json.dumps({"set_id": True, "links": []}),  # bool id
            json.dumps({"title": "no id", "links": []}),  # missing id
            json.dumps({"set_id": 5, "links": "notalist"}),  # non-list links
            "",  # blank line skipped, not counted
        ]
    )


def test_summarize_links():
    processed, counts = summarize_links(_links_ndjson())
    assert processed == ["1", "2"]
    assert counts["sets_with_links"] == 1
    assert counts["sets_no_links"] == 1
    assert counts["base_links"] == 1
    assert counts["deezer_links"] == 1
    assert counts["malformed"] == 4  # bad json + bool id + missing id + non-list links
    assert counts["total"] == 6  # 6 non-blank lines; blank line not counted


def test_build_import_command():
    assert build_import_command(False).endswith("import_set_artists_matches.py")
    assert build_import_command(True).endswith("import_set_artists_matches.py --apply")
    assert "docker compose exec -T api" in build_import_command(False)


def test_apply_or_plan_dry_run_calls_ops_without_apply_and_no_checkpoint(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(ndjson_text, apply):
        calls.append((ndjson_text, apply))
        return "=== DRY-RUN ===\n"

    counts = apply_or_plan(
        _links_ndjson(), apply=False, checkpoint_path=str(path), runner=runner
    )
    assert len(calls) == 1
    assert calls[0][1] is False  # OPS invoked WITHOUT --apply
    assert counts["sets_with_links"] == 1
    # dry-run checkpoints NOTHING (nothing was written)
    assert load_checkpoint(str(path)) == set()


def test_apply_or_plan_apply_calls_ops_with_apply_and_checkpoints(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(ndjson_text, apply):
        calls.append((ndjson_text, apply))
        return "=== APPLY ===\n"

    apply_or_plan(
        _links_ndjson(), apply=True, checkpoint_path=str(path), runner=runner
    )
    assert len(calls) == 1
    assert calls[0][1] is True  # OPS invoked WITH --apply
    # every processed set id (with or without links) checkpointed after apply
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
