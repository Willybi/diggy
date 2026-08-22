"""Unit tests for the at-scale eval PULL/parse/assembly logic (no network, no SSH).

Deliberately placed in the package, NOT under ``tests/``: CI has no diggy-vps SSH
and must not depend on this local-tooling package. Run standalone from the repo root:

    pytest worker/embedding_backfill/test_eval_at_scale.py -q
    pytest worker/embedding_backfill/ -q
"""

import numpy as np

from worker.embedding_backfill.eval_at_scale import (
    MODEL_NAME,
    MODEL_VERSION,
    REMOTE_PSQL_PULL,
    assemble_universe,
    build_embedding_query,
    build_universe_query,
    chunked,
    evaluate,
    fetch_embeddings,
    fetch_universe,
    parse_embeddings_csv,
    parse_universe,
    parse_vector_literal,
    run_remote_sql,
)

# --------------------------- pgvector literal parsing -----------------------


def test_parse_vector_literal_basic():
    v = parse_vector_literal("[0.1,0.2,-3.5]")
    assert isinstance(v, np.ndarray)
    assert v.dtype == np.float32
    np.testing.assert_allclose(v, [0.1, 0.2, -3.5], rtol=1e-6)


def test_parse_vector_literal_whitespace_and_spaces():
    # tolerate surrounding whitespace + spaces after commas
    v = parse_vector_literal("  [1.0, 2.0, 3.0]  ")
    np.testing.assert_allclose(v, [1.0, 2.0, 3.0], rtol=1e-6)


def test_parse_vector_literal_no_brackets():
    v = parse_vector_literal("1,2,3")
    np.testing.assert_allclose(v, [1.0, 2.0, 3.0], rtol=1e-6)


def test_parse_vector_literal_scientific_notation():
    v = parse_vector_literal("[1e-05,-2.5e3]")
    np.testing.assert_allclose(v, [1e-05, -2.5e3], rtol=1e-6)


def test_parse_vector_literal_unusable_returns_none():
    assert parse_vector_literal(None) is None
    assert parse_vector_literal("") is None
    assert parse_vector_literal("   ") is None
    assert parse_vector_literal("[]") is None
    assert parse_vector_literal("[not,a,number]") is None


# ------------------------- embeddings CSV -> {cid: vec} ----------------------


def test_parse_embeddings_csv():
    csv_text = (
        "catalog_id,embedding\n"
        '1,"[0.1,0.2,0.3]"\n'
        '2,"[1.0,2.0,3.0]"\n'
    )
    emb = parse_embeddings_csv(csv_text)
    assert set(emb) == {"1", "2"}
    np.testing.assert_allclose(emb["1"], [0.1, 0.2, 0.3], rtol=1e-6)
    np.testing.assert_allclose(emb["2"], [1.0, 2.0, 3.0], rtol=1e-6)


def test_parse_embeddings_csv_skips_bad_rows():
    csv_text = (
        "catalog_id,embedding\n"
        '1,"[0.1,0.2]"\n'
        '2,""\n'            # empty vector -> skipped
        ',"[9,9]"\n'        # missing id -> skipped
        '3,"[3.0,4.0]"\n'
    )
    emb = parse_embeddings_csv(csv_text)
    assert set(emb) == {"1", "3"}


# ------------------------------ universe assembly ---------------------------


def _sample_rows():
    # two sets; artists carry the cross-artist signal
    return [
        {"set_id": "10", "catalog_id": "1", "artist": "Alpha", "title": "a"},
        {"set_id": "10", "catalog_id": "2", "artist": "Beta", "title": "b"},
        {"set_id": "10", "catalog_id": "3", "artist": "Gamma", "title": "c"},
        {"set_id": "20", "catalog_id": "2", "artist": "Beta", "title": "b"},
        # 99 sampled but has NO embedding -> must be dropped from the universe
        {"set_id": "20", "catalog_id": "99", "artist": "Zeta", "title": "z"},
    ]


def test_assemble_universe_intersection_and_alignment():
    emb_map = {
        "1": np.array([1.0, 0.0], np.float32),
        "2": np.array([0.0, 1.0], np.float32),
        "3": np.array([1.0, 1.0], np.float32),
        # no "99" -> dropped
    }
    ids, V, artists = assemble_universe(_sample_rows(), emb_map, expected_dim=2)
    assert ids == ["1", "2", "3"]          # sorted by int, 99 absent (no embedding)
    assert V.shape == (3, 2)
    np.testing.assert_allclose(V[1], [0.0, 1.0])   # row aligned to ids[1] == "2"
    assert artists["2"] == "beta"                   # lower-cased
    assert artists["99"] == "zeta"                  # artists map keeps all rows


def test_assemble_universe_drops_wrong_dim():
    emb_map = {
        "1": np.array([1.0, 0.0], np.float32),
        "2": np.array([0.0, 1.0, 2.0], np.float32),  # wrong dim -> dropped
    }
    ids, V, _ = assemble_universe(_sample_rows(), emb_map, expected_dim=2)
    assert ids == ["1"]
    assert V.shape == (1, 2)


def test_assemble_universe_empty():
    ids, V, artists = assemble_universe(_sample_rows(), {}, expected_dim=2)
    assert ids == []
    assert V.shape == (0, 0)


# ------------------------------ SQL builders --------------------------------


def test_build_universe_query():
    sql = build_universe_query(n_sets=1500, min_tracks=8)
    assert "COPY (" in sql
    assert "parent_set_id IS NULL" in sql          # roots only
    assert "unreliable IS NOT TRUE" in sql         # reliable only (C8)
    assert "has_preview = true" in sql
    assert "deezer_id <> 'NOT_FOUND'" in sql
    assert "HAVING count(DISTINCT c.id) >= 8" in sql
    assert "LIMIT 1500" in sql
    assert "ORDER BY random()" in sql
    assert "TO STDOUT WITH (FORMAT csv, HEADER true)" in sql


def test_build_embedding_query():
    sql = build_embedding_query([3, 1, 2], model_name=MODEL_NAME, model_version=MODEL_VERSION)
    assert "FROM track_embeddings" in sql
    assert f"model_name = '{MODEL_NAME}'" in sql
    assert f"model_version = '{MODEL_VERSION}'" in sql
    assert "catalog_id IN (3, 1, 2)" in sql        # int-coerced, injection-safe
    assert "TO STDOUT WITH (FORMAT csv, HEADER true)" in sql


def test_build_embedding_query_coerces_ints():
    # string ids from the CSV are coerced to int literals (no quotes)
    sql = build_embedding_query(["10", "20"])
    assert "catalog_id IN (10, 20)" in sql


def test_chunked():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(chunked([], 3)) == []


def test_parse_universe():
    rows = parse_universe("set_id,catalog_id,artist,title\n10,1,Alpha,a\n10,2,Beta,b\n")
    assert rows == [
        {"set_id": "10", "catalog_id": "1", "artist": "Alpha", "title": "a"},
        {"set_id": "10", "catalog_id": "2", "artist": "Beta", "title": "b"},
    ]


# --------------------------- SSH / subprocess MOCKED ------------------------


def test_run_remote_sql_success(monkeypatch):
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = "set_id,catalog_id\n10,1\n"
        stderr = ""

    def fake_run(cmd, input, capture_output, text, encoding):  # noqa: A002
        captured["cmd"] = cmd
        captured["input"] = input
        return FakeProc()

    monkeypatch.setattr(
        "worker.embedding_backfill.eval_at_scale.subprocess.run", fake_run
    )
    out = run_remote_sql(REMOTE_PSQL_PULL, "SELECT 1;")
    assert out == "set_id,catalog_id\n10,1\n"
    assert captured["cmd"][0] == "ssh"
    assert captured["input"] == "SELECT 1;"


def test_run_remote_sql_failure_raises(monkeypatch):
    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(
        "worker.embedding_backfill.eval_at_scale.subprocess.run",
        lambda *a, **k: FakeProc(),
    )
    try:
        run_remote_sql(REMOTE_PSQL_PULL, "SELECT 1;")
    except RuntimeError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("expected RuntimeError on non-zero exit")


def test_fetch_universe_with_fake_runner():
    def runner(cmd, sql):
        assert cmd == REMOTE_PSQL_PULL
        assert "sampled_sets" in sql
        return "set_id,catalog_id,artist,title\n10,1,Alpha,a\n10,2,Beta,b\n"

    rows = fetch_universe(500, 8, runner=runner)
    assert [r["catalog_id"] for r in rows] == ["1", "2"]


def _ids_in_clause(sql):
    """Extract the integer ids from a ``catalog_id IN (a, b, c)`` clause."""
    inner = sql.split("catalog_id IN (", 1)[1].split(")", 1)[0]
    return [int(x) for x in inner.split(",")]


def test_fetch_embeddings_chunks_and_merges():
    calls = []

    def runner(cmd, sql):
        calls.append(sql)
        lines = ["catalog_id,embedding"]
        for cid in _ids_in_clause(sql):
            lines.append(f'{cid},"[{cid}.0,{cid}.0]"')
        return "\n".join(lines) + "\n"

    emb = fetch_embeddings([1, 2, 3, 4, 5], chunk=2, runner=runner)
    # 5 ids, chunk 2 -> 3 chunks
    assert len(calls) == 3
    assert set(emb) == {"1", "2", "3", "4", "5"}
    np.testing.assert_allclose(emb["3"], [3.0, 3.0], rtol=1e-6)


def test_fetch_embeddings_dedups_ids():
    calls = []

    def runner(cmd, sql):
        calls.append(sql)
        return "catalog_id,embedding\n"

    # duplicate ids collapse to a single sorted unique list, one chunk (<= 10)
    fetch_embeddings(["2", "2", "1", "1", "3"], chunk=10, runner=runner)
    assert len(calls) == 1
    assert "catalog_id IN (1, 2, 3)" in calls[0]


# --------------------- end-to-end eval on a synthetic universe --------------


def test_evaluate_reuses_embed_eval_on_synthetic_universe():
    """Smoke test the eval wiring (reuse of embed_eval) with no network.

    Build two clusters of near-identical vectors that co-occur inside the same
    set. Same-cluster (cross-artist) neighbours must score far above chance, so
    lift@1 > 1 and the shuffled control ≈ 1×.
    """
    rng = np.random.RandomState(0)

    def unit(v):
        return (v / np.linalg.norm(v)).astype(np.float32)

    # cluster A near [1,0,0,0], cluster B near [0,1,0,0]; each track a distinct
    # artist. eval_scorer indexes into the top-50, so keep the universe > 50.
    ids, rows, vecs = [], [], {}
    base = {"A": np.array([1, 0, 0, 0.0]), "B": np.array([0, 1, 0, 0.0])}
    per_cluster = 40
    cid = 0
    for cluster, setid in (("A", "100"), ("B", "200")):
        for _ in range(per_cluster):
            cid += 1
            c = str(cid)
            ids.append(c)
            vecs[c] = unit(base[cluster] + 0.01 * rng.randn(4))
            rows.append(
                {"set_id": setid, "catalog_id": c, "artist": f"artist{cid}", "title": c}
            )

    uids, V, artists = assemble_universe(rows, vecs, expected_dim=4)
    assert len(uids) == 2 * per_cluster
    res = evaluate(rows, uids, V, artists)

    assert res["universe"] == 2 * per_cluster
    assert res["n_seeds_xart"] > 0
    # a real content signal: cross-artist lift@1 well above chance
    assert res["lift_xart"][1] > 1.0
    # shuffled control kills the signal (~1×, allow slack on a tiny universe)
    assert res["shuf10"] < res["lift_xart"][10]
    # hit-rate keys present
    assert set(res["hit"]) == {10, 20, 50}
    assert "xart_ci10" in res and len(res["xart_ci10"]) == 2
