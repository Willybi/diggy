"""Unit tests for the hybrid-bonus calibration eval (no network, no SSH).

Deliberately placed in the package, NOT under ``tests/``: CI (``pytest tests/``,
``testpaths = ["tests"]``) has no diggy-vps SSH and must not depend on this
local-tooling package. Run standalone from the repo root:

    pytest worker/embedding_backfill/test_eval_hybrid.py -q
    pytest worker/embedding_backfill/ -q
"""

import numpy as np

from worker.embedding_backfill.eval_hybrid import (
    RETRIEVAL_COOC_CAP,
    RETRIEVAL_KNN_K,
    _parse_bonus_grid,
    _recommend,
    build_meta,
    build_retrieval_universes,
    build_universe_query,
    build_variants,
    evaluate,
    masked_scorer,
    parse_universe,
)

# ------------------------------ SQL builder ---------------------------------


def test_build_universe_query_is_rich_and_reliable():
    sql = build_universe_query(n_sets=1500, min_tracks=8)
    assert "COPY (" in sql
    assert "parent_set_id IS NULL" in sql  # roots only
    assert "unreliable IS NOT TRUE" in sql  # reliable only (C8)
    assert "has_preview = true" in sql
    assert "deezer_id <> 'NOT_FOUND'" in sql
    assert "HAVING count(DISTINCT c.id) >= 8" in sql
    assert "LIMIT 1500" in sql
    # the RICH columns the metadata channel + excluder read
    assert "c.bpm" in sql and "c.key" in sql and "c.release_date" in sql
    assert "c.label" in sql
    assert "array_to_string(c.genres, '|')" in sql
    assert "c.isrc" in sql and "c.normalized_key" in sql
    assert "TO STDOUT WITH (FORMAT csv, HEADER true)" in sql


def test_parse_universe_and_build_meta():
    rows = parse_universe(
        "set_id,catalog_id,artist,bpm\n10,1,Alpha,128\n10,2,Beta,120\n20,1,Alpha,128\n"
    )
    assert [r["catalog_id"] for r in rows] == ["1", "2", "1"]
    meta = build_meta(rows)
    assert set(meta) == {"1", "2"}
    assert meta["1"]["bpm"] == "128"  # first occurrence kept


# ------------------------------ bonus grid ----------------------------------


def test_parse_bonus_grid_sorts_dedups_drops_nonpositive():
    assert _parse_bonus_grid("2,0.5,1,2,0,0.5,-3") == (0.5, 1.0, 2.0)
    assert _parse_bonus_grid(" 4 , 0.25 ") == (0.25, 4.0)
    assert _parse_bonus_grid("0,-1") == ()


# --------------------------- retrieval universe -----------------------------


def _unit_rows_and_V():
    """Two tight clusters (A near e0, B near e1); each track a distinct artist.

    Cluster A = set 100, cluster B = set 200 → co-occurrence is intra-cluster.
    """
    rng = np.random.RandomState(0)

    def unit(v):
        return (v / np.linalg.norm(v)).astype(np.float32)

    base = {"A": np.array([1, 0, 0, 0.0]), "B": np.array([0, 1, 0, 0.0])}
    ids, rows, vecs = [], [], {}
    cid = 0
    for cluster, setid in (("A", "100"), ("B", "200")):
        for _ in range(30):
            cid += 1
            c = str(cid)
            ids.append(c)
            vecs[c] = unit(base[cluster] + 0.01 * rng.randn(4))
            rows.append(
                {"set_id": setid, "catalog_id": c, "artist": f"artist{cid}", "title": c}
            )
    V = np.vstack([vecs[c] for c in ids]).astype(np.float32)
    return ids, rows, V, vecs


def test_build_retrieval_universes_knn_and_cooc():
    ids = ["1", "2", "3", "4"]
    # 1 & 2 identical direction, 3 & 4 orthogonal
    V = np.array(
        [[1, 0.0], [1, 0.0], [0, 1.0], [0, 1.0]], np.float32
    )
    partners = {"1": {"3"}, "3": {"1"}}  # a co-occurrence link 1<->3
    uni = build_retrieval_universes(V, ids, partners, knn_k=1, cooc_cap=10)
    # seed 0 ("1"): KNN top-1 = index 1 ("2", identical) ∪ co-occ index 2 ("3")
    assert set(uni[0].tolist()) == {1, 2}
    assert 0 not in uni[0].tolist()  # seed excluded


def test_build_retrieval_universes_cooc_cap():
    ids = [str(i) for i in range(1, 6)]
    V = np.eye(5, dtype=np.float32)[:, :4] if False else np.random.RandomState(1).randn(5, 4).astype(np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    partners = {"1": {"2", "3", "4", "5"}}
    uni = build_retrieval_universes(V, ids, partners, knn_k=0, cooc_cap=2)
    # knn_k=0 → only co-occ, capped at 2 in ascending id order → "2","3" = idx 1,2
    assert set(uni[0].tolist()) == {1, 2}


def test_masked_scorer_confines_to_universe():
    universes = {0: np.array([2, 3], np.int64)}
    base = lambda si: np.array([10.0, 9.0, 8.0, 7.0], np.float32)  # noqa: E731
    fn = masked_scorer(base, universes)
    s = fn(0)
    assert s[0] == -np.inf and s[1] == -np.inf  # outside universe
    assert s[2] == 8.0 and s[3] == 7.0  # inside
    # empty / missing universe → skip the seed
    assert masked_scorer(base, {0: np.empty(0, np.int64)})(0) is None
    assert masked_scorer(base, {})(0) is None


# ------------------------------- variants -----------------------------------


def test_build_variants_shape():
    ee = __import__(
        "worker.embedding_backfill.eval_at_scale", fromlist=["_import_embed_eval"]
    )._import_embed_eval()
    ids, rows, V, _ = _unit_rows_and_V()
    meta = build_meta(rows)
    feats = ee.build_feats(ids, meta, {}, {})
    feats["artist_ids"] = ee._factorize([f"artist{i}" for i in range(len(ids))])
    variants = build_variants(feats, V, (0.5, 2.0))
    names = [v[0] for v in variants]
    assert names == ["meta", "hybrid@0.5", "hybrid@2", "audio"]
    # meta bonus 0, hybrids carry their bonus, audio None
    assert variants[0][3] == 0.0
    assert variants[1][3] == 0.5 and variants[2][3] == 2.0
    assert variants[-1][3] is None
    # hybrid = gower + b*emb: at b=2 the score differs from meta (b=0)
    s_meta = variants[0][1](0)
    s_hyb = variants[2][1](0)
    assert not np.allclose(s_meta, s_hyb)


# --------------------------- recommendation ---------------------------------


def test_recommend_picks_best_lift_and_parsimony():
    variants = {
        "meta": {"is_hybrid": False, "bonus": 0.0, "lift_xart": {10: 2.0},
                 "hit": {50: 0.4}, "xart_ci10": [1.8, 2.2]},
        "hybrid@0.5": {"is_hybrid": True, "bonus": 0.5, "lift_xart": {10: 3.0},
                       "hit": {50: 0.5}, "xart_ci10": [2.8, 3.2]},
        "hybrid@1": {"is_hybrid": True, "bonus": 1.0, "lift_xart": {10: 3.1},
                     "hit": {50: 0.55}, "xart_ci10": [2.9, 3.3]},
        "audio": {"is_hybrid": False, "bonus": None, "lift_xart": {10: 2.5},
                  "hit": {50: 0.45}, "xart_ci10": [2.3, 2.7]},
    }
    rec = _recommend(variants)
    assert rec["best_bonus"] == 1.0  # max lift@10 among hybrids
    assert rec["best_variant"] == "hybrid@1"
    # 0.5's lift@10 (3.0) >= winner CI95 low (2.9) → parsimonious = 0.5
    assert rec["parsimonious_bonus"] == 0.5
    # audio adds ~55% over the meta baseline (3.1 / 2.0 - 1)
    assert abs(rec["audio_adds_pct"] - 55.0) < 1e-6


# --------------------- end-to-end eval on a synthetic universe --------------


def test_evaluate_end_to_end_synthetic():
    """Smoke the full wiring (retrieval + variants + embed_eval metric) offline.

    Same two-cluster construction as eval_at_scale's smoke test: same-cluster
    (cross-artist) neighbours co-occur, so the audio channel lifts cross-artist
    co-occurrence far above chance — the hybrid must beat meta-only here.
    """
    ids, rows, V, vecs = _unit_rows_and_V()
    artists = {c: f"artist{c}" for c in ids}
    res = evaluate(
        rows, ids, V, artists,
        bonus_grid=(0.5, 2.0), knn_k=RETRIEVAL_KNN_K, cooc_cap=RETRIEVAL_COOC_CAP,
    )
    assert res["universe"] == len(ids)
    assert set(res["variants"]) == {"meta", "hybrid@0.5", "hybrid@2", "audio"}
    for v in res["variants"].values():
        assert 10 in v["lift_xart"] and set(v["hit"]) == {10, 20, 50}
        assert len(v["xart_ci10"]) == 2
    # audio carries the real signal here → audio lift@10 > meta lift@10
    assert res["variants"]["audio"]["lift_xart"][10] > res["variants"]["meta"]["lift_xart"][10]
    rec = res["recommendation"]
    assert "best_bonus" in rec and rec["best_bonus"] in (0.5, 2.0)
