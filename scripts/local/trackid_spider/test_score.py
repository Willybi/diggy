"""Offline tests for score.py — phase assignment + NDJSON export (no network)."""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import score  # noqa: E402


# --- pure phase logic ------------------------------------------------------
def test_assign_phase_pure():
    # exclu -> never emitted
    assert score.assign_phase(0, True, True) is None
    # has_lib wins over everything (except exclu)
    assert score.assign_phase(3, True, False) == 0
    assert score.assign_phase(None, True, False) == 0
    # P1 -> phase 1 (even with no artist signal)
    assert score.assign_phase(1, False, False) == 1
    # P2 + has_g10 -> phase 1
    assert score.assign_phase(2, False, True) == 1
    # has_g10 on a "reste" channel -> phase 2
    assert score.assign_phase(None, False, True) == 2
    # P2 without g10 -> phase 3 ; P3 without g10 -> phase 3
    assert score.assign_phase(2, False, False) == 3
    assert score.assign_phase(3, False, False) == 3
    # reste, no artist -> not emitted
    assert score.assign_phase(None, False, False) is None


def test_net_new_bonus_monotonic_and_bounded():
    cap, span = 30, 9.0
    # strictly increasing with net_new_count, up to the cap
    assert score.net_new_bonus(0, cap, span) == 0.0
    assert score.net_new_bonus(1, cap, span) < score.net_new_bonus(2, cap, span)
    assert score.net_new_bonus(5, cap, span) < score.net_new_bonus(20, cap, span)
    # bounded by span and saturating at the cap (no crossing the 10-pt phase gap)
    assert score.net_new_bonus(cap, cap, span) == span
    assert score.net_new_bonus(cap, cap, span) <= span
    assert score.net_new_bonus(1000, cap, span) == span
    assert span < 10  # invariant: a full bonus cannot cross into the next phase band
    # a phase1 set at max bonus stays below a phase0 set at min bonus
    scores = score.load_phase_scores()
    phase1_max = scores[1] + score.net_new_bonus(1000, cap, span)
    phase0_min = scores[0] + score.net_new_bonus(0, cap, span)
    assert phase1_max < phase0_min


def test_channel_prio_label():
    assert score.channel_prio_label(1) == 1
    assert score.channel_prio_label(3) == 3
    assert score.channel_prio_label(None) == "reste"
    assert score.channel_prio_label(0) == "reste"


def test_load_target_artists(tmp_path):
    p = tmp_path / "target.txt"
    p.write_text("big artist\t10\nsmall\t3\nborder\t9\nbad line\n", encoding="utf-8")
    q = score.load_target_artists(str(p), 10)
    assert q == {"big artist"}
    q9 = score.load_target_artists(str(p), 9)
    assert q9 == {"big artist", "border"}


def test_load_channel_prio_bom(tmp_path):
    p = tmp_path / "chan.csv"
    # utf-8-sig BOM + the real column contract
    p.write_text(
        "﻿prio,channel,sets,net_new,known,lib,net_new_rate\n"
        "1,The Lot Radio,10,20,15,2,0.5\n"
        "0,Banned Chan,5,5,1,0,0.1\n",
        encoding="utf-8",
    )
    m = score.load_channel_prio(str(p))
    assert m == {"The Lot Radio": 1, "Banned Chan": 0}


# --- end-to-end over a hand-built staging db -------------------------------
def _seed_db(path):
    """Build a tiny staging.db covering each phase branch.

    Sets (channel / net-new artist):
      10  reste channel, net-new artist in lib          -> phase 0
      20  P1 channel, only ID tracks (no artist)        -> phase 1
      30  P2 channel, net-new artist with g10           -> phase 1
      40  reste channel, net-new artist with g10        -> phase 2
      50  P3 channel, no artist signal                  -> phase 3
      60  reste channel, no artist signal               -> NOT emitted
      70  exclu channel (prio 0), net-new lib artist    -> NOT emitted
    """
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE trackid_index_staging "
        "(trackid_id INTEGER PRIMARY KEY, channel TEXT)"
    )
    conn.execute(
        "CREATE TABLE set_detail (trackid_id INTEGER PRIMARY KEY, http_status INTEGER)"
    )
    conn.execute(
        "CREATE TABLE tracklist "
        "(trackid_id INTEGER, position INTEGER, raw_artist TEXT, "
        " is_id INTEGER, matched INTEGER, norm_key TEXT)"
    )
    channels = {
        10: "Reste FM", 20: "P1 Radio", 30: "P2 Radio", 40: "Reste FM",
        50: "P3 Radio", 60: "Reste FM", 70: "Banned",
    }
    for tid, ch in channels.items():
        conn.execute("INSERT INTO trackid_index_staging VALUES (?,?)", (tid, ch))
        conn.execute("INSERT INTO set_detail VALUES (?,200)", (tid,))
    # tracklist rows: (tid, pos, raw_artist, is_id, matched)
    # (tid, pos, raw_artist, is_id, matched, norm_key)
    rows = [
        (10, 1, "Lib Guy", 0, 0, "song a - lib guy"),   # net-new, in lib
        (10, 2, "Someone", 0, 1, "song b - someone"),   # matched -> not net-new
        (20, 1, "ID", 1, 0, None),                       # ID track, no artist signal
        (30, 1, "Genre Star", 0, 0, "song c - genre star"),  # net-new, g10 artist
        (40, 1, "Genre Star", 0, 0, "song d - genre star"),  # net-new, g10 artist
        (50, 1, "Nobody", 0, 1, "song e - nobody"),      # matched, no net-new
        (60, 1, "Random", 0, 0, "song f - random"),      # net-new, unknown artist
        (70, 1, "Lib Guy", 0, 0, "song a - lib guy"),    # net-new lib, excluded chan
    ]
    conn.executemany(
        "INSERT INTO tracklist VALUES (?,?,?,?,?,?)", rows
    )
    conn.commit()
    conn.close()


def test_score_end_to_end(tmp_path):
    db = str(tmp_path / "staging.db")
    _seed_db(db)

    lib = tmp_path / "lib.txt"
    lib.write_text("lib guy\n", encoding="utf-8")   # normalized already
    target = tmp_path / "target.txt"
    target.write_text("genre star\t25\nlib guy\t2\n", encoding="utf-8")
    channels = tmp_path / "chan.csv"
    channels.write_text(
        "prio,channel,sets,net_new,known,lib,net_new_rate\n"
        "1,P1 Radio,1,1,1,1,1\n"
        "2,P2 Radio,1,1,1,1,1\n"
        "3,P3 Radio,1,1,1,1,1\n"
        "0,Banned,1,1,1,1,1\n",
        encoding="utf-8",
    )
    out = tmp_path / "scores.ndjson"

    cap, span = score.load_bonus_params()
    stats = score.score(
        db, str(lib), str(target), str(channels), str(out),
        threshold=10, phase_scores=score.load_phase_scores(),
        bonus_cap=cap, bonus_span=span, verbose=False,
    )

    assert stats["emitted"] == 5
    assert stats["skipped"] == 2
    assert stats["per_phase"] == {0: 1, 1: 2, 2: 1, 3: 1}

    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    by_id = {r["trackid_id"]: r for r in records}
    # NDJSON is ordered by trackid_id
    assert [r["trackid_id"] for r in records] == sorted(by_id)
    # 60 (reste no artist) and 70 (exclu) are absent
    assert 60 not in by_id and 70 not in by_id

    # each seeded set has exactly 1 distinct net-new key -> bonus = 1/30*9 = 0.3
    bonus1 = score.net_new_bonus(1, cap, span)
    assert by_id[10]["score_components"] == {
        "phase": 0, "has_lib": True, "has_g10": False, "channel_prio": "reste",
        "net_new_count": 1,
    }
    assert by_id[10]["score"] == 90.0 + bonus1
    assert by_id[20]["score_components"] == {
        "phase": 1, "has_lib": False, "has_g10": False, "channel_prio": 1,
        "net_new_count": 0,   # only an ID track, no distinct net-new key
    }
    assert by_id[20]["score"] == 80.0  # no net-new -> no bonus
    assert by_id[30]["score_components"] == {
        "phase": 1, "has_lib": False, "has_g10": True, "channel_prio": 2,
        "net_new_count": 1,
    }
    assert by_id[40]["score_components"] == {
        "phase": 2, "has_lib": False, "has_g10": True, "channel_prio": "reste",
        "net_new_count": 1,
    }
    assert by_id[50]["score_components"] == {
        "phase": 3, "has_lib": False, "has_g10": False, "channel_prio": 3,
        "net_new_count": 0,
    }
    assert by_id[50]["score"] == 60.0


def test_score_tie_break_within_phase(tmp_path):
    """Same phase: richer net-new -> strictly higher score, still inside the band."""
    db = str(tmp_path / "staging.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE trackid_index_staging "
        "(trackid_id INTEGER PRIMARY KEY, channel TEXT)"
    )
    conn.execute(
        "CREATE TABLE set_detail (trackid_id INTEGER PRIMARY KEY, http_status INTEGER)"
    )
    conn.execute(
        "CREATE TABLE tracklist "
        "(trackid_id INTEGER, position INTEGER, raw_artist TEXT, "
        " is_id INTEGER, matched INTEGER, norm_key TEXT)"
    )
    # 100 = phase0, 1 distinct net-new key ; 200 = phase0, 3 distinct net-new keys.
    # 300 = phase1 (P1) maxed out with many net-new keys -> must stay below phase0.
    for tid in (100, 200, 300):
        chan = "P1 Radio" if tid == 300 else "Reste FM"
        conn.execute("INSERT INTO trackid_index_staging VALUES (?,?)", (tid, chan))
        conn.execute("INSERT INTO set_detail VALUES (?,200)", (tid,))
    rows = [(100, 1, "Lib Guy", 0, 0, "k1 - lib guy")]
    rows += [(200, i, "Lib Guy", 0, 0, f"k{i} - lib guy") for i in range(1, 4)]
    rows += [(300, i, "Nobody", 0, 0, f"n{i} - nobody") for i in range(1, 60)]
    conn.executemany("INSERT INTO tracklist VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    lib = tmp_path / "lib.txt"
    lib.write_text("lib guy\n", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("", encoding="utf-8")
    channels = tmp_path / "chan.csv"
    channels.write_text(
        "prio,channel,sets,net_new,known,lib,net_new_rate\n1,P1 Radio,1,1,1,1,1\n",
        encoding="utf-8",
    )
    out = tmp_path / "scores.ndjson"
    cap, span = score.load_bonus_params()
    score.score(
        db, str(lib), str(target), str(channels), str(out),
        threshold=10, phase_scores=score.load_phase_scores(),
        bonus_cap=cap, bonus_span=span, verbose=False,
    )
    by_id = {
        r["trackid_id"]: r
        for r in (json.loads(x) for x in out.read_text(encoding="utf-8").splitlines())
    }
    # both phase 0, 200 richer than 100 -> strictly higher score
    assert by_id[100]["score_components"]["net_new_count"] == 1
    assert by_id[200]["score_components"]["net_new_count"] == 3
    assert by_id[200]["score"] > by_id[100]["score"]
    # phase1 (300) maxed out never crosses into the phase0 band
    assert by_id[300]["score_components"]["phase"] == 1
    assert by_id[300]["score"] < by_id[100]["score"]


def test_score_idempotent(tmp_path):
    db = str(tmp_path / "staging.db")
    _seed_db(db)
    lib = tmp_path / "lib.txt"
    lib.write_text("lib guy\n", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("genre star\t25\n", encoding="utf-8")
    channels = tmp_path / "chan.csv"
    channels.write_text(
        "prio,channel,sets,net_new,known,lib,net_new_rate\n"
        "1,P1 Radio,1,1,1,1,1\n2,P2 Radio,1,1,1,1,1\n"
        "3,P3 Radio,1,1,1,1,1\n0,Banned,1,1,1,1,1\n",
        encoding="utf-8",
    )
    out = tmp_path / "scores.ndjson"
    cap, span = score.load_bonus_params()
    kw = dict(
        threshold=10, phase_scores=score.load_phase_scores(),
        bonus_cap=cap, bonus_span=span, verbose=False,
    )
    score.score(db, str(lib), str(target), str(channels), str(out), **kw)
    first = out.read_text(encoding="utf-8")
    score.score(db, str(lib), str(target), str(channels), str(out), **kw)
    assert out.read_text(encoding="utf-8") == first
