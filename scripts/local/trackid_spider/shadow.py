"""Shadow-hydration: fetch TrackID set tracklists and MATCH them against a
read-only snapshot of the prod catalog — WITHOUT creating any catalog row,
without any Deezer/Beatport/embedding call. Pre-flight benchmark for C12.

Cost model (why this is cheap): full hydration is three stages we always ran as
one block — (1) fetch the detail tracklist from trackid.net, (2) create catalog
rows + match, (3) enrich (Beatport/Deezer) + embed. Only stage 3 is expensive
(rate-limited external APIs, Essentia/EffNet CPU, autovacuum churn). This tool
does stage 1 + a READ-ONLY variant of stage 2 into the local SQLite staging, so
we learn each set's real contents, its net-new count and its relevance BEFORE any
prod write — the exact numbers the C12 "estimation net-new" gate needs.

Match parity: the prod resolver (server/workers/db.py bulk_get_or_create_catalog)
dedups on ISRC first, then normalized_key. The TrackID detail payload carries no
ISRC on a detection track, so we match on normalized_key alone — exactly what prod
does when ISRC is absent, so the measured match rate is self-consistent and, if
anything, slightly CONSERVATIVE (prod would also catch a few ISRC matches → real
net-new is <= what we report).

normalize / make_normalized_key / is_id_track below are byte-faithful replicas of
  server/api/utils.py            (normalize, make_normalized_key)
  server/api/trackid/parsing.py  (is_id_track)
  server/api/trackid/client.py   (merge_tracklist)
Keep them in sync if the prod versions change (they are the identity key).

Standalone, no server package, no prod connection. Run:  python shadow.py <cmd> --help
"""

import argparse
import gzip
import json
import re
import sqlite3
import sys
import time
import unicodedata

import httpx

BASE_URL = "https://trackid.net/api/public"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://trackid.net",
    "Referer": "https://trackid.net/",
}
RATE_LIMIT = 1.1  # seconds between requests (politeness, matches the spider)
TIMEOUT = 15.0

_ID_MARKERS = {"id", "id - id", "?", "??", "unknown", ""}


# --- prod-faithful normalization (see module docstring) --------------------
def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"\bft\.", "ft", s)
    s = re.sub(r"\bfeat\.", "feat", s)
    s = unicodedata.normalize("NFC", s)
    return s


def make_normalized_key(title: str, artist: str | None) -> str:
    return normalize(title) + " - " + normalize(artist or "")


def is_id_track(title: str | None, artist: str | None) -> bool:
    t = (title or "").strip().lower()
    a = (artist or "").strip().lower()
    if t in _ID_MARKERS and a in _ID_MARKERS:
        return True
    if t in _ID_MARKERS and not a:
        return True
    if not t:
        return True
    return False


def merge_tracklist(detail: dict) -> list[dict]:
    """Merge all detectionProcesses, dedup on musicTrackId (keep first seen)."""
    seen = {}
    for process in detail.get("detectionProcesses") or []:
        for track in process.get("detectionProcessMusicTracks") or []:
            mtid = track.get("musicTrackId")
            if mtid is None:
                continue
            seen.setdefault(mtid, track)
    return list(seen.values())


# --- staging store (extends the spider's staging.db) -----------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS set_detail (
    trackid_id   INTEGER PRIMARY KEY,
    slug         TEXT,
    fetched_at   TEXT,
    http_status  INTEGER,          -- 200 ok, else HTTP code, -1 network/parse
    error        TEXT,
    n_tracks     INTEGER,          -- merged tracklist size
    n_id         INTEGER,          -- is_id (unidentified) count
    n_identified INTEGER           -- n_tracks - n_id
);
CREATE TABLE IF NOT EXISTS tracklist (
    trackid_id   INTEGER,
    position     INTEGER,
    mtid         INTEGER,
    raw_title    TEXT,
    raw_artist   TEXT,
    is_id        INTEGER,
    norm_key     TEXT,
    matched      INTEGER,          -- 0/1, NULL until match phase
    artist_known INTEGER,          -- 0/1, NULL until match phase
    PRIMARY KEY (trackid_id, position)
);
CREATE INDEX IF NOT EXISTS ix_tracklist_normkey ON tracklist(norm_key);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _eligible_where(include_deleted: bool, min_hit_rate: float) -> str:
    clauses = ["track_count > 0"]
    if not include_deleted:
        clauses.append("is_deleted = 0")
    if min_hit_rate > 0:
        clauses.append(f"track_hit_rate >= {min_hit_rate}")
    return " AND ".join(clauses)


def sample_ids(conn, n, include_deleted, min_hit_rate):
    """Deterministic uniform sample of ~n eligible sets via modulus on trackid_id.

    Uniform over the id space, stable across runs (no RNG), and picks the SAME
    sets when resumed — so a fetch can be interrupted and continued.
    """
    where = _eligible_where(include_deleted, min_hit_rate)
    total = conn.execute(
        f"SELECT COUNT(*) c FROM trackid_index_staging WHERE {where}"
    ).fetchone()["c"]
    if total == 0:
        return []
    modulus = max(1, total // n)
    rows = conn.execute(
        f"SELECT trackid_id, slug FROM trackid_index_staging "
        f"WHERE {where} AND (trackid_id % {modulus}) = 0 ORDER BY trackid_id"
    ).fetchall()
    return [(r["trackid_id"], r["slug"]) for r in rows]


# --- fetch phase -----------------------------------------------------------
def fetch(db_path, n, include_deleted, min_hit_rate, limit, verbose=True):
    conn = connect(db_path)
    targets = sample_ids(conn, n, include_deleted, min_hit_rate)
    done = {r["trackid_id"] for r in conn.execute("SELECT trackid_id FROM set_detail")}
    todo = [(tid, slug) for tid, slug in targets if tid not in done]
    if limit:
        todo = todo[:limit]
    if verbose:
        print(
            f"[fetch] sample={len(targets)} already_done={len(targets) - len(todo) if not limit else 'n/a'} "
            f"to_fetch={len(todo)}  (~{len(todo) * RATE_LIMIT / 60:.0f} min)",
            flush=True,
        )
    ok = err = 0
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        last = 0.0
        for i, (tid, slug) in enumerate(todo, 1):
            elapsed = time.monotonic() - last
            if elapsed < RATE_LIMIT:
                time.sleep(RATE_LIMIT - elapsed)
            last = time.monotonic()
            try:
                resp = client.get(f"{BASE_URL}/audiostreams/{slug}")
                status = resp.status_code
                resp.raise_for_status()
                detail = resp.json().get("result", {}) or {}
                _store_detail(conn, tid, slug, status, None, detail)
                ok += 1
            except httpx.HTTPStatusError as e:
                _store_detail(conn, tid, slug, e.response.status_code, str(e), None)
                err += 1
            except Exception as e:  # network / json / parse
                _store_detail(conn, tid, slug, -1, str(e), None)
                err += 1
            if verbose and i % 100 == 0:
                print(f"  {i}/{len(todo)}  ok={ok} err={err}", flush=True)
    conn.commit()
    conn.close()
    if verbose:
        print(f"[fetch] done  ok={ok} err={err}", flush=True)
    return ok, err


def _store_detail(conn, tid, slug, status, error, detail):
    if detail is None:
        conn.execute(
            "INSERT OR REPLACE INTO set_detail"
            "(trackid_id, slug, fetched_at, http_status, error, n_tracks, n_id, n_identified)"
            " VALUES (?,?,?,?,?,0,0,0)",
            (tid, slug, _now(), status, error),
        )
        return
    merged = merge_tracklist(detail)
    n_id = 0
    rows = []
    for pos, tr in enumerate(merged, 1):
        title, artist = tr.get("title"), tr.get("artist")
        idflag = 1 if is_id_track(title, artist) else 0
        n_id += idflag
        nk = None if idflag else make_normalized_key(title, artist)
        rows.append(
            (tid, pos, tr.get("musicTrackId"), title, artist, idflag, nk)
        )
    conn.execute("DELETE FROM tracklist WHERE trackid_id=?", (tid,))
    conn.executemany(
        "INSERT INTO tracklist"
        "(trackid_id, position, mtid, raw_title, raw_artist, is_id, norm_key)"
        " VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO set_detail"
        "(trackid_id, slug, fetched_at, http_status, error, n_tracks, n_id, n_identified)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (tid, slug, _now(), status, None, len(rows), n_id, len(rows) - n_id),
    )


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- match phase (read-only against prod snapshots) ------------------------
def _load_lines(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return {line.rstrip("\n") for line in f if line.strip()}


def match(db_path, catalog_path, artists_path, verbose=True):
    conn = connect(db_path)
    catalog = _load_lines(catalog_path)
    artists = _load_lines(artists_path)
    if verbose:
        print(f"[match] catalog_keys={len(catalog)} artist_names={len(artists)}", flush=True)
    updates = []
    cur = conn.execute(
        "SELECT rowid, norm_key, raw_artist, is_id FROM tracklist"
    )
    for r in cur:
        if r["is_id"]:
            updates.append((0, 0, r["rowid"]))
            continue
        matched = 1 if r["norm_key"] in catalog else 0
        known = 1 if normalize(r["raw_artist"] or "") in artists else 0
        updates.append((matched, known, r["rowid"]))
    conn.executemany(
        "UPDATE tracklist SET matched=?, artist_known=? WHERE rowid=?", updates
    )
    conn.commit()
    conn.close()
    if verbose:
        print(f"[match] updated {len(updates)} track rows", flush=True)


# --- report phase ----------------------------------------------------------
def report(db_path, out_prefix=None):
    conn = connect(db_path)
    d = {}
    sd = conn.execute(
        "SELECT COUNT(*) sets, SUM(n_tracks) tracks, SUM(n_id) idtracks, "
        "SUM(n_identified) identified FROM set_detail WHERE http_status=200"
    ).fetchone()
    d["sets_fetched"] = sd["sets"] or 0
    d["fetch_errors"] = conn.execute(
        "SELECT COUNT(*) c FROM set_detail WHERE http_status<>200"
    ).fetchone()["c"]
    d["tracks_total"] = sd["tracks"] or 0
    d["tracks_id"] = sd["idtracks"] or 0
    d["tracks_identified"] = sd["identified"] or 0

    # instance-level (each (set,track) occurrence), identified only
    inst = conn.execute(
        "SELECT COUNT(*) n, SUM(matched) m, SUM(artist_known) k "
        "FROM tracklist WHERE is_id=0 AND matched IS NOT NULL"
    ).fetchone()
    n_inst = inst["n"] or 0
    d["identified_instances"] = n_inst
    d["instances_matched"] = inst["m"] or 0
    d["instances_netnew"] = n_inst - (inst["m"] or 0)
    d["instance_netnew_rate"] = round((n_inst - (inst["m"] or 0)) / n_inst, 4) if n_inst else None

    # distinct-key level (dedup within the sample — the real net-new question)
    distinct = conn.execute(
        "SELECT norm_key, MAX(matched) m, MAX(artist_known) k "
        "FROM tracklist WHERE is_id=0 AND norm_key IS NOT NULL AND matched IS NOT NULL "
        "GROUP BY norm_key"
    ).fetchall()
    d["distinct_keys"] = len(distinct)
    d["distinct_matched"] = sum(1 for r in distinct if r["m"])
    d["distinct_netnew"] = sum(1 for r in distinct if not r["m"])
    netnew = [r for r in distinct if not r["m"]]
    d["distinct_netnew_artist_known"] = sum(1 for r in netnew if r["k"])
    d["distinct_netnew_rate"] = round(len(netnew) / len(distinct), 4) if distinct else None
    d["distinct_netnew_artist_known_rate"] = (
        round(d["distinct_netnew_artist_known"] / len(netnew), 4) if netnew else None
    )

    # population extrapolation context (distinct grows SUBLINEARLY → upper bound)
    where = _eligible_where(include_deleted=False, min_hit_rate=0.0)
    pop = conn.execute(
        f"SELECT COUNT(*) c FROM trackid_index_staging WHERE {where}"
    ).fetchone()["c"]
    d["eligible_population"] = pop
    d["sample_coverage"] = round(d["sets_fetched"] / pop, 5) if pop else None

    # lift proxy: net-new value by track_hit_rate decile of the source set
    d["by_hitrate_decile"] = _decile_table(conn)
    # channel yield: top channels by identified tracks in the sample
    d["top_channels_by_yield"] = _channel_table(conn)

    out = json.dumps(d, indent=2, ensure_ascii=False)
    print(out)
    if out_prefix:
        with open(f"{out_prefix}.json", "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\n[report] written to {out_prefix}.json", flush=True)
    conn.close()
    return d


def _decile_table(conn):
    rows = conn.execute(
        "SELECT s.track_hit_rate hr, t.matched m, t.is_id idf "
        "FROM tracklist t JOIN trackid_index_staging s ON s.trackid_id=t.trackid_id "
        "WHERE t.matched IS NOT NULL AND t.is_id=0"
    ).fetchall()
    buckets = {}
    for r in rows:
        b = min(9, int((r["hr"] or 0) * 10))
        e = buckets.setdefault(b, {"identified": 0, "matched": 0})
        e["identified"] += 1
        e["matched"] += r["m"] or 0
    out = []
    for b in sorted(buckets):
        e = buckets[b]
        out.append(
            {
                "hit_rate_bucket": f"{b/10:.1f}-{(b+1)/10:.1f}",
                "identified": e["identified"],
                "netnew": e["identified"] - e["matched"],
                "netnew_rate": round((e["identified"] - e["matched"]) / e["identified"], 3)
                if e["identified"]
                else None,
            }
        )
    return out


def _channel_table(conn, limit=20):
    rows = conn.execute(
        "SELECT s.channel ch, COUNT(*) identified, SUM(t.matched) matched "
        "FROM tracklist t JOIN trackid_index_staging s ON s.trackid_id=t.trackid_id "
        "WHERE t.matched IS NOT NULL AND t.is_id=0 "
        "GROUP BY s.channel ORDER BY identified DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "channel": r["ch"],
            "identified": r["identified"],
            "netnew": r["identified"] - (r["matched"] or 0),
            "netnew_rate": round((r["identified"] - (r["matched"] or 0)) / r["identified"], 3)
            if r["identified"]
            else None,
        }
        for r in rows
    ]


# --- CLI -------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="fetch tracklists for a sample of sets")
    pf.add_argument("--db", default="data/staging.db")
    pf.add_argument("--sample", type=int, default=5000, help="approx sets to sample")
    pf.add_argument("--include-deleted", action="store_true")
    pf.add_argument("--min-hit-rate", type=float, default=0.0)
    pf.add_argument("--limit", type=int, default=0, help="cap this run (resume-friendly)")

    pm = sub.add_parser("match", help="match fetched tracks vs prod snapshots")
    pm.add_argument("--db", default="data/staging.db")
    pm.add_argument("--catalog", default="data/catalog_nk.txt.gz")
    pm.add_argument("--artists", default="data/artists_nn.txt.gz")

    pr = sub.add_parser("report", help="aggregate + emit metrics")
    pr.add_argument("--db", default="data/staging.db")
    pr.add_argument("--out", default=None, help="output prefix (writes <out>.json)")

    args = p.parse_args(argv)
    if args.cmd == "fetch":
        fetch(args.db, args.sample, args.include_deleted, args.min_hit_rate, args.limit or 0)
    elif args.cmd == "match":
        match(args.db, args.catalog, args.artists)
    elif args.cmd == "report":
        report(args.db, args.out)


if __name__ == "__main__":
    sys.exit(main())
