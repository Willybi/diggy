"""C9.0 / C9.0-bis benchmark — do content-embedding neighbours predict DJ-set co-occurrence?

Multi-model harness (C9.0-bis): the SAME frozen sample (`sample.csv`) is embedded by each
candidate model, then the metric is computed on the COMMON universe (tracks all models embedded
successfully) so the models are compared apples-to-apples.

Models (`--model`):
  - effnet : Essentia Discogs-EffNet (1280-d, TF CNN, 16 kHz). The C9.0 baseline.
             Needs the essentia-tensorflow image (Dockerfile).
  - clap   : LAION CLAP htsat-unfused via HF transformers (512-d, 48 kHz). Audio-TEXT aligned
             (opens text->audio search, C9.d). Needs the torch image (Dockerfile.torch).
  - mert   : m-a-p/MERT-v1-95M via HF transformers (768-d, 24 kHz, time-mean over layer-mean).
             Needs the torch image (Dockerfile.torch). MERT-330M is deliberately out (too slow on CPU).

Phase `embed`: for each distinct catalog track in the sample, resolve the Deezer preview live
(public GET api.deezer.com/track/{id} -> .preview), download the 30 s MP3 transiently, run the
chosen model, mean/L2-normalise into one vector, delete the MP3. No audio is persisted (CGU posture,
same as E2.a). Vectors -> embeddings_<model>.npz ; per-track status -> status_<model>.csv.

Phase `eval`: rebuild the co-occurrence graph from the sample and measure precision@k / recall@k /
LIFT@k of the embedding neighbours vs chance, for one model's npz.

Phase `compare`: load several embeddings_<model>.npz, restrict to the COMMON embedded universe,
and print lift@k (all-positives + cross-artist) side by side. This is the C9.0-bis deliverable.

Usage (in the container):
  # essentia image:
  python /work/embed_eval.py embed --model effnet [--workers K] [--limit N]
  # torch image:
  python /work/embed_eval.py embed --model clap  --workers 4
  python /work/embed_eval.py embed --model mert  --workers 4
  # anywhere (pure numpy):
  python /work/embed_eval.py eval    --model effnet
  python /work/embed_eval.py compare --models effnet,clap,mert
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict

import numpy as np
import requests

DEEZER_API = "https://api.deezer.com"

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


def ffmpeg_decode(path, sr):
    """Decode an audio file to mono float32 at `sr` Hz via ffmpeg (raw f32le on stdout).

    Used by the torch models (CLAP/MERT). Robust MP3 decode without extra audio libs — ffmpeg is
    already in the image. EffNet keeps essentia's MonoLoader (proven in C9.0)."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def _l2(v):
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


# --------------------------- model embedders --------------------------------
# Each model is loaded ONCE per worker thread (heavy graph) via thread-local storage, so the
# ThreadPoolExecutor provides the parallelism. Imports are inside each loader so an image only
# needs its own model's deps (essentia OR torch), never both.
#
# An embedder returns (outputs, n_frames) where `outputs` is a dict {output_name: np.array}. Most
# models yield one output; CLAP yields TWO from ONE forward (clap = projected 512-d, clap_pre =
# pre-projection 768-d, protocol v2 A1). MERT yields the 13 per-layer time-means RAW (13,768) — L2
# and layer selection happen at eval time so mert_mean_all/L6/L9/L12 cost no re-inference.

_local = threading.local()
CLAP_CKPT = "laion/larger_clap_music"   # music-trained checkpoint (protocol v2 A1)
MERT_CKPT = "m-a-p/MERT-v1-95M"


def _effnet_embed(path):
    m = getattr(_local, "effnet", None)
    if m is None:
        import essentia.standard as es
        _local.es = es
        # embeddings node = PartitionedCall:1 (1280-d penultimate); :0 = genre logits
        _local.effnet = es.TensorflowPredictEffnetDiscogs(
            graphFilename="/models/discogs-effnet-bs64-1.pb", output="PartitionedCall:1"
        )
        m = _local.effnet
    es = _local.es
    audio = es.MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)()
    patches = m(audio)                         # (n_patches, 1280)
    v = np.asarray(patches, dtype=np.float32).mean(axis=0)
    return {"effnet": _l2(v)}, int(np.asarray(patches).shape[0])


def _clap_windows(wav, sr=48000, win_s=10):
    """Split into fixed 10 s windows (HTSAT native), so CLAP sees the full 30 s like EffNet/MERT
    (protocol v2 A1: segment handling held constant). Short tails are kept if >= 1 s."""
    w = int(sr * win_s)
    n = max(1, len(wav) // w)
    out = [wav[i * w:(i + 1) * w] for i in range(n)]
    tail = wav[n * w:]
    if len(tail) >= sr:
        out.append(tail)
    return out


def _clap_embed(path):
    pair = getattr(_local, "clap", None)
    if pair is None:
        import torch
        from transformers import ClapModel, ClapProcessor
        torch.set_num_threads(1)               # 1 intra-op thread/worker; parallelism = worker pool
        model = ClapModel.from_pretrained(CLAP_CKPT).eval()
        proc = ClapProcessor.from_pretrained(CLAP_CKPT)
        _local.torch = torch
        _local.clap = (model, proc)
        pair = _local.clap
    torch = _local.torch
    model, proc = pair
    wav = ffmpeg_decode(path, 48000)                    # CLAP expects 48 kHz
    projs, pres = [], []
    for win in _clap_windows(wav, 48000, 10):
        inputs = proc(audios=win, sampling_rate=48000, return_tensors="pt")
        with torch.no_grad():
            # one audio forward -> pooled (pre-projection, ~768-d) + projected (512-d)
            audio_out = model.audio_model(**{k: v for k, v in inputs.items()})
            pooled = audio_out[1] if len(audio_out) > 1 else audio_out.pooler_output
            proj = model.audio_projection(pooled)
        pres.append(pooled.squeeze(0).numpy().astype(np.float32))
        projs.append(proj.squeeze(0).numpy().astype(np.float32))
    return {
        "clap": _l2(np.mean(projs, axis=0)),            # projected 512-d (joint space)
        "clap_pre": _l2(np.mean(pres, axis=0)),         # pre-projection 768-d
    }, len(projs)


def _mert_embed(path):
    pair = getattr(_local, "mert", None)
    if pair is None:
        import torch
        from transformers import AutoModel, Wav2Vec2FeatureExtractor
        torch.set_num_threads(1)
        # trust_remote_code: MERT ships a custom modeling class on the Hub
        model = AutoModel.from_pretrained(MERT_CKPT, trust_remote_code=True).eval()
        proc = Wav2Vec2FeatureExtractor.from_pretrained(MERT_CKPT, trust_remote_code=True)
        _local.torch = torch
        _local.mert = (model, proc)
        pair = _local.mert
    torch = _local.torch
    model, proc = pair
    wav = ffmpeg_decode(path, 24000)                    # MERT expects 24 kHz
    inputs = proc(wav, sampling_rate=24000, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs, output_hidden_states=True)
    # hidden_states: tuple (L0..L12) of (1, T, H). Store the per-layer TIME-mean RAW (13, H);
    # L2 + layer choice (mean_all/L6/L9/L12) happen at eval. L0=input embeddings, L1..L12=transformer.
    hs = torch.stack(out.hidden_states)                 # (13, 1, T, H)
    layers = hs.mean(dim=2).squeeze(1).numpy().astype(np.float32)   # (13, H)
    return {"mert": layers}, int(hs.shape[0])


EMBEDDERS = {"effnet": _effnet_embed, "clap": _clap_embed, "mert": _mert_embed}


def process(row, model):
    cid = str(row["catalog_id"]).strip()
    did = str(row["deezer_id"]).strip()
    base = {"catalog_id": cid, "deezer_id": did,
            "artist": row.get("artist", ""), "title": row.get("title", "")}
    embed = EMBEDDERS[model]
    try:
        url = fetch_preview_url(did)
        if not url:
            return {**base, "status": "no_preview"}, None
        r = _get(url, timeout=30)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            tmp.write(r.content)
            tmp.close()
            t_inf = time.monotonic()
            outputs, nframe = embed(tmp.name)           # {name: vec}; B4: time inference only
            infer_s = time.monotonic() - t_inf
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return {**base, "status": "ok", "n_patches": nframe,
                "infer_s": round(infer_s, 3)}, (cid, outputs)
    except Exception as e:  # noqa: BLE001
        return {**base, "status": f"error:{type(e).__name__}", "err": str(e)[:200]}, None


STATUS_FIELDS = ["catalog_id", "deezer_id", "artist", "title", "status", "n_patches", "infer_s", "err"]


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


def _status_path(args):
    return args.status or f"/work/status_{args.model}.csv"


# ------------------------------- embed phase --------------------------------

def run_embed(args):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    rows = distinct_tracks(load_sample(args.sample))
    if args.limit:
        rows = rows[: args.limit]
    status_out = _status_path(args)
    print(f"[c9] model={args.model} embedding {len(rows)} distinct tracks | "
          f"workers={args.workers}", flush=True)

    acc = defaultdict(dict)          # output_name -> {cid: np.array}
    infer_times = []
    t0 = time.monotonic()
    out_f = open(status_out, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=STATUS_FIELDS, extrasaction="ignore")
    writer.writeheader()
    lock = threading.Lock()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process, r, args.model) for r in rows]
        for fut in as_completed(futs):
            status, payload = fut.result()
            if payload is not None:
                cid, outputs = payload
                for name, arr in outputs.items():
                    acc[name][cid] = arr
                if "infer_s" in status:
                    infer_times.append(status["infer_s"])
            with lock:
                writer.writerow(status)
                out_f.flush()
            done += 1
            if done % 50 == 0 or done == len(rows):
                nok = len(next(iter(acc.values()))) if acc else 0
                print(f"[c9] {args.model} {done}/{len(rows)} ok={nok} "
                      f"elapsed={time.monotonic() - t0:.0f}s", flush=True)
    out_f.close()
    for name, d in acc.items():
        ids = list(d.keys())
        mat = np.stack([d[i] for i in ids]) if ids else np.zeros((0, 0), np.float32)
        out = args.emb or f"/work/embeddings_{name}.npz"
        np.savez_compressed(out, ids=np.array(ids, dtype=object), vecs=mat)
        print(f"[c9] {name}: {len(ids)}/{len(rows)} shape={mat.shape} -> {out}", flush=True)
    if infer_times:
        arr = np.array(infer_times)
        # B4: extrapolate CPU inference cost to the 175k backfill (per-thread, single stream)
        print(f"[c9] {args.model} inference/track (CPU): mean={arr.mean():.2f}s "
              f"median={np.median(arr):.2f}s | 175k @1 thread ≈ {arr.mean()*175000/3600:.0f}h",
              flush=True)


# ======================= eval phase — unified loop (v2) =====================
# Every config (embedding, baseline, fusion) exposes a scorer scores_fn(si) -> np.array over the
# universe (higher = closer), or None to skip the seed. ONE metric loop computes precision@k /
# lift@k with per-seed arrays -> mean, median, bootstrap CI95, degree strata. Exclusions
# (none/cross_artist/cross_release) and modes (cooccurrence/adjacency@3) reuse the same loop.

K_LIST = [1, 5, 10, 20]
BPM_RANGE = 60.0     # normaliser for gower bpm component
YEAR_RANGE = 20.0


def _load_emb(path):
    data = np.load(path, allow_pickle=True)
    ids = [str(x) for x in data["ids"].tolist()]
    return ids, data["vecs"]


def load_meta(path):
    out = {}
    for r in load_sample(path):
        out[str(r["catalog_id"]).strip()] = r
    return out


def load_pos(path):
    """set_id -> list of (position, catalog_id)."""
    sets = defaultdict(list)
    for r in load_sample(path):
        try:
            p = int(r["position"])
        except (ValueError, KeyError, TypeError):
            continue
        sets[str(r["set_id"]).strip()].append((p, str(r["catalog_id"]).strip()))
    return sets


def load_genre_graph(map_path, edges_path):
    name_to_node, parent = {}, defaultdict(set)
    if os.path.exists(map_path):
        for r in load_sample(map_path):
            name_to_node[r["raw_name"].strip()] = int(r["node_id"])
    if os.path.exists(edges_path):
        for r in load_sample(edges_path):
            parent[int(r["from_node_id"])].add(int(r["to_node_id"]))
    return name_to_node, parent


def expand_genre_tokens(genres, name_to_node, parent, full):
    """Token set for a track's genres. gower_lite: raw tokens. gower_full: raw node + ancestors
    (reuses C2's parent walk); unmapped names fall back to their raw token."""
    toks = set()
    for g in genres:
        g = g.strip()
        if not g:
            continue
        if full and g in name_to_node:
            nid = name_to_node[g]
            seen, stack = set(), [nid]
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                toks.add(f"n{x}")
                stack.extend(parent.get(x, ()))
        else:
            toks.add("g" + g.lower())
    return toks


def build_partners(rows, universe):
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


def build_adjacency(pos_sets, universe, n_adj=3):
    """Adjacency positives: two tracks within n_adj positions in a shared set (protocol B3)."""
    partners = defaultdict(set)
    for members in pos_sets.values():
        ms = sorted((p, c) for p, c in members if c in universe)
        for i in range(len(ms)):
            pi, ci = ms[i]
            for j in range(i + 1, len(ms)):
                pj, cj = ms[j]
                if pj - pi > n_adj:
                    break
                partners[ci].add(cj)
                partners[cj].add(ci)
    return partners


def _parse_camelot(k):
    m = re.match(r"^\s*(\d{1,2})([ABab])\s*$", k or "")
    if not m:
        return np.nan, np.nan
    return float(m.group(1)), (0.0 if m.group(2).upper() == "A" else 1.0)


def _parse_year(d):
    try:
        return float(str(d)[:4])
    except (ValueError, TypeError):
        return np.nan


def build_feats(ids, meta, name_to_node, parent):
    n = len(ids)
    bpm = np.full(n, np.nan, np.float32)
    cnum = np.full(n, np.nan, np.float32)
    clet = np.full(n, np.nan, np.float32)
    year = np.full(n, np.nan, np.float32)
    labels, artist, album, isrc, normkey, title = [], [], [], [], [], []
    lite_sets, full_sets = [], []
    for i, cid in enumerate(ids):
        m = meta.get(cid, {})
        try:
            bpm[i] = float(m.get("bpm") or "nan")
        except ValueError:
            pass
        cnum[i], clet[i] = _parse_camelot(m.get("key"))
        year[i] = _parse_year(m.get("release_date"))
        labels.append((m.get("label") or "").strip().lower())
        artist.append((m.get("artist") or "").strip().lower())   # from meta join? fallback below
        album.append((m.get("album_id") or "").strip())
        isrc.append((m.get("isrc") or "").strip())
        normkey.append((m.get("normalized_key") or "").strip())
        gl = [g for g in (m.get("genres") or "").split("|") if g.strip()]
        t = re.split(r"[\(\[]", (m.get("title") or "").lower())[0]
        title.append(re.sub(r"[^a-z0-9]", "", t))
        lite_sets.append(expand_genre_tokens(gl, name_to_node, parent, full=False))
        full_sets.append(expand_genre_tokens(gl, name_to_node, parent, full=True))
    lab_id = _factorize(labels)
    return {
        "bpm": bpm, "cnum": cnum, "clet": clet, "year": year,
        "label_id": lab_id, "album": album, "isrc": isrc, "normkey": normkey,
        "title": title, "G_lite": _onehot(lite_sets), "G_full": _onehot(full_sets),
    }


def _factorize(vals):
    vocab, out = {}, np.full(len(vals), -1, np.int64)
    for i, v in enumerate(vals):
        if not v:
            continue
        out[i] = vocab.setdefault(v, len(vocab))
    return out


def _onehot(token_sets):
    vocab = {}
    for s in token_sets:
        for t in s:
            vocab.setdefault(t, len(vocab))
    M = np.zeros((len(token_sets), max(1, len(vocab))), np.float32)
    for i, s in enumerate(token_sets):
        for t in s:
            M[i, vocab[t]] = 1.0
    return M


# ---- scorers (scores_fn(si) -> np.array over ids, higher=closer; or None to skip seed) ----

def emb_scorer(V):
    def f(si):
        return V @ V[si]
    return f


def pop_scorer(partners, ids):
    deg = np.array([len(partners.get(c, ())) for c in ids], np.float32)
    return lambda si: deg


def _dist_scorer(vals, rng):
    valid = ~np.isnan(vals)
    med = np.nanmedian(np.abs(vals - np.nanmean(vals))) if valid.any() else 0.0

    def f(si):
        if np.isnan(vals[si]):
            return None
        d = np.abs(vals - vals[si])
        d = np.where(valid, d, med)          # missing candidate -> neutral
        return -d
    return f


def bpm_camelot_scorer(feats):
    bpm, cnum, clet = feats["bpm"], feats["cnum"], feats["clet"]

    def f(si):
        if np.isnan(bpm[si]) and np.isnan(cnum[si]):
            return None
        s = np.zeros(len(bpm), np.float32)
        if not np.isnan(bpm[si]):
            d = np.abs(bpm - bpm[si]) / BPM_RANGE
            s += -np.where(~np.isnan(bpm), np.clip(d, 0, 1), 0.5)
        if not np.isnan(cnum[si]):
            dd = np.abs(cnum - cnum[si])
            cyc = np.minimum(dd, 12 - dd)
            dl = (clet != clet[si]).astype(np.float32)
            dist = (cyc + dl) / 7.0
            s += -np.where(~np.isnan(cnum), dist, 0.5)
        return s
    return f


def gower_scorer(feats, genre_key):
    bpm, cnum, clet, year = feats["bpm"], feats["cnum"], feats["clet"], feats["year"]
    lab = feats["label_id"]
    G = feats[genre_key]
    gsum = G.sum(1)

    def f(si):
        num = np.zeros(G.shape[0], np.float32)
        den = np.zeros(G.shape[0], np.float32)
        if not np.isnan(bpm[si]):
            v = ~np.isnan(bpm)
            sim = 1 - np.clip(np.abs(bpm - bpm[si]) / BPM_RANGE, 0, 1)
            num += np.where(v, sim, 0); den += v
        if not np.isnan(cnum[si]):
            v = ~np.isnan(cnum)
            dd = np.abs(cnum - cnum[si]); cyc = np.minimum(dd, 12 - dd)
            dist = (cyc + (clet != clet[si]).astype(np.float32)) / 7.0
            num += np.where(v, 1 - dist, 0); den += v
        if gsum[si] > 0:
            inter = G @ G[si]
            union = gsum[si] + gsum - inter
            jac = np.where(union > 0, inter / np.where(union == 0, 1, union), 0)
            v = (gsum > 0).astype(np.float32)
            num += jac * v; den += v
        if lab[si] >= 0:
            v = (lab >= 0).astype(np.float32)
            num += (lab == lab[si]).astype(np.float32) * v; den += v
        if not np.isnan(year[si]):
            v = ~np.isnan(year)
            sim = 1 - np.clip(np.abs(year - year[si]) / YEAR_RANGE, 0, 1)
            num += np.where(v, sim, 0); den += v
        return np.where(den > 0, num / np.where(den == 0, 1, den), 0)
    return f


def label_year_scorer(feats):
    lab, year = feats["label_id"], feats["year"]

    def f(si):
        s = np.zeros(len(lab), np.float32)
        if lab[si] >= 0:
            s += (lab == lab[si]).astype(np.float32)
        if not np.isnan(year[si]):
            s += (year == year[si]).astype(np.float32)
        return s
    return f


def _rankdesc(s):
    order = np.argsort(-s)
    ranks = np.empty(len(s), np.int64)
    ranks[order] = np.arange(len(s))
    return ranks


def fusion_scorer(a, b):
    def f(si):
        sa, sb = a(si), b(si)
        if sa is None or sb is None:
            return None
        return -(_rankdesc(sa) + _rankdesc(sb)).astype(np.float32)
    return f


def _excluder(feats, ids, kind):
    if kind == "none":
        return None
    idx = {c: i for i, c in enumerate(ids)}
    art, lab, alb, isr, nk, tit = (feats["artist_ids"], feats["label_id"], feats["album"],
                                   feats["isrc"], feats["normkey"], feats["title"])

    def same_artist(i, j):
        return art[i] == art[j] and art[i] >= 0
    if kind == "cross_artist":
        def ex(seed, cand):
            i, j = idx[seed], idx[cand]
            return same_artist(i, j)
        return ex
    if kind == "cross_label":                 # xlabel: how much of the lift is label-ecosystem
        def ex(seed, cand):
            i, j = idx[seed], idx[cand]
            return same_artist(i, j) or (lab[i] >= 0 and lab[i] == lab[j])
        return ex

    def ex(seed, cand):                       # cross_release
        i, j = idx[seed], idx[cand]
        if same_artist(i, j):
            return True
        if alb[i] and alb[i] == alb[j]:
            return True
        if isr[i] and isr[i] == isr[j]:
            return True
        if nk[i] and nk[i] == nk[j]:
            return True
        if tit[i] and tit[i] == tit[j]:
            return True
        return False
    return ex


HIT_K = (10, 20, 50)


def eval_scorer(ids, scores_fn, partners, excl_fn, ks=K_LIST):
    idx = {c: i for i, c in enumerate(ids)}
    n = len(ids)
    maxk = max(max(ks), max(HIT_K))            # top-50 for hit-rate@50
    per_lift = {k: [] for k in ks}
    per_hit = {k: [] for k in HIT_K}           # hit-rate: >=1 true setmate in top-k
    degs = []
    for si, seed in enumerate(ids):
        pos = partners.get(seed)
        if not pos:
            continue
        pos = {p for p in pos if p in idx and p != seed}
        if excl_fn:
            pos = {p for p in pos if not excl_fn(seed, p)}
        if not pos:
            continue
        s = scores_fn(si)
        if s is None:
            continue
        s = s.astype(np.float32).copy()
        s[si] = -np.inf
        top = np.argsort(-s)[:maxk]
        member = np.array([1 if ids[j] in pos else 0 for j in top], np.float32)
        cum = np.cumsum(member)
        base = len(pos) / (n - 1)
        for k in ks:
            per_lift[k].append((cum[k - 1] / k) / base if base > 0 else 0.0)
        for k in HIT_K:
            per_hit[k].append(1.0 if cum[k - 1] >= 1 else 0.0)
        degs.append(len(pos))
    out = {"n_seeds": len(degs), "degs": np.array(degs)}
    for k in ks:
        out[k] = np.array(per_lift[k])
    out["hit"] = {k: np.array(per_hit[k]) for k in HIT_K}
    return out


def _boot_ci(arr, n=1000):
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    rs = np.random.RandomState(0)
    means = [arr[rs.randint(0, len(arr), len(arr))].mean() for _ in range(n)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _strata(lift_arr, degs):
    out = {}
    for name, lo, hi in [("3-9", 3, 9), ("10+", 10, 10**9)]:
        m = (degs >= lo) & (degs <= hi)
        out[name] = float(lift_arr[m].mean()) if m.any() else float("nan")
    return out


def run_eval(args):
    run_compare(args)   # single-model eval is just compare with one model


# ----------------------------- compare phase --------------------------------

def _expand_emb_configs(models, base):
    """Load each embedding npz -> {config_name: (ids, vecs2d)}. MERT (N,13,H) expands to
    mert_mean_all + mert_L6/L9/L12 (each L2-normalised) without re-inference."""
    cfgs = {}
    for m in models:
        path = os.path.join(base, f"embeddings_{m}.npz")
        if not os.path.exists(path):
            print(f"[compare] skip {m}: {path} absent", file=sys.stderr)
            continue
        ids, vecs = _load_emb(path)
        if m == "mert" and vecs.ndim == 3:                 # (N,13,H)
            def norm(a):
                return a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-9, None)
            cfgs["mert_mean_all"] = (ids, norm(vecs.mean(1)))
            for L in (6, 9, 12):
                cfgs[f"mert_L{L}"] = (ids, norm(vecs[:, L, :]))
        else:
            cfgs[m] = (ids, vecs.astype(np.float32))
    return cfgs


def run_compare(args):
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    base = os.path.dirname(args.sample) or "."
    emb = _expand_emb_configs(models, base)
    if not emb:
        print("[compare] no embeddings available", file=sys.stderr)
        return
    common = sorted(set.intersection(*[set(i) for i, _ in emb.values()]))
    print(f"[compare] embedding configs: {list(emb)} | common universe = {len(common)}", flush=True)

    rows = load_sample(args.sample)
    meta = load_meta(args.meta)
    # artist from sample.csv (authoritative), fold into meta rows
    art_of = {str(r["catalog_id"]).strip(): (r.get("artist") or "").strip().lower() for r in rows}
    for cid, m in meta.items():
        m["artist"] = art_of.get(cid, "")
    name_to_node, parent = load_genre_graph(args.genre_map, args.genre_edges)
    feats = build_feats(common, meta, name_to_node, parent)
    feats["artist_ids"] = _factorize([art_of.get(c, "") for c in common])

    partners = build_partners(rows, set(common))
    adj = build_adjacency(load_pos(args.pos), set(common)) if os.path.exists(args.pos) else {}

    # aligned embedding matrices on the common universe
    V = {}
    for name, (ids_all, vecs_all) in emb.items():
        pos = {c: i for i, c in enumerate(ids_all)}
        V[name] = np.vstack([vecs_all[pos[c]] for c in common]).astype(np.float32)

    # ---- assemble configs: scorer + flags ----
    emb_mat = dict(V)                                    # every embedding config -> its matrix
    if "effnet" in V and "clap" in V:
        emb_mat["effnet+clap"] = np.hstack([V["effnet"], V["clap"]])
    configs = []  # (name, dim, scorer, is_emb)
    for name, mat in emb_mat.items():
        configs.append((name, mat.shape[1], emb_scorer(mat), True))
    configs.append(("popularity", 0, pop_scorer(partners, common), False))
    configs.append(("bpm", 1, _dist_scorer(feats["bpm"], BPM_RANGE), False))
    configs.append(("bpm_camelot", 2, bpm_camelot_scorer(feats), False))
    configs.append(("label_year", 2, label_year_scorer(feats), False))
    g_lite = gower_scorer(feats, "G_lite")
    configs.append(("gower_lite", 5, g_lite, False))
    g_full = gower_scorer(feats, "G_full")
    configs.append(("gower_full", 5, g_full, False))
    for em in ("effnet", "clap", "mert_mean_all"):
        if em in V:
            configs.append((f"gower_lite+{em}", 0, fusion_scorer(g_lite, emb_scorer(V[em])), False))

    excl = {k: _excluder(feats, common, k)
            for k in ("none", "cross_artist", "cross_release", "cross_label")}

    results = {}
    for name, dim, fn, is_emb in configs:
        r = {"dim": dim, "is_emb": is_emb}
        allp = eval_scorer(common, fn, partners, excl["none"])
        xart = eval_scorer(common, fn, partners, excl["cross_artist"])
        xrel = eval_scorer(common, fn, partners, excl["cross_release"])
        xlab = eval_scorer(common, fn, partners, excl["cross_label"])
        r["all"] = {k: float(allp[k].mean()) for k in K_LIST}
        r["xart"] = {k: float(xart[k].mean()) for k in K_LIST}
        r["xart_med10"] = float(np.median(xart[10])) if len(xart[10]) else float("nan")
        r["xart_ci10"] = _boot_ci(xart[10])
        r["xrel10"] = float(xrel[10].mean()) if len(xrel[10]) else float("nan")
        r["xlabel10"] = float(xlab[10].mean()) if len(xlab[10]) else float("nan")
        r["strata10"] = _strata(xart[10], xart["degs"])
        # hit-rate@k (>=1 true setmate in top-k) on cross-artist positives, + degree strata (P4)
        r["hit"] = {k: float(xart["hit"][k].mean()) for k in HIT_K}
        r["hit10_strata"] = _strata(xart["hit"][10], xart["degs"])
        if adj:
            adjr = eval_scorer(common, fn, adj, excl["cross_artist"])
            r["adj3_10"] = float(adjr[10].mean()) if len(adjr[10]) else float("nan")
        if is_emb:
            perm = np.random.RandomState(0).permutation(len(common))
            shuf_fn = emb_scorer(emb_mat[name][perm])
            r["shuf10"] = float(eval_scorer(common, shuf_fn, partners, excl["cross_artist"])[10].mean())
        results[name] = r

    _print_compare(results, common)
    out_json = os.path.join(base, "compare_results.json")
    with open(out_json, "w") as f:
        json.dump({"n_common": len(common), "results": results}, f, indent=2)
    print(f"[compare] wrote {out_json}", flush=True)
    return results


def _print_compare(results, common):
    print("\n" + "=" * 100)
    print(f"C9.0-bis MODEL COMPARISON — common universe = {len(common)} tracks")
    print("=" * 100)
    hdr = (f"{'config':<18}{'dim':>5}{'all@10':>9}{'xart@10':>10}{'ci95':>16}"
           f"{'xrel@10':>9}{'xlbl@10':>9}{'adj3@10':>9}{'shuf@10':>9}{'med':>7}")
    print(hdr)
    print("-" * 110)
    best = (None, -1.0)
    for name, r in results.items():
        ci = f"[{r['xart_ci10'][0]:.1f},{r['xart_ci10'][1]:.1f}]"
        print(f"{name:<18}{r['dim']:>5}{r['all'][10]:>8.2f}x{r['xart'][10]:>9.2f}x{ci:>16}"
              f"{r['xrel10']:>8.2f}x{r.get('xlabel10', float('nan')):>8.2f}x"
              f"{r.get('adj3_10', float('nan')):>8.2f}x"
              f"{r.get('shuf10', float('nan')):>8.2f}x{r['xart_med10']:>6.1f}")
        if r["is_emb"] and r["xart"][10] > best[1]:
            best = (name, r["xart"][10])
    print("-" * 110)
    # hit-rate@k (>=1 setmate in top-k, cross-artist) for embedding configs + degree strata (P4)
    print("\n  hit-rate@k (>=1 vrai setmate dans le top-k, cross-artist) — configs embeddings :")
    print(f"  {'config':<18}{'hit@10':>8}{'hit@20':>8}{'hit@50':>8}   {'hit@10 par degré':>0}")
    for name, r in results.items():
        if not r["is_emb"]:
            continue
        st = r.get("hit10_strata", {})
        print(f"  {name:<18}{r['hit'][10]*100:>7.1f}%{r['hit'][20]*100:>7.1f}%"
              f"{r['hit'][50]*100:>7.1f}%   3-9={st.get('3-9', float('nan'))*100:.0f}%"
              f"  10+={st.get('10+', float('nan'))*100:.0f}%")
    print()
    gl = results.get("gower_lite", {}).get("xart", {}).get(10, float("nan"))
    print(f"  best embedding by xart@10 : {best[0]} ({best[1]:.2f}x)")
    print(f"  gower_lite xart@10        : {gl:.2f}x")
    if gl and gl == gl and best[1] > 0:
        ratio = best[1] / gl
        gf = results.get("gower_full", {}).get("xart", {}).get(10, float("nan"))
        trig = ratio < 1.5
        print(f"  best/gower_lite ratio     : {ratio:.2f}x  -> gower_full trigger (<1.5x): "
              f"{'ARMED — see gower_full row (%.2fx)' % gf if trig else 'not armed'}")
    print("=" * 100, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["embed", "eval", "both", "compare"])
    ap.add_argument("--model", choices=list(EMBEDDERS), default="effnet")
    ap.add_argument("--models", default="effnet,clap,mert", help="compare: CSV of model names")
    ap.add_argument("--sample", default="/work/sample.csv")
    ap.add_argument("--meta", default="/work/sample_meta.csv")
    ap.add_argument("--pos", default="/work/sample_pos.csv")
    ap.add_argument("--genre-map", default="/work/genre_map.csv")
    ap.add_argument("--genre-edges", default="/work/genre_edges.csv")
    ap.add_argument("--emb", default=None, help="override; default embeddings_<model>.npz")
    ap.add_argument("--status", default=None, help="override; default status_<model>.csv")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.phase in ("embed", "both"):
        run_embed(args)
    if args.phase in ("eval", "both", "compare"):
        run_compare(args)


if __name__ == "__main__":
    main()
