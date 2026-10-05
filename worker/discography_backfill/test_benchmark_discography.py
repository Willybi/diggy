"""Unit tests for the PURE host-orchestrator logic (no network, no ssh, no Docker).

Deliberately placed in the package, NOT under ``tests/``: CI must not depend on this
local-tooling package. Run standalone from the repo root:

    pytest worker/discography_backfill/test_benchmark_discography.py -q

The container-side walk (``fetch_driver.walk_discography``) is tested in
``tests/worker/test_discography_fetch_driver.py`` (host-importable — its server imports
are lazy).
"""

from worker.discography_backfill.benchmark_discography import (
    _stats,
    aggregate,
    build_catalog_index_query,
    build_sample_query,
    classify_record,
    format_report,
    load_identity_index,
    load_ndjson,
    parse_cohort_arg,
    project_cohort,
)

# ─────────────────────────── query builders ───────────────────────────

def test_build_sample_query_defaults():
    sql = build_sample_query()
    assert "COPY (" in sql
    assert "TO STDOUT WITH (FORMAT csv, HEADER true)" in sql
    # mutually-exclusive strata by descending depth
    assert "WHEN in_lib THEN 'a_lib'" in sql
    assert "WHEN set_count >= 5 THEN 'b_sets12m'" in sql
    assert "WHEN catalog_track_count >= 10 THEN 'c_catalog'" in sql
    assert "ELSE 'd_traine'" in sql
    # the cohort Signal-3 predicate (reliable DJ sets in 12m)
    assert "sa.role = 'dj'" in sql
    assert "s.parent_set_id IS NULL" in sql
    assert "s.unreliable IS NOT TRUE" in sql
    assert "COALESCE(s.event_date, s.played_date)" in sql
    # only fetchable artists
    assert "a.deezer_id IS NOT NULL AND a.deezer_id <> 'NOT_FOUND'" in sql
    # per-tier default 10, no seed, no traine filter
    assert "rn <= 10" in sql
    assert "setseed" not in sql
    assert "AND (set_count = 0" not in sql


def test_build_sample_query_seed_pertier_traine():
    sql = build_sample_query(per_tier=15, seed="0.42", traine_strict=True)
    # seeded draw = deterministic pure-SQL md5 shuffle, NOT a stdout-polluting setseed
    assert "setseed" not in sql
    assert "ORDER BY md5('0.42' || '|' || artist_id::text)" in sql
    assert "ORDER BY random()" not in sql
    assert "rn <= 15" in sql
    # traine tightening only affects d_traine
    assert "WHERE tier <> 'd_traine'" in sql
    assert "set_count = 0 AND catalog_track_count < 3 AND NOT in_lib" in sql


def test_build_sample_query_seed_quotes_escaped():
    # a single quote in the salt must be doubled (no SQL break)
    sql = build_sample_query(seed="a'b")
    assert "md5('a''b' || '|' || artist_id::text)" in sql


def test_build_catalog_index_query():
    sql = build_catalog_index_query()
    assert "SELECT normalized_key, coalesce(isrc, '') AS isrc FROM catalog" in sql
    assert "TO STDOUT WITH (FORMAT csv, HEADER true)" in sql


# ─────────────────────────── identity index ───────────────────────────

def test_load_identity_index_drops_empty_isrc():
    keys, isrcs = load_identity_index(
        "normalized_key,isrc\n"
        "cola - camelphat,GBAAA1700001\n"
        "some track - artist,\n"          # empty isrc dropped
        "another - x,USAAA1234567\n"
    )
    assert keys == {"cola - camelphat", "some track - artist", "another - x"}
    assert isrcs == {"GBAAA1700001", "USAAA1234567"}


# ─────────────────────────── classification ───────────────────────────

def _rec(tier="a_lib", tracks=None, error=None, n_requests=5):
    return {
        "artist_id": 1, "deezer_id": "9", "tier": tier, "name": "X",
        "n_requests": n_requests, "n_albums": 2,
        "tracks": tracks if tracks is not None else [], "error": error,
    }


def test_classify_key_only():
    keys = {"a - x", "b - x"}
    rec = _rec(tracks=[
        {"key": "a - x", "isrc": "I1", "title": "A"},   # in base by key
        {"key": "c - x", "isrc": "I2", "title": "C"},   # net-new
        {"key": "b - x", "isrc": None, "title": "B"},   # in base by key
    ])
    c = classify_record(rec, keys, {"I2"}, use_isrc=False)
    assert c == {"distinct": 3, "in_base": 2, "net_new": 1, "isrc_only": 0}


def test_classify_isrc_recovers_net_new_by_key():
    keys = {"a - x"}
    isrcs = {"I2"}  # track C is net-new by key but its isrc IS in base
    rec = _rec(tracks=[
        {"key": "a - x", "isrc": "I1", "title": "A"},   # in base by key
        {"key": "c - x", "isrc": "I2", "title": "C"},   # in base ONLY by isrc
        {"key": "d - x", "isrc": "I9", "title": "D"},   # net-new (neither)
    ])
    # key-only: C counts as net-new
    assert classify_record(rec, keys, isrcs, use_isrc=False)["net_new"] == 2
    # with isrc: C recovered, flagged isrc_only (the dupe the cheap path would create)
    c = classify_record(rec, keys, isrcs, use_isrc=True)
    assert c == {"distinct": 3, "in_base": 2, "net_new": 1, "isrc_only": 1}


# ─────────────────────────── stats + aggregate ───────────────────────────

def test_stats_basic_and_empty():
    assert _stats([]) == {"n": 0, "sum": 0, "mean": 0.0, "median": 0.0, "p90": 0, "max": 0}
    s = _stats([1, 2, 3, 4])
    assert s["n"] == 4 and s["sum"] == 10 and s["median"] == 2.5 and s["max"] == 4


def test_aggregate_per_tier_and_errored_excluded():
    keys = {"a - x"}
    records = [
        _rec(tier="a_lib", n_requests=10, tracks=[
            {"key": "a - x", "isrc": None, "title": "A"},   # in base
            {"key": "z - x", "isrc": None, "title": "Z"},   # net-new
        ]),
        _rec(tier="a_lib", n_requests=20, tracks=[
            {"key": "y - x", "isrc": None, "title": "Y"},   # net-new
        ]),
        # a fatal-error artist: no tracks → excluded from rate stats, counted errored
        _rec(tier="a_lib", error="albums: boom", tracks=[]),
        _rec(tier="d_traine", n_requests=4, tracks=[
            {"key": "n1 - x", "isrc": None, "title": "N1"},
            {"key": "n2 - x", "isrc": None, "title": "N2"},
        ]),
    ]
    agg = aggregate(records, keys, set(), use_isrc=False)
    a = agg["tiers"]["a_lib"]
    assert a["artists_sampled"] == 3
    assert a["artists_producing"] == 2
    assert a["artists_errored"] == 1
    assert a["sum_distinct"] == 3 and a["sum_in_base"] == 1 and a["sum_net_new"] == 2
    assert a["pct_in_base"] == round(100.0 / 3, 1)
    # requests median over producing artists only (10, 20) = 15
    assert a["requests_per_artist"]["median"] == 15
    d = agg["tiers"]["d_traine"]
    assert d["sum_net_new"] == 2 and d["pct_in_base"] == 0.0
    # overall spans every record
    assert agg["overall"]["artists_sampled"] == 4
    assert agg["overall"]["sum_net_new"] == 4


# ─────────────────────────── projection ───────────────────────────

def test_project_cohort_math():
    p = project_cohort(median_net_new=20, median_requests=30, cohort_size=1000, deezer_rate=1.0)
    assert p["projected_net_new"] == 20000
    assert p["projected_requests"] == 30000
    assert p["deezer_fetch_hours"] == round(30000 / 3600.0, 1)
    assert p["beatport_drain_days"] == round(20000 / 9900, 1)
    assert p["embedding_cpu_hours"] == round(20000 * 8.0 / 3600.0, 1)


def test_project_cohort_zero_rate_no_div0():
    p = project_cohort(10, 10, 100, deezer_rate=0)
    assert p["deezer_fetch_hours"] == 0.0


def test_parse_cohort_arg():
    assert parse_cohort_arg("") == {}
    assert parse_cohort_arg("a_lib=580,b_sets12m=971") == {"a_lib": 580, "b_sets12m": 971}
    assert parse_cohort_arg(" a_lib = 5 , ") == {"a_lib": 5}


# ─────────────────────────── ndjson + report smoke ───────────────────────────

def test_load_ndjson_skips_malformed(tmp_path):
    p = tmp_path / "d.ndjson"
    p.write_text(
        '{"artist_id": 1, "tier": "a_lib", "tracks": [{"key": "a - x"}]}\n'
        "{ not json\n"
        '{"artist_id": 2, "tracks": "notalist"}\n'   # tracks not a list → skipped
        "\n"
        '{"artist_id": 3, "tier": "d_traine", "tracks": []}\n',
        encoding="utf-8",
    )
    recs = load_ndjson(str(p))
    assert [r["artist_id"] for r in recs] == [1, 3]


def test_format_report_smoke():
    keys = {"a - x"}
    records = [_rec(tier="a_lib", tracks=[
        {"key": "a - x", "isrc": None, "title": "A"},
        {"key": "z - x", "isrc": None, "title": "Z"},
    ])]
    agg = aggregate(records, keys, set(), use_isrc=False)
    out = format_report(agg, deezer_rate=1.0, cohort_sizes=[500, 1000],
                        cohort_map={"a_lib": 580}, with_isrc=False)
    assert "DISCOGRAPHY BACKFILL BENCHMARK" in out
    assert "a_lib" in out
    assert "PROJECTIONS" in out
    assert "TOTAL cohort" in out  # cohort_map given → total line
