#!/usr/bin/env python
"""C9.c — offline calibration of the hybrid reco's ``CONTENT_BONUS``. Runs on the HOST.

The hybrid recommendation (C9.c, lot L2) ranks a bounded retrieval universe
(``KNN ∪ co-occurrence``, the L1 retrieval core) with a metadata score PLUS an
ADDITIVE, surpondered audio-content bonus::

    hybrid_score(seed, cand) = metadata_score(seed, cand)
                             + CONTENT_BONUS * (1 - cosine_distance(seed, cand))

``CONTENT_BONUS`` (``recommendation_service.RecommendationConfig``) defaults to
``1.0`` and is NOT calibrated. This tool measures the ranking quality of that
hybrid at several bonus values against a co-occurrence hold-out, so the operator
can freeze the weight on numbers instead of a guess.

It is the SIBLING of ``eval_at_scale.py`` — same read-only ``ssh diggy-vps …
psql`` channel, same npz cache, same metric loop imported VERBATIM from
``docs/c9-benchmark/embed_eval.py`` (``build_partners``/``eval_scorer``/
``_boot_ci``/``_excluder``/``gower_scorer``/``emb_scorer``). The ONLY additions
are (a) a richer universe pull that also carries the metadata the metadata
channel needs, (b) the per-seed retrieval universe (``KNN ∪ co-occ``) that bounds
every ranking, and (c) the additive-bonus fusion evaluated over a ``--bonus-grid``.

WHAT IS COMPARED (all on the SAME per-seed retrieval universe = prod's universe):

  - ``meta``        : metadata-only ranking = ``CONTENT_BONUS = 0``. The metadata
                      channel is ``embed_eval``'s ``gower_lite`` scorer (BPM +
                      Camelot + genres + label + year) — the same content-free
                      metadata similarity the C9.0-bis benchmark validated. It
                      carries NO co-occurrence term, so it cannot leak the
                      co-occurrence hold-out (see EVAL_HYBRIDE.md §"leakage").
  - ``hybrid@b``    : ``gower_lite + b·(1 - dist)`` for each ``b`` in the grid
                      (default {0.5, 1.0, 2.0, 4.0}).
  - ``audio``       : content-only reference = ``(1 - dist)`` = cosine similarity
                      of the EffNet vectors (``emb_scorer``).

HOLD-OUT & METRIC (identical to ``eval_at_scale``): the ground truth is DJ-set
co-occurrence (``build_partners``); for each track-seed we score its retrieval
universe and measure whether its co-occurring set-mates surface in the top-k.
Reported per variant: lift@10 (all + cross-artist), hit-rate@10/@20/@50
(cross-artist), and the bootstrap CI95 on cross-artist lift@10. The recommended
bonus = the one maximising cross-artist lift@10 (tie-break hit@50).

IMPORTANT SCALE CAVEAT: the metadata channel here is ``gower_lite`` (∈ [0, 1]),
NOT the server's ``_score_seed_against_pool`` ``score_pct`` (a different scale
that also folds in a co-occurrence term). So the calibrated bonus is on the
gower-lite metadata scale — read the SHAPE of the curve (where does the audio
channel start / stop helping) rather than transplanting the raw number. See
EVAL_HYBRIDE.md §"decision rule".

STRICTLY READ-ONLY: SELECT / ``COPY … TO STDOUT`` only. Never writes to prod,
never changes server behaviour. Local tooling (A7-07): stdlib + numpy + ``ssh``
(the ``diggy-vps`` alias) — no Essentia/Docker (the vectors already live in prod).

Usage (from the repo root, or anywhere):
    python worker/embedding_backfill/eval_hybrid.py                       # default pull + eval
    python worker/embedding_backfill/eval_hybrid.py --sample-sets 3000    # bigger sample
    python worker/embedding_backfill/eval_hybrid.py --bonus-grid 0.25,0.5,1,2
    python worker/embedding_backfill/eval_hybrid.py --reuse               # re-eval saved universe/npz
"""

import argparse
import json
import os
import sys

import numpy as np

# Make the repo root importable so this runs BOTH as a script
# (``python worker/embedding_backfill/eval_hybrid.py`` — sys.path[0] is the
# package dir, not the root) AND as a module (``pytest worker/embedding_backfill/``).
_REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Windows consoles default to cp1252; the report + argparse help use a few UTF-8
# glyphs (∪ → ➤). Force UTF-8 where supported so the tool never dies formatting
# output (these local tools run on the operator's Windows PC — A7-07).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # already-wrapped / non-reconfigurable stream
        pass

# Reuse eval_at_scale's read channel, pull/parse plumbing and npz cache VERBATIM —
# this tool is its sibling, not a fork. ``print`` is its flush-on-print partial
# (keeps piped progress ordered).
from worker.embedding_backfill.eval_at_scale import (  # noqa: E402
    EMBEDDING_DIM,
    MODEL_NAME,
    MODEL_VERSION,
    REMOTE_PSQL_PULL,
    _import_embed_eval,
    _load_embeddings_npz,
    _save_embeddings_npz,
    assemble_universe,
    fetch_embeddings,
    print,
    run_remote_sql,
)

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data_hybrid")

# Retrieval widths — MIRROR the reco's defaults so the evaluated universe is the
# one prod actually builds. Kept in sync with
# services.similarity_service.RETRIEVAL_KNN_K_DEFAULT / RETRIEVAL_COOC_CAP_DEFAULT
# (this host script is stdlib-only and cannot import that SQLAlchemy module).
RETRIEVAL_KNN_K = 200
RETRIEVAL_COOC_CAP = 500

# Default bonus grid to sweep (CONTENT_BONUS candidates). 0 (meta-only) and the
# audio-only reference are ALWAYS added around it.
DEFAULT_BONUS_GRID = (0.5, 1.0, 2.0, 4.0)

# Sampling mirrors eval_at_scale (>= 8 previewable tracks / set). Default aligned
# to eval_at_scale's DEFAULT_SETS.
DEFAULT_SAMPLE_SETS = 2000
DEFAULT_MIN_TRACKS = 8

# Columns the metadata channel (gower_lite) + the cross-artist excluder read.
UNIVERSE_FIELDS = [
    "set_id",
    "catalog_id",
    "artist",
    "title",
    "bpm",
    "key",
    "release_date",
    "label",
    "genres",
    "isrc",
    "normalized_key",
]


# ------------------------------- SQL builder --------------------------------


def build_universe_query(n_sets=DEFAULT_SAMPLE_SETS, min_tracks=DEFAULT_MIN_TRACKS):
    """COPY query: reliable ROOT sets + their previewable membership WITH metadata.

    A richer twin of ``eval_at_scale.build_universe_query`` — same sampling
    (roots only ``parent_set_id IS NULL``, reliable ``unreliable IS NOT TRUE``,
    fetchable Deezer preview, ``>= min_tracks`` distinct previewable tracks) but
    it also carries the per-track metadata the gower-lite channel scores on
    (bpm/key/release_date/label/genres) + the cross-artist/​cross-release excluder
    fields (artist/isrc/normalized_key). ``genres`` (a ``TEXT[]``) is flattened to
    a ``|``-joined string, the shape ``embed_eval.build_feats`` expects.
    """
    return (
        "COPY (\n"
        "  WITH sampled_sets AS (\n"
        "    SELECT s.id\n"
        "    FROM sets s\n"
        "    JOIN set_tracks st ON st.set_id = s.id\n"
        "    JOIN catalog c ON c.id = st.catalog_id\n"
        "    WHERE s.parent_set_id IS NULL\n"
        "      AND s.unreliable IS NOT TRUE\n"
        "      AND c.has_preview = true\n"
        "      AND c.deezer_id IS NOT NULL\n"
        "      AND c.deezer_id <> 'NOT_FOUND'\n"
        "    GROUP BY s.id\n"
        f"    HAVING count(DISTINCT c.id) >= {int(min_tracks)}\n"
        "    ORDER BY random()\n"
        f"    LIMIT {int(n_sets)}\n"
        "  )\n"
        "  SELECT DISTINCT st.set_id, c.id AS catalog_id, c.artist, c.title,\n"
        "         c.bpm, c.key, c.release_date, c.label,\n"
        "         array_to_string(c.genres, '|') AS genres,\n"
        "         c.isrc, c.normalized_key\n"
        "  FROM sampled_sets ss\n"
        "  JOIN set_tracks st ON st.set_id = ss.id\n"
        "  JOIN catalog c ON c.id = st.catalog_id\n"
        "  WHERE c.has_preview = true\n"
        "    AND c.deezer_id IS NOT NULL\n"
        "    AND c.deezer_id <> 'NOT_FOUND'\n"
        "  ORDER BY st.set_id, c.id\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


# ------------------------------- parsing ------------------------------------


def parse_universe(csv_text):
    """Rows (dicts on UNIVERSE_FIELDS) from the COPY CSV output."""
    import csv
    import io

    return list(csv.DictReader(io.StringIO(csv_text)))


def build_meta(sample_rows):
    """``{catalog_id: row}`` keeping the FIRST occurrence of each track.

    The metadata is per-track; the membership CSV repeats it once per set, so we
    collapse to the first row seen (all copies are identical for a given track).
    """
    meta = {}
    for r in sample_rows:
        cid = str(r["catalog_id"]).strip()
        if cid not in meta:
            meta[cid] = r
    return meta


def fetch_universe(n_sets, min_tracks, runner=run_remote_sql):
    """Pull + parse the sampled universe rows WITH metadata (read-only)."""
    csv_text = runner(REMOTE_PSQL_PULL, build_universe_query(n_sets, min_tracks))
    return parse_universe(csv_text)


# --------------------------- retrieval universe -----------------------------


def build_retrieval_universes(V, ids, partners, knn_k, cooc_cap):
    """Per-seed retrieval universe = top-``knn_k`` audio neighbours ∪ co-occurrence.

    Mirrors the reco retrieval core (``content_neighbor_ids`` ∪
    ``cooc_candidate_ids``), computed here in numpy on the local ``V``:

      - KNN : the ``knn_k`` nearest embedding neighbours of the seed by cosine
        (``V`` is L2-normalised, so ``V @ V[si]`` is cosine similarity), seed
        excluded.
      - co-occ : every set-mate of the seed present in the scorable universe,
        capped at ``cooc_cap`` in ASCENDING catalog-id order — exactly
        ``cooc_candidate_ids``' stable cap.

    Returns ``{seed_index: np.int64 array of candidate indices}`` (seed excluded).
    A seed with an empty universe maps to an empty array (its scorer returns
    ``None`` → the metric skips it, like a prod seed that retrieved nothing).
    """
    n = len(ids)
    idx = {c: i for i, c in enumerate(ids)}
    out = {}
    for si in range(n):
        sims = V @ V[si]
        sims[si] = -np.inf
        k = min(knn_k, n - 1)
        if k <= 0:
            knn = np.empty(0, np.int64)
        elif k >= n - 1:
            knn = np.array([j for j in range(n) if j != si], np.int64)
        else:
            # argpartition top-k (unordered is fine — the union is a set)
            knn = np.argpartition(-sims, k)[:k].astype(np.int64)
        seed_cid = ids[si]
        partner_cids = sorted(
            (c for c in partners.get(seed_cid, ()) if c in idx), key=int
        )[:cooc_cap]
        cooc = np.array([idx[c] for c in partner_cids], np.int64)
        u = np.unique(np.concatenate([knn, cooc])) if cooc.size else np.unique(knn)
        out[si] = u[u != si]
    return out


def masked_scorer(base_fn, universes):
    """Wrap a scorer so it only ranks a seed's retrieval universe.

    Candidates OUTSIDE ``universes[si]`` are pushed to ``-inf`` (never top-k), so
    every ranking is confined to the SAME per-seed universe prod would build. A
    seed with an empty universe yields ``None`` (skipped by ``eval_scorer``), as
    does a ``base_fn`` that returns ``None``.
    """

    def f(si):
        s = base_fn(si)
        if s is None:
            return None
        u = universes.get(si)
        if u is None or u.size == 0:
            return None
        masked = np.full(s.shape, -np.inf, np.float32)
        masked[u] = np.asarray(s, np.float32)[u]
        return masked

    return f


def build_variants(feats, V, bonus_grid):
    """Assemble ``[(name, base_scorer, is_hybrid, bonus), ...]`` in report order.

    ``meta`` (bonus 0) first, then one ``hybrid@b`` per grid value, then ``audio``
    (content-only reference). ``base_scorer`` is the UNMASKED scorer over the full
    ``ids`` universe; the caller wraps it with :func:`masked_scorer`.
    """
    ee = _import_embed_eval()
    gower = ee.gower_scorer(feats, "G_lite")  # metadata channel (co-occ-free)
    emb = ee.emb_scorer(V)  # content channel: V @ V[si] = 1 - cosine_distance

    def hybrid(b):
        def f(si):
            return gower(si) + b * emb(si)

        return f

    variants = [("meta", gower, False, 0.0)]
    for b in bonus_grid:
        variants.append((f"hybrid@{b:g}", hybrid(b), True, float(b)))
    variants.append(("audio", emb, False, None))
    return variants


# --------------------------------- eval -------------------------------------


def evaluate(sample_rows, ids, V, artists, *, bonus_grid, knn_k, cooc_cap):
    """Full hybrid calibration → results dict (reuses embed_eval throughout).

    For every variant (meta / hybrid@b… / audio) ranks each seed's retrieval
    universe and measures lift@k + hit-rate@k against the co-occurrence ground
    truth, cross-artist and all-positives, with the CI95 on cross-artist lift@10.
    """
    ee = _import_embed_eval()
    n = len(ids)
    partners = ee.build_partners(sample_rows, set(ids))

    # feats for gower_lite + the cross-artist excluder. build_feats reads the
    # metadata columns off the meta rows; genre graph unused (G_lite = raw tokens),
    # so an empty name_to_node/parent is passed (full-node expansion falls back to
    # raw tokens, which we do not consume).
    meta = build_meta(sample_rows)
    feats = ee.build_feats(ids, meta, {}, {})
    feats["artist_ids"] = ee._factorize([artists.get(c, "") for c in ids])

    excl_none = ee._excluder(feats, ids, "none")
    excl_xart = ee._excluder(feats, ids, "cross_artist")

    universes = build_retrieval_universes(V, ids, partners, knn_k, cooc_cap)
    uni_sizes = np.array([u.size for u in universes.values()]) if universes else np.zeros(0)

    variants = build_variants(feats, V, bonus_grid)
    out_variants = {}
    for name, base_fn, is_hybrid, bonus in variants:
        fn = masked_scorer(base_fn, universes)
        allp = ee.eval_scorer(ids, fn, partners, excl_none)
        xart = ee.eval_scorer(ids, fn, partners, excl_xart)

        def _mean(d, k):
            return float(d[k].mean()) if len(d[k]) else float("nan")

        out_variants[name] = {
            "is_hybrid": is_hybrid,
            "bonus": bonus,
            "n_seeds_all": int(allp["n_seeds"]),
            "n_seeds_xart": int(xart["n_seeds"]),
            "lift_all": {k: _mean(allp, k) for k in ee.K_LIST},
            "lift_xart": {k: _mean(xart, k) for k in ee.K_LIST},
            "xart_ci10": list(ee._boot_ci(xart[10])),
            "hit": {
                k: (float(xart["hit"][k].mean()) if len(xart["hit"][k]) else float("nan"))
                for k in ee.HIT_K
            },
        }

    rec = _recommend(out_variants)
    return {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "universe": n,
        "retrieval": {"knn_k": knn_k, "cooc_cap": cooc_cap},
        "universe_size": {
            "mean": float(uni_sizes.mean()) if uni_sizes.size else float("nan"),
            "median": float(np.median(uni_sizes)) if uni_sizes.size else float("nan"),
            "max": int(uni_sizes.max()) if uni_sizes.size else 0,
        },
        "bonus_grid": list(bonus_grid),
        "variants": out_variants,
        "recommendation": rec,
    }


def _recommend(variants):
    """Best CONTENT_BONUS = max cross-artist lift@10 among hybrids, tie-break hit@50.

    Also reports the METADATA baseline (bonus 0) and the parsimonious pick — the
    SMALLEST bonus whose lift@10 point estimate lands within the winner's CI95
    (adding audio weight beyond it does not measurably help). ``audio`` is a
    reference, never a recommendation.
    """
    hybrids = [
        (name, v) for name, v in variants.items() if v["is_hybrid"]
    ]
    if not hybrids:
        return {}

    def _l10(v):
        x = v["lift_xart"].get(10, float("nan"))
        return x if x == x else -1.0  # NaN → worst

    def _h50(v):
        h = v["hit"].get(50, float("nan"))
        return h if h == h else -1.0

    best_name, best_v = max(hybrids, key=lambda kv: (_l10(kv[1]), _h50(kv[1])))
    lo = best_v["xart_ci10"][0]
    # parsimonious: smallest bonus whose lift@10 >= the winner's CI95 lower bound
    parsimonious = min(
        (
            (name, v)
            for name, v in hybrids
            if _l10(v) >= lo
        ),
        key=lambda kv: kv[1]["bonus"],
        default=(best_name, best_v),
    )
    meta = variants.get("meta", {})
    return {
        "best_bonus": best_v["bonus"],
        "best_variant": best_name,
        "best_lift_xart10": _l10(best_v),
        "parsimonious_bonus": parsimonious[1]["bonus"],
        "parsimonious_variant": parsimonious[0],
        "meta_lift_xart10": _l10(meta) if meta else float("nan"),
        "audio_adds_pct": (
            (_l10(best_v) / _l10(meta) - 1.0) * 100.0
            if meta and _l10(meta) > 0
            else float("nan")
        ),
    }


def _print_report(res, n_sets):
    print("\n" + "=" * 92)
    print("C9.c — Calibration offline de CONTENT_BONUS (reco hybride métadonnées + audio)")
    print("=" * 92)
    print(f"modèle           : {res['model_name']} / {res['model_version']}")
    print(f"échantillon      : {n_sets} sets demandés | univers scorable = {res['universe']} tracks")
    rt = res["retrieval"]
    us = res["universe_size"]
    print(f"retrieval/seed   : KNN k={rt['knn_k']} ∪ co-occ cap={rt['cooc_cap']}"
          f"  → univers/seed méd={us['median']:.0f} moy={us['mean']:.0f} max={us['max']}")

    print("\nlift@10 (× vs hasard) et hit-rate@k (cross-artist) par variante :")
    hdr = f"  {'variante':<12}{'bonus':>7}{'lift_all@10':>13}{'lift_xart@10':>14}{'ci95':>16}{'hit@10':>9}{'hit@50':>9}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for name, v in res["variants"].items():
        b = v["bonus"]
        bs = "audio" if b is None else f"{b:g}"
        ci = v["xart_ci10"]
        print(
            f"  {name:<12}{bs:>7}{v['lift_all'][10]:>12.2f}x{v['lift_xart'][10]:>13.2f}x"
            f"{f'[{ci[0]:.2f},{ci[1]:.2f}]':>16}"
            f"{v['hit'][10] * 100:>8.1f}%{v['hit'][50] * 100:>8.1f}%"
        )

    rec = res.get("recommendation") or {}
    if rec:
        print("\n" + "-" * 92)
        print(f"➤ BONUS RECOMMANDÉ : {rec['best_bonus']:g}  (variante {rec['best_variant']}, "
              f"cross-artist lift@10 = {rec['best_lift_xart10']:.2f}x)")
        print(f"  baseline méta-seule (bonus 0) : lift@10 = {rec['meta_lift_xart10']:.2f}x"
              f"   → l'audio ajoute {rec['audio_adds_pct']:+.0f}%")
        print(f"  choix parcimonieux (plus petit bonus dans l'IC95 du meilleur) : "
              f"{rec['parsimonious_bonus']:g} ({rec['parsimonious_variant']})")
        print("  Règle de décision + mise en garde d'échelle : cf. docs/c9-benchmark/EVAL_HYBRIDE.md")
    print("=" * 92)


def _parse_bonus_grid(raw):
    """Parse ``--bonus-grid`` CSV → sorted tuple of positive floats (dedup, drop 0)."""
    vals = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        b = float(part)
        if b > 0:  # 0 (meta) is added implicitly; audio is the content-only ref
            vals.append(b)
    return tuple(sorted(dict.fromkeys(vals)))


def main(args):
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    universe_path = os.path.join(workdir, "universe.csv")
    npz_path = os.path.join(workdir, "embeddings.npz")
    results_path = os.path.join(workdir, "eval_hybrid_results.json")

    bonus_grid = _parse_bonus_grid(args.bonus_grid)
    if not bonus_grid:
        sys.exit("[eval] empty bonus grid — pass e.g. --bonus-grid 0.5,1,2,4")
    if args.seed is not None:
        np.random.seed(args.seed)  # reproducibility (metric CI uses its own RNG)

    if args.reuse:
        if not (os.path.exists(universe_path) and os.path.exists(npz_path)):
            sys.exit(f"--reuse: need both {universe_path} and {npz_path} from a previous run")
        print(f"[reuse] loading {universe_path} + {npz_path} (no pull)")
        sample_rows = _read_csv(universe_path)
        emb_map = _load_embeddings_npz(npz_path)
    else:
        print(f"[sample] pulling {args.sample_sets} sets (>= {args.min_tracks} tracks/set)...")
        sample_rows = fetch_universe(args.sample_sets, args.min_tracks)
        _write_csv(universe_path, sample_rows, UNIVERSE_FIELDS)
        distinct_cids = sorted({str(r["catalog_id"]).strip() for r in sample_rows}, key=int)
        n_sets_seen = len({str(r["set_id"]).strip() for r in sample_rows})
        print(
            f"[sample] {len(sample_rows)} membership rows | {n_sets_seen} sets | "
            f"{len(distinct_cids)} distinct tracks -> {universe_path}"
        )
        if not distinct_cids:
            sys.exit("[sample] empty universe — nothing to evaluate")
        print(f"[pull-emb] pulling embeddings for {len(distinct_cids)} tracks...")
        emb_map = fetch_embeddings(distinct_cids)
        _save_embeddings_npz(npz_path, emb_map)
        print(f"[pull-emb] {len(emb_map)}/{len(distinct_cids)} tracks have an embedding -> {npz_path}")

    ids, V, artists = assemble_universe(sample_rows, emb_map, expected_dim=EMBEDDING_DIM)
    if args.limit_tracks and len(ids) > args.limit_tracks:
        # deterministic subsample of the scorable universe (speed knob): keep the
        # first N ids (already sorted by int), rebuild V aligned to the trimmed
        # ids, and drop the membership rows of dropped tracks so ``partners`` stays
        # consistent with the kept universe.
        keep = set(ids[: args.limit_tracks])
        ids = [c for c in ids if c in keep]
        V = np.vstack([emb_map[c] for c in ids]).astype(np.float32)
        sample_rows = [r for r in sample_rows if str(r["catalog_id"]).strip() in keep]

    print(f"[eval] scorable universe = {len(ids)} tracks (V shape {V.shape})")
    if len(ids) < 2:
        sys.exit("[eval] universe too small to score")

    res = evaluate(
        sample_rows,
        ids,
        V,
        artists,
        bonus_grid=bonus_grid,
        knn_k=args.knn_k,
        cooc_cap=args.cooc_cap,
    )
    _print_report(res, args.sample_sets)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"[eval] wrote {results_path}")
    return res


# ------------------------------- IO helpers ---------------------------------


def _write_csv(path, rows, fieldnames):
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Offline calibration of the hybrid reco CONTENT_BONUS: rank the "
        "prod retrieval universe (KNN ∪ co-occ) with metadata + b·audio for several "
        "bonus values, scored against a co-occurrence hold-out. READ-ONLY."
    )
    parser.add_argument(
        "--sample-sets", type=int, default=DEFAULT_SAMPLE_SETS,
        help=f"reliable root sets to sample (default {DEFAULT_SAMPLE_SETS}, aligned to eval_at_scale)",
    )
    parser.add_argument(
        "--min-tracks", type=int, default=DEFAULT_MIN_TRACKS,
        help=f"min previewable tracks per sampled set (default {DEFAULT_MIN_TRACKS})",
    )
    parser.add_argument(
        "--bonus-grid", default=",".join(f"{b:g}" for b in DEFAULT_BONUS_GRID),
        help="CSV of CONTENT_BONUS values to sweep (default '0.5,1,2,4'); 0 (meta) "
        "and audio-only are added automatically",
    )
    parser.add_argument(
        "--knn-k", type=int, default=RETRIEVAL_KNN_K,
        help=f"top-K audio neighbours retrieved per seed (default {RETRIEVAL_KNN_K}, reco default)",
    )
    parser.add_argument(
        "--cooc-cap", type=int, default=RETRIEVAL_COOC_CAP,
        help=f"max co-occurrence candidates per seed (default {RETRIEVAL_COOC_CAP}, reco default)",
    )
    parser.add_argument(
        "--limit-tracks", type=int, default=0,
        help="cap the scorable universe size for a faster run (0 = no cap)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="numpy RNG seed for reproducibility (default 0; the metric CI uses its own fixed RNG)",
    )
    parser.add_argument(
        "--workdir", default=DEFAULT_WORKDIR,
        help="working dir for universe.csv / embeddings.npz / results JSON (default: <package>/data_hybrid)",
    )
    parser.add_argument(
        "--reuse", action="store_true",
        help="skip the prod pulls and re-evaluate a previous run's universe.csv + embeddings.npz",
    )
    main(parser.parse_args())
