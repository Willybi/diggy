"""Unit tests for the PURE host-orchestrator logic of the L2 clean-hydration tool
(no network, no ssh, no Docker, no Essentia).

Deliberately placed in the package, NOT under ``tests/``: CI must not depend on this
local-tooling package (and enrich_driver.py imports the server code, only present
inside the container). Run standalone from the repo root:

    pytest worker/trackid_hydrate/test_hydrate.py -q
"""

import json

from worker.trackid_hydrate.hydrate import (
    DRIVER_CSV_FIELDS,
    DetailFetcher,
    _bundle_ids,
    _trim_deezer,
    append_checkpoint,
    assemble_bundle,
    build_driver_rows,
    build_tracklist,
    build_worklist_query,
    filter_new,
    is_id_track,
    load_checkpoint,
    merge_tracklist,
    parse_driver_output,
    parse_worklist,
    push_bundle,
)

# ── worklist SQL ──


def test_build_worklist_query_defaults():
    sql = build_worklist_query()
    assert "COPY (" in sql
    assert "FROM trackid_index" in sql
    # only not-hydrated, scored sets, highest score first
    assert "hydration_state = 'not_hydrated'" in sql
    assert "score IS NOT NULL" in sql
    assert "ORDER BY score DESC, trackid_id DESC" in sql
    # no windowing by default
    assert "LIMIT" not in sql
    assert "score <" not in sql


def test_build_worklist_query_limit_and_after_score():
    sql = build_worklist_query(limit=20, after_score=87.5)
    assert "LIMIT 20" in sql
    assert "AND score < 87.5" in sql


def test_build_worklist_query_after_score_zero_is_emitted():
    # 0.0 is a legitimate bound (score >= 0), so it must NOT be treated as "no bound"
    sql = build_worklist_query(after_score=0.0)
    assert "AND score < 0.0" in sql


# ── worklist parsing ──


def test_parse_worklist():
    rows = parse_worklist(
        "trackid_id,slug,score\n"
        "101,some-set,90\n"
        "102,other-set,72.5\n"
    )
    assert rows == [
        {"trackid_id": "101", "slug": "some-set", "score": "90"},
        {"trackid_id": "102", "slug": "other-set", "score": "72.5"},
    ]
    assert set(rows[0]) == {"trackid_id", "slug", "score"}


# ── checkpoint filtering ──


def test_filter_new_skips_checkpointed():
    rows = [{"trackid_id": "1"}, {"trackid_id": "2"}, {"trackid_id": "3"}]
    assert filter_new(rows, {"2"}) == [{"trackid_id": "1"}, {"trackid_id": "3"}]
    assert filter_new(rows, set()) == rows


def test_load_and_append_checkpoint(tmp_path):
    path = tmp_path / "cp.txt"
    assert load_checkpoint(str(path)) == set()
    append_checkpoint(str(path), ["10", "11"])
    append_checkpoint(str(path), [])  # no-op
    assert load_checkpoint(str(path)) == {"10", "11"}


# ── prod-faithful helpers (recopied from shadow) ──


def test_is_id_track():
    assert is_id_track("ID", "ID") is True
    assert is_id_track("", None) is True
    assert is_id_track(None, "Someone") is True  # blank title → id
    assert is_id_track("Glue", "Bicep") is False


def test_merge_tracklist_dedups_on_mtid():
    detail = {
        "detectionProcesses": [
            {
                "detectionProcessMusicTracks": [
                    {"musicTrackId": 1, "title": "A", "artist": "X"},
                    {"musicTrackId": 2, "title": "B", "artist": "Y"},
                ]
            },
            {
                "detectionProcessMusicTracks": [
                    {"musicTrackId": 1, "title": "A dup", "artist": "X"},  # dropped
                    {"musicTrackId": None, "title": "no mtid"},            # dropped
                ]
            },
        ]
    }
    merged = merge_tracklist(detail)
    assert [t["musicTrackId"] for t in merged] == [1, 2]
    assert merged[0]["title"] == "A"  # first seen kept


# ── tracklist build ──


def test_build_tracklist():
    detail = {
        "detectionProcesses": [
            {
                "detectionProcessMusicTracks": [
                    {
                        "musicTrackId": 7, "title": "Glue", "artist": "Bicep",
                        "startTime": "00:01:00", "endTime": "00:04:00", "label": "Ninja",
                    },
                    {"musicTrackId": 8, "title": "ID", "artist": "ID"},
                ]
            }
        ]
    }
    tl = build_tracklist(detail)
    assert [t["position"] for t in tl] == [1, 2]
    assert tl[0] == {
        "position": 1, "raw_title": "Glue", "raw_artist": "Bicep", "is_id": False,
        "musicTrackId": 7, "startTime": "00:01:00", "endTime": "00:04:00",
        "label": "Ninja",
    }
    assert tl[1]["is_id"] is True  # ID - ID track flagged
    assert tl[1]["label"] is None  # absent field → None


# ── driver CSV build ──


def test_build_driver_rows():
    tracklist = [
        {"position": 1, "raw_title": "Glue", "raw_artist": "Bicep", "is_id": False},
        {"position": 2, "raw_title": None, "raw_artist": None, "is_id": True},
    ]
    rows = build_driver_rows(101, tracklist)
    assert rows == [
        {"set_trackid_id": 101, "position": 1, "title": "Glue",
         "artist": "Bicep", "is_id": "0"},
        {"set_trackid_id": 101, "position": 2, "title": "",
         "artist": "", "is_id": "1"},
    ]
    # every row carries exactly the driver CSV contract keys
    assert all(set(r) == set(DRIVER_CSV_FIELDS) for r in rows)


# ── driver output parsing ──


def test_parse_driver_output():
    ndjson = "\n".join(
        [
            json.dumps({"set_trackid_id": 101, "position": 1, "status": "found",
                        "deezer": {"track": {"id": 9}}}),
            json.dumps({"set_trackid_id": 101, "position": 2, "status": "not_found",
                        "deezer": None}),
            "{ not json",                                        # malformed → skipped
            json.dumps(["not", "a", "dict"]),                   # non-dict → skipped
            json.dumps({"set_trackid_id": None, "position": 3}),  # bad key → skipped
            "",                                                 # blank → skipped
        ]
    )
    index = parse_driver_output(ndjson)
    assert set(index) == {(101, 1), (101, 2)}
    assert index[(101, 1)]["status"] == "found"


# ── deezer trim ──


def test_trim_deezer_keeps_only_contract_fields():
    dz = {
        "track": {"id": 9, "isrc": "GB1"},
        "preview_url": "http://p",       # dropped
        "cover_catalog_url": "http://c",  # dropped
        "cover_album_url": "http://a",    # dropped
        "cover_catalog_b64": "AAA",
        "cover_album_b64": "BBB",
    }
    assert _trim_deezer(dz) == {
        "track": {"id": 9, "isrc": "GB1"},
        "cover_catalog_b64": "AAA",
        "cover_album_b64": "BBB",
    }
    assert _trim_deezer(None) is None
    assert _trim_deezer("nope") is None


# ── bundle assembly (the join) ──


def _tracklist_three():
    return [
        {"position": 1, "raw_title": "Glue", "raw_artist": "Bicep", "is_id": False,
         "musicTrackId": 7, "startTime": "00:01:00", "endTime": None, "label": "Ninja"},
        {"position": 2, "raw_title": "ID", "raw_artist": "ID", "is_id": True,
         "musicTrackId": None, "startTime": None, "endTime": None, "label": None},
        {"position": 3, "raw_title": "Kerala", "raw_artist": "Bonobo", "is_id": False,
         "musicTrackId": 8, "startTime": "00:05:00", "endTime": None, "label": None},
    ]


def test_assemble_bundle_joins_and_trims():
    set_row = {"trackid_id": "101", "slug": "the-set", "score": "88.4"}
    detail = {"id": 101, "title": "The Set", "artworkUrl": "http://cover"}
    driver_index = {
        # position 1 found → enriched (deezer trimmed)
        (101, 1): {
            "set_trackid_id": 101, "position": 1, "status": "found",
            "deezer": {"track": {"id": 9}, "preview_url": "http://p",
                       "cover_catalog_b64": "CAT", "cover_album_b64": "ALB"},
            "beatport": {"bp_track": {"id": 5, "key": "8A"}},
            "bpm": {"value": 124.0, "conf": 3.1}, "key": "8A",
            "embedding": [0.1, 0.2],
        },
        # position 3 not_found → all null
        (101, 3): {
            "set_trackid_id": 101, "position": 3, "status": "not_found", "deezer": None,
        },
        # position 2 (the id track) has NO driver line here on purpose
    }
    bundle = assemble_bundle(
        set_row, detail, _tracklist_three(), driver_index, set_artwork_b64="SETB64"
    )

    # top-level contract
    assert bundle["trackid_id"] == 101          # coerced to int
    assert bundle["slug"] == "the-set"
    assert bundle["score"] == 88.4              # coerced to float
    assert bundle["detail"] is detail
    assert bundle["set_artwork_b64"] == "SETB64"
    assert len(bundle["tracks"]) == 3

    # position 1: enriched, deezer TRIMMED to the 3 contract fields
    t1 = bundle["tracks"][0]
    assert t1["deezer"] == {
        "track": {"id": 9}, "cover_catalog_b64": "CAT", "cover_album_b64": "ALB"
    }
    assert "preview_url" not in t1["deezer"]
    assert t1["beatport"] == {"bp_track": {"id": 5, "key": "8A"}}
    assert t1["bpm"] == {"value": 124.0, "conf": 3.1}
    assert t1["key"] == "8A"
    assert t1["embedding"] == [0.1, 0.2]
    # tracklist metadata preserved
    assert t1["musicTrackId"] == 7 and t1["label"] == "Ninja"

    # position 2: is_id track with no driver line → fully null
    t2 = bundle["tracks"][1]
    assert t2["is_id"] is True
    assert (t2["deezer"], t2["beatport"], t2["bpm"], t2["key"], t2["embedding"]) == (
        None, None, None, None, None
    )

    # position 3: not_found driver line → fully null (record still present)
    t3 = bundle["tracks"][2]
    assert t3["raw_title"] == "Kerala"
    assert (t3["deezer"], t3["beatport"], t3["bpm"], t3["key"], t3["embedding"]) == (
        None, None, None, None, None
    )


def test_assemble_bundle_track_without_driver_line_is_null():
    # a Deezer outage → NO driver line for that (set, position) → all enrichment null
    set_row = {"trackid_id": "5", "slug": "s", "score": ""}
    tl = [
        {"position": 1, "raw_title": "A", "raw_artist": "X", "is_id": False,
         "musicTrackId": 1, "startTime": None, "endTime": None, "label": None},
    ]
    bundle = assemble_bundle(set_row, {"id": 5}, tl, driver_index={}, set_artwork_b64=None)
    assert bundle["score"] is None            # blank score → null
    assert bundle["set_artwork_b64"] is None
    t = bundle["tracks"][0]
    assert t["deezer"] is None and t["embedding"] is None


# ── push gating (mirror of backfill apply_or_plan) ──


_BUNDLE = json.dumps({"trackid_id": 101, "slug": "s", "tracks": []}) + "\n"


def test_push_default_local_dry_run_no_ssh_no_checkpoint(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append((text, apply))
        return "should not run"

    push_bundle(
        _BUNDLE, ["101"], apply=False, dry_run_push=False,
        checkpoint_path=str(path), runner=runner,
    )
    assert calls == []                       # NO ssh in the local default
    assert load_checkpoint(str(path)) == set()


def test_push_dry_run_push_calls_ops_without_apply_no_checkpoint(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append((text, apply))
        return "=== OPS DRY-RUN ===\n"

    push_bundle(
        _BUNDLE, ["101"], apply=False, dry_run_push=True,
        checkpoint_path=str(path), runner=runner,
    )
    assert len(calls) == 1
    assert calls[0][1] is False              # OPS invoked WITHOUT --apply
    assert load_checkpoint(str(path)) == set()  # nothing written → nothing checkpointed


def test_push_apply_calls_ops_with_apply_and_checkpoints(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append((text, apply))
        return "=== OPS APPLY ===\n"

    push_bundle(
        _BUNDLE, ["101", "102"], apply=True, dry_run_push=False,
        checkpoint_path=str(path), runner=runner,
    )
    assert len(calls) == 1
    assert calls[0][1] is True               # OPS invoked WITH --apply
    assert load_checkpoint(str(path)) == {"101", "102"}


def test_push_empty_bundle_short_circuits(tmp_path):
    path = tmp_path / "cp.txt"
    calls = []

    def runner(text, apply):
        calls.append((text, apply))
        return ""

    push_bundle(
        "\n  \n", [], apply=True, dry_run_push=False,
        checkpoint_path=str(path), runner=runner,
    )
    assert calls == []                       # OPS never invoked on an empty bundle
    assert load_checkpoint(str(path)) == set()


# ── reuse-bundle id extraction ──


def test_bundle_ids():
    text = "\n".join(
        [
            json.dumps({"trackid_id": 101, "tracks": []}),
            json.dumps({"trackid_id": 102, "tracks": []}),
            "{ not json",                        # skipped
            json.dumps({"no_id": 1}),            # skipped (no trackid_id)
            "",
        ]
    )
    assert _bundle_ids(text) == ["101", "102"]


# ── DetailFetcher (injected getter/sleep — no network) ──


def test_detail_fetcher_success_returns_result():
    calls = {"n": 0}

    def getter(url):
        calls["n"] += 1
        assert url.endswith("/audiostreams/the-slug")
        return 200, json.dumps({"result": {"id": 101, "title": "T"}}).encode(), {}

    f = DetailFetcher(6.0, getter=getter, sleep=lambda _s: None)
    assert f.fetch("the-slug") == {"id": 101, "title": "T"}
    assert calls["n"] == 1
    assert f.throttled == 0


def test_detail_fetcher_throttle_then_success():
    seq = [
        (429, b"", {"Retry-After": "1"}),
        (200, json.dumps({"result": {"id": 5}}).encode(), {}),
    ]
    slept = []

    def getter(url):
        return seq.pop(0)

    f = DetailFetcher(6.0, getter=getter, sleep=slept.append)
    assert f.fetch("s") == {"id": 5}
    assert f.throttled == 1
    assert slept                       # cooled off before the retry


def test_detail_fetcher_non_200_returns_none():
    f = DetailFetcher(6.0, getter=lambda url: (500, b"", {}), sleep=lambda _s: None)
    assert f.fetch("s") is None


def test_detail_fetcher_network_error_returns_none():
    def getter(url):
        raise OSError("boom")

    f = DetailFetcher(6.0, getter=getter, sleep=lambda _s: None)
    assert f.fetch("s") is None
