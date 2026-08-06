"""E2.a benchmark — measure BPM + key accuracy of preview audio analysis vs Beatport ground truth.

For each catalog row (id, deezer_id, bpm[, Camelot key] = Beatport truth): resolve the Deezer preview
URL live (public GET api.deezer.com/track/{id} -> .preview), download the 30s MP3 transiently, analyze
with Essentia (RhythmExtractor2013 multifeature BPM + KeyExtractor 'edma'/'edmm' profiles) and librosa
(beat_track BPM cross-check), convert key to Camelot, delete the MP3, score. No audio is persisted.

Also captures the Deezer track title/duration to spot version mismatches (a deezer_id pointing at a
different edit than the Beatport BPM/key describes = ground-truth noise, not an analysis failure).

Usage (in the container):  python /work/benchmark.py [--limit N] [--workers K] [--out PATH]
"""
import argparse
import csv
import os
import tempfile
import threading
import time

import numpy as np
import requests

import essentia.standard as es
import librosa

from camelot import bpm_fold, bpm_fold_ext, camelot_neighbors, key_to_camelot

DEEZER_API = "https://api.deezer.com"
KEY_PROFILES = ("edma", "edmm")

_rl_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = 0.2  # ~5 rps ceiling to api.deezer.com (repo scripts use 0.12s / ~8rps)


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


def fetch_track(deezer_id):
    """Return (preview_url, meta) from the public Deezer /track endpoint."""
    throttle()
    r = _get(f"{DEEZER_API}/track/{deezer_id}", timeout=20)
    j = r.json()
    if isinstance(j, dict) and j.get("error"):
        raise RuntimeError(f"deezer_error:{j['error']}")
    meta = {
        "deezer_title": (j.get("title") or "").strip(),
        "deezer_bpm_meta": j.get("bpm"),
        "deezer_dur": j.get("duration"),
    }
    return (j.get("preview") or "").strip(), meta


def analyze(path):
    audio = es.MonoLoader(filename=path, sampleRate=44100)()
    r_bpm, _beats, r_conf, _est, _iv = es.RhythmExtractor2013(method="multifeature")(audio)
    out = {"ess_bpm": round(float(r_bpm), 2), "ess_conf": round(float(r_conf), 2)}
    for prof in KEY_PROFILES:
        k, sc, st = es.KeyExtractor(profileType=prof)(audio)
        out[f"key_{prof}"] = key_to_camelot(k, sc)
        out[f"keyraw_{prof}"] = f"{k} {sc}"
        out[f"keystr_{prof}"] = round(float(st), 3)
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
        t = librosa.beat.beat_track(y=y, sr=sr)[0]
        out["lib_bpm"] = round(float(np.atleast_1d(t)[0]), 2)
    except Exception:  # noqa: BLE001
        out["lib_bpm"] = None
    return out


def process(row):
    did = str(row["deezer_id"]).strip()
    try:
        url, meta = fetch_track(did)
        row = {**row, **meta}
        if not url:
            return {**row, "status": "no_preview"}
        r = _get(url, timeout=30)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            tmp.write(r.content)
            tmp.close()
            res = analyze(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return {**row, "status": "ok", "mp3_bytes": len(r.content), **res}
    except Exception as e:  # noqa: BLE001
        return {**row, "status": f"error:{type(e).__name__}", "err": str(e)[:200]}


FIELDNAMES = [
    "id", "artist", "title", "bpm", "key", "deezer_id", "status", "mp3_bytes",
    "deezer_title", "deezer_bpm_meta", "deezer_dur",
    "ess_bpm", "ess_conf", "lib_bpm",
    "key_edma", "keyraw_edma", "keystr_edma",
    "key_edmm", "keyraw_edmm", "keystr_edmm", "err",
]


# ----------------------------- metrics -----------------------------

def _pct(vals, th):
    return 100.0 * sum(1 for v in vals if v <= th) / len(vals) if vals else 0.0


def bpm_ladder(ok, field, fold):
    errs = []
    for r in ok:
        a = r.get(field)
        if a in (None, ""):
            continue
        errs.append(fold(float(a), float(r["bpm"]))[1])
    errs.sort()
    m = len(errs)
    med = errs[m // 2] if m else float("nan")
    return m, _pct(errs, 1), _pct(errs, 2), _pct(errs, 3), med


def key_ladder(ok, prof, strength_th=0.0):
    exact = neigh = m = 0
    for r in ok:
        pred = r.get(f"key_{prof}")
        if not pred:
            continue
        st = r.get(f"keystr_{prof}")
        if st not in (None, "") and float(st) < strength_th:
            continue
        m += 1
        truth = str(r["key"]).strip().upper()
        exact += pred == truth
        neigh += pred in camelot_neighbors(truth)
    return m, (100.0 * exact / m if m else 0.0), (100.0 * neigh / m if m else 0.0)


def report(results):
    ok = [r for r in results if r.get("status") == "ok"]
    n = len(ok)
    print("\n" + "=" * 74)
    print(f"E2.a BENCHMARK — {n} analyzed / {len(results)} attempted ({len(results) - n} failed)")
    print("=" * 74)
    if not n:
        print("no successful analyses")
        return

    # ---- BPM: strict (roadmap) vs extended metrical fold ----
    print("\n--- BPM accuracy (all analyzed tracks) ---")
    for field, label in (("ess_bpm", "Essentia RhythmExtractor2013"), ("lib_bpm", "librosa beat_track")):
        m, s1, s2, s3, smed = bpm_ladder(ok, field, bpm_fold)
        _, e1, e2, e3, _ = bpm_ladder(ok, field, bpm_fold_ext)
        print(f"{label}  (n={m})")
        print(f"   strict x2/÷2 fold : <=1 {s1:5.1f}%  <=2 {s2:5.1f}%  <=3 {s3:5.1f}%   median {smed:.2f}")
        print(f"   extended metrical : <=1 {e1:5.1f}%  <=2 {e2:5.1f}%  <=3 {e3:5.1f}%")

    # ---- BPM confidence-coverage tradeoff (Essentia) — the lever for E2.b write policy ----
    print("\n--- Essentia BPM by confidence gate (strict fold, <=2 BPM = correct) ---")
    print("   conf>=   coverage    accuracy(<=2)   accuracy_ext(<=2)")
    for th in (0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        sub = [r for r in ok if r.get("ess_conf") not in (None, "") and float(r["ess_conf"]) >= th]
        if not sub:
            continue
        _, _, s2, _, _ = bpm_ladder(sub, "ess_bpm", bpm_fold)
        _, _, e2, _, _ = bpm_ladder(sub, "ess_bpm", bpm_fold_ext)
        print(f"   {th:4.1f}     {100 * len(sub) / n:5.1f}%      {s2:5.1f}%          {e2:5.1f}%")

    # ---- KEY: per profile, by strength gate ----
    for prof in KEY_PROFILES:
        print(f"\n--- KEY Essentia KeyExtractor(profile={prof}) ---")
        print("   strength>=   coverage    exact     exact-or-neighbor")
        for th in (0.0, 0.5, 0.6, 0.7, 0.8):
            m, ex, ng = key_ladder(ok, prof, th)
            if not m:
                continue
            print(f"   {th:4.1f}        {100 * m / n:5.1f}%     {ex:5.1f}%    {ng:5.1f}%")

    # ---- KEY: profile agreement as a confidence proxy ----
    agree = [r for r in ok if r.get("key_edma") and r.get("key_edma") == r.get("key_edmm")]
    if agree:
        m, ex, ng = key_ladder(agree, "edma", 0.0)
        print(f"\n   edma==edmm agreement: coverage {100 * len(agree) / n:5.1f}%   "
              f"exact {ex:5.1f}%   exact-or-neighbor {ng:5.1f}%")

    # ---- worst BPM offenders (diagnose version mismatch vs low-conf) ----
    scored = []
    for r in ok:
        a = r.get("ess_bpm")
        if a in (None, ""):
            continue
        _, err = bpm_fold(float(a), float(r["bpm"]))
        scored.append((err, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    print("\n--- worst 10 BPM misses (strict fold) — truth | ess(conf) | lib | title ---")
    for err, r in scored[:10]:
        print(f"   d{err:6.1f}  truth={float(r['bpm']):6.1f}  ess={r['ess_bpm']:>6}(c{r['ess_conf']})"
              f"  lib={r['lib_bpm']:>6}  | {str(r.get('title'))[:38]}  [dz:{str(r.get('deezer_title'))[:24]}]")

    # ---- headline GO/NO-GO vs roadmap thresholds ----
    _, _, p2_strict, _, _ = bpm_ladder(ok, "ess_bpm", bpm_fold)
    _, _, kng = key_ladder(ok, "edma", 0.0)
    print("\n" + "-" * 74)
    print("GO/NO-GO vs roadmap thresholds (Essentia primary, ALL tracks, no gating):")
    print(f"   BPM <=2 strict fold         : {p2_strict:5.1f}%   (proposed >=95%)  -> "
          f"{'PASS' if p2_strict >= 95 else 'FAIL'}")
    print(f"   KEY exact-or-neighbor (edma): {kng:5.1f}%   (proposed >=75%)  -> "
          f"{'PASS' if kng >= 75 else 'FAIL'}")
    print("   (see confidence/strength gates above — gating is the E2.b lever)")
    print("-" * 74, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/work/ground_truth.csv")
    ap.add_argument("--out", default="/work/results.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--report-only", default="")
    args = ap.parse_args()

    if args.report_only:
        with open(args.report_only, newline="", encoding="utf-8") as f:
            report(list(csv.DictReader(f)))
        return

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]
    print(f"[e2a] {len(rows)} tracks | workers={args.workers} | out={args.out}", flush=True)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    t0 = time.monotonic()
    write_lock = threading.Lock()
    out_f = open(args.out, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process, r) for r in rows]
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            with write_lock:
                writer.writerow(res)
                out_f.flush()
            done += 1
            if done % 25 == 0 or done == len(rows):
                nok = sum(1 for x in results if x.get("status") == "ok")
                print(f"[e2a] {done}/{len(rows)} ok={nok} elapsed={time.monotonic() - t0:.0f}s", flush=True)
    out_f.close()
    report(results)


if __name__ == "__main__":
    main()
