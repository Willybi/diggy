"""Offline tests for the C13.b title miner — brick recognisers, skeletonisation,
distribution/coverage and the mining artefacts. No network, no prod, synthetic
titles only."""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bricks  # noqa: E402
import mine  # noqa: E402


def skel(title, collapse=True):
    return bricks.skeletonize(title, collapse=collapse)


# ── DATE brick ────────────────────────────────────────────────────────────────
def test_date_all_forms():
    for title in [
        "05/09/2025",
        "2025-09-05",
        "05.09.25",
        "05092025",
        "050925",
        "2025",
        "1999",
        "20th Feb 2032",
        "5 June",
        "June 2026",
        "Feb 20 2032",
        "December 2020",
    ]:
        assert skel(title) == "<DATE>", f"{title!r} -> {skel(title)!r}"


def test_year_boundaries():
    # 1900-2039 are years; a glued number is NOT a date
    assert skel("2039") == "<DATE>"
    assert skel("Room2025") == "?"  # glued -> residue, not a date


# ── EP brick ──────────────────────────────────────────────────────────────────
def test_ep_all_forms():
    for title in ["EP12", "EP 12", "Episode 12", "#12", "Vol.3", "Vol 3",
                  "Volume 3", "Part 2", "Pt 2", "Set 5", "S01E02", "123", "4567"]:
        assert skel(title) == "<EP>", f"{title!r} -> {skel(title)!r}"


def test_date_wins_over_ep_for_years():
    # a 4-digit year is a DATE, not a bare \d{3,} episode number
    assert skel("2024") == "<DATE>"


# ── FORMAT brick ────────────────────────────────────────────────────────────
def test_format_all_forms():
    for title in ["DJ Set", "DJ Mix", "Live", "Podcast", "Guest Mix",
                  "Exclusive", "FREE DOWNLOAD", "Official", "Live Set", "Mixtape"]:
        assert skel(title) == "<FORMAT>", f"{title!r} -> {skel(title)!r}"


def test_format_multiword_not_split():
    # "guest mix" is ONE format brick, not "? <FORMAT>"
    assert skel("Guest Mix") == "<FORMAT>"
    assert skel("Free Download") == "<FORMAT>"


def test_format_not_partial_word():
    # "mix"/"set" must not fire inside a longer word
    assert skel("Mixmaster") == "?"
    assert skel("Sunset") == "?"


def test_format_phrase_before_ep_number():
    # "guest mix" claimed as a FORMAT phrase before EP's "mix #128" could steal it
    assert skel("Ben Bohmer Guest Mix #128") == "? <FORMAT> <EP>"
    # but a lone "Set N"/"Mix N" (no phrase) still falls to EP
    assert skel("Set 5") == "<EP>"
    assert skel("Mix 5") == "<EP>"


# ── DELIM brick ───────────────────────────────────────────────────────────────
def test_delim_all_forms():
    assert skel("A B2B B") == "? <DELIM> ?"
    assert skel("A B3B B") == "? <DELIM> ?"
    assert skel("A VS B") == "? <DELIM> ?"
    assert skel("A vs. B") == "? <DELIM> ?"
    assert skel("A X B") == "? <DELIM> ?"
    assert skel("A & B") == "? <DELIM> ?"
    assert skel("A feat. B") == "? <DELIM> ?"
    assert skel("A ft B") == "? <DELIM> ?"
    assert skel("A presents B") == "? <DELIM> ?"


def test_delim_x_not_inside_word():
    # standalone "x" is a delim; "x" inside a name is not
    assert skel("Max Cooper") == "?"
    assert skel("Bonobo x Floating Points") == "? <DELIM> ?"


# ── skeleton assembly + edge cases ──────────────────────────────────────────
def test_full_skeleton_any_order():
    assert (
        skel("Artist B2B Artist2 @ Boiler Room 05/09/2025")
        == "? <DELIM> ? <DATE>"
    )
    # noise before the name must NOT be gated away (robustness to format)
    assert skel("Brooklyn - 20 June - Some Artist") == "? <DATE> ?"


def test_edge_empty_and_whitespace():
    assert skel("") == ""
    assert skel("   ") == ""
    assert skel(None) == ""


def test_edge_pure_noise():
    # a title made only of bricks has NO residue "?"
    assert skel("Live 2024 #5") == "<FORMAT> <DATE> <EP>"
    assert skel("DJ Set Vol.3") == "<FORMAT> <EP>"


def test_edge_single_name():
    assert skel("Deadmau5") == "?"
    assert skel("Four Tet") == "?"  # two words, one name -> collapsed single ?


def test_collapse_vs_no_collapse():
    assert skel("Some Long Artist Name", collapse=True) == "?"
    assert skel("Some Long Artist Name", collapse=False) == "? ? ? ?"
    assert skel("DJ Set Live", collapse=True) == "<FORMAT>"
    assert skel("DJ Set Live", collapse=False) == "<FORMAT> <FORMAT>"


def test_tag_bricks_helper():
    tagged = bricks.tag_bricks("A feat B 2024")
    assert "\x00DELIM\x00" in tagged
    assert "\x00DATE\x00" in tagged


# ── miner: distribution / coverage ──────────────────────────────────────────
def test_distribution_and_coverage():
    counts = mine.Counter({"?": 60, "? <FORMAT>": 30, "? <DELIM> ?": 10})
    total = 100
    dist = mine.distribution(counts, total)
    # ordered most-frequent first
    assert [d[0] for d in dist] == ["?", "? <FORMAT>", "? <DELIM> ?"]
    assert dist[0][1] == 60 and abs(dist[0][2] - 60.0) < 1e-9
    # cumulative
    assert abs(dist[0][3] - 60.0) < 1e-9
    assert abs(dist[1][3] - 90.0) < 1e-9
    assert abs(dist[2][3] - 100.0) < 1e-9
    assert abs(mine.coverage_at(dist, 2) - 90.0) < 1e-9
    assert abs(mine.coverage_at(dist, 999) - 100.0) < 1e-9


def test_distribution_deterministic_tiebreak():
    counts = mine.Counter({"b": 5, "a": 5, "c": 5})
    dist = mine.distribution(counts, 15)
    assert [d[0] for d in dist] == ["a", "b", "c"]  # ties -> lexical


# ── miner: reading inputs ─────────────────────────────────────────────────────
def test_read_ndjson(tmp_path):
    p = tmp_path / "in.ndjson"
    p.write_text(
        json.dumps({"title": "Deadmau5 Live", "channel": "Boiler Room"}) + "\n"
        + json.dumps({"title": "  "}) + "\n"          # blank title -> skipped
        + "\n"                                          # blank line -> skipped
        + "{not json}\n"                                # bad json -> skipped
        + json.dumps({"channel": "x"}) + "\n"           # no title -> skipped
        + json.dumps({"title": "Bicep"}) + "\n",        # no channel -> ""
        encoding="utf-8",
    )
    rows = list(mine.read_titles(str(p), "ndjson", "title", "channel"))
    assert rows == [("Deadmau5 Live", "Boiler Room"), ("Bicep", "")]


def test_read_csv(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text(
        "title,channel\nDeadmau5 Live,Boiler Room\n,skipme\nBicep,\n",
        encoding="utf-8",
    )
    rows = list(mine.read_titles(str(p), "csv", "title", "channel"))
    assert rows == [("Deadmau5 Live", "Boiler Room"), ("Bicep", "")]


# ── miner: sampling ───────────────────────────────────────────────────────────
def test_sample_representative_deterministic():
    rows = [(f"t{i}", "") for i in range(100)]
    s1 = mine.sample_representative(rows, 10)
    s2 = mine.sample_representative(rows, 10)
    assert s1 == s2 and len(s1) == 10
    # n >= total returns everything
    assert len(mine.sample_representative(rows, 500)) == 100


def test_sample_stratified_covers_tail(tmp_path):
    # 90 titles of one skeleton, 1 of a rare one; stratified must keep the rare
    rows = [(f"Artist{i}", "") for i in range(90)]  # skeleton "?"
    rows.append(("Live 2024 #5", ""))               # skeleton "<FORMAT> <DATE> <EP>"
    counts = mine.Counter()
    for t, _ in rows:
        counts[bricks.skeletonize(t)] += 1
    sampled = mine.sample_stratified(rows, counts, len(rows), 10)
    skels = {bricks.skeletonize(t) for t, _ in sampled}
    assert "<FORMAT> <DATE> <EP>" in skels  # tail covered


# ── miner: end-to-end artefacts ─────────────────────────────────────────────
def test_mine_end_to_end(tmp_path):
    inp = tmp_path / "titles.ndjson"
    titles = (
        ["Deadmau5 Live"] * 5
        + ["Artist A B2B Artist B 2024"] * 3
        + ["Bicep @ Boiler Room #12"] * 2
    )
    inp.write_text(
        "\n".join(json.dumps({"title": t, "channel": "c"}) for t in titles),
        encoding="utf-8",
    )
    workdir = tmp_path / "out"
    rc = mine.main([str(inp), "--workdir", str(workdir), "--label-sample", "5"])
    assert rc == 0

    # skeletons.csv present, well-formed, cumulative reaches 100%
    with open(workdir / "skeletons.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert abs(float(rows[-1]["cumulative_pct"]) - 100.0) < 1e-6
    assert sum(int(r["count"]) for r in rows) == 10

    # label template has the blank column and the right number of rows
    with open(workdir / "label_template.csv", encoding="utf-8") as f:
        lab = list(csv.DictReader(f))
    assert len(lab) == 5
    assert all(r["expected_artist"] == "" for r in lab)
    assert all(r["skeleton"] for r in lab)

    # report + samples exist and mention coverage
    report = (workdir / "report.md").read_text(encoding="utf-8")
    assert "cumulative coverage" in report.lower()
    assert (workdir / "samples.md").read_text(encoding="utf-8").startswith("# Skeleton samples")


def test_mine_idempotent(tmp_path):
    inp = tmp_path / "titles.ndjson"
    inp.write_text(
        "\n".join(json.dumps({"title": t}) for t in ["A Live", "B B2B C", "D"]),
        encoding="utf-8",
    )
    workdir = tmp_path / "out"
    mine.main([str(inp), "--workdir", str(workdir)])
    first = (workdir / "skeletons.csv").read_text(encoding="utf-8")
    mine.main([str(inp), "--workdir", str(workdir)])
    assert (workdir / "skeletons.csv").read_text(encoding="utf-8") == first
