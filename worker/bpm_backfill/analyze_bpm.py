"""E2.b — BPM analysis pass. Runs INSIDE the Docker container (essentia + ffmpeg).

Reads a candidates CSV (columns: ``id,deezer_id``) and, for each row:
throttle (~5 rps on the Deezer API) -> resolve the 30s preview URL via the public
``GET api.deezer.com/track/{id}`` -> transient MP3 download ->
``RhythmExtractor2013(method="multifeature")`` -> (bpm, confidence).

The BPM is kept ONLY when confidence >= ``--min-conf`` (default 2.0, the E2.a
gate: ~84% precision over ~82% of tracks); below the gate the row is reported
``status="low_conf"`` with NO bpm (better no BPM than a wrong one). The MP3 is
deleted right after analysis — NO audio is ever persisted (same CGU posture as
the E2.a benchmark; the preview URL itself is never stored either).

Output CSV columns: ``id,bpm,conf,status``
  status: ok | low_conf | no_preview | error:<ExceptionName>
``bpm`` is rounded to 1 decimal, ``conf`` to 2. A failed row never crashes the
run — it is written with an ``error:*`` status and the pass moves on.

Usage (container, via backfill_bpm.py or by hand):
    python /work/analyze_bpm.py --csv /work/to_analyze.csv --out /work/results.csv \
        [--limit N] [--workers K] [--min-conf 2.0]
"""

import argparse
import csv
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import essentia.standard as es
import requests

DEEZER_API = "https://api.deezer.com"
MIN_CONF = 2.0
FIELDNAMES = ["id", "bpm", "conf", "status"]

# Deezer API throttle (~5 rps), shared across worker threads — mirrors the E2.a
# benchmark harness. Only the /track/{id} lookup is throttled; the preview MP3
# itself is served by the CDN.
_rl_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = 0.2


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


def analyze_file(path):
    """(bpm, confidence) from RhythmExtractor2013 multifeature at 44.1 kHz."""
    audio = es.MonoLoader(filename=path, sampleRate=44100)()
    bpm, _beats, conf, _estimates, _intervals = es.RhythmExtractor2013(
        method="multifeature"
    )(audio)
    return float(bpm), float(conf)


def process(row, min_conf):
    out = {"id": row["id"], "bpm": "", "conf": "", "status": ""}
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
            bpm, conf = analyze_file(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        out["conf"] = round(conf, 2)
        if conf >= min_conf:
            out["bpm"] = round(bpm, 1)
            out["status"] = "ok"
        else:
            out["status"] = "low_conf"
        return out
    except Exception as e:  # noqa: BLE001
        out["status"] = f"error:{type(e).__name__}"
        return out


def main():
    ap = argparse.ArgumentParser(
        description="Analyze Deezer previews for BPM (RhythmExtractor2013, "
        "confidence-gated) — E2.b container pass"
    )
    ap.add_argument("--csv", default="/work/to_analyze.csv")
    ap.add_argument("--out", default="/work/results.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--min-conf", type=float, default=MIN_CONF)
    args = ap.parse_args()

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]
    print(
        f"[bpm-backfill] {len(rows)} tracks | workers={args.workers} "
        f"| min_conf={args.min_conf} | out={args.out}",
        flush=True,
    )

    t0 = time.monotonic()
    lock = threading.Lock()
    done = 0
    counts = {"ok": 0, "low_conf": 0, "no_preview": 0, "error": 0}
    with open(args.out, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(process, r, args.min_conf) for r in rows]
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
                        f"[bpm-backfill] {done}/{len(rows)} ok={counts['ok']} "
                        f"low_conf={counts['low_conf']} "
                        f"elapsed={time.monotonic() - t0:.0f}s",
                        flush=True,
                    )
    print(
        f"[bpm-backfill] done: ok={counts['ok']} low_conf={counts['low_conf']} "
        f"no_preview={counts['no_preview']} error={counts['error']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
