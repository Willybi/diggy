"""E2.a round 2 — head-to-head on the SAME frozen ground truth (ground_truth.csv).

BPM: Essentia RhythmExtractor2013 (round-1 baseline) vs Essentia TempoCNN (deeptemp, perceptual tempo).
KEY: Essentia KeyExtractor 'edma' vs 'shaath' (KeyFinder's key profiles) vs real libkeyfinder (optional).

One preview download per track, transient (deleted). No audio persisted.
Usage (container):  python /work/benchmark2.py [--limit N] [--workers K] [--out PATH] [--report-only CSV]
"""
import argparse
import csv
import os
import tempfile
import threading
import time

import requests

import essentia.standard as es

from camelot import bpm_fold, bpm_fold_ext, camelot_neighbors, key_to_camelot

DEEZER_API = "https://api.deezer.com"
TEMPOCNN_MODEL = "/models/deeptemp-k16-3.pb"

try:
    import keyfinder as _keyfinder
    HAVE_KF = True
except Exception:  # noqa: BLE001
    HAVE_KF = False

_tls = threading.local()


def _tempocnn():
    m = getattr(_tls, "tcnn", None)
    if m is None:
        m = es.TempoCNN(graphFilename=TEMPOCNN_MODEL)  # per-thread instance (graph load once/thread)
        _tls.tcnn = m
    return m


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


def analyze(path):
    audio44 = es.MonoLoader(filename=path, sampleRate=44100)()
    out = {}
    rt_bpm, _b, rt_conf, _e, _i = es.RhythmExtractor2013(method="multifeature")(audio44)
    out["rt_bpm"] = round(float(rt_bpm), 2)
    out["rt_conf"] = round(float(rt_conf), 2)
    audio11 = es.Resample(inputSampleRate=44100, outputSampleRate=11025)(audio44)
    g, _lt, _lp = _tempocnn()(audio11)
    out["tcnn_bpm"] = round(float(g), 2)
    for prof in ("edma", "shaath"):
        k, sc, st = es.KeyExtractor(profileType=prof)(audio44)
        out[f"key_{prof}"] = key_to_camelot(k, sc)
        out[f"keystr_{prof}"] = round(float(st), 3)
    if HAVE_KF:
        try:
            out["key_kf"] = str(_keyfinder.key(path).camelot()).strip().upper()
        except Exception:  # noqa: BLE001
            out["key_kf"] = None
    return out


def process(row):
    try:
        url = fetch_preview_url(str(row["deezer_id"]).strip())
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
        return {**row, "status": "ok", **res}
    except Exception as e:  # noqa: BLE001
        return {**row, "status": f"error:{type(e).__name__}", "err": str(e)[:200]}


FIELDNAMES = [
    "id", "artist", "title", "bpm", "key", "deezer_id", "status",
    "rt_bpm", "rt_conf", "tcnn_bpm",
    "key_edma", "keystr_edma", "key_shaath", "keystr_shaath", "key_kf", "err",
]


def _errs(ok, field, fold):
    out = []
    for r in ok:
        a = r.get(field)
        if a in (None, ""):
            continue
        out.append(fold(float(a), float(r["bpm"]))[1])
    return out


def _pct(vals, th):
    return 100.0 * sum(1 for v in vals if v <= th) / len(vals) if vals else 0.0


def _raw(a, t):
    return a, abs(a - t)


def bpm_row(ok, field, label):
    raw = _errs(ok, field, _raw)
    strict = _errs(ok, field, bpm_fold)
    ext = _errs(ok, field, bpm_fold_ext)
    strict_sorted = sorted(strict)
    med = strict_sorted[len(strict_sorted) // 2] if strict_sorted else float("nan")
    print(f"{label:<32} (n={len(strict)})")
    print(f"   raw (no fold) : <=1 {_pct(raw,1):5.1f}%  <=2 {_pct(raw,2):5.1f}%")
    print(f"   strict x2/÷2  : <=1 {_pct(strict,1):5.1f}%  <=2 {_pct(strict,2):5.1f}%  <=3 {_pct(strict,3):5.1f}%   median {med:.2f}")
    print(f"   extended metr : <=1 {_pct(ext,1):5.1f}%  <=2 {_pct(ext,2):5.1f}%  <=3 {_pct(ext,3):5.1f}%")


def key_line(ok, field, n, strength_field=None, strength_th=0.0):
    exact = neigh = m = 0
    for r in ok:
        pred = r.get(field)
        if not pred:
            continue
        if strength_field:
            st = r.get(strength_field)
            if st not in (None, "") and float(st) < strength_th:
                continue
        m += 1
        truth = str(r["key"]).strip().upper()
        exact += pred == truth
        neigh += pred in camelot_neighbors(truth)
    cov = 100.0 * m / n if n else 0.0
    ex = 100.0 * exact / m if m else 0.0
    ng = 100.0 * neigh / m if m else 0.0
    return cov, ex, ng


def report(results):
    ok = [r for r in results if r.get("status") == "ok"]
    n = len(ok)
    print("\n" + "=" * 74)
    print(f"E2.a ROUND 2 — {n} analyzed / {len(results)} attempted  (libkeyfinder={'YES' if HAVE_KF else 'no'})")
    print("=" * 74)
    if not n:
        print("no successful analyses")
        return

    print("\n--- BPM: RhythmExtractor2013 vs TempoCNN (all tracks) ---")
    bpm_row(ok, "rt_bpm", "Essentia RhythmExtractor2013")
    bpm_row(ok, "tcnn_bpm", "Essentia TempoCNN (deeptemp)")

    print("\n--- TempoCNN BPM by RhythmExtractor confidence gate (raw, <=2 = correct) ---")
    print("   conf>=   coverage   tcnn raw<=2   tcnn strict<=2")
    for th in (0.0, 1.5, 2.0, 2.5, 3.0):
        sub = [r for r in ok if r.get("rt_conf") not in (None, "") and float(r["rt_conf"]) >= th]
        if not sub:
            continue
        raw = _errs(sub, "tcnn_bpm", _raw)
        strict = _errs(sub, "tcnn_bpm", bpm_fold)
        print(f"   {th:4.1f}     {100*len(sub)/n:5.1f}%     {_pct(raw,2):5.1f}%        {_pct(strict,2):5.1f}%")

    print("\n--- KEY: edma vs shaath vs libkeyfinder ---")
    fields = [("key_edma", "keystr_edma", "Essentia edma"), ("key_shaath", "keystr_shaath", "Essentia shaath")]
    if HAVE_KF:
        fields.append(("key_kf", None, "libkeyfinder"))
    for field, sfield, label in fields:
        cov, ex, ng = key_line(ok, field, n)
        print(f"{label:<22} all:       coverage {cov:5.1f}%   exact {ex:5.1f}%   neighbor {ng:5.1f}%")
        if sfield:
            for th in (0.6, 0.7, 0.8):
                cov, ex, ng = key_line(ok, field, n, sfield, th)
                print(f"{'':22} str>={th}: coverage {cov:5.1f}%   exact {ex:5.1f}%   neighbor {ng:5.1f}%")
    print("-" * 74, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/work/ground_truth.csv")
    ap.add_argument("--out", default="/work/results2_full.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
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
    print(f"[e2a-2] {len(rows)} tracks | workers={args.workers} | kf={HAVE_KF} | out={args.out}", flush=True)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    t0 = time.monotonic()
    lock = threading.Lock()
    out_f = open(args.out, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process, r) for r in rows]
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            with lock:
                writer.writerow(res)
                out_f.flush()
            done += 1
            if done % 25 == 0 or done == len(rows):
                nok = sum(1 for x in results if x.get("status") == "ok")
                print(f"[e2a-2] {done}/{len(rows)} ok={nok} elapsed={time.monotonic()-t0:.0f}s", flush=True)
    out_f.close()
    report(results)


if __name__ == "__main__":
    main()
