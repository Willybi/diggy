"""Offline tests for the C14.b GATE 🅱 resolver — fold-matching, the 3-method
cascade, response parsing and the --score precision. ``fetch_json`` is always
mocked with inline JSON fixtures, so NO real network call is ever made (Wikidata /
MusicBrainz / YouTube). No prod, no server package."""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import resolve  # noqa: E402


def _no_sleep(*_a, **_k):
    return None


# ── fake HTTP layer ───────────────────────────────────────────────────────────
class FakeFetch:
    """Route a URL to an inline fixture by substring; raise to simulate an outage.

    ``routes`` = list of ``(substring, response_or_exception)``, first match wins.
    """

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append(url)
        # a courteous UA must always be sent (Wikidata/MB require it)
        assert headers.get("User-Agent"), "missing User-Agent header"
        for substr, resp in self.routes:
            if substr in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"no route for {url}")


# fixture builders --------------------------------------------------------------
def wd_search(qid="Q1", label="Some Artist"):
    return {"search": [{"id": qid, "label": label, "description": "musician"}]}


def wd_claims(p2397=None, p3040=None, p434=None):
    claims = {}
    if p2397:
        claims["P2397"] = [{"mainsnak": {"datavalue": {"value": p2397}}}]
    if p3040:
        claims["P3040"] = [{"mainsnak": {"datavalue": {"value": p3040}}}]
    if p434:
        claims["P434"] = [{"mainsnak": {"datavalue": {"value": p434}}}]
    return {"entities": {"Q1": {"claims": claims}}}


def mb_search(mbid="mbid-123"):
    return {"artists": [{"id": mbid, "name": "Some Artist"}]}


def mb_rels(youtube=None, soundcloud=None):
    rels = []
    if youtube:
        rels.append({"type": "youtube", "url": {"resource": youtube}})
    if soundcloud:
        rels.append({"type": "soundcloud", "url": {"resource": soundcloud}})
    return {"relations": rels}


def yt_items(channel_id="UCxyz", title="Some Artist"):
    return {"items": [{"id": {"channelId": channel_id},
                       "snippet": {"channelId": channel_id, "channelTitle": title}}]}


def resolve_one(artist, fetch, **kw):
    kw.setdefault("sleep", _no_sleep)
    return resolve.resolve_artist(artist, fetch_json=fetch, **kw)


# ── (1) fold-match ─────────────────────────────────────────────────────────────
def test_fold_match_equal():
    assert resolve.fold_match("Amelie Lens", "Amelie Lens")
    assert resolve.fold_match("Charlotte de Witte", "Charlotte de Witte")


def test_fold_match_inclusion():
    assert resolve.fold_match("Bicep", "Bicep Official")
    assert resolve.fold_match("Boris Brejcha", "Boris Brejcha - Official")


def test_fold_match_accents_and_punct():
    assert resolve.fold_match("Amélie Lens", "Amelie Lens")  # accent fold
    assert resolve.fold_match("Mr. Oizo", "Mr Oizo")         # punctuation fold
    assert resolve.fold_match("St. Germain", "St Germain")


def test_fold_match_length_guard():
    # a 2-char folded name must NOT match by trivial inclusion in a long title
    assert not resolve.fold_match("KI", "The KI KI Radio Show Channel")
    # a fully non-Latin name folds to "" -> never matches (invariant #4)
    assert not resolve.fold_match("初音ミク", "Some Channel")


def test_fold_match_unrelated():
    assert not resolve.fold_match("Fred again..", "Totally Different Channel")


def test_fold_match_space_insensitive():
    # YT channel titles/handles are often glued together -> space-insensitive pass
    assert resolve.fold_match("Amelie Lens", "AmelieLens")            # equal, no space
    assert resolve.fold_match("David Guetta", "davidguettaofficial")  # inclusion, glued
    assert resolve.fold_match("Boris Brejcha", "BorisBrejcha")


def test_fold_match_space_insensitive_length_guard():
    # the min_len guard still holds on the space-stripped inclusion: a short glued
    # key must NOT match a long concatenated title
    assert not resolve.fold_match("KI", "TheKiKiRadioShowChannel")
    # a non-Latin name folds to "" -> never matches, even in the space-insensitive pass
    assert not resolve.fold_match("初音ミク", "SomeGluedChannel")


# ── (2) cascade ────────────────────────────────────────────────────────────────
def test_cascade_wikidata_p2397():
    fetch = FakeFetch([
        ("wbsearchentities", wd_search()),
        ("wbgetentities", wd_claims(p2397="UCabc", p3040="fredagain")),
    ])
    result, event = resolve_one({"name": "Fred again..", "artist_id": 7, "tier": 1}, fetch)
    assert result["method"] == "wikidata"
    assert result["confidence"] == "high"
    assert result["yt_channel_id"] == "UCabc"
    assert result["yt_url"] == "https://www.youtube.com/channel/UCabc"
    assert result["has_soundcloud"] is True
    assert result["sc_ref"] == "https://soundcloud.com/fredagain"
    assert event is None  # no search consumed
    # stops at (a): never hits MusicBrainz/YouTube
    assert not any("musicbrainz" in u for u in fetch.calls)


def test_cascade_musicbrainz_via_p434():
    # Wikidata has the MBID (P434) but no P2397 -> MB rels carry the YouTube link
    fetch = FakeFetch([
        ("wbsearchentities", wd_search()),
        ("wbgetentities", wd_claims(p434="mbid-9")),
        ("/artist/mbid-9", mb_rels(youtube="https://www.youtube.com/@fredagain")),
    ])
    result, event = resolve_one({"name": "Fred again.."}, fetch)
    assert result["method"] == "musicbrainz"
    assert result["confidence"] == "high"
    assert result["yt_channel_id"] == "@fredagain"
    assert result["yt_url"] == "https://www.youtube.com/@fredagain"
    assert event is None
    # used the P434 MBID directly -> NO MusicBrainz search call
    assert not any("/artist?" in u for u in fetch.calls)


def test_cascade_musicbrainz_via_search():
    # No P2397, no P434 -> fall back to a MB search, then rels
    fetch = FakeFetch([
        ("wbsearchentities", wd_search()),
        ("wbgetentities", wd_claims()),  # empty claims
        ("/artist?", mb_search(mbid="mbid-77")),
        ("/artist/mbid-77", mb_rels(
            youtube="https://www.youtube.com/channel/UCkiki",
            soundcloud="https://soundcloud.com/kiki",
        )),
    ])
    result, event = resolve_one({"name": "KiKi"}, fetch)
    assert result["method"] == "musicbrainz"
    assert result["yt_channel_id"] == "UCkiki"
    assert result["has_soundcloud"] is True
    assert result["sc_ref"] == "https://soundcloud.com/kiki"
    assert event is None


def test_cascade_search_needs_verify():
    fetch = FakeFetch([
        ("wbsearchentities", {"search": []}),   # no wikidata entity
        ("/artist?", {"artists": []}),          # no MB artist
        ("youtube/v3/search", yt_items(channel_id="UCsara", title="Sara Landry")),
    ])
    result, event = resolve_one(
        {"name": "Sara Landry"}, fetch, api_key="KEY", search_budget_ok=True
    )
    assert result["method"] == "search"
    assert result["confidence"] == "NEEDS_VERIFY"
    assert result["yt_channel_id"] == "UCsara"
    assert result["yt_channel_title"] == "Sara Landry"
    assert event == "used"


def test_cascade_search_rejected_by_fold_stays_none():
    # search returns an UNRELATED channel -> fold guard rejects -> method none
    fetch = FakeFetch([
        ("wbsearchentities", {"search": []}),
        ("/artist?", {"artists": []}),
        ("youtube/v3/search", yt_items(channel_id="UCx", title="Random Gaming Channel")),
    ])
    result, event = resolve_one(
        {"name": "Sara Landry"}, fetch, api_key="KEY", search_budget_ok=True
    )
    assert result["method"] == "none"
    assert event == "used"  # a search still consumed quota


def test_cascade_all_absent_none():
    fetch = FakeFetch([
        ("wbsearchentities", {"search": []}),
        ("/artist?", {"artists": []}),
        ("youtube/v3/search", {"items": []}),
    ])
    result, event = resolve_one(
        {"name": "Nobody Underground"}, fetch, api_key="KEY", search_budget_ok=True
    )
    assert result["method"] == "none"
    assert result["yt_url"] == ""
    assert event == "used"


def test_cascade_network_error_is_isolated():
    fetch = FakeFetch([("wbsearchentities", RuntimeError("boom"))])
    result, event = resolve_one({"name": "Some Artist"}, fetch)
    assert result["method"] == "error"
    assert event is None  # never reached the search stage


def test_cascade_search_skipped_without_key():
    fetch = FakeFetch([
        ("wbsearchentities", {"search": []}),
        ("/artist?", {"artists": []}),
    ])
    result, event = resolve_one({"name": "KI/KI"}, fetch, api_key=None)
    assert result["method"] == "none"
    assert event == "skipped_no_key"
    assert not any("youtube" in u for u in fetch.calls)  # no search issued


def test_cascade_search_skipped_for_budget():
    fetch = FakeFetch([
        ("wbsearchentities", {"search": []}),
        ("/artist?", {"artists": []}),
    ])
    result, event = resolve_one(
        {"name": "KI/KI"}, fetch, api_key="KEY", search_budget_ok=False
    )
    assert result["method"] == "none"
    assert event == "skipped_budget"
    assert not any("youtube" in u for u in fetch.calls)


def test_soundcloud_noted_even_when_no_youtube():
    # no YT anywhere, but Wikidata P3040 present -> has_soundcloud, method none
    fetch = FakeFetch([
        ("wbsearchentities", wd_search()),
        ("wbgetentities", wd_claims(p3040="schrotthagen")),
        ("/artist?", {"artists": []}),
    ])
    result, event = resolve_one({"name": "Schrotthagen"}, fetch, api_key=None)
    assert result["method"] == "none"
    assert result["has_soundcloud"] is True
    assert result["sc_ref"] == "https://soundcloud.com/schrotthagen"


# ── (3) parsing of the three response shapes ───────────────────────────────────
def test_parse_wikidata_claim_string():
    claims = wd_claims(p2397="UCzz")["entities"]["Q1"]["claims"]
    assert resolve._claim_string(claims, "P2397") == "UCzz"
    assert resolve._claim_string(claims, "P9999") is None
    # a malformed claim (no datavalue) is skipped, not crashed
    assert resolve._claim_string({"P1": [{"mainsnak": {}}]}, "P1") is None


def test_parse_musicbrainz_rels():
    rels = mb_rels(
        youtube="https://youtube.com/@artist",
        soundcloud="https://soundcloud.com/artist",
    )["relations"]
    yt, sc = resolve.scan_rels_for_links(rels)
    assert yt == "https://youtube.com/@artist"
    assert sc == "https://soundcloud.com/artist"
    # no links -> (None, None)
    assert resolve.scan_rels_for_links([]) == (None, None)


def test_parse_youtube_ref_all_forms():
    assert resolve.parse_youtube_ref("https://www.youtube.com/channel/UCabc") == (
        "channel_id", "UCabc")
    assert resolve.parse_youtube_ref("https://youtube.com/@fred.again") == (
        "handle", "@fred.again")
    assert resolve.parse_youtube_ref("https://www.youtube.com/c/BorisBrejcha") == (
        "custom", "BorisBrejcha")
    assert resolve.parse_youtube_ref("https://www.youtube.com/user/deadmau5") == (
        "user", "deadmau5")
    assert resolve.parse_youtube_ref("https://example.com/foo") is None
    assert resolve.parse_youtube_ref(None) is None


def test_verify_search_hits_prefers_first_match():
    items = [
        {"id": {"channelId": "UCa"},
         "snippet": {"channelId": "UCa", "channelTitle": "Unrelated"}},
        {"id": {"channelId": "UCb"},
         "snippet": {"channelId": "UCb", "channelTitle": "Amelie Lens"}},
    ]
    assert resolve.verify_search_hits("Amelie Lens", items) == ("UCb", "Amelie Lens")
    assert resolve.verify_search_hits("Amelie Lens", []) == (None, None)


# ── driver: search budget accounting ───────────────────────────────────────────
def test_run_gate_budget_caps_searches():
    # 3 artists that all fall through to search; cap at 1 -> 1 used, 2 budget-skipped
    fetch = FakeFetch([
        ("wbsearchentities", {"search": []}),
        ("/artist?", {"artists": []}),
        ("youtube/v3/search", {"items": []}),
    ])
    artists = [{"name": f"Artist {i}"} for i in range(3)]
    results, stats = resolve.run_gate(
        artists, fetch_json=fetch, api_key="KEY", max_search=1, sleep=_no_sleep
    )
    assert len(results) == 3
    assert stats["searches_used"] == 1
    assert stats["searches_skipped_budget"] == 2


# ── input reading ──────────────────────────────────────────────────────────────
def test_read_artists(tmp_path):
    p = tmp_path / "artists.ndjson"
    p.write_text(
        json.dumps({"artist_id": 1, "name": "Fred again..", "tier": 1}) + "\n"
        + json.dumps({"name": "  "}) + "\n"          # blank name -> skipped
        + "\n"                                         # blank line -> skipped
        + "{bad json}\n"                               # bad json -> skipped
        + json.dumps({"artist_id": 2, "name": "KI/KI"}) + "\n",
        encoding="utf-8",
    )
    rows = list(resolve.read_artists(str(p)))
    assert [r["name"] for r in rows] == ["Fred again..", "KI/KI"]
    assert rows[0]["tier"] == 1


# ── (4) --score precision ──────────────────────────────────────────────────────
def test_compute_precision_global_and_per_method():
    rows = [
        {"name": "A", "method": "wikidata", "confidence": "high", "correct": "1"},
        {"name": "B", "method": "wikidata", "confidence": "high", "correct": "1"},
        {"name": "C", "method": "musicbrainz", "confidence": "high", "correct": "0"},
        {"name": "D", "method": "search", "confidence": "NEEDS_VERIFY", "correct": "1"},
        {"name": "E", "method": "search", "confidence": "NEEDS_VERIFY", "correct": "0"},
        {"name": "F", "method": "search", "confidence": "NEEDS_VERIFY", "correct": ""},
    ]
    res = resolve.compute_precision(rows)
    assert res["rows"] == 6
    assert res["marked"] == 5   # the blank one is unmarked, excluded
    assert res["unmarked"] == 1
    assert res["correct"] == 3
    assert abs(res["precision"] - 60.0) < 1e-9
    assert res["by_method"]["wikidata"] == {"marked": 2, "correct": 2}
    assert res["by_method"]["musicbrainz"] == {"marked": 1, "correct": 0}
    assert res["by_method"]["search"] == {"marked": 2, "correct": 1}


def test_score_review_end_to_end(tmp_path, capsys):
    p = tmp_path / "review.csv"
    with open(p, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "method", "confidence", "yt_url", "correct"])
        w.writerow(["A", "wikidata", "high", "http://x", "1"])
        w.writerow(["B", "search", "NEEDS_VERIFY", "http://y", "0"])
    res = resolve.score_review(str(p))
    out = capsys.readouterr().out
    assert res["marked"] == 2 and res["correct"] == 1
    assert "GLOBAL precision" in out
    assert "wikidata" in out and "search" in out


# ── end-to-end artefacts ───────────────────────────────────────────────────────
def test_main_end_to_end(tmp_path, monkeypatch):
    inp = tmp_path / "artists.ndjson"
    inp.write_text(
        "\n".join(json.dumps(a) for a in [
            {"artist_id": 1, "name": "Fred again..", "tier": 1},
            {"artist_id": 2, "name": "Nobody Underground", "tier": 3},
        ]),
        encoding="utf-8",
    )
    out = tmp_path / "gate_out"

    fetch = FakeFetch([
        ("wbsearchentities&search=Fred", wd_search()),
        ("wbsearchentities", {"search": []}),
        ("wbgetentities", wd_claims(p2397="UCfred")),
        ("/artist?", {"artists": []}),
    ])
    # no key -> method (c) skipped, all offline through the mocked fetch
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(resolve, "fetch_json", fetch)
    monkeypatch.setattr(resolve.time, "sleep", _no_sleep)

    rc = resolve.main([str(inp), "--out", str(out)])
    assert rc == 0

    with open(out / "results.ndjson", encoding="utf-8") as f:
        results = [json.loads(line) for line in f if line.strip()]
    assert len(results) == 2
    fred = next(r for r in results if r["name"] == "Fred again..")
    assert fred["method"] == "wikidata" and fred["yt_channel_id"] == "UCfred"
    # every result row carries exactly the contract fields
    assert all(set(r.keys()) == set(resolve.RESULT_FIELDS) for r in results)

    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "Coverage" in summary and "By method" in summary

    with open(out / "review.csv", encoding="utf-8") as f:
        review = list(csv.DictReader(f))
    assert len(review) == 1  # only the resolved Fred row has a yt_url
    assert review[0]["correct"] == ""


def test_main_idempotent(tmp_path, monkeypatch):
    inp = tmp_path / "artists.ndjson"
    inp.write_text(json.dumps({"name": "Fred again.."}), encoding="utf-8")
    out = tmp_path / "gate_out"
    fetch = FakeFetch([
        ("wbsearchentities", wd_search()),
        ("wbgetentities", wd_claims(p2397="UCfred")),
    ])
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(resolve, "fetch_json", fetch)
    monkeypatch.setattr(resolve.time, "sleep", _no_sleep)

    resolve.main([str(inp), "--out", str(out)])
    first = (out / "results.ndjson").read_text(encoding="utf-8")
    resolve.main([str(inp), "--out", str(out)])
    assert (out / "results.ndjson").read_text(encoding="utf-8") == first
