"""C13.b — corpus mining GATE for the set-title -> artist extractor (read-only).

Reads a LOCAL export of set titles (NDJSON or CSV), reduces every title to its
brick SKELETON (see ``bricks.py``), and produces the decision material:

  1. ``skeletons.csv``     — the full skeleton distribution: skeleton, count, pct,
                             cumulative pct (rows ordered most-frequent first).
  2. ``samples.md``        — the top-N skeletons, each with a handful of REAL sample
                             titles, so a human can eyeball what each family holds.
  3. ``label_template.csv``— a sample of titles as {title, channel, expected_artist}
                             with ``expected_artist`` LEFT BLANK, for the operator to
                             hand-label into the C13.b test set (precision/recall).
  4. ``report.md``         — a synthesis: corpus size, distinct skeletons, the
                             cumulative coverage of the top-N, and pointers.

100% read-only, LOCAL, stdlib. Connects to NOTHING (no DB, no network, no ``server``
package). It does NOT decide GO/NO-GO on the LLM: that call is made by READING these
numbers on the REAL ~381k export. See the README.

Run:  python scripts/local/trackid_titles/mine.py <input> [options]
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bricks import skeletonize  # noqa: E402

_DEFAULT_WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ── input reading ─────────────────────────────────────────────────────────────
def _detect_format(path, override):
    if override and override != "auto":
        return override
    ext = os.path.splitext(path)[1].lower()
    if ext in (".ndjson", ".jsonl"):
        return "ndjson"
    if ext == ".csv":
        return "csv"
    # default to ndjson: the spider's native export shape
    return "ndjson"


def read_titles(path, fmt, title_field, channel_field):
    """Yield ``(title, channel)`` from the NDJSON/CSV export.

    NDJSON: one JSON object per line, ``title_field`` required, ``channel_field``
    optional (``""`` when absent). Blank lines and objects missing the title field
    are skipped. CSV: a header row naming at least ``title_field``.
    """
    with open(path, "rt", encoding="utf-8", newline="") as f:
        if fmt == "csv":
            for row in csv.DictReader(f):
                title = (row.get(title_field) or "").strip()
                if not title:
                    continue
                yield title, (row.get(channel_field) or "").strip()
        else:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                title = (obj.get(title_field) or "").strip()
                if not title:
                    continue
                yield title, (obj.get(channel_field) or "").strip()


# ── mining core ─────────────────────────────────────────────────────────────
def mine(rows, collapse=True, samples_per_skeleton=8):
    """Fold the ``(title, channel)`` stream into the mining result.

    Returns a dict with ``total`` (titles seen), ``counts`` (Counter skeleton->n),
    and ``samples`` (skeleton -> up to ``samples_per_skeleton`` (title, channel)).
    Single streaming pass — safe on the full ~381k corpus.
    """
    counts = Counter()
    samples = defaultdict(list)
    total = 0
    for title, channel in rows:
        total += 1
        skel = skeletonize(title, collapse=collapse)
        counts[skel] += 1
        bucket = samples[skel]
        if len(bucket) < samples_per_skeleton:
            bucket.append((title, channel))
    return {"total": total, "counts": counts, "samples": samples}


def distribution(counts, total):
    """Rows ``(skeleton, count, pct, cumulative_pct)`` most-frequent first.

    Ties broken by skeleton text so the ordering (and thus every artefact) is
    deterministic across runs.
    """
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out = []
    cum = 0
    for skel, n in ordered:
        cum += n
        pct = (n / total * 100) if total else 0.0
        cum_pct = (cum / total * 100) if total else 0.0
        out.append((skel, n, pct, cum_pct))
    return out


def coverage_at(dist, n):
    """Cumulative % of the corpus covered by the top-``n`` skeletons."""
    if not dist:
        return 0.0
    idx = min(n, len(dist)) - 1
    return dist[idx][3]


# ── label-template sampling (deterministic) ───────────────────────────────────
def _representative_indices(total, n):
    """Evenly-spaced indices across ``[0, total)`` — a frequency-representative
    sample (common skeletons appear in proportion to their weight)."""
    if total <= 0 or n <= 0:
        return set()
    if n >= total:
        return set(range(total))
    step = total / n
    return {int(i * step) for i in range(n)}


def sample_representative(rows_list, n):
    """Pick ``n`` (title, channel) evenly spread across the corpus order."""
    idx = _representative_indices(len(rows_list), n)
    return [rows_list[i] for i in sorted(idx)]


def sample_stratified(rows_list, counts, total, n, collapse=True):
    """Pick ``n`` titles allocated across skeletons proportional to frequency, at
    least one per skeleton until the budget runs out (rarest gets a look-in too).

    Deterministic: skeletons are visited most-frequent first, and the first-seen
    titles of each skeleton are taken. Guarantees tail coverage that a purely
    representative sample would miss.
    """
    if n <= 0 or total <= 0:
        return []
    # per-skeleton quota, rounded, min 1, capped at the skeleton's own size
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    quota = {}
    for skel, c in ordered:
        want = max(1, round(c / total * n))
        quota[skel] = min(want, c)
    # collect first-seen titles per skeleton up to its quota
    picked = defaultdict(list)
    remaining = dict(quota)
    for title, channel in rows_list:
        skel = skeletonize(title, collapse=collapse)
        if remaining.get(skel, 0) > 0:
            picked[skel].append((title, channel))
            remaining[skel] -= 1
    # round-robin across skeletons (freq order): every skeleton yields its first
    # title before any yields a second, so the trim to n never starves the tail
    out = []
    depth = max((len(v) for v in picked.values()), default=0)
    for r in range(depth):
        for skel, _c in ordered:
            bucket = picked.get(skel)
            if bucket and r < len(bucket):
                out.append(bucket[r])
                if len(out) >= n:
                    return out
    return out


# ── artefact writers ──────────────────────────────────────────────────────────
def write_skeletons_csv(path, dist):
    with open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["skeleton", "count", "pct", "cumulative_pct"])
        for skel, n, pct, cum_pct in dist:
            w.writerow([skel, n, f"{pct:.4f}", f"{cum_pct:.4f}"])


def write_samples_md(path, dist, samples, top):
    lines = ["# Skeleton samples (top {})".format(top), ""]
    for rank, (skel, n, pct, cum_pct) in enumerate(dist[:top], start=1):
        lines.append(f"## {rank}. `{skel or '(empty)'}` — {n} ({pct:.2f}%, cum {cum_pct:.2f}%)")
        for title, channel in samples.get(skel, []):
            chan = f"  ·  _{channel}_" if channel else ""
            lines.append(f"- {title}{chan}")
        lines.append("")
    with open(path, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_label_template(path, sampled):
    with open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["title", "channel", "skeleton", "expected_artist"])
        for title, channel in sampled:
            w.writerow([title, channel, skeletonize(title), ""])


def write_report(path, result, dist, top_marks, label_count, label_strategy, collapse):
    total = result["total"]
    distinct = len(dist)
    lines = [
        "# C13.b — Corpus mining report (title skeletons)",
        "",
        f"- Titles mined       : **{total}**",
        f"- Distinct skeletons : **{distinct}**",
        f"- Collapse runs      : {collapse}",
        f"- Label sample       : {label_count} titles ({label_strategy})",
        "",
        "## Cumulative coverage of the top-N skeletons",
        "",
        "| top-N | cumulative coverage |",
        "|------:|--------------------:|",
    ]
    for mark in top_marks:
        if mark <= distinct:
            lines.append(f"| {mark} | {coverage_at(dist, mark):.2f}% |")
    lines += [
        f"| {distinct} (all) | 100.00% |",
        "",
        "## Top 40 skeletons",
        "",
        "| rank | skeleton | count | pct | cum pct |",
        "|-----:|----------|------:|----:|--------:|",
    ]
    for rank, (skel, n, pct, cum_pct) in enumerate(dist[:40], start=1):
        lines.append(f"| {rank} | `{skel or '(empty)'}` | {n} | {pct:.2f}% | {cum_pct:.2f}% |")
    lines += [
        "",
        "## Reading this for the GO/NO-GO (LLM)",
        "",
        "- A deterministic subtractive extractor (C13.c) handles the head of this",
        "  distribution cheaply. Look at how few skeletons it takes to cover ~85% of",
        "  the corpus, and whether the residue (`?`) positions in those skeletons",
        "  actually hold artist names (check `samples.md`).",
        "- If a small top-N covers ~85% with clean artist residues -> **NO LLM**.",
        "- If coverage plateaus near ~60% with a long, artist-rich tail -> a LLM on",
        "  the residue (C13.d) becomes worthwhile.",
        "- This tool does NOT decide: fill `label_template.csv` by hand, then measure",
        "  precision/recall of the extractor against it. The decision is made on",
        "  THOSE numbers, on the REAL export — not a priori.",
        "",
    ]
    with open(path, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("input", help="path to the NDJSON/CSV export of set titles")
    p.add_argument("--format", choices=["auto", "ndjson", "csv"], default="auto")
    p.add_argument("--title-field", default="title")
    p.add_argument("--channel-field", default="channel")
    p.add_argument("--workdir", default=_DEFAULT_WORKDIR, help="output directory")
    p.add_argument("--top", type=int, default=40, help="top-N skeletons in samples.md")
    p.add_argument(
        "--samples-per-skeleton", type=int, default=8,
        help="real sample titles kept per skeleton for samples.md",
    )
    p.add_argument("--label-sample", type=int, default=300, help="titles in the label template")
    p.add_argument(
        "--label-strategy", choices=["representative", "stratified"],
        default="representative",
        help="representative = evenly spread (weighted by frequency); "
        "stratified = proportional per-skeleton with tail coverage",
    )
    p.add_argument(
        "--no-collapse", action="store_true",
        help="keep exact token multiplicity (do not collapse repeated placeholders)",
    )
    args = p.parse_args(argv)

    collapse = not args.no_collapse
    fmt = _detect_format(args.input, args.format)
    os.makedirs(args.workdir, exist_ok=True)

    # Materialise once so we can both mine and sample deterministically. ~381k
    # short tuples is a few tens of MB — comfortably in memory on the local PC.
    rows_list = list(
        read_titles(args.input, fmt, args.title_field, args.channel_field)
    )
    result = mine(rows_list, collapse=collapse, samples_per_skeleton=args.samples_per_skeleton)
    total = result["total"]
    dist = distribution(result["counts"], total)

    if args.label_strategy == "stratified":
        sampled = sample_stratified(
            rows_list, result["counts"], total, args.label_sample, collapse=collapse
        )
    else:
        sampled = sample_representative(rows_list, args.label_sample)

    skeletons_csv = os.path.join(args.workdir, "skeletons.csv")
    samples_md = os.path.join(args.workdir, "samples.md")
    label_csv = os.path.join(args.workdir, "label_template.csv")
    report_md = os.path.join(args.workdir, "report.md")

    write_skeletons_csv(skeletons_csv, dist)
    write_samples_md(samples_md, dist, result["samples"], args.top)
    write_label_template(label_csv, sampled)
    top_marks = [10, 20, 40, 100, 250, 500, 1000]
    write_report(
        report_md, result, dist, top_marks, len(sampled), args.label_strategy, collapse
    )

    print(
        f"[mine] titles={total} distinct_skeletons={len(dist)} "
        f"top40_coverage={coverage_at(dist, 40):.2f}% "
        f"label_sample={len(sampled)}",
        flush=True,
    )
    print(f"[mine] wrote: {skeletons_csv}", flush=True)
    print(f"[mine] wrote: {samples_md}", flush=True)
    print(f"[mine] wrote: {label_csv}", flush=True)
    print(f"[mine] wrote: {report_md}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
