"""C9.a — EffNet embedding pass. Runs INSIDE the Docker container (essentia-tensorflow + ffmpeg).

Reads a candidates CSV (columns: ``id,deezer_id``) and, for each row:
throttle (~5 rps on the Deezer API) -> resolve the 30s preview URL via the public
``GET api.deezer.com/track/{id}`` -> transient MP3 download -> Discogs-EffNet
(``TensorflowPredictEffnetDiscogs``, node ``PartitionedCall:1``, 16 kHz) -> mean
over patches -> L2-normalise -> 1280 floats. The MP3 is deleted right after
inference — NO audio is ever persisted (same CGU posture as the C9.0-bis
benchmark; the preview URL itself is never stored either).

The embed logic is the ``_effnet_embed`` function validated in
``docs/c9-benchmark/embed_eval.py`` (frozen C9 v1 model). This container pass is
the twin of ``worker/bpm_backfill/analyze_bpm.py``, but instead of a scalar BPM
it emits a 1280-d vector.

Output CSV columns: ``id,status,dim,emb``
  status: ok | no_preview | error:<ExceptionName>
  emb:    JSON list of ``dim`` floats (6-decimal rounded) on status ok, else "".
A failed row never crashes the run — it is written with an ``error:*`` status and
the pass moves on. The host (``backfill_embeddings.py``) parses ``emb`` back and
formats the pgvector literal.

Usage (container, via backfill_embeddings.py or by hand):
    python /work/embed.py --csv /work/to_analyze.csv --out /work/results.csv \
        [--limit N] [--workers K]
"""

import argparse
import csv
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests

DEEZER_API = "https://api.deezer.com"
EMBEDDING_DIM = 1280
EMB_DECIMALS = 6
FIELDNAMES = ["id", "status", "dim", "emb"]

EFFNET_GRAPH = "/models/discogs-effnet-bs64-1.pb"

# Deezer API throttle (~5 rps), shared across worker threads — mirrors the C9.0-bis
# benchmark harness. Only the /track/{id} lookup is throttled; the preview MP3
# itself is served by the CDN.
_rl_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = 0.2

# Each worker thread loads the EffNet graph ONCE (heavy TF graph) via thread-local
# storage; the ThreadPoolExecutor provides the parallelism.
_local = threading.local()


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


def _l2(v):
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def effnet_embed(path):
    """1280-d L2-normalised EffNet embedding (mean over patches) — the frozen C9 v1
    logic from docs/c9-benchmark/embed_eval.py (``PartitionedCall:1``, 16 kHz)."""
    m = getattr(_local, "effnet", None)
    if m is None:
        import essentia.standard as es

        _local.es = es
        # embeddings node = PartitionedCall:1 (1280-d penultimate); :0 = genre logits
        _local.effnet = es.TensorflowPredictEffnetDiscogs(
            graphFilename=EFFNET_GRAPH, output="PartitionedCall:1"
        )
        m = _local.effnet
    es = _local.es
    audio = es.MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)()
    patches = m(audio)  # (n_patches, 1280)
    v = np.asarray(patches, dtype=np.float32).mean(axis=0)
    return _l2(v)


def process(row):
    out = {"id": row["id"], "status": "", "dim": "", "emb": ""}
    try:
        url = fetch_preview_url(str(row["deezer_id"]).strip())
        if not url:
            out["status"] = "no_preview"
            return out
        r = _get(url, timeout=30)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            tmp.write(r.content)
            tmp.close()
            vec = effnet_embed(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        rounded = [round(float(x), EMB_DECIMALS) for x in vec.tolist()]
        out["dim"] = len(rounded)
        out["emb"] = json.dumps(rounded)
        out["status"] = "ok"
        return out
    except Exception as e:  # noqa: BLE001
        out["status"] = f"error:{type(e).__name__}"
        return out


def main():
    ap = argparse.ArgumentParser(
        description="Embed Deezer previews with Discogs-EffNet (1280-d, L2-norm) "
        "— C9.a container pass"
    )
    ap.add_argument("--csv", default="/work/to_analyze.csv")
    ap.add_argument("--out", default="/work/results.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]
    print(
        f"[embed-backfill] {len(rows)} tracks | workers={args.workers} "
        f"| out={args.out}",
        flush=True,
    )

    t0 = time.monotonic()
    lock = threading.Lock()
    done = 0
    counts = {"ok": 0, "no_preview": 0, "error": 0}
    with open(args.out, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(process, r) for r in rows]
            for fut in as_completed(futs):
                res = fut.result()
                key = "error" if res["status"].startswith("error:") else res["status"]
                counts[key] += 1
                with lock:
                    writer.writerow(res)
                    out_f.flush()
                done += 1
                if done % 25 == 0 or done == len(rows):
                    print(
                        f"[embed-backfill] {done}/{len(rows)} ok={counts['ok']} "
                        f"no_preview={counts['no_preview']} error={counts['error']} "
                        f"elapsed={time.monotonic() - t0:.0f}s",
                        flush=True,
                    )
    print(
        f"[embed-backfill] done: ok={counts['ok']} "
        f"no_preview={counts['no_preview']} error={counts['error']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
