#!/usr/bin/env python
"""C9.a — at-scale replay of the C9.0-bis co-occurrence benchmark. Runs on the HOST.

The C9.0-bis benchmark (``docs/c9-benchmark/RAPPORT_C9.0-bis.md``) settled the model
choice — EffNet wins, frozen as v1 — but it only MEASURED the "do embedding
neighbours predict DJ-set co-occurrence?" question on a small, CO-OCCURRENCE-DENSE
sample (500 sets, common universe 6740 tracks). Once the EffNet vectors are
backfilled into the prod ``track_embeddings`` pgvector table (twin tool
``backfill_embeddings.py``), we must REPLAY that evaluation at the real, noisier
scale to confirm the signal still holds.

This script does exactly that, read-ONLY:

  1. SAMPLE — pull N reliable ROOT sets from prod (adapts
     ``docs/c9-benchmark/query.sql``: ``parent_set_id IS NULL`` + ``unreliable IS
     NOT TRUE`` + a fetchable Deezer preview) via the documented ``ssh diggy-vps
     … psql`` channel, and export the ``(set_id, catalog_id, artist)`` membership.
     That is the universe + the co-occurrence ground truth.
  2. PULL EMBEDDINGS — for the DISTINCT catalog_ids of that universe, stream
     ``SELECT catalog_id, embedding FROM track_embeddings WHERE model_name=… AND
     model_version=… AND catalog_id IN (…)`` (chunked), parse each pgvector text
     literal ``[f1,f2,…]`` into a ``np.float32`` array, and persist a local
     ``embeddings.npz`` (``ids`` + ``vecs``, same shape as the benchmark's npz).
  3. EVAL — run the co-occurrence metric loop from
     ``docs/c9-benchmark/embed_eval.py`` (imported, NOT re-implemented):
     lift@k all + cross-artist, bootstrap CI95, hit-rate@10/20/50, and the
     shuffled control — over the universe = tracks present in BOTH the sample and
     the embedding table. Prints a table and writes a results JSON.

The ABSOLUTE precision does NOT transport from the dense 6740-track sample to the
real noisy scale (the per-set base rate collapses) — what we track is the
EXISTENCE and STRENGTH of the signal (lift far above 1×, shuffled control ≈ 1×)
and the product-facing hit-rate@k. See ``RAPPORT_C9.0-bis.md`` §4.

STRICTLY READ-ONLY: this tool never writes to prod. It only SELECTs (COPY … TO
STDOUT). No reco service, no VPS task — that is out of scope for this lot.

Local tooling (A7-07 pattern): needs only the Python stdlib + numpy + ``ssh`` (the
``diggy-vps`` alias). It does NOT need Essentia/Docker — the vectors already live
in prod; this only reads and scores them.

Usage (from the repo root, or anywhere):
    python worker/embedding_backfill/eval_at_scale.py                 # default sample, pull + eval
    python worker/embedding_backfill/eval_at_scale.py --sets 3000     # bigger sample
    python worker/embedding_backfill/eval_at_scale.py --reuse         # re-eval saved universe/npz
"""

import argparse
import csv
import functools
import io
import json
import os
import subprocess
import sys

import numpy as np

# keep progress ordered even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path: -q keeps the COPY stream clean (CSV only on stdout). Mirrors the
# read channel of worker/bpm_backfill/ and worker/embedding_backfill/.
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
# docs/c9-benchmark holds embed_eval.py — the metric loop we reuse verbatim.
C9_BENCH_DIR = os.path.normpath(
    os.path.join(PKG_DIR, "..", "..", "docs", "c9-benchmark")
)

# Frozen C9.a identity of the default embedding model. MUST stay in sync with
# server/api/models/embedding.py (this host script is stdlib-only and cannot
# import that SQLAlchemy module) and with backfill_embeddings.py.
MODEL_NAME = "discogs-effnet"
MODEL_VERSION = "bs64-1"
EMBEDDING_DIM = 1280

# Default sampling: mirror query.sql (>= 8 previewable tracks / set), more sets
# than the frozen 500 so the "at-scale" universe is materially larger.
DEFAULT_SETS = 2000
DEFAULT_MIN_TRACKS = 8
# IN-list size per embedding pull query (keeps each SQL statement reasonable).
EMB_PULL_CHUNK = 2000

# C9.0-bis reference numbers (dense universe 6740), for on-screen comparison only.
REF_C9_0_BIS = {
    "universe": 6740,
    "xart10": 32.35,
    "all10": 34.87,
    "hit10": 0.350,
    "hit20": 0.472,
    "hit50": 0.645,
    "shuf10": 1.02,
}


# ------------------------------- SQL builders -------------------------------


def build_universe_query(n_sets=DEFAULT_SETS, min_tracks=DEFAULT_MIN_TRACKS):
    """COPY query sampling reliable ROOT sets and their previewable membership.

    Adapts ``docs/c9-benchmark/query.sql``: roots only (``parent_set_id IS NULL``),
    reliable only (``unreliable IS NOT TRUE``, C8), fetchable Deezer preview.
    ``ORDER BY random()`` is the only non-determinism (the sample is frozen to
    ``universe.csv`` on the first run and reused with ``--reuse``).
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
        "  SELECT DISTINCT st.set_id, c.id AS catalog_id, c.artist, c.title\n"
        "  FROM sampled_sets ss\n"
        "  JOIN set_tracks st ON st.set_id = ss.id\n"
        "  JOIN catalog c ON c.id = st.catalog_id\n"
        "  WHERE c.has_preview = true\n"
        "    AND c.deezer_id IS NOT NULL\n"
        "    AND c.deezer_id <> 'NOT_FOUND'\n"
        "  ORDER BY st.set_id, c.id\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def build_embedding_query(catalog_ids, model_name=MODEL_NAME, model_version=MODEL_VERSION):
    """COPY query pulling the embeddings of a chunk of catalog_ids, read-only.

    ``int()`` coercion of every id makes the interpolated IN-list injection-safe.
    The pgvector ``embedding`` column renders as a text literal ``[f1,f2,…]``
    (CSV-quoted because it contains commas), parsed back by ``parse_vector_literal``.
    """
    ids = ", ".join(str(int(c)) for c in catalog_ids)
    return (
        "COPY (\n"
        "  SELECT catalog_id, embedding\n"
        "  FROM track_embeddings\n"
        f"  WHERE model_name = '{model_name}'\n"
        f"    AND model_version = '{model_version}'\n"
        f"    AND catalog_id IN ({ids})\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


# ------------------------------- parsing ------------------------------------


def parse_universe(csv_text):
    """Rows (dicts: set_id/catalog_id/artist/title) from the COPY CSV output."""
    return list(csv.DictReader(io.StringIO(csv_text)))


def parse_vector_literal(raw):
    """Parse a pgvector text literal ``[f1,f2,…]`` into a ``np.float32`` array.

    Returns ``None`` for anything unusable (None, empty, empty brackets, a cell
    that does not parse as a comma-separated float list). Tolerates surrounding
    whitespace and the presence/absence of the enclosing brackets.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if s[0] == "[" and s[-1] == "]":
        s = s[1:-1].strip()
    if not s:
        return None
    try:
        vals = [float(x) for x in s.split(",")]
    except ValueError:
        return None
    if not vals:
        return None
    return np.asarray(vals, dtype=np.float32)


def parse_embeddings_csv(csv_text):
    """{catalog_id(str): np.float32 array} from the embedding COPY CSV output.

    Skips rows with a missing id or an unparsable vector (defense in depth — the
    fixed-width pgvector column should never emit those, but never crash on one).
    """
    out = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        cid = str(row.get("catalog_id", "")).strip()
        if not cid:
            continue
        vec = parse_vector_literal(row.get("embedding"))
        if vec is None:
            continue
        out[cid] = vec
    return out


def assemble_universe(sample_rows, emb_map, expected_dim=EMBEDDING_DIM):
    """Intersect the sampled universe with the embeddings actually present.

    Returns ``(ids, V, artists)``:
      - ``ids``    : sorted-by-id list of catalog_id (str) present in BOTH the
                     sample and ``emb_map`` (and, if ``expected_dim`` is set, of
                     the right length).
      - ``V``      : ``(len(ids), dim)`` float32 matrix aligned row-for-row to
                     ``ids``. Empty ``(0, 0)`` when no track qualifies.
      - ``artists``: ``{catalog_id: artist.lower()}`` for the cross-artist
                     exclusion (from the sample rows).

    A track sampled but not yet embedded (backfill incomplete) is simply dropped
    — the universe is the set of scorable tracks.
    """
    sample_ids = {str(r["catalog_id"]).strip() for r in sample_rows}
    ids = [c for c in sample_ids if c in emb_map]
    if expected_dim:
        ids = [c for c in ids if emb_map[c].shape[0] == expected_dim]
    ids.sort(key=int)
    V = (
        np.vstack([emb_map[c] for c in ids]).astype(np.float32)
        if ids
        else np.zeros((0, 0), np.float32)
    )
    artists = {
        str(r["catalog_id"]).strip(): (r.get("artist") or "").strip().lower()
        for r in sample_rows
    }
    return ids, V, artists


def chunked(seq, size):
    """Yield successive ``size``-length chunks of ``seq``."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ------------------------------- IO helpers ---------------------------------


def run_remote_sql(remote_cmd, sql):
    """Feed ``sql`` to psql on the VPS via ssh stdin; return psql's stdout."""
    proc = subprocess.run(
        ["ssh", SSH_HOST, remote_cmd],
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote psql failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def fetch_universe(n_sets, min_tracks, runner=run_remote_sql):
    """Pull + parse the sampled universe rows (read-only)."""
    csv_text = runner(REMOTE_PSQL_PULL, build_universe_query(n_sets, min_tracks))
    return parse_universe(csv_text)


def fetch_embeddings(
    catalog_ids,
    model_name=MODEL_NAME,
    model_version=MODEL_VERSION,
    chunk=EMB_PULL_CHUNK,
    runner=run_remote_sql,
):
    """Pull the embeddings of ``catalog_ids`` in chunks; return {cid: vec}."""
    uniq = sorted({str(int(c)) for c in catalog_ids}, key=int)
    emb_map = {}
    n_chunks = (len(uniq) + chunk - 1) // chunk if uniq else 0
    for i, part in enumerate(chunked(uniq, chunk), 1):
        csv_text = runner(
            REMOTE_PSQL_PULL, build_embedding_query(part, model_name, model_version)
        )
        got = parse_embeddings_csv(csv_text)
        emb_map.update(got)
        print(f"[pull-emb] chunk {i}/{n_chunks}: +{len(got)} (total {len(emb_map)})")
    return emb_map


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_embeddings_npz(path, emb_map):
    ids = sorted(emb_map, key=int)
    mat = (
        np.vstack([emb_map[c] for c in ids]).astype(np.float32)
        if ids
        else np.zeros((0, 0), np.float32)
    )
    np.savez_compressed(path, ids=np.array(ids, dtype=object), vecs=mat)


def _load_embeddings_npz(path):
    data = np.load(path, allow_pickle=True)
    ids = [str(x) for x in data["ids"].tolist()]
    vecs = data["vecs"]
    return {cid: vecs[i].astype(np.float32) for i, cid in enumerate(ids)}


# --------------------------------- eval -------------------------------------


def _import_embed_eval():
    """Import the benchmark's metric loop (imported, never re-implemented).

    Imported lazily so the pure parsing/assembly helpers (and their unit tests)
    do not depend on the docs/ path being importable.
    """
    if C9_BENCH_DIR not in sys.path:
        sys.path.insert(0, C9_BENCH_DIR)
    import embed_eval  # noqa: E402

    return embed_eval


def evaluate(sample_rows, ids, V, artists):
    """Full at-scale evaluation → results dict (reuses embed_eval throughout).

    Reuses ``embed_eval``'s metric functions verbatim: ``build_partners`` for the
    co-occurrence ground-truth graph, ``eval_scorer`` for lift@k + hit-rate@k,
    ``_boot_ci`` for CI95, ``_excluder('cross_artist')`` for the cross-artist cut,
    plus the same row-permutation shuffled control ``run_compare`` uses. No metric
    is re-implemented here.
    """
    ee = _import_embed_eval()
    n = len(ids)
    partners = ee.build_partners(sample_rows, set(ids))

    # minimal feats for the excluder: cross_artist only reads artist_ids, but the
    # _excluder constructor unpacks the other keys, so provide neutral placeholders.
    feats = {
        "artist_ids": ee._factorize([artists.get(c, "") for c in ids]),
        "label_id": np.full(n, -1, np.int64),
        "album": [""] * n,
        "isrc": [""] * n,
        "normkey": [""] * n,
        "title": [""] * n,
    }
    excl_none = ee._excluder(feats, ids, "none")           # -> None (no exclusion)
    excl_xart = ee._excluder(feats, ids, "cross_artist")

    scorer = ee.emb_scorer(V)
    allp = ee.eval_scorer(ids, scorer, partners, excl_none)
    xart = ee.eval_scorer(ids, scorer, partners, excl_xart)

    # shuffled control: permute the embedding rows, re-score cross-artist. A real
    # signal collapses to ~chance (~1×) — exactly run_compare's construction.
    perm = np.random.RandomState(0).permutation(n) if n else np.array([], int)
    shuf = ee.eval_scorer(ids, ee.emb_scorer(V[perm]), partners, excl_xart) if n else None

    def _mean(d, k):
        return float(d[k].mean()) if len(d[k]) else float("nan")

    res = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "universe": n,
        "n_seeds_all": int(allp["n_seeds"]),
        "n_seeds_xart": int(xart["n_seeds"]),
        "lift_all": {k: _mean(allp, k) for k in ee.K_LIST},
        "lift_xart": {k: _mean(xart, k) for k in ee.K_LIST},
        "xart_med10": float(np.median(xart[10])) if len(xart[10]) else float("nan"),
        "xart_ci10": list(ee._boot_ci(xart[10])),
        "hit": {k: float(xart["hit"][k].mean()) if len(xart["hit"][k]) else float("nan")
                for k in ee.HIT_K},
        "hit10_strata": ee._strata(xart["hit"][10], xart["degs"]),
        "shuf10": (_mean(shuf, 10) if shuf is not None else float("nan")),
        "ref_c9_0_bis": REF_C9_0_BIS,
    }
    return res


def _print_report(res, n_sets, min_tracks):
    ref = res["ref_c9_0_bis"]
    print("\n" + "=" * 88)
    print("C9.a — Éval à l'échelle : les voisins EffNet prédisent-ils la co-occurrence en sets ?")
    print("=" * 88)
    print(f"modèle          : {res['model_name']} / {res['model_version']}")
    print(f"échantillon     : {n_sets} sets demandés (>= {min_tracks} tracks previewables/set)")
    print(f"univers scorable: {res['universe']} tracks (présents dans le sample ET la table embeddings)")
    print(f"seeds évalués   : all={res['n_seeds_all']}  cross-artist={res['n_seeds_xart']}")

    print("\nlift@k (× vs hasard ; > 1 = signal) :")
    print(f"  {'k':>3}{'all':>10}{'cross-artist':>16}")
    for k in sorted(res["lift_all"]):
        print(f"  {k:>3}{res['lift_all'][k]:>9.2f}x{res['lift_xart'][k]:>15.2f}x")
    ci = res["xart_ci10"]
    print(f"  cross-artist@10 IC95 = [{ci[0]:.2f}, {ci[1]:.2f}]   médiane={res['xart_med10']:.2f}")

    print(f"\ncontrôle shuffled@10 (cross-artist) : {res['shuf10']:.2f}x   (attendu ~1.0 = aucun signal)")

    st = res["hit10_strata"]
    print("\nhit-rate@k (>=1 vrai setmate dans le top-k, cross-artist) :")
    print(f"  hit@10 = {res['hit'][10] * 100:.1f}%   hit@20 = {res['hit'][20] * 100:.1f}%"
          f"   hit@50 = {res['hit'][50] * 100:.1f}%")
    print(f"  par degré : 3-9 = {st.get('3-9', float('nan')) * 100:.0f}%"
          f"   10+ = {st.get('10+', float('nan')) * 100:.0f}%")

    print(f"\nréférence C9.0-bis (univers dense {ref['universe']}) : "
          f"xart@10 {ref['xart10']}x · hit@10 {ref['hit10'] * 100:.1f}% · "
          f"hit@50 {ref['hit50'] * 100:.1f}% · shuf@10 {ref['shuf10']}x")
    print("NOTE : la precision ABSOLUE ne se transporte pas de l'échantillon dense (6740) au")
    print("réel bruité — on suit l'EXISTENCE/FORCE du signal (lift >> 1, shuffled ~1) et le")
    print("hit-rate@k, PAS le lift absolu. Cf. RAPPORT_C9.0-bis.md §4.")
    print("=" * 88)


def main(args):
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    universe_path = os.path.join(workdir, "universe.csv")
    npz_path = os.path.join(workdir, "embeddings.npz")
    results_path = os.path.join(workdir, "eval_at_scale_results.json")

    if args.reuse:
        if not (os.path.exists(universe_path) and os.path.exists(npz_path)):
            sys.exit(
                f"--reuse: need both {universe_path} and {npz_path} from a previous run"
            )
        print(f"[reuse] loading {universe_path} + {npz_path} (no pull)")
        sample_rows = _read_csv(universe_path)
        emb_map = _load_embeddings_npz(npz_path)
    else:
        # 1. SAMPLE — read-only COPY of reliable root sets + membership
        print(f"[sample] pulling {args.sets} sets (>= {args.min_tracks} tracks/set)...")
        sample_rows = fetch_universe(args.sets, args.min_tracks)
        _write_csv(
            universe_path, sample_rows, ["set_id", "catalog_id", "artist", "title"]
        )
        distinct_cids = sorted(
            {str(r["catalog_id"]).strip() for r in sample_rows}, key=int
        )
        n_sets_seen = len({str(r["set_id"]).strip() for r in sample_rows})
        print(
            f"[sample] {len(sample_rows)} membership rows | {n_sets_seen} sets | "
            f"{len(distinct_cids)} distinct tracks -> {universe_path}"
        )
        if not distinct_cids:
            sys.exit("[sample] empty universe — nothing to evaluate")

        # 2. PULL EMBEDDINGS — read-only, chunked IN
        print(f"[pull-emb] pulling embeddings for {len(distinct_cids)} tracks...")
        emb_map = fetch_embeddings(distinct_cids)
        _save_embeddings_npz(npz_path, emb_map)
        print(
            f"[pull-emb] {len(emb_map)}/{len(distinct_cids)} tracks have an embedding "
            f"-> {npz_path}"
        )

    # 3. EVAL — reuse embed_eval's metric loop
    ids, V, artists = assemble_universe(sample_rows, emb_map)
    print(f"[eval] scorable universe = {len(ids)} tracks (V shape {V.shape})")
    if len(ids) < 2:
        sys.exit("[eval] universe too small to score")
    res = evaluate(sample_rows, ids, V, artists)
    _print_report(res, args.sets, args.min_tracks)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"[eval] wrote {results_path}")
    return res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="At-scale replay of the C9.0-bis co-occurrence benchmark: do the "
        "backfilled EffNet embedding neighbours predict DJ-set co-occurrence at the "
        "real (noisy) scale? READ-ONLY (SELECT only, never writes to prod)."
    )
    parser.add_argument(
        "--sets",
        type=int,
        default=DEFAULT_SETS,
        help=f"number of reliable root sets to sample (default {DEFAULT_SETS})",
    )
    parser.add_argument(
        "--min-tracks",
        type=int,
        default=DEFAULT_MIN_TRACKS,
        help=f"min previewable tracks per sampled set (default {DEFAULT_MIN_TRACKS})",
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help="working directory for universe.csv / embeddings.npz / results JSON "
        "(default: <package>/data)",
    )
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="skip the prod pulls and re-evaluate a previous run's universe.csv + "
        "embeddings.npz (offline)",
    )
    main(parser.parse_args())
