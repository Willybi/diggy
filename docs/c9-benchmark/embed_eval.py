"""C9.0 benchmark — do content-embedding neighbours predict DJ-set co-occurrence?

Phase `embed`: for each distinct catalog track in the frozen sample, resolve the Deezer
preview live (public GET api.deezer.com/track/{id} -> .preview), download the 30s MP3
transiently, run Essentia Discogs-EffNet, mean-pool the per-patch 1280-d embeddings into
one L2-normalised vector, delete the MP3. No audio is persisted (CGU posture, same as E2.a).
Vectors -> embeddings.npz ; per-track status -> status.csv.

Phase `eval`: rebuild the co-occurrence graph from the sample (two tracks co-occur if they
share >=1 set_id), then for every seed with >=1 co-occurring partner in the embedded universe,
rank all other tracks by cosine (= dot, vectors are normalised) and measure how much better than
chance the embedding neighbours are at surfacing co-occurring tracks: precision@k, recall@k and
LIFT@k (precision / base-rate). A shuffled-embedding control and a same-artist-excluded variant
calibrate the verdict. GO if the content signal lifts co-occurrence well above chance even across
different artists; NO-GO if lift ~1x (raw EffNet doesn't capture mix-relevant structure -> would
need C9.d contrastive fine-tuning before any v1 feature).

Usage (in the container):
  python /work/embed_eval.py embed [--workers K] [--limit N]
  python /work/embed_eval.py eval        # uses embeddings.npz + sample.csv
  python /work/embed_eval.py both
"""
import argparse
import csv
import os
import sys
import tempfile
import threading
import time
from collections import defaultdict

import numpy as np
import requests

DEEZER_API = "https://api.deezer.com"
MODEL_PB = "/models/discogs-effnet-bs64-1.pb"
EMB_OUT_NODE = "PartitionedCall:1"   # 1280-d embedding (PartitionedCall:0 = genre logits)

_rl_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = 0.2  # ~5 rps ceiling to api.deezer.com


def throttle():
    with _rl_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def _get(url, tries=3, timeout=30):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.5 * (i + 1))
    raise last


def fetch_preview_url(deezer_id):
    throttle()
    r = _get(f"{DEEZER_API}/track/{deezer_id}", timeout=20)
    j = r.json()
    if isinstance(j, dict) and j.get("error"):
        raise RuntimeError(f"deezer_error:{j['error']}")
    return (j.get("preview") or "").strip()


# --------- Essentia model is loaded once per process (heavy TF graph) ----------
_model_local = threading.local()


def _embedder():
    m = getattr(_model_local, "m", None)
    if m is None:
        import essentia.standard as es
        _model_local.es = es
        _model_local.m = es.TensorflowPredictEffnetDiscogs(
            graphFilename=MODEL_PB, output=EMB_OUT_NODE
        )
        m = _model_local.m
    return _model_local.es, m


def embed_file(path):
    es, model = _embedder()
    audio = es.MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)()
    patches = model(audio)                    # (n_patches, 1280)
    v = np.asarray(patches, dtype=np.float32).mean(axis=0)
    n = float(np.linalg.norm(v))
    if n > 0:
        v = v / n
    return v, int(np.asarray(patches).shape[0])


def process(row):
    cid = str(row["catalog_id"]).strip()
    did = str(row["deezer_id"]).strip()
    base = {"catalog_id": cid, "deezer_id": did,
            "artist": row.get("artist", ""), "title": row.get("title", "")}
    try:
        url = fetch_preview_url(did)
        if not url:
            return {**base, "status": "no_preview"}, None
        r = _get(url, timeout=30)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            tmp.write(r.content)
            tmp.close()
            vec, npatch = embed_file(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return {**base, "status": "ok", "n_patches": npatch}, (cid, vec)
    except Exception as e:  # noqa: BLE001
        return {**base, "status": f"error:{type(e).__name__}", "err": str(e)[:200]}, None


STATUS_FIELDS = ["catalog_id", "deezer_id", "artist", "title", "status", "n_patches", "err"]


def load_sample(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def distinct_tracks(rows):
    seen, out = set(), []
    for r in rows:
        cid = str(r["catalog_id"]).strip()
        if cid not in seen:
            seen.add(cid)
            out.append(r)
    return out


# ------------------------------- embed phase --------------------------------

def run_embed(args):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    rows = distinct_tracks(load_sample(args.sample))
    if args.limit:
        rows = rows[: args.limit]
    print(f"[c9] embedding {len(rows)} distinct tracks | workers={args.workers}", flush=True)

    vectors, results = {}, []
    t0 = time.monotonic()
    out_f = open(args.status, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=STATUS_FIELDS, extrasaction="ignore")
    writer.writeheader()
    lock = threading.Lock()
    done = 0
    # workers default low: the TF graph is the bottleneck and each holds its own copy
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process, r) for r in rows]
        for fut in as_completed(futs):
            status, vec = fut.result()
            results.append(status)
            if vec is not None:
                vectors[vec[0]] = vec[1]
            with lock:
                writer.writerow(status)
                out_f.flush()
            done += 1
            if done % 50 == 0 or done == len(rows):
                nok = len(vectors)
                print(f"[c9] {done}/{len(rows)} ok={nok} "
                      f"elapsed={time.monotonic() - t0:.0f}s", flush=True)
    out_f.close()
    ids = list(vectors.keys())
    mat = np.vstack([vectors[i] for i in ids]) if ids else np.zeros((0, 1280), np.float32)
    np.savez_compressed(args.emb, ids=np.array(ids, dtype=object), vecs=mat)
    print(f"[c9] embedded {len(ids)}/{len(rows)} -> {args.emb}", flush=True)


# ------------------------------- eval phase ---------------------------------

def build_cooc(rows, universe):
    """set_id -> members (restricted to embedded universe); and per-track partner set."""
    set_members = defaultdict(set)
    for r in rows:
        cid = str(r["catalog_id"]).strip()
        if cid in universe:
            set_members[str(r["set_id"]).strip()].add(cid)
    partners = defaultdict(set)
    for members in set_members.values():
        for a in members:
            partners[a] |= members
    for a in partners:
        partners[a].discard(a)
    return partners


def _precision_recall(order, positives, ks):
    hits, out_p, out_r = 0, {}, {}
    npos = len(positives)
    for i, cid in enumerate(order, 1):
        if cid in positives:
            hits += 1
        if i in ks:
            out_p[i] = hits / i
            out_r[i] = hits / npos if npos else 0.0
    return out_p, out_r


def evaluate(ids, vecs, partners, artist_of, ks, exclude_same_artist=False, shuffle=False):
    idx = {c: i for i, c in enumerate(ids)}
    V = vecs
    if shuffle:
        perm = np.random.RandomState(0).permutation(len(ids))
        V = vecs[perm]
    n = len(ids)
    agg_p = {k: [] for k in ks}
    agg_lift = {k: [] for k in ks}
    agg_r = {k: [] for k in ks}
    first_ranks = []
    n_seeds = 0
    for seed in ids:
        pos = set(partners.get(seed, ()))
        if exclude_same_artist:
            a = artist_of.get(seed, "")
            pos = {p for p in pos if artist_of.get(p, "") != a}
        pos &= set(ids)
        pos.discard(seed)
        if not pos:
            continue
        n_seeds += 1
        si = idx[seed]
        sims = V @ V[si]
        sims[si] = -np.inf
        order_idx = np.argsort(-sims)
        order = [ids[j] for j in order_idx]
        base = len(pos) / (n - 1)          # random precision
        p, r = _precision_recall(order, pos, ks)
        for k in ks:
            agg_p[k].append(p[k])
            agg_r[k].append(r[k])
            agg_lift[k].append(p[k] / base if base > 0 else 0.0)
        for rank, cid in enumerate(order, 1):
            if cid in pos:
                first_ranks.append(rank)
                break
    return {
        "n_seeds": n_seeds,
        "prec": {k: float(np.mean(agg_p[k])) for k in ks},
        "recall": {k: float(np.mean(agg_r[k])) for k in ks},
        "lift": {k: float(np.mean(agg_lift[k])) for k in ks},
        "median_first_rank": float(np.median(first_ranks)) if first_ranks else float("nan"),
    }


def run_eval(args):
    data = np.load(args.emb, allow_pickle=True)
    ids = [str(x) for x in data["ids"].tolist()]
    vecs = data["vecs"].astype(np.float32)
    if len(ids) == 0:
        print("no embeddings", file=sys.stderr)
        return
    universe = set(ids)
    rows = load_sample(args.sample)
    artist_of = {str(r["catalog_id"]).strip(): (r.get("artist") or "").strip().lower()
                 for r in rows}
    partners = build_cooc(rows, universe)
    n_with_partner = sum(1 for c in ids if partners.get(c))
    ks = [1, 5, 10, 20]

    main = evaluate(ids, vecs, partners, artist_of, ks)
    xart = evaluate(ids, vecs, partners, artist_of, ks, exclude_same_artist=True)
    ctrl = evaluate(ids, vecs, partners, artist_of, ks, shuffle=True)

    print("\n" + "=" * 74)
    print(f"C9.0 BENCHMARK — Discogs-EffNet embeddings vs DJ-set co-occurrence")
    print("=" * 74)
    print(f"universe (embedded)     : {len(ids)} tracks")
    print(f"tracks with >=1 partner : {n_with_partner}")
    print(f"eval seeds (main)       : {main['n_seeds']}")

    def block(name, res):
        print(f"\n--- {name} (n_seeds={res['n_seeds']}) ---")
        print("   k     precision   recall    lift(vs random)")
        for k in ks:
            print(f"  {k:>3}     {res['prec'][k]*100:6.2f}%   "
                  f"{res['recall'][k]*100:6.2f}%     {res['lift'][k]:5.2f}x")
        print(f"   median rank of first co-occurring neighbour: {res['median_first_rank']:.0f}")

    block("EMBEDDING neighbours (all positives)", main)
    block("EMBEDDING neighbours (same-artist positives EXCLUDED)", xart)
    block("SHUFFLED-embedding control (should be ~1.00x)", ctrl)

    lift10 = main["lift"][10]
    lift10_xa = xart["lift"][10]
    print("\n" + "-" * 74)
    print("GO/NO-GO read (heuristic — William arbitrates):")
    print(f"   lift@10 all positives        : {lift10:5.2f}x")
    print(f"   lift@10 cross-artist only     : {lift10_xa:5.2f}x   <-- the load-bearing number")
    verdict = ("GO (strong content signal)" if lift10_xa >= 3
               else "LEAN GO (modest signal)" if lift10_xa >= 1.8
               else "NO-GO / needs C9.d fine-tuning" if lift10_xa < 1.3
               else "AMBIGUOUS — inspect")
    print(f"   -> {verdict}")
    print("   (cross-artist isolates genuine acoustic proximity from artist-identity leakage)")
    print("-" * 74, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["embed", "eval", "both"])
    ap.add_argument("--sample", default="/work/sample.csv")
    ap.add_argument("--emb", default="/work/embeddings.npz")
    ap.add_argument("--status", default="/work/status.csv")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.phase in ("embed", "both"):
        run_embed(args)
    if args.phase in ("eval", "both"):
        run_eval(args)


if __name__ == "__main__":
    main()
