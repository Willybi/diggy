"""Offline tests for shadow.py — normalization parity + match logic (no network)."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import shadow  # noqa: E402


def test_normalize_parity():
    # byte-faithful with server/api/utils.py normalize()
    assert shadow.normalize("  Amélie  ") == "amélie"
    assert shadow.normalize("Feat. Foo") == "feat foo"
    assert shadow.normalize("A ft. B") == "a ft b"
    assert shadow.normalize("It’s") == "it's"  # curly apostrophe folded
    # NFC: decomposed e + combining acute -> precomposed é (same key)
    assert shadow.normalize("Café") == shadow.normalize("Café")
    # NOT accent-folded (invariant #4): León != Leon
    assert shadow.normalize("León") != shadow.normalize("Leon")


def test_make_normalized_key():
    assert shadow.make_normalized_key("Title", "Artist") == "title - artist"
    assert shadow.make_normalized_key("T", None) == "t - "


def test_is_id_track():
    assert shadow.is_id_track("ID", "ID")
    assert shadow.is_id_track("", "")
    assert shadow.is_id_track("?", None)
    assert not shadow.is_id_track("Real Title", "Real Artist")


def test_merge_tracklist_dedup():
    detail = {
        "detectionProcesses": [
            {"detectionProcessMusicTracks": [{"musicTrackId": 1, "title": "A"}]},
            {"detectionProcessMusicTracks": [{"musicTrackId": 1, "title": "A2"}, {"musicTrackId": 2, "title": "B"}]},
            {"detectionProcessMusicTracks": [{"musicTrackId": None, "title": "X"}]},
        ]
    }
    merged = shadow.merge_tracklist(detail)
    assert {t["musicTrackId"] for t in merged} == {1, 2}


def test_match_flow(tmp_path):
    db = str(tmp_path / "s.db")
    conn = shadow.connect(db)
    # seed a minimal staging row + one fetched set with 3 tracks
    conn.execute(
        "CREATE TABLE trackid_index_staging (trackid_id INTEGER PRIMARY KEY, "
        "channel TEXT, track_hit_rate REAL, track_count INTEGER, is_deleted INTEGER)"
    )
    conn.execute(
        "INSERT INTO trackid_index_staging VALUES (10,'Chan',0.8,3,0)"
    )
    detail = {
        "detectionProcesses": [
            {"detectionProcessMusicTracks": [
                {"musicTrackId": 1, "title": "Known", "artist": "Foo"},
                {"musicTrackId": 2, "title": "NetNew", "artist": "Bar"},
                {"musicTrackId": 3, "title": "ID", "artist": "ID"},
            ]}
        ]
    }
    shadow._store_detail(conn, 10, "slug", 200, None, detail)
    conn.commit()

    cat = tmp_path / "cat.txt"
    cat.write_text("known - foo\n", encoding="utf-8")
    art = tmp_path / "art.txt"
    art.write_text("bar\n", encoding="utf-8")
    conn.close()

    shadow.match(db, str(cat), str(art), verbose=False)
    d = shadow.report(db)
    assert d["tracks_total"] == 3
    assert d["tracks_id"] == 1
    assert d["identified_instances"] == 2
    assert d["instances_matched"] == 1  # "known - foo"
    assert d["distinct_netnew"] == 1  # "netnew - bar"
    assert d["distinct_netnew_artist_known"] == 1  # artist "bar" is known
