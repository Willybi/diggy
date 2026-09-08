"""Tests for the C13.c extractor benchmark harness
(scripts/local/trackid_titles/benchmark.py).

The harness lives under scripts/local (a LOCAL validation tool) but imports the
server extractor, so it is exercised here in tests/worker (the collected suite).
Synthetic labelled rows only — no network, no prod. We verify the precision/recall
arithmetic, the per-skeleton breakdown, the unlabelled-row skip, and the
false-negative capture.
"""

import csv
import os
import sys

# Server package (for the extractor the harness imports).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)
# The benchmark tool's own directory (its module + sibling bricks.py).
_TOOL_PATH = os.path.join(os.path.dirname(__file__), "../../scripts/local/trackid_titles")
if _TOOL_PATH not in sys.path:
    sys.path.insert(0, _TOOL_PATH)

import benchmark  # noqa: E402


# ── matching / fold key ──────────────────────────────────────────────────────


class TestFoldKeyMatch:
    def test_punctuation_insensitive(self):
        assert benchmark.fold_key("St. Germain") == benchmark.fold_key("St Germain")

    def test_accent_insensitive(self):
        assert benchmark.fold_key("Chlär") == benchmark.fold_key("Chlar")


# ── score_row ────────────────────────────────────────────────────────────────


class TestScoreRow:
    def test_full_hit_lineup(self):
        # both expected artists proposed, no extra candidate
        n_exp, n_hit, n_cand, n_cand_hit, missed = benchmark.score_row(
            "Artist One b2b Artist Two", "", ["Artist One", "Artist Two"]
        )
        assert n_exp == 2 and n_hit == 2
        assert n_cand == 2 and n_cand_hit == 2
        assert missed == []

    def test_partial_with_false_positive(self):
        # C2a: the dash now emits BOTH sides, so "Songs of Spring" is also a candidate;
        # the expected artist is still hit, and the extra track + channel candidates
        # drag precision below 100%
        n_exp, n_hit, n_cand, n_cand_hit, missed = benchmark.score_row(
            "Ley Moore - Songs of Spring", "Some Label", ["Ley Moore"]
        )
        assert n_exp == 1 and n_hit == 1
        # Ley Moore + Songs of Spring + Some Label
        assert n_cand == 3 and n_cand_hit == 1
        assert missed == []

    def test_false_negative(self):
        # a freeform "at venue" glue the deterministic pass can't recover
        n_exp, n_hit, n_cand, n_cand_hit, missed = benchmark.score_row(
            "Wata Igarashi at Samhain XX", "chan", ["Wata Igarashi"]
        )
        assert n_hit == 0
        assert missed == ["Wata Igarashi"]


# ── benchmark aggregation ────────────────────────────────────────────────────


def _rows():
    # 3 labelled rows + 1 unlabelled (empty expected)
    return [
        ("Artist One b2b Artist Two", "", ["Artist One", "Artist Two"]),
        ("Ley Moore - Songs of Spring", "Some Label", ["Ley Moore"]),
        ("Wata Igarashi at Samhain XX", "chan", ["Wata Igarashi"]),
        ("Unlabelled Title", "chan", []),
    ]


class TestBenchmark:
    def test_counts_and_rates(self):
        result = benchmark.benchmark(_rows())
        assert result["labelled"] == 3
        assert result["unlabelled"] == 1
        totals = result["totals"]
        # expected = 2 + 1 + 1 = 4 ; matched_expected = 2 + 1 + 0 = 3
        assert totals["expected"] == 4
        assert totals["matched_expected"] == 3
        assert abs(benchmark.recall(totals) - 0.75) < 1e-9
        # precision denominator = all candidates across labelled rows
        assert 0.0 < benchmark.precision(totals) <= 1.0

    def test_false_negatives_captured(self):
        result = benchmark.benchmark(_rows())
        missed_titles = [t for t, _c, _m in result["false_negatives"]]
        assert "Wata Igarashi at Samhain XX" in missed_titles

    def test_per_skeleton_breakdown(self):
        result = benchmark.benchmark(_rows())
        rows = benchmark.skeleton_rows(result["per_skel"])
        # every labelled skeleton is represented, ordered by row count desc
        assert rows
        counts = [r[1] for r in rows]
        assert counts == sorted(counts, reverse=True)

    def test_empty_input(self):
        result = benchmark.benchmark([])
        assert result["labelled"] == 0
        assert benchmark.precision(result["totals"]) == 0.0
        assert benchmark.recall(result["totals"]) == 0.0


# ── reading + end-to-end CLI ─────────────────────────────────────────────────


class TestReadAndCli:
    def test_read_csv(self, tmp_path):
        p = tmp_path / "labels.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["title", "channel", "expected_artist"])
            w.writerow(["A b2b B", "chan", "A;B"])
            w.writerow(["", "skip", "X"])  # blank title → skipped
            w.writerow(["Solo", "c", ""])  # unlabelled
        rows = list(
            benchmark.read_labelled(str(p), "csv", "title", "channel", "expected_artist")
        )
        assert rows == [
            ("A b2b B", "chan", ["A", "B"]),
            ("Solo", "c", []),
        ]

    def test_end_to_end_writes_report(self, tmp_path):
        p = tmp_path / "labels.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["title", "channel", "expected_artist"])
            w.writerow(["Artist One b2b Artist Two", "", "Artist One;Artist Two"])
            w.writerow(["Ley Moore - Songs of Spring", "lbl", "Ley Moore"])
        workdir = tmp_path / "out"
        rc = benchmark.main([str(p), "--workdir", str(workdir)])
        assert rc == 0
        report = (workdir / "benchmark_report.md").read_text(encoding="utf-8")
        assert "Precision" in report and "Recall" in report
        assert "Per-skeleton breakdown" in report

    def test_no_report_flag(self, tmp_path):
        p = tmp_path / "labels.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["title", "channel", "expected_artist"])
            w.writerow(["A & B", "", "A;B"])
        workdir = tmp_path / "out"
        rc = benchmark.main([str(p), "--workdir", str(workdir), "--no-report"])
        assert rc == 0
        assert not workdir.exists()
