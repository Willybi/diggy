"""C13.c — benchmark GATE for the deterministic set-title → artist extractor.

Reads a HAND-LABELLED sample of set titles ({title, channel, expected_artist}),
runs each through the SUBTRACTIVE extractor (``server/workers/set_artist_extract``),
and measures how well the CANDIDATE extraction covers the expected artists:

  * global **precision** (share of proposed candidates that hit an expected artist)
    and **recall** (share of expected artists proposed by SOME candidate);
  * a per-SKELETON breakdown (reusing ``bricks.skeletonize`` to group), so you can
    see which title families the deterministic extractor handles cleanly and which
    leak — the material that decides GO/NO-GO on a LLM (C13.d);
  * examples of FALSE NEGATIVES (expected artists never proposed) — the concrete
    residue a LLM would have to recover.

A match is EQUALITY OF FOLD KEY (``workers.artist_names.punct_fold_key`` — accent /
punctuation insensitive), so "St. Germain" == "St Germain". Matching is done on the
candidate names ONLY — this harness does NO Deezer/existence check (that is a later
lot); it measures the deterministic extraction in isolation.

100% read-only, LOCAL, deterministic, no network. Unlike ``mine.py`` this tool DOES
import the ``server`` package (it validates the real extractor) — that is fine, it
is a local validation harness, not the stdlib-pure miner.

Run:  python scripts/local/trackid_titles/benchmark.py <labelled.csv> [options]
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../server"))

from bricks import skeletonize  # noqa: E402
from workers.artist_names import fold_base, punct_fold_key  # noqa: E402
from workers.set_artist_extract import extract_candidate_names  # noqa: E402

_DEFAULT_WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Separator between several expected artists in one label cell.
_EXPECTED_SEP = ";"


# ── input reading ─────────────────────────────────────────────────────────────
def _detect_format(path, override):
    if override and override != "auto":
        return override
    ext = os.path.splitext(path)[1].lower()
    if ext in (".ndjson", ".jsonl"):
        return "ndjson"
    return "csv"


def read_labelled(path, fmt, title_field, channel_field, expected_field):
    """Yield ``(title, channel, [expected_artist, …])`` from the labelled export.

    CSV: header row naming at least ``title_field`` and ``expected_field``. NDJSON:
    one JSON object per line. The expected cell is split on ``;`` into artists (each
    trimmed, blanks dropped) — an empty cell means the row is UNLABELLED.
    """
    def _row(obj):
        title = (obj.get(title_field) or "").strip()
        channel = (obj.get(channel_field) or "").strip()
        raw = (obj.get(expected_field) or "").strip()
        expected = [a.strip() for a in raw.split(_EXPECTED_SEP) if a.strip()]
        return title, channel, expected

    with open(path, "rt", encoding="utf-8", newline="") as f:
        if fmt == "csv":
            for row in csv.DictReader(f):
                title, channel, expected = _row(row)
                if title:
                    yield title, channel, expected
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
                title, channel, expected = _row(obj)
                if title:
                    yield title, channel, expected


# ── matching ──────────────────────────────────────────────────────────────────
def fold_key(name):
    """Match key: punctuation/accent-insensitive fold, falling back to the base
    fold then the casefold for a fully non-Latin name (parity with the extractor's
    own dedup key)."""
    return punct_fold_key(name) or fold_base(name) or (name or "").strip().casefold()


def score_row(title, channel, expected):
    """Score one labelled row.

    Returns ``(n_expected, n_matched_expected, n_candidates, n_matched_candidates,
    missed)`` where ``missed`` is the list of expected artists no candidate hit.
    """
    expected_keys = {fold_key(a): a for a in expected}
    candidates = extract_candidate_names(title, channel)
    cand_keys = [fold_key(c) for c in candidates]
    cand_key_set = set(cand_keys)

    matched_expected = [k for k in expected_keys if k in cand_key_set]
    matched_candidates = [k for k in cand_keys if k in expected_keys]
    missed = [name for k, name in expected_keys.items() if k not in cand_key_set]
    return (
        len(expected_keys),
        len(matched_expected),
        len(cand_keys),
        len(matched_candidates),
        missed,
    )


# ── benchmark core ─────────────────────────────────────────────────────────────
def benchmark(rows):
    """Fold the labelled ``(title, channel, expected)`` stream into the result dict.

    Skips UNLABELLED rows (empty expected) from the metrics but counts them. Returns
    global totals, a per-skeleton aggregation, and false-negative examples.
    """
    totals = {"expected": 0, "matched_expected": 0, "candidates": 0, "matched_candidates": 0}
    per_skel = defaultdict(
        lambda: {"rows": 0, "expected": 0, "matched_expected": 0, "candidates": 0, "matched_candidates": 0}
    )
    false_negatives = []
    labelled = 0
    unlabelled = 0

    for title, channel, expected in rows:
        if not expected:
            unlabelled += 1
            continue
        labelled += 1
        n_exp, n_hit, n_cand, n_cand_hit, missed = score_row(title, channel, expected)

        totals["expected"] += n_exp
        totals["matched_expected"] += n_hit
        totals["candidates"] += n_cand
        totals["matched_candidates"] += n_cand_hit

        skel = skeletonize(title)
        agg = per_skel[skel]
        agg["rows"] += 1
        agg["expected"] += n_exp
        agg["matched_expected"] += n_hit
        agg["candidates"] += n_cand
        agg["matched_candidates"] += n_cand_hit

        if missed:
            false_negatives.append((title, channel, missed))

    return {
        "labelled": labelled,
        "unlabelled": unlabelled,
        "totals": totals,
        "per_skel": per_skel,
        "false_negatives": false_negatives,
    }


def _ratio(num, den):
    return (num / den) if den else 0.0


def precision(totals):
    return _ratio(totals["matched_candidates"], totals["candidates"])


def recall(totals):
    return _ratio(totals["matched_expected"], totals["expected"])


def skeleton_rows(per_skel):
    """Per-skeleton rows ``(skeleton, rows, precision, recall, expected)`` ordered by
    row count desc, ties broken by skeleton text (deterministic)."""
    out = []
    for skel, agg in per_skel.items():
        out.append(
            (
                skel,
                agg["rows"],
                _ratio(agg["matched_candidates"], agg["candidates"]),
                _ratio(agg["matched_expected"], agg["expected"]),
                agg["expected"],
            )
        )
    out.sort(key=lambda r: (-r[1], r[0]))
    return out


# ── report writer ──────────────────────────────────────────────────────────────
def write_report(path, result, top, fn_examples):
    totals = result["totals"]
    lines = [
        "# C13.c — Extractor benchmark (deterministic, no LLM)",
        "",
        f"- Labelled rows     : **{result['labelled']}**",
        f"- Unlabelled (skip) : {result['unlabelled']}",
        f"- Expected artists  : {totals['expected']}",
        f"- Candidates emitted: {totals['candidates']}",
        "",
        f"- **Precision** : {precision(totals) * 100:.2f}% "
        f"({totals['matched_candidates']}/{totals['candidates']})",
        f"- **Recall**    : {recall(totals) * 100:.2f}% "
        f"({totals['matched_expected']}/{totals['expected']})",
        "",
        f"## Per-skeleton breakdown (top {top} by row count)",
        "",
        "| skeleton | rows | precision | recall | expected |",
        "|----------|-----:|----------:|-------:|---------:|",
    ]
    for skel, rows, prec, rec, exp in skeleton_rows(result["per_skel"])[:top]:
        lines.append(
            f"| `{skel or '(empty)'}` | {rows} | {prec * 100:.1f}% | {rec * 100:.1f}% | {exp} |"
        )
    lines += [
        "",
        f"## False negatives (expected artists never proposed) — up to {fn_examples}",
        "",
    ]
    for title, channel, missed in result["false_negatives"][:fn_examples]:
        chan = f"  ·  _{channel}_" if channel else ""
        lines.append(f"- **missed** {'; '.join(missed)} — {title}{chan}")
    lines += [
        "",
        "## Reading this for the GO/NO-GO (LLM, C13.d)",
        "",
        "- High recall with a clean per-skeleton spread → the deterministic",
        "  extractor suffices, NO LLM.",
        "- Recall that plateaus with an artist-rich false-negative list → a LLM on",
        "  the residue becomes worthwhile. Its output would still re-enter the same",
        "  Deezer verification (invariant #4/#5).",
        "- Precision here is candidate-level; a later lot's Deezer/known-artist",
        "  verification is what protects the FINAL link precision, so favour recall.",
        "",
    ]
    with open(path, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── CLI ─────────────────────────────────────────────────────────────────────────
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("input", help="path to the hand-labelled CSV/NDJSON test set")
    p.add_argument("--format", choices=["auto", "ndjson", "csv"], default="auto")
    p.add_argument("--title-field", default="title")
    p.add_argument("--channel-field", default="channel")
    p.add_argument("--expected-field", default="expected_artist")
    p.add_argument("--workdir", default=_DEFAULT_WORKDIR, help="output directory")
    p.add_argument("--top", type=int, default=40, help="top-N skeletons in the breakdown")
    p.add_argument(
        "--fn-examples", type=int, default=50, help="false-negative examples to list"
    )
    p.add_argument(
        "--no-report", action="store_true", help="print the summary only, write no file"
    )
    args = p.parse_args(argv)

    fmt = _detect_format(args.input, args.format)
    rows = read_labelled(
        args.input, fmt, args.title_field, args.channel_field, args.expected_field
    )
    result = benchmark(rows)
    totals = result["totals"]

    print(
        f"[benchmark] labelled={result['labelled']} unlabelled={result['unlabelled']} "
        f"precision={precision(totals) * 100:.2f}% recall={recall(totals) * 100:.2f}% "
        f"expected={totals['expected']} candidates={totals['candidates']}",
        flush=True,
    )

    if not args.no_report:
        os.makedirs(args.workdir, exist_ok=True)
        report_md = os.path.join(args.workdir, "benchmark_report.md")
        write_report(report_md, result, args.top, args.fn_examples)
        print(f"[benchmark] wrote: {report_md}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
