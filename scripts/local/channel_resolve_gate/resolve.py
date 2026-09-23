"""C14.b GATE 🅱 — feasibility pre-flight for artist -> YouTube-channel resolution.

Read-only, LOCAL, stdlib only. Takes a NDJSON sample of cohort artists and, per
artist, runs a 3-method CASCADE (stop at the first that resolves):

  (a) Wikidata   : wbsearchentities -> top Q-id -> wbgetentities claims -> P2397
                   (YouTube channel id). Also notes P3040 (SoundCloud) + P434 (MBID).
                   method="wikidata", confidence="high".
  (b) MusicBrainz: MBID (from Wikidata P434 else a MB search) -> artist url-rels ->
                   an official YouTube link. STRICT 1 req/s. method="musicbrainz",
                   confidence="high". Also notes a SoundCloud rel.
  (c) YouTube search (only if YOUTUBE_API_KEY is set and the search budget is not
                   spent): search.list type=channel -> VERIFY by folded name -> a
                   risky fallback. method="search", confidence="NEEDS_VERIFY".

None resolves -> method="none". A per-artist exception -> method="error" (never a
global crash). `has_soundcloud` is ALWAYS recorded (P3040 or a MB SoundCloud rel) to
size the future SoundCloud volet.

It MEASURES the yield + precision of the cascade — it does NOT build the pillar, and
it connects to NOTHING in prod (it reads a file the operator produces). The HTTP layer
is the single injectable :func:`fetch_json`, so the tests replace it and hit no real
network.

Run:    python scripts/local/channel_resolve_gate/resolve.py <artists.ndjson> [opts]
Score:  python scripts/local/channel_resolve_gate/resolve.py --score gate_out/review.csv
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter
from urllib.parse import quote, urlencode

# ── endpoints & tunables ──────────────────────────────────────────────────────
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"

# Politeness. Wikidata is generous but be gentle; MusicBrainz is a STRICT 1 req/s.
WIKIDATA_DELAY = 0.5
MUSICBRAINZ_DELAY = 1.0
YOUTUBE_DELAY = 0.2
HTTP_TIMEOUT = 20.0

DEFAULT_MAX_SEARCH = 60  # each YouTube search costs 100 quota units
SEARCH_FOLD_MIN_LEN = 5  # a folded name shorter than this is not trusted for inclusion

# Wikidata & MusicBrainz both REQUIRE a descriptive User-Agent (they 403/429 a blank
# one). Keep it identifying, with a contact — this is a courteous local pre-flight.
DEFAULT_USER_AGENT = (
    "diggy-channel-resolve-gate/1.0 "
    "(https://diggy-music.fr; williamb.bienvenu@gmail.com) local-preflight"
)

# The exact contract of results.ndjson (and the shared column order of review.csv).
RESULT_FIELDS = (
    "artist_id", "name", "tier", "method", "yt_channel_id", "yt_channel_title",
    "yt_url", "has_soundcloud", "sc_ref", "confidence",
)
FOUND_METHODS = ("wikidata", "musicbrainz", "search")


# ── HTTP layer (the SINGLE injectable seam) ───────────────────────────────────
def fetch_json(url, headers):
    """GET ``url`` with ``headers`` and return the parsed JSON (``{}`` on empty body).

    The ONE function the whole tool routes its network through — tests inject a fake
    in its place so no real request is ever made. Raises on transport/HTTP/JSON
    errors; the per-artist caller catches and degrades to method="error".
    """
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


# ── name folding (minimal standalone copy of artist_names.punct_fold_key) ──────
# Reproduced here on purpose: this tool stays stdlib-pure and imports NO server
# package (pattern A7-07). Origin: server/workers/artist_names.py::punct_fold_key —
# lowercase + transliterate non-decomposable Latin/smart-punct + NFKD + drop ASCII
# rest + strip a small intra-name punctuation set. Keep the two in spirit-sync.
_TRANSLIT = str.maketrans(
    {
        "ı": "i", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "ß": "ss",
        "þ": "th", "æ": "ae", "œ": "oe", "ħ": "h", "ŧ": "t", "ĸ": "k",
        "’": "'", "‘": "'", "‛": "'", "‚": "'",
        "“": '"', "”": '"', "„": '"', "–": "-", "—": "-", "―": "-",
    }
)
_RE_PUNCT_STRIP = re.compile(r"[.,'\-·•]")
_RE_SPACES = re.compile(r"\s+")


def fold_key(name):
    """Punctuation/accents-insensitive fold key for MATCHING (never an identity key).

    "St. Germain" == "St Germain", "Amélie" == "Amelie", "Mr. Oizo" == "Mr Oizo".
    A fully non-Latin name folds to "" — the caller MUST treat an empty key as "no
    signal, do not match" (invariant #4).
    """
    s = (name or "").lower().strip().translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = _RE_PUNCT_STRIP.sub("", s)
    return _RE_SPACES.sub(" ", s).strip()


def _equal_or_included(a, b, min_len):
    """Equal, or the shorter of ``a``/``b`` contained in the longer with a length
    guard. Assumes both are non-empty."""
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= min_len and shorter in longer


def fold_match(name, title, min_len=SEARCH_FOLD_MIN_LEN):
    """True when the artist ``name`` folds equal to, or is confidently contained in,
    the channel ``title`` (or vice-versa).

    Two passes on the :func:`fold_key` forms. First on the space-COMPACTED form:
    equal folds match, and an INCLUSION (the shorter inside the longer) matches only
    when the shorter is at least ``min_len`` chars — a length guard so a 2-3 char
    fold ("ki", "art") cannot trivially match a long channel title. Then, if that
    fails, a SPACE-INSENSITIVE pass with every space removed on both sides
    (``"Amelie Lens"`` vs ``"AmelieLens"``, ``"David Guetta"`` vs
    ``"davidguettaofficial"``): YouTube channel titles/handles are often concatenated,
    so an artist name would otherwise never match — safe to be this permissive here
    because method (c) stays ``NEEDS_VERIFY`` (human-confirmed). The same ``min_len``
    guard applies on the space-stripped inclusion. A blank fold on either side
    (non-Latin name) never matches, in either pass.
    """
    a = fold_key(name)
    b = fold_key(title)
    if not a or not b:
        return False
    if _equal_or_included(a, b, min_len):
        return True
    # space-insensitive pass — YT titles/handles are often glued together
    a_ns = a.replace(" ", "")
    b_ns = b.replace(" ", "")
    if not a_ns or not b_ns:
        return False
    return _equal_or_included(a_ns, b_ns, min_len)


# ── YouTube URL parsing / building ────────────────────────────────────────────
_YT_CHANNEL_RE = re.compile(r"youtube\.com/channel/([A-Za-z0-9_-]+)", re.IGNORECASE)
_YT_HANDLE_RE = re.compile(r"youtube\.com/(@[A-Za-z0-9_.-]+)", re.IGNORECASE)
_YT_CUSTOM_RE = re.compile(r"youtube\.com/c/([A-Za-z0-9_.-]+)", re.IGNORECASE)
_YT_USER_RE = re.compile(r"youtube\.com/user/([A-Za-z0-9_.-]+)", re.IGNORECASE)


def parse_youtube_ref(url):
    """Extract a ``(kind, ref)`` from a YouTube URL, or ``None``.

    kind ∈ channel_id ("UC…") / handle ("@name") / custom ("/c/Name") / user
    ("/user/Name"). Matched most-specific-first so "/channel/" wins over a bare path.
    """
    if not url:
        return None
    for kind, rx in (
        ("channel_id", _YT_CHANNEL_RE),
        ("handle", _YT_HANDLE_RE),
        ("custom", _YT_CUSTOM_RE),
        ("user", _YT_USER_RE),
    ):
        m = rx.search(url)
        if m:
            return kind, m.group(1)
    return None


def youtube_url_from_ref(kind, ref):
    """Canonical YouTube URL for a ``(kind, ref)`` — the clickable ↗ in review.csv."""
    if kind == "channel_id":
        return f"https://www.youtube.com/channel/{ref}"
    if kind == "handle":
        return f"https://www.youtube.com/{ref}"
    if kind == "custom":
        return f"https://www.youtube.com/c/{ref}"
    if kind == "user":
        return f"https://www.youtube.com/user/{ref}"
    return ""


# ── method (a): Wikidata ──────────────────────────────────────────────────────
def _wikidata_search(name, *, fetch_json, headers, sleep):
    """Return ``(qid, label)`` for the top wbsearchentities hit, or ``(None, None)``."""
    sleep(WIKIDATA_DELAY)
    url = WIKIDATA_API + "?" + urlencode(
        {
            "action": "wbsearchentities", "search": name, "language": "en",
            "uselang": "en", "format": "json", "type": "item", "limit": 5,
        }
    )
    data = fetch_json(url, headers)
    hits = data.get("search") or []
    if not hits:
        return None, None
    top = hits[0]
    return top.get("id"), top.get("label")


def _wikidata_claims(qid, *, fetch_json, headers, sleep):
    """Return the claims dict of entity ``qid`` (``{}`` when absent)."""
    sleep(WIKIDATA_DELAY)
    url = WIKIDATA_API + "?" + urlencode(
        {"action": "wbgetentities", "ids": qid, "format": "json", "props": "claims"}
    )
    data = fetch_json(url, headers)
    ent = (data.get("entities") or {}).get(qid) or {}
    return ent.get("claims") or {}


def _claim_string(claims, prop):
    """First non-empty string value of ``prop`` in a Wikidata claims dict, or None."""
    for c in claims.get(prop) or []:
        try:
            value = c["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# ── method (b): MusicBrainz ───────────────────────────────────────────────────
def _musicbrainz_search(name, *, fetch_json, headers, sleep):
    """Return the MBID of the top MusicBrainz artist search hit, or None."""
    sleep(MUSICBRAINZ_DELAY)
    url = MUSICBRAINZ_API + "/artist?" + urlencode(
        {"query": name, "fmt": "json", "limit": 3}
    )
    data = fetch_json(url, headers)
    artists = data.get("artists") or []
    if not artists:
        return None
    return artists[0].get("id")


def _musicbrainz_rels(mbid, *, fetch_json, headers, sleep):
    """Return the url-rels relations list of a MusicBrainz artist (``[]`` when none)."""
    sleep(MUSICBRAINZ_DELAY)
    url = f"{MUSICBRAINZ_API}/artist/{quote(mbid)}?" + urlencode(
        {"inc": "url-rels", "fmt": "json"}
    )
    data = fetch_json(url, headers)
    return data.get("relations") or []


def scan_rels_for_links(relations):
    """Return ``(youtube_url, soundcloud_url)`` — the first of each in the rels."""
    yt = sc = None
    for rel in relations:
        target = (rel.get("url") or {}).get("resource") or ""
        if not target:
            continue
        low = target.lower()
        if yt is None and "youtube.com" in low:
            yt = target
        if sc is None and "soundcloud.com" in low:
            sc = target
    return yt, sc


# ── method (c): verified YouTube search ───────────────────────────────────────
def _youtube_search(name, api_key, *, fetch_json, headers, sleep):
    """Return the search.list items for a channel query (``[]`` on empty)."""
    sleep(YOUTUBE_DELAY)
    url = YOUTUBE_SEARCH_API + "?" + urlencode(
        {
            "type": "channel", "part": "snippet", "q": name,
            "maxResults": 5, "key": api_key,
        }
    )
    data = fetch_json(url, headers)
    return data.get("items") or []


def verify_search_hits(name, items, min_len=SEARCH_FOLD_MIN_LEN):
    """First search hit whose channel title folds-matches ``name``: ``(cid, title)``.

    The VERIFICATION that turns a raw search into a (still risky) candidate. Returns
    ``(None, None)`` when no hit passes the fold guard.
    """
    for item in items:
        snip = item.get("snippet") or {}
        title = snip.get("channelTitle") or snip.get("title") or ""
        cid = snip.get("channelId") or (item.get("id") or {}).get("channelId")
        if cid and title and fold_match(name, title, min_len):
            return cid, title
    return None, None


# ── cascade ───────────────────────────────────────────────────────────────────
def _blank_result(artist):
    return {
        "artist_id": artist.get("artist_id"),
        "name": (artist.get("name") or "").strip(),
        "tier": artist.get("tier"),
        "method": "none",
        "yt_channel_id": "",
        "yt_channel_title": "",
        "yt_url": "",
        "has_soundcloud": False,
        "sc_ref": "",
        "confidence": "",
    }


def resolve_artist(
    artist,
    *,
    fetch_json=fetch_json,
    api_key=None,
    search_budget_ok=True,
    sleep=time.sleep,
    user_agent=DEFAULT_USER_AGENT,
    fold_min_len=SEARCH_FOLD_MIN_LEN,
):
    """Run the 3-method cascade for one artist.

    Returns ``(result, search_event)`` where ``result`` carries exactly
    :data:`RESULT_FIELDS` and ``search_event`` ∈ {None, "used", "skipped_no_key",
    "skipped_budget"} lets the driver keep an honest quota tally. Any exception is
    caught -> method="error" (the run never crashes on one artist).
    """
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    result = _blank_result(artist)
    name = result["name"]
    search_event = None
    if not name:
        return result, search_event

    try:
        # (a) Wikidata ----------------------------------------------------------
        qid, _label = _wikidata_search(
            name, fetch_json=fetch_json, headers=headers, sleep=sleep
        )
        claims = {}
        if qid:
            claims = _wikidata_claims(
                qid, fetch_json=fetch_json, headers=headers, sleep=sleep
            )
            sc_id = _claim_string(claims, "P3040")
            if sc_id:
                result["has_soundcloud"] = True
                result["sc_ref"] = f"https://soundcloud.com/{sc_id}"
            channel_id = _claim_string(claims, "P2397")
            if channel_id:
                result["method"] = "wikidata"
                result["confidence"] = "high"
                result["yt_channel_id"] = channel_id
                result["yt_url"] = youtube_url_from_ref("channel_id", channel_id)
                return result, search_event

        # (b) MusicBrainz -------------------------------------------------------
        mbid = _claim_string(claims, "P434") if claims else None
        if not mbid:
            mbid = _musicbrainz_search(
                name, fetch_json=fetch_json, headers=headers, sleep=sleep
            )
        if mbid:
            rels = _musicbrainz_rels(
                mbid, fetch_json=fetch_json, headers=headers, sleep=sleep
            )
            yt_url, sc_url = scan_rels_for_links(rels)
            if sc_url and not result["has_soundcloud"]:
                result["has_soundcloud"] = True
                result["sc_ref"] = sc_url
            ref = parse_youtube_ref(yt_url) if yt_url else None
            if ref:
                kind, val = ref
                result["method"] = "musicbrainz"
                result["confidence"] = "high"
                result["yt_channel_id"] = val
                result["yt_url"] = youtube_url_from_ref(kind, val)
                return result, search_event

        # (c) verified YouTube search ------------------------------------------
        if not api_key:
            search_event = "skipped_no_key"
        elif not search_budget_ok:
            search_event = "skipped_budget"
        else:
            search_event = "used"
            items = _youtube_search(
                name, api_key, fetch_json=fetch_json, headers=headers, sleep=sleep
            )
            cid, title = verify_search_hits(name, items, fold_min_len)
            if cid:
                result["method"] = "search"
                result["confidence"] = "NEEDS_VERIFY"
                result["yt_channel_id"] = cid
                result["yt_channel_title"] = title
                result["yt_url"] = youtube_url_from_ref("channel_id", cid)
    except Exception as exc:  # noqa: BLE001 — per-artist isolation, never crash the run
        result["method"] = "error"
        print(f"[resolve] error on {name!r}: {exc}", file=sys.stderr, flush=True)
    return result, search_event


# ── input reading ─────────────────────────────────────────────────────────────
def read_artists(path):
    """Yield artist dicts from the NDJSON sample.

    One JSON object per line; ``name`` required (others optional). Blank lines,
    invalid JSON, non-objects and name-less objects are skipped.
    """
    with open(path, "rt", encoding="utf-8") as f:
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
            name = (obj.get("name") or "").strip()
            if not name:
                continue
            yield {
                "artist_id": obj.get("artist_id"),
                "name": name,
                "tier": obj.get("tier"),
                "nb_sets": obj.get("nb_sets"),
                "nb_lib": obj.get("nb_lib"),
            }


# ── driver ────────────────────────────────────────────────────────────────────
def run_gate(
    artists,
    *,
    fetch_json=fetch_json,
    api_key=None,
    max_search=DEFAULT_MAX_SEARCH,
    sleep=time.sleep,
    user_agent=DEFAULT_USER_AGENT,
    log=None,
):
    """Resolve every artist, tracking the YouTube search budget.

    Returns ``(results, stats)``. ``stats`` counts searches used / skipped-for-budget
    / skipped-for-no-key so the summary can report the quota story WITHOUT silent
    truncation (a budget-capped artist is logged, never quietly dropped).
    """
    results = []
    searches_used = 0
    skipped_budget = 0
    skipped_no_key = 0
    for i, artist in enumerate(artists):
        budget_ok = searches_used < max_search
        result, event = resolve_artist(
            artist,
            fetch_json=fetch_json,
            api_key=api_key,
            search_budget_ok=budget_ok,
            sleep=sleep,
            user_agent=user_agent,
        )
        if event == "used":
            searches_used += 1
        elif event == "skipped_budget":
            skipped_budget += 1
            if log:
                log(
                    f"[gate] SEARCH BUDGET SPENT ({max_search}) — search skipped for "
                    f"{artist.get('name')!r} (methods a/b found nothing)"
                )
        elif event == "skipped_no_key":
            skipped_no_key += 1
        results.append(result)
        if log:
            log(
                f"[gate] {i + 1} {result['name']!r} -> {result['method']}"
                f" ({result['confidence'] or '-'})"
            )
    stats = {
        "searches_used": searches_used,
        "searches_skipped_budget": skipped_budget,
        "searches_skipped_no_key": skipped_no_key,
        "max_search": max_search,
    }
    return results, stats


# ── output writers ────────────────────────────────────────────────────────────
def write_results_ndjson(path, results):
    with open(path, "wt", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({k: r[k] for k in RESULT_FIELDS}, ensure_ascii=False))
            f.write("\n")


def summarize(results, stats):
    """Compute the coverage/precision-input figures reported in summary.txt."""
    total = len(results)
    by_method = Counter(r["method"] for r in results)
    found = sum(by_method[m] for m in FOUND_METHODS)
    needs_verify = sum(1 for r in results if r["confidence"] == "NEEDS_VERIFY")
    no_youtube = [r for r in results if r["method"] not in FOUND_METHODS]
    sc_no_yt = sum(1 for r in no_youtube if r["has_soundcloud"])
    has_sc_total = sum(1 for r in results if r["has_soundcloud"])
    return {
        "total": total,
        "by_method": by_method,
        "found": found,
        "needs_verify": needs_verify,
        "no_youtube": len(no_youtube),
        "sc_no_yt": sc_no_yt,
        "has_sc_total": has_sc_total,
        "stats": stats,
    }


def _pct(n, d):
    return (n / d * 100) if d else 0.0


def write_summary(path, results, stats):
    s = summarize(results, stats)
    total = s["total"]
    lines = [
        "# C14.b GATE 🅱 — artist -> YouTube channel resolution (feasibility)",
        "",
        f"Artists measured : {total}",
        "",
        "## Coverage",
        f"- Resolved a YouTube channel (any method) : {s['found']}/{total} "
        f"({_pct(s['found'], total):.1f}%)",
        "",
        "## By method",
    ]
    for method in ("wikidata", "musicbrainz", "search", "none", "error"):
        n = s["by_method"].get(method, 0)
        lines.append(f"- {method:<12}: {n}/{total} ({_pct(n, total):.1f}%)")
    lines += [
        "",
        f"- NEEDS_VERIFY (search fallback, human-confirm) : {s['needs_verify']}",
        "",
        "## SoundCloud (sizes the future SC volet)",
        f"- With SoundCloud reference (any method)  : {s['has_sc_total']}/{total} "
        f"({_pct(s['has_sc_total'], total):.1f}%)",
        f"- No YouTube but SoundCloud present       : {s['sc_no_yt']}/{s['no_youtube']}"
        f" (of the no-YouTube artists)",
        "",
        "## YouTube search budget",
        f"- Searches used            : {stats['searches_used']} "
        f"(cap {stats['max_search']}, 100 quota units each)",
        f"- Skipped (budget spent)   : {stats['searches_skipped_budget']}",
        f"- Skipped (no YOUTUBE_API_KEY) : {stats['searches_skipped_no_key']}",
        "",
        "## Reading this for the GO/NO-GO (build 🅱?)",
        "- Good yield (found/total) AND good precision (see review.csv, marked by the",
        "  operator, then `--score`) -> 🅱 is a real pillar.",
        "- A noisy search fallback (low precision on method=search) -> 🅱 in",
        "  assisted-manual mode: propose, admin confirms (invariant #4).",
        "- The search fallback stays human-confirmed in ALL cases.",
        "",
    ]
    with open(path, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_review_csv(path, results):
    """Write the precision-review sheet: one row per RESOLVED artist, ``correct`` blank.

    Only rows with a ``yt_url`` are worth a ↗-click; method none/error carry none.
    """
    with open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "method", "confidence", "yt_url", "correct"])
        for r in results:
            if r["yt_url"]:
                w.writerow([r["name"], r["method"], r["confidence"], r["yt_url"], ""])


# ── scoring (--score) ─────────────────────────────────────────────────────────
def compute_precision(rows):
    """Precision from marked review rows (``correct`` ∈ {"0","1"}).

    Returns a dict: global precision, per-method precision, marked/unmarked counts and
    the confirmed (found AND correct) count. Rows with a blank/other ``correct`` are
    treated as unmarked and excluded from precision (never silently counted as wrong).
    """
    marked = [r for r in rows if (r.get("correct") or "").strip() in ("0", "1")]
    unmarked = len(rows) - len(marked)
    correct = sum(1 for r in marked if (r.get("correct") or "").strip() == "1")
    by_method = {}
    for r in marked:
        method = (r.get("method") or "").strip() or "?"
        agg = by_method.setdefault(method, {"marked": 0, "correct": 0})
        agg["marked"] += 1
        if (r.get("correct") or "").strip() == "1":
            agg["correct"] += 1
    return {
        "rows": len(rows),
        "marked": len(marked),
        "unmarked": unmarked,
        "correct": correct,
        "precision": _pct(correct, len(marked)),
        "by_method": by_method,
    }


def score_review(path, total=None):
    """Read a marked review.csv, print precision global + per method, return the dict."""
    with open(path, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    res = compute_precision(rows)
    print(f"[score] review rows: {res['rows']}  marked: {res['marked']}  "
          f"unmarked: {res['unmarked']}")
    print(f"[score] GLOBAL precision: {res['correct']}/{res['marked']} "
          f"({res['precision']:.1f}%)")
    print("[score] precision by method:")
    for method in sorted(res["by_method"]):
        agg = res["by_method"][method]
        print(f"          {method:<12}: {agg['correct']}/{agg['marked']} "
              f"({_pct(agg['correct'], agg['marked']):.1f}%)")
    if total:
        print(f"[score] CONFIRMED coverage (found AND correct): {res['correct']}/{total}"
              f" ({_pct(res['correct'], total):.1f}% of the {total} sampled artists)")
    else:
        print(f"[score] CONFIRMED (found AND correct): {res['correct']} "
              f"(of {res['marked']} marked resolved rows; pass --total N for a "
              f"coverage % over the whole sample)")
    return res


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "input", nargs="?", help="NDJSON sample of artists ({name, artist_id, tier…})"
    )
    p.add_argument("--out", default="./gate_out", help="output directory")
    p.add_argument(
        "--max-search", type=int, default=DEFAULT_MAX_SEARCH,
        help="max YouTube searches (100 quota units each); the rest are logged skipped",
    )
    p.add_argument(
        "--limit", type=int, default=0, help="cap the number of artists processed (0=all)"
    )
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    p.add_argument(
        "--score", metavar="REVIEW_CSV",
        help="re-read a marked review.csv and print precision global + per method",
    )
    p.add_argument(
        "--total", type=int, default=0,
        help="with --score: sample size, to express confirmed coverage as a %%",
    )
    args = p.parse_args(argv)

    if args.score:
        score_review(args.score, total=args.total or None)
        return 0

    if not args.input:
        p.error("an input NDJSON of artists is required (or use --score)")

    api_key = os.environ.get("YOUTUBE_API_KEY") or None
    if not api_key:
        print(
            "[gate] WARNING: YOUTUBE_API_KEY not set — method (c) verified search is "
            "SKIPPED for every artist (coverage will read low; that is expected).",
            file=sys.stderr, flush=True,
        )

    artists = list(read_artists(args.input))
    if args.limit and args.limit > 0:
        artists = artists[: args.limit]

    os.makedirs(args.out, exist_ok=True)

    def log(msg):
        print(msg, flush=True)

    results, stats = run_gate(
        artists,
        fetch_json=fetch_json,
        api_key=api_key,
        max_search=args.max_search,
        sleep=time.sleep,
        user_agent=args.user_agent,
        log=log,
    )

    results_path = os.path.join(args.out, "results.ndjson")
    summary_path = os.path.join(args.out, "summary.txt")
    review_path = os.path.join(args.out, "review.csv")
    write_results_ndjson(results_path, results)
    write_summary(summary_path, results, stats)
    write_review_csv(review_path, results)

    s = summarize(results, stats)
    print(
        f"[gate] artists={s['total']} resolved={s['found']} "
        f"({_pct(s['found'], s['total']):.1f}%) needs_verify={s['needs_verify']} "
        f"searches_used={stats['searches_used']}",
        flush=True,
    )
    print(f"[gate] wrote: {results_path}", flush=True)
    print(f"[gate] wrote: {summary_path}", flush=True)
    print(f"[gate] wrote: {review_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
