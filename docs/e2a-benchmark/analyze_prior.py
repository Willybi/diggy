"""Deployable BPM accuracy: fold to a FIXED range prior (no ground truth needed to pick the octave),
unlike the 'strict fold' which is an oracle. Runs on the host (pure csv, no audio libs)."""
import csv
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "results2_full.csv"
rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r.get("status") == "ok"]


def fold_to_range(bpm, lo, hi):
    cands = [bpm / 4, bpm / 2, bpm, bpm * 2, bpm * 4]
    inr = [c for c in cands if lo <= c < hi]
    if inr:
        return min(inr, key=lambda c: abs(c - (lo + hi) / 2))
    return min(cands, key=lambda c: abs(c - (lo + hi) / 2))


def oracle_fold(bpm, truth):
    return min([bpm / 2, bpm, bpm * 2], key=lambda c: abs(c - truth))


def acc(field, transform, tol=2.0):
    n = hit = 0
    for r in rows:
        a = r.get(field)
        if not a:
            continue
        a = float(a)
        t = float(r["bpm"])
        n += 1
        if abs(transform(a, t) - t) <= tol:
            hit += 1
    return 100.0 * hit / n if n else 0.0, n


print(f"n_ok={len(rows)}  (tol=±2 BPM)")
print(f"{'method':<14}{'raw':>8}{'[90,180)':>10}{'[76,152)':>10}{'[70,140)':>10}{'oracle':>9}")
for field in ("rt_bpm", "tcnn_bpm"):
    raw, _ = acc(field, lambda a, t: a)
    r90, _ = acc(field, lambda a, t: fold_to_range(a, 90, 180))
    r76, _ = acc(field, lambda a, t: fold_to_range(a, 76, 152))
    r70, _ = acc(field, lambda a, t: fold_to_range(a, 70, 140))
    orc, _ = acc(field, oracle_fold)
    print(f"{field:<14}{raw:>7.1f}%{r90:>9.1f}%{r76:>9.1f}%{r70:>9.1f}%{orc:>8.1f}%")

# distribution of truth BPM (to sanity-check which prior window fits our catalog)
buckets = {}
for r in rows:
    b = int(float(r["bpm"]) // 10 * 10)
    buckets[b] = buckets.get(b, 0) + 1
print("\ntruth BPM histogram (10-wide):")
for b in sorted(buckets):
    print(f"  {b:3d}-{b+9}: {'#' * (buckets[b] * 40 // len(rows))} {buckets[b]}")
