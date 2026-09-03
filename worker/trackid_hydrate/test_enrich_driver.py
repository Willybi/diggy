"""Unit tests for the PURE driver logic (no network, no server import, no Docker).

Deliberately placed in the package, NOT under ``tests/``: CI must not depend on this
local-tooling package (and ``enrich_driver.py`` imports the server code lazily, only
inside ``_hydrate`` — the top-level ``sys.path.insert("/app")`` is harmless on the host,
so the module imports cleanly here). The Deezer search + /track fetch are injected into
``process_row`` as async callables, so these tests mock them and never touch the server.
Run standalone from the repo root:

    pytest worker/trackid_hydrate/test_enrich_driver.py -q
"""

import asyncio

from worker.trackid_hydrate.enrich_driver import (
    _is_id_track,
    _match_artist,
    build_found_record,
    build_record,
    classify_deezer_error,
    extract_deezer,
    extract_key,
    gate_bpm,
    new_counts,
    process_row,
)


class _FakeHTTPError(Exception):
    """Stand-in for DeezerHTTPError — process_row duck-types on ``.status_code``."""

    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"fake {status_code}")


def _run(row, search_fn, fetch_fn, *, beatport_fn=None, analyze_fn=None, cover_fn=None):
    """Drive process_row on a fresh counters dict; return (record, counts).

    The L1b enrichment callables default to None (Deezer-only paths); the full-assembly
    tests pass mocks for them — no server import, no Essentia, no network.
    """
    counts = new_counts()
    rec = asyncio.run(
        process_row(
            row,
            search_fn,
            fetch_fn,
            counts,
            beatport_fn=beatport_fn,
            analyze_fn=analyze_fn,
            cover_fn=cover_fn,
        )
    )
    return rec, counts


def _search_returning(value):
    async def search_fn(artist, title):
        return value

    return search_fn


def _fetch_returning(value):
    async def fetch_fn(deezer_id):
        return value

    return fetch_fn


def _beatport_returning(value):
    async def fn(title, artist, isrc):
        return value

    return fn


def _analyze_returning(value):
    async def fn(preview_url):
        return value

    return fn


def _cover_returning(value):
    async def fn(cat_url, alb_url):
        return value

    return fn


def _raising(exc):
    async def fn(*args, **kwargs):
        raise exc

    return fn


# ── classify_deezer_error ──


def test_classify_deezer_error():
    assert classify_deezer_error(404) == "not_found"
    assert classify_deezer_error(429) == "outage"
    assert classify_deezer_error(500) == "outage"
    assert classify_deezer_error(503) == "outage"


# ── _is_id_track ──


def test_is_id_track():
    for v in ("1", "true", "True", "YES", "t", "y", "  true  "):
        assert _is_id_track({"is_id": v}) is True
    for v in ("0", "false", "no", "", "n", None):
        assert _is_id_track({"is_id": v}) is False
    assert _is_id_track({}) is False


# ── _match_artist ──


def test_match_artist():
    assert _match_artist({"artist": "Bicep"}) == "Bicep"
    assert _match_artist({"artist": "  Bonobo  "}) == "Bonobo"
    assert _match_artist({"artist": ""}) is None
    assert _match_artist({"artist": None}) is None
    assert _match_artist({}) is None


# ── build_record ──


def test_build_record():
    rec = build_record(42, 3, "not_found", None)
    assert rec == {
        "set_trackid_id": 42,
        "position": 3,
        "status": "not_found",
        "deezer": None,
    }


# ── extract_deezer ──


def test_extract_deezer_full():
    track = {
        "id": 9,
        "isrc": "GB1234",
        "preview": "https://cdn/preview.mp3",
        "album": {"cover_medium": "https://cdn/med.jpg", "cover_big": "https://cdn/big.jpg"},
    }
    dz = extract_deezer(track)
    assert dz["track"] is track
    assert dz["preview_url"] == "https://cdn/preview.mp3"
    # both cover keys resolve to cover_medium (preferred over cover_big)
    assert dz["cover_catalog_url"] == "https://cdn/med.jpg"
    assert dz["cover_album_url"] == "https://cdn/med.jpg"


def test_extract_deezer_cover_falls_back_to_big():
    dz = extract_deezer({"id": 1, "album": {"cover_big": "https://cdn/big.jpg"}})
    assert dz["cover_catalog_url"] == "https://cdn/big.jpg"
    assert dz["cover_album_url"] == "https://cdn/big.jpg"


def test_extract_deezer_missing_album_and_preview():
    dz = extract_deezer({"id": 1})
    assert dz["preview_url"] is None
    assert dz["cover_catalog_url"] is None
    assert dz["cover_album_url"] is None
    # blank preview strips to None
    dz2 = extract_deezer({"id": 1, "preview": "   "})
    assert dz2["preview_url"] is None


# ── process_row ──


def test_process_row_id_track_skips_search():
    called = {"search": False}

    async def search_fn(artist, title):
        called["search"] = True
        return None

    row = {"set_trackid_id": "5", "position": "1", "title": "?", "artist": "?", "is_id": "true"}
    rec, counts = _run(row, search_fn, _fetch_returning(None))
    assert rec == build_record(5, 1, "id", None)
    assert counts["id"] == 1
    assert called["search"] is False  # id tracks never hit Deezer


def test_process_row_found():
    # No enrichment callables passed → found record with the L1b keys defaulted to null.
    track = {
        "id": 9,
        "isrc": "GB1",
        "preview": "https://cdn/p.mp3",
        "album": {"cover_medium": "https://cdn/m.jpg"},
    }
    row = {"set_trackid_id": "7", "position": "2", "title": "Glue", "artist": "Bicep", "is_id": "0"}
    rec, counts = _run(row, _search_returning({"id": 9}), _fetch_returning(track))
    assert rec["set_trackid_id"] == 7
    assert rec["position"] == 2
    assert rec["status"] == "found"
    assert rec["deezer"]["track"] is track
    assert rec["deezer"]["preview_url"] == "https://cdn/p.mp3"
    assert rec["deezer"]["cover_catalog_url"] == "https://cdn/m.jpg"
    # L1b keys present, all null (no enrichment callables)
    assert rec["deezer"]["cover_catalog_b64"] is None
    assert rec["deezer"]["cover_album_b64"] is None
    assert rec["beatport"] is None
    assert rec["bpm"] is None
    assert rec["key"] is None
    assert rec["embedding"] is None
    assert counts["found"] == 1


def test_process_row_not_found_when_search_none():
    called = {"fetch": False}

    async def fetch_fn(deezer_id):
        called["fetch"] = True
        return {}

    row = {"set_trackid_id": "1", "position": "1", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(row, _search_returning(None), fetch_fn)
    assert rec == build_record(1, 1, "not_found", None)
    assert counts["not_found"] == 1
    assert called["fetch"] is False  # no hit → no /track fetch


def test_process_row_track_error_dict_is_not_found():
    row = {"set_trackid_id": "1", "position": "1", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(
        row, _search_returning({"id": 9}), _fetch_returning({"error": {"code": 800}})
    )
    assert rec == build_record(1, 1, "not_found", None)
    assert counts["not_found"] == 1


def test_process_row_404_on_search_is_not_found_line():
    row = {"set_trackid_id": "3", "position": "4", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(row, _raising(_FakeHTTPError(404)), _fetch_returning(None))
    assert rec == build_record(3, 4, "not_found", None)
    assert counts["not_found"] == 1
    assert counts["outage"] == 0


def test_process_row_429_outage_emits_nothing():
    row = {"set_trackid_id": "3", "position": "4", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(row, _raising(_FakeHTTPError(429)), _fetch_returning(None))
    assert rec is None  # outage → no line, row re-tried later
    assert counts["outage"] == 1
    assert counts["not_found"] == 0


def test_process_row_5xx_outage_emits_nothing():
    row = {"set_trackid_id": "3", "position": "4", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(row, _raising(_FakeHTTPError(503)), _fetch_returning(None))
    assert rec is None
    assert counts["outage"] == 1


def test_process_row_404_on_track_fetch_is_not_found_line():
    # search succeeds, /track fetch 404s → classified not_found
    row = {"set_trackid_id": "3", "position": "4", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(row, _search_returning({"id": 9}), _raising(_FakeHTTPError(404)))
    assert rec == build_record(3, 4, "not_found", None)
    assert counts["not_found"] == 1


def test_process_row_network_error_emits_nothing_counts_error():
    row = {"set_trackid_id": "3", "position": "4", "title": "x", "artist": "y", "is_id": "0"}
    rec, counts = _run(row, _raising(ValueError("boom")), _fetch_returning(None))
    assert rec is None
    assert counts["error"] == 1
    assert counts["outage"] == 0


def test_process_row_malformed_row_counts_error():
    row = {"set_trackid_id": "notanint", "position": "1", "is_id": "0"}
    rec, counts = _run(row, _search_returning(None), _fetch_returning(None))
    assert rec is None
    assert counts["error"] == 1


# ── L1b pure helpers ──


def test_gate_bpm():
    # cleared gate → rounded value/conf
    assert gate_bpm(128.04, 3.146) == {"value": 128.0, "conf": 3.15}
    # exactly at the gate → kept
    assert gate_bpm(120.0, 2.0) == {"value": 120.0, "conf": 2.0}
    # below the gate → null (better no BPM than a wrong one)
    assert gate_bpm(120.0, 1.99) is None


def test_extract_key():
    assert extract_key({"key": "8A", "bpm": 128}) == "8A"
    assert extract_key({"bpm": 128}) is None  # no key on the bp_track
    assert extract_key(None) is None  # no beatport match


def test_build_found_record():
    bp = {"id": 5, "key": "8A", "bpm": 128}
    rec = build_found_record(
        1, 2, {"track": {}}, bp, {"value": 128.0, "conf": 3.0}, "8A", [0.1, 0.2]
    )
    assert rec == {
        "set_trackid_id": 1,
        "position": 2,
        "status": "found",
        "deezer": {"track": {}},
        "beatport": {"bp_track": bp},
        "bpm": {"value": 128.0, "conf": 3.0},
        "key": "8A",
        "embedding": [0.1, 0.2],
    }


def test_build_found_record_null_beatport():
    rec = build_found_record(1, 2, {}, None, None, None, None)
    assert rec["beatport"] is None  # None bp_track → null, not {"bp_track": None}
    assert rec["bpm"] is None
    assert rec["key"] is None
    assert rec["embedding"] is None


# ── L1b full assembly (all heavy calls mocked) ──


def _found_row():
    return {
        "set_trackid_id": "7",
        "position": "2",
        "title": "Glue",
        "artist": "Bicep",
        "is_id": "0",
    }


def _found_track(preview="https://cdn/p.mp3"):
    track = {"id": 9, "isrc": "GB1", "album": {"cover_medium": "https://cdn/m.jpg"}}
    if preview is not None:
        track["preview"] = preview
    return track


def test_process_row_full_enrichment():
    bp = {"id": 5, "key": "8A", "bpm": 128}
    emb = [0.01] * 1280
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        beatport_fn=_beatport_returning(bp),
        analyze_fn=_analyze_returning(({"value": 128.0, "conf": 3.1}, emb)),
        cover_fn=_cover_returning(("CAT64", "ALB64")),
    )
    assert rec["status"] == "found"
    assert rec["deezer"]["cover_catalog_b64"] == "CAT64"
    assert rec["deezer"]["cover_album_b64"] == "ALB64"
    assert rec["beatport"] == {"bp_track": bp}
    assert rec["key"] == "8A"  # hoisted from the bp_track
    assert rec["bpm"] == {"value": 128.0, "conf": 3.1}
    assert rec["embedding"] == emb
    assert counts["found"] == 1
    assert counts["bp_found"] == 1
    assert counts["bpm_ok"] == 1
    assert counts["embed_ok"] == 1


def test_process_row_bpm_gated_out_is_null():
    # analyze_fn returns null bpm (conf was below the gate) but a valid embedding.
    emb = [0.02] * 1280
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        analyze_fn=_analyze_returning((None, emb)),
    )
    assert rec["bpm"] is None
    assert rec["embedding"] == emb
    assert counts["bpm_ok"] == 0
    assert counts["embed_ok"] == 1


def test_process_row_analysis_failure_nulls_bpm_and_embedding():
    # A raising analyze_fn (download/Essentia blow-up) must leave bpm+embedding null
    # WITHOUT dropping the record.
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        analyze_fn=_raising(RuntimeError("essentia boom")),
        cover_fn=_cover_returning(("CAT64", "ALB64")),
    )
    assert rec["status"] == "found"
    assert rec["bpm"] is None
    assert rec["embedding"] is None
    # the rest of the record survives
    assert rec["deezer"]["cover_catalog_b64"] == "CAT64"
    assert counts["found"] == 1
    assert counts["bpm_ok"] == 0
    assert counts["embed_ok"] == 0


def test_process_row_no_preview_skips_analysis():
    called = {"analyze": False}

    async def analyze_fn(preview_url):
        called["analyze"] = True
        return ({"value": 1.0, "conf": 9.0}, [0.0] * 1280)

    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track(preview=None)),  # no preview
        analyze_fn=analyze_fn,
    )
    assert rec["bpm"] is None
    assert rec["embedding"] is None
    assert called["analyze"] is False  # no preview → analyze_fn never invoked


def test_process_row_beatport_found_key_hoisted():
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        beatport_fn=_beatport_returning({"id": 5, "key": "5A", "bpm": 124}),
    )
    assert rec["beatport"]["bp_track"]["bpm"] == 124  # bpm stays inside bp_track
    assert rec["key"] == "5A"
    assert counts["bp_found"] == 1
    assert counts["bp_outage"] == 0


def test_process_row_beatport_outage_still_emits_record():
    # 403/429/5xx → no beatport, but the rest of the record IS emitted (E1-tolerant).
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        beatport_fn=_raising(_FakeHTTPError(403)),
        cover_fn=_cover_returning(("CAT64", "ALB64")),
    )
    assert rec["status"] == "found"
    assert rec["beatport"] is None
    assert rec["key"] is None
    assert rec["deezer"]["cover_catalog_b64"] == "CAT64"  # unaffected
    assert counts["found"] == 1
    assert counts["bp_outage"] == 1


def test_process_row_beatport_404_is_no_match_not_outage():
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        beatport_fn=_raising(_FakeHTTPError(404)),
    )
    assert rec["status"] == "found"
    assert rec["beatport"] is None
    assert rec["key"] is None
    assert counts["bp_outage"] == 0  # a 404 "no match" is not an outage
    assert counts["bp_found"] == 0


def test_process_row_beatport_none_is_no_match():
    # search returns None (no Beatport track) → null beatport, no outage.
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        beatport_fn=_beatport_returning(None),
    )
    assert rec["beatport"] is None
    assert rec["key"] is None
    assert counts["bp_found"] == 0
    assert counts["bp_outage"] == 0


def test_process_row_cover_failure_nulls_b64_keeps_record():
    rec, counts = _run(
        _found_row(),
        _search_returning({"id": 9}),
        _fetch_returning(_found_track()),
        cover_fn=_raising(RuntimeError("cdn down")),
        analyze_fn=_analyze_returning(({"value": 128.0, "conf": 3.0}, [0.0] * 1280)),
    )
    assert rec["status"] == "found"
    assert rec["deezer"]["cover_catalog_b64"] is None
    assert rec["deezer"]["cover_album_b64"] is None
    assert rec["bpm"] == {"value": 128.0, "conf": 3.0}  # analysis unaffected


def test_process_row_not_found_carries_no_enrichment_keys():
    # a not_found record keeps the bare shape (no beatport/bpm/key/embedding keys).
    rec, _ = _run(
        _found_row(),
        _search_returning(None),
        _fetch_returning(None),
        beatport_fn=_beatport_returning({"key": "8A"}),
        analyze_fn=_analyze_returning(({"value": 1.0, "conf": 9.0}, [0.0])),
        cover_fn=_cover_returning(("X", "Y")),
    )
    assert rec == build_record(7, 2, "not_found", None)
    assert "beatport" not in rec
    assert "bpm" not in rec
