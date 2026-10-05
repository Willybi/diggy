#!/usr/bin/env python
"""C14.a Phase 2 — discography-backfill BENCHMARK orchestrator. Runs on the HOST (PC), stdlib only.

READ-ONLY GATE for the C14.a Phase 2 discography backfill. Before building the real
backfill tool + draining Deezer over a whole cohort, this measures — on a stratified
sample of ~40 artists — the two numbers the decision hinges on:

  * **NET-NEW per artist, by tier** — of an artist's full Deezer discography, how many
    tracks are NOT already in our catalog (dedup on the EXACT ingestion identity
    ``normalized_key`` = ``normalize(title) + " - " + normalize(artist)``, plus, with
    ``--with-isrc``, ``isrc``). This decides where to cut the backfill cohort (couper là
    où le net-new reste digeste).
  * **COST** — requests per artist (~1 + nb albums) → Deezer fetch time at the
    residential floor; and the Beatport enrichment inflow the net-new would create
    (capacity ~9 900/day, the AV10 throttle risk) + the EffNet embedding CPU it implies.

Nothing is written anywhere — not on prod (pure SELECT/COPY reads), not on Deezer (only
GETs). There is deliberately NO ``--apply``: a benchmark has nothing to apply. The
compute runs LOCALLY (residential IP) because mass Deezer is forbidden on the VPS
(AV10); the fetch reuses the PROD server image so ``make_normalized_key`` + the Deezer
HTTP/rate-limit stack are byte-identical to ingestion. Moule of ``worker/set_artist_backfill/``
(same SSH/psql channel, same container-driven compute) minus the write path.

The four steps (orchestrated here):

  1. SAMPLE — read-only ``COPY`` of a STRATIFIED artist sample through the documented
     SSH/psql channel: mutually-exclusive strata by descending depth
     (``a_lib`` → ``b_sets12m`` ≥5 reliable DJ sets/12m → ``c_catalog`` ≥10 catalog
     tracks → ``d_traine`` fetchable long tail), ``--per-tier`` each (``ORDER BY
     random()``, ``--seed`` for reproducibility), only artists with a real
     ``deezer_id`` (``<> 'NOT_FOUND'``). → ``data/sample.csv``.
  2. INDEX  — read-only ``COPY`` of the catalog IDENTITY index
     (``normalized_key,isrc`` of every row) → two Python sets. Cached to
     ``data/catalog_index.csv`` (a big one-off pull; ``--reuse`` skips re-pulling it).
  3. FETCH  — ``docker run`` the driver (``fetch_driver.py``) in the prod server image:
     for each sampled artist it walks ``/artist/{id}/albums`` (paginated) →
     ``/album/{id}`` tracklists, computes the ingestion key per track, dedups within
     the artist, and emits ``data/discography.ndjson`` (one record per artist, with a
     request count). ``--with-isrc`` additionally fetches ``/track/{id}`` per track.
  4. REPORT — classify every track in-base vs net-new against the index, aggregate per
     tier (per-artist median/mean net-new, requests, tracks; % already in base), and
     project the Deezer fetch time + Beatport inflow + embedding CPU for candidate
     cohort sizes. Prints a report and writes ``data/benchmark_report.json``.

>>> Nothing here mutates prod or Deezer. The reads are heavy-ish (one full catalog
    index COPY) — run it in the Beatport/Deezer off-hours, but no dump is needed. <<<

Usage (from the repo root, or anywhere):
    python worker/discography_backfill/benchmark_discography.py                 # full run, ~40 artists
    python worker/discography_backfill/benchmark_discography.py --per-tier 15   # ~60 artists
    python worker/discography_backfill/benchmark_discography.py --limit 8 --with-isrc  # small isrc calibration
    python worker/discography_backfill/benchmark_discography.py --reuse         # re-report cached fetch (no pull/fetch)
"""

import argparse
import csv
import functools
import io
import json
import os
import statistics
import subprocess
import sys

# progress + report must stay ordered even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path: -q keeps the COPY stream clean (CSV only on stdout).
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)

# Prod server image (context ./server via server/Dockerfile): carries api/ (utils) +
# workers/ + curl_cffi at /app. The package image is a thin FROM of it; the driver is
# bind-mounted at /work at run time.
SERVER_IMAGE = "diggy-discography-server"
IMAGE = "diggy-discography-backfill"

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
SERVER_DOCKERFILE = os.path.join(SERVER_DIR, "Dockerfile")
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")

SAMPLE_FIELDS = ["tier", "artist_id", "name", "deezer_id", "set_count",
                 "catalog_track_count", "in_lib"]
TIER_ORDER = ["a_lib", "b_sets12m", "c_catalog", "d_traine"]

# Residential-IP Deezer pace (req/s), passed to the container as DEEZER_RATE — the C9
# lesson (~1 rps lifts the residential rate-limit). NEVER raise the PROD rate.
DEFAULT_DEEZER_RATE = 1.0
DEFAULT_DEEZER_CONCURRENCY = 5

# Downstream cost constants (documented, overridable on the CLI):
BEATPORT_DAILY_CAPACITY = 9900   # runs/day, MON/sanity-check 2026-07-31
EMBED_CPU_SECONDS = 8.0          # EffNet ~8 CPU-s/track (C9)


def _configure_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def safe_print(text=""):
    """Print without ever raising on a narrow console encoding (artist names carry accents)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(text).encode(enc, errors="replace").decode(enc, errors="replace"))


# ─────────────────────────── prod queries ───────────────────────────

def build_sample_query(per_tier=10, seed=None, traine_strict=False):
    """Stratified artist sample SQL (COPY ... TO STDOUT csv).

    Mutually-exclusive strata by descending depth (CASE priority a>b>c>d), matching the
    cohort's Signal-3 predicate for the set count (``role='dj'``, roots-only,
    non-virtual, ``unreliable IS NOT TRUE``, ``coalesce(event_date, played_date)``
    within 365 days). Only artists with a usable ``deezer_id``. ``per_tier`` rows per
    stratum via ``ROW_NUMBER() OVER (PARTITION BY tier ORDER BY <draw>)``. The draw is
    ``random()`` by default, or — when ``seed`` is given — a DETERMINISTIC pure-SQL
    shuffle ``md5(seed || '|' || artist_id)`` (reproducible per seed, uniform because
    md5 is). A pure-SQL order deliberately AVOIDS a separate ``SELECT setseed(...)``
    statement, whose result rows would pollute the COPY stream on stdout. ``traine_strict``
    tightens ``d_traine`` to genuinely-low-signal artists (no sets, <3 catalog, not lib).
    """
    if seed is None:
        order_expr = "random()"
    else:
        salt = str(seed).replace("'", "''")
        order_expr = f"md5('{salt}' || '|' || artist_id::text)"
    traine_filter = (
        "  WHERE tier <> 'd_traine'\n"
        "     OR (set_count = 0 AND catalog_track_count < 3 AND NOT in_lib)\n"
        if traine_strict else ""
    )
    return (
        "COPY (\n"
        "WITH sets12 AS (\n"
        "  SELECT sa.artist_id, COUNT(DISTINCT s.id) AS set_count\n"
        "  FROM set_artists sa JOIN sets s ON s.id = sa.set_id\n"
        "  WHERE sa.role = 'dj' AND s.parent_set_id IS NULL AND s.is_virtual = false\n"
        "    AND s.unreliable IS NOT TRUE\n"
        "    AND COALESCE(s.event_date, s.played_date) >= (CURRENT_DATE - INTERVAL '365 days')\n"
        "  GROUP BY sa.artist_id\n"
        "),\n"
        "cat AS (\n"
        "  SELECT artist_id, COUNT(DISTINCT catalog_id) AS catalog_track_count\n"
        "  FROM catalog_artists GROUP BY artist_id\n"
        "),\n"
        "lib AS (\n"
        "  SELECT ca.artist_id, COUNT(DISTINCT ut.catalog_id) AS lib_count\n"
        "  FROM catalog_artists ca JOIN user_tracks ut ON ut.catalog_id = ca.catalog_id\n"
        "  GROUP BY ca.artist_id\n"
        "),\n"
        "base AS (\n"
        "  SELECT a.id AS artist_id, a.name, a.deezer_id,\n"
        "         COALESCE(s.set_count, 0) AS set_count,\n"
        "         COALESCE(c.catalog_track_count, 0) AS catalog_track_count,\n"
        "         (COALESCE(l.lib_count, 0) > 0) AS in_lib\n"
        "  FROM artists a\n"
        "  LEFT JOIN sets12 s ON s.artist_id = a.id\n"
        "  LEFT JOIN cat c ON c.artist_id = a.id\n"
        "  LEFT JOIN lib l ON l.artist_id = a.id\n"
        "  WHERE a.deezer_id IS NOT NULL AND a.deezer_id <> 'NOT_FOUND'\n"
        "),\n"
        "tagged AS (\n"
        "  SELECT *, CASE\n"
        "      WHEN in_lib THEN 'a_lib'\n"
        "      WHEN set_count >= 5 THEN 'b_sets12m'\n"
        "      WHEN catalog_track_count >= 10 THEN 'c_catalog'\n"
        "      ELSE 'd_traine' END AS tier\n"
        "  FROM base\n"
        "),\n"
        "filtered AS (\n"
        "  SELECT * FROM tagged\n"
        f"{traine_filter}"
        "),\n"
        "sampled AS (\n"
        f"  SELECT *, ROW_NUMBER() OVER (PARTITION BY tier ORDER BY {order_expr}) AS rn\n"
        "  FROM filtered\n"
        ")\n"
        "SELECT tier, artist_id, name, deezer_id, set_count, catalog_track_count, in_lib\n"
        f"FROM sampled WHERE rn <= {int(per_tier)}\n"
        "ORDER BY tier, rn\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def build_catalog_index_query():
    """COPY of the catalog identity index (``normalized_key,isrc``) for offline dedup."""
    return (
        "COPY (\n"
        "  SELECT normalized_key, coalesce(isrc, '') AS isrc FROM catalog\n"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


# ─────────────────────────── pure helpers ───────────────────────────

def parse_rows(csv_text):
    return list(csv.DictReader(io.StringIO(csv_text)))


def load_identity_index(csv_text):
    """``(keyset, isrcset)`` from the catalog-index CSV. Empty isrc cells are dropped."""
    keys = set()
    isrcs = set()
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        k = row.get("normalized_key")
        if k:
            keys.add(k)
        i = (row.get("isrc") or "").strip()
        if i:
            isrcs.add(i)
    return keys, isrcs


def classify_record(record, keyset, isrcset, use_isrc):
    """Per-artist net-new counts for one discography record.

    A track is IN BASE iff its ``key`` is in ``keyset`` OR (``use_isrc`` and its ``isrc``
    is in ``isrcset``) — the exact ingestion identity. Returns a dict with
    ``distinct`` / ``in_base`` / ``net_new`` / ``isrc_only`` (in-base ONLY via isrc, not
    key = the duplication the cheap key-only backfill would create).
    """
    in_base = net_new = isrc_only = 0
    for t in record.get("tracks", []):
        k = t.get("key")
        k_in = bool(k) and k in keyset
        isrc = (t.get("isrc") or "").strip()
        i_in = bool(use_isrc and isrc and isrc in isrcset)
        if k_in or i_in:
            in_base += 1
            if not k_in and i_in:
                isrc_only += 1
        else:
            net_new += 1
    return {
        "distinct": len(record.get("tracks", [])),
        "in_base": in_base,
        "net_new": net_new,
        "isrc_only": isrc_only,
    }


def _stats(values):
    """``{n, sum, mean, median, p90, max}`` for a list of numbers (zeros for empty)."""
    if not values:
        return {"n": 0, "sum": 0, "mean": 0.0, "median": 0.0, "p90": 0, "max": 0}
    s = sorted(values)
    p90_idx = min(len(s) - 1, int(round(0.9 * (len(s) - 1))))
    return {
        "n": len(s),
        "sum": sum(s),
        "mean": round(statistics.mean(s), 1),
        "median": round(statistics.median(s), 1),
        "p90": s[p90_idx],
        "max": s[-1],
    }


def aggregate(records, keyset, isrcset, use_isrc):
    """Per-tier + overall aggregation of the discography records.

    Returns ``{"tiers": {tier: {...}}, "overall": {...}}``. Each block carries per-artist
    ``requests`` / ``distinct`` / ``net_new`` stats, the pooled ``pct_in_base``, the
    ``isrc_only`` total (only meaningful with ``--with-isrc``), and the artist/error
    counts. Records with a fatal ``error`` (no album list) are counted but excluded from
    the per-artist rate stats (they have no discography, not a zero one).
    """
    def block(recs):
        # per-artist series over artists that produced a discography (a fatal-error
        # artist has NO discography, not a zero one → excluded from the rate stats but
        # still counted in artists_sampled / artists_errored).
        producing = [r for r in recs if r.get("tracks")]
        classes = [classify_record(r, keyset, isrcset, use_isrc) for r in producing]
        req = [r.get("n_requests", 0) for r in producing]
        dist = [c["distinct"] for c in classes]
        net = [c["net_new"] for c in classes]
        sum_distinct = sum(dist)
        sum_in_base = sum(c["in_base"] for c in classes)
        return {
            "artists_sampled": len(recs),
            "artists_producing": len(producing),
            "artists_errored": sum(1 for r in recs if r.get("error")),
            "requests_per_artist": _stats(req),
            "tracks_per_artist": _stats(dist),
            "net_new_per_artist": _stats(net),
            "sum_distinct": sum_distinct,
            "sum_in_base": sum_in_base,
            "sum_net_new": sum(net),
            "pct_in_base": round(100.0 * sum_in_base / sum_distinct, 1) if sum_distinct else 0.0,
            "isrc_only_total": sum(c["isrc_only"] for c in classes),
        }

    tiers = {}
    for tier in TIER_ORDER:
        recs = [r for r in records if r.get("tier") == tier]
        if recs:
            tiers[tier] = block(recs)
    # any unexpected tier label
    for tier in sorted({r.get("tier") for r in records} - set(TIER_ORDER) - {None}):
        tiers[tier] = block([r for r in records if r.get("tier") == tier])
    return {"tiers": tiers, "overall": block(records)}


def project_cohort(median_net_new, median_requests, cohort_size, deezer_rate):
    """Project the cost of backfilling ``cohort_size`` artists at the sampled rates."""
    net_new = median_net_new * cohort_size
    requests = median_requests * cohort_size
    fetch_hours = (requests / deezer_rate / 3600.0) if deezer_rate > 0 else 0.0
    beatport_days = net_new / BEATPORT_DAILY_CAPACITY if BEATPORT_DAILY_CAPACITY else 0.0
    embed_cpu_hours = net_new * EMBED_CPU_SECONDS / 3600.0
    return {
        "cohort_size": cohort_size,
        "projected_net_new": int(round(net_new)),
        "projected_requests": int(round(requests)),
        "deezer_fetch_hours": round(fetch_hours, 1),
        "beatport_drain_days": round(beatport_days, 1),
        "embedding_cpu_hours": round(embed_cpu_hours, 1),
    }


def parse_cohort_arg(spec):
    """``"a_lib=580,b_sets12m=971"`` -> ``{tier: count}`` (ValueError on a bad token)."""
    out = {}
    if not spec:
        return out
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        k, _, v = tok.partition("=")
        out[k.strip()] = int(v)
    return out


# ─────────────────────────── report ───────────────────────────

def format_report(agg, deezer_rate, cohort_sizes, cohort_map, with_isrc):
    """Human-readable report string from an aggregation dict."""
    lines = []
    w = lines.append
    w("=" * 78)
    w("  C14.a Phase 2 — DISCOGRAPHY BACKFILL BENCHMARK")
    w("=" * 78)
    w(f"  identity: normalized_key{' + isrc' if with_isrc else ' only (no isrc — key-only, the cheap path)'}")
    w("")
    hdr = (
        f"  {'tier':<11} {'artists':>8} {'req/art':>9} {'trk/art':>9} "
        f"{'new/art':>9} {'%in-base':>9} {'net-new':>9}"
    )
    w(hdr)
    w("  " + "-" * (len(hdr) - 2))
    for tier in TIER_ORDER + [t for t in agg["tiers"] if t not in TIER_ORDER]:
        b = agg["tiers"].get(tier)
        if not b:
            continue
        w(
            f"  {tier:<11} {b['artists_producing']:>3}/{b['artists_sampled']:<4} "
            f"{b['requests_per_artist']['median']:>9} "
            f"{b['tracks_per_artist']['median']:>9} "
            f"{b['net_new_per_artist']['median']:>9} "
            f"{b['pct_in_base']:>8}% "
            f"{b['sum_net_new']:>9}"
        )
    o = agg["overall"]
    w("  " + "-" * (len(hdr) - 2))
    w(
        f"  {'OVERALL':<11} {o['artists_producing']:>3}/{o['artists_sampled']:<4} "
        f"{o['requests_per_artist']['median']:>9} "
        f"{o['tracks_per_artist']['median']:>9} "
        f"{o['net_new_per_artist']['median']:>9} "
        f"{o['pct_in_base']:>8}% {o['sum_net_new']:>9}"
    )
    if o["artists_errored"]:
        w(f"  ({o['artists_errored']} artist(s) errored — excluded from per-artist rates)")
    if with_isrc:
        w("")
        w(f"  isrc-only in-base (dupes the key-only path would create): "
          f"{o['isrc_only_total']} of {o['sum_in_base']} in-base "
          f"({round(100.0 * o['isrc_only_total'] / o['sum_in_base'], 1) if o['sum_in_base'] else 0.0}%)")

    # ── projections ──
    w("")
    w("  PROJECTIONS (median net-new × cohort, at %.2f rps residential):" % deezer_rate)
    w(f"  Beatport capacity ~{BEATPORT_DAILY_CAPACITY}/day; EffNet ~{EMBED_CPU_SECONDS:.0f} CPU-s/track.")
    w("")
    ph = (
        f"  {'tier':<11} {'cohort':>7} {'net-new':>9} {'requests':>9} "
        f"{'fetch h':>8} {'beatport d':>11} {'embed CPUh':>11}"
    )
    w(ph)
    w("  " + "-" * (len(ph) - 2))
    for tier in TIER_ORDER + [t for t in agg["tiers"] if t not in TIER_ORDER]:
        b = agg["tiers"].get(tier)
        if not b:
            continue
        med_new = b["net_new_per_artist"]["median"]
        med_req = b["requests_per_artist"]["median"]
        sizes = [cohort_map[tier]] if tier in cohort_map else cohort_sizes
        for size in sizes:
            p = project_cohort(med_new, med_req, size, deezer_rate)
            w(
                f"  {tier:<11} {p['cohort_size']:>7} {p['projected_net_new']:>9} "
                f"{p['projected_requests']:>9} {p['deezer_fetch_hours']:>8} "
                f"{p['beatport_drain_days']:>11} {p['embedding_cpu_hours']:>11}"
            )
    if cohort_map:
        tot_new = tot_req = 0
        for tier, size in cohort_map.items():
            b = agg["tiers"].get(tier)
            if not b:
                continue
            tot_new += b["net_new_per_artist"]["median"] * size
            tot_req += b["requests_per_artist"]["median"] * size
        w("  " + "-" * (len(ph) - 2))
        w(f"  {'TOTAL cohort':<19} {int(round(tot_new)):>9} {int(round(tot_req)):>9} "
          f"{round(tot_req / deezer_rate / 3600.0, 1) if deezer_rate else 0:>8} "
          f"{round(tot_new / BEATPORT_DAILY_CAPACITY, 1):>11} "
          f"{round(tot_new * EMBED_CPU_SECONDS / 3600.0, 1):>11}")
    w("=" * 78)
    return "\n".join(lines)


# ─────────────────────────── ssh / docker ───────────────────────────

def run_remote_sql(remote_cmd, sql):
    """Feed ``sql`` to psql on the VPS via ssh stdin; return psql's stdout."""
    proc = subprocess.run(
        ["ssh", SSH_HOST, remote_cmd],
        input=sql, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote psql failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def _docker_build():
    print(f"[fetch] docker build -t {SERVER_IMAGE} (server/Dockerfile) ...")
    subprocess.run(
        ["docker", "build", "-t", SERVER_IMAGE, "-f", SERVER_DOCKERFILE, SERVER_DIR],
        check=True,
    )
    print(f"[fetch] docker build -t {IMAGE} (FROM {SERVER_IMAGE}) ...")
    subprocess.run(
        ["docker", "build", "-t", IMAGE,
         "--build-arg", f"SERVER_IMAGE={SERVER_IMAGE}", PKG_DIR],
        check=True,
    )


def _docker_fetch(workdir, deezer_rate, deezer_concurrency, with_isrc):
    """Run fetch_driver.py in the container over sample.csv → discography.ndjson.

    No Redis in the container: REDIS_URL points at a dead port so the shared Deezer
    window fails open and only the local bucket + the residential floor govern.
    """
    import shutil

    shutil.copy2(
        os.path.join(PKG_DIR, "fetch_driver.py"),
        os.path.join(workdir, "fetch_driver.py"),
    )
    env_flags = [
        "-e", "REDIS_URL=redis://127.0.0.1:1/0",
        "-e", f"DEEZER_RATE={deezer_rate}",
        "-e", f"DEEZER_CONCURRENCY={deezer_concurrency}",
    ]
    cmd = [
        "docker", "run", "--rm", "-v", f"{workdir}:/work", *env_flags, IMAGE,
        "python", "/work/fetch_driver.py",
        "--worklist", "/work/sample.csv", "--out", "/work/discography.ndjson",
    ]
    if with_isrc:
        cmd.append("--with-isrc")
    subprocess.run(cmd, check=True)


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_ndjson(path):
    """Well-formed records from a discography NDJSON blob (skips malformed lines)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("tracks"), list):
                out.append(rec)
    return out


# ─────────────────────────── main ───────────────────────────

def main(args):
    _configure_stdout()
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    sample_path = os.path.join(workdir, "sample.csv")
    index_path = os.path.join(workdir, "catalog_index.csv")
    ndjson_path = os.path.join(workdir, "discography.ndjson")
    report_path = os.path.join(workdir, "benchmark_report.json")

    cohort_sizes = [int(s) for s in args.cohort_sizes.split(",") if s.strip()]
    cohort_map = parse_cohort_arg(args.cohort)

    if not args.reuse:
        # 1. SAMPLE
        per_tier = args.limit or args.per_tier
        print(f"[sample] pulling stratified sample (per_tier={per_tier}, "
              f"seed={args.seed}, traine_strict={args.traine_strict})...")
        sample_csv = run_remote_sql(
            REMOTE_PSQL_PULL,
            build_sample_query(per_tier, args.seed, args.traine_strict),
        )
        sample = parse_rows(sample_csv)
        _write_csv(sample_path, sample, SAMPLE_FIELDS)
        if sample and "tier" not in sample[0]:
            sys.exit(
                "[sample] parsed rows have no 'tier' column — the psql stdout was "
                f"polluted (columns: {list(sample[0].keys())}). Aborting."
            )
        by_tier = {}
        for r in sample:
            by_tier[r.get("tier", "?")] = by_tier.get(r.get("tier", "?"), 0) + 1
        print(f"[sample] {len(sample)} artist(s): " +
              ", ".join(f"{k}={v}" for k, v in sorted(by_tier.items())))
        if not sample:
            sys.exit("[sample] empty — nothing to benchmark")

        # 2. INDEX (cached; --reuse skips this heavy pull)
        if os.path.exists(index_path) and args.reuse_index:
            print(f"[index] reusing cached {index_path}")
        else:
            print("[index] pulling catalog identity index (normalized_key,isrc) — big one-off...")
            index_csv = run_remote_sql(REMOTE_PSQL_PULL, build_catalog_index_query())
            with open(index_path, "w", encoding="utf-8", newline="") as f:
                f.write(index_csv)

        # 3. FETCH
        _docker_build()
        _docker_fetch(workdir, args.deezer_rate, args.deezer_concurrency, args.with_isrc)
        if not os.path.exists(ndjson_path):
            sys.exit(f"[fetch] the container produced no {ndjson_path}")
    else:
        print("[reuse] re-reporting cached sample + index + discography (no pull, no fetch)")
        for p in (index_path, ndjson_path):
            if not os.path.exists(p):
                sys.exit(f"--reuse: missing {p} from a previous run")

    # 4. REPORT
    print("[report] loading catalog identity index...")
    with open(index_path, encoding="utf-8") as f:
        keyset, isrcset = load_identity_index(f.read())
    print(f"[report] index: {len(keyset)} keys, {len(isrcset)} isrcs")
    records = load_ndjson(ndjson_path)
    print(f"[report] {len(records)} artist record(s)")

    agg = aggregate(records, keyset, isrcset, args.with_isrc)
    report = format_report(agg, args.deezer_rate, cohort_sizes, cohort_map, args.with_isrc)
    safe_print("")
    safe_print(report)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "params": {
                    "per_tier": args.limit or args.per_tier,
                    "seed": args.seed,
                    "with_isrc": args.with_isrc,
                    "deezer_rate": args.deezer_rate,
                    "traine_strict": args.traine_strict,
                    "cohort_sizes": cohort_sizes,
                    "cohort_map": cohort_map,
                    "index_keys": len(keyset),
                    "index_isrcs": len(isrcset),
                },
                "aggregate": agg,
            },
            f, ensure_ascii=False, indent=2,
        )
    print(f"\n[report] wrote {report_path}")
    print("READ-ONLY benchmark — nothing was written to prod or Deezer. Review the "
          "net-new-by-tier + projections, then arbitrate the backfill cohort with William.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="C14.a Phase 2 discography-backfill BENCHMARK (read-only gate): "
        "sample artists by tier, fetch their Deezer discography in the prod server "
        "image, classify net-new against the catalog identity, and project the "
        "Deezer/Beatport/embedding cost. Nothing is written to prod or Deezer."
    )
    parser.add_argument("--per-tier", dest="per_tier", type=int, default=10,
                        help="artists sampled per stratum (4 strata → ~4× total; default 10)")
    parser.add_argument("--limit", type=int, default=0,
                        help="alias overriding --per-tier (small calibration runs, e.g. --limit 2 --with-isrc)")
    parser.add_argument("--seed", type=str, default=None,
                        help="salt for a reproducible draw (deterministic md5 shuffle); "
                        "omit for a fresh random sample each run")
    parser.add_argument("--traine-strict", dest="traine_strict", action="store_true",
                        help="tighten d_traine to genuinely-low-signal artists (0 sets, <3 catalog, not lib)")
    parser.add_argument("--with-isrc", dest="with_isrc", action="store_true",
                        help="fetch /track/{id} per track for isrc (EXPENSIVE, +1 req/track) — "
                        "measures the dedup the cheap key-only path misses; use with a small --limit")
    parser.add_argument("--deezer-rate", dest="deezer_rate", type=float,
                        default=DEFAULT_DEEZER_RATE,
                        help=f"residential Deezer pace req/s (DEEZER_RATE, default "
                        f"{DEFAULT_DEEZER_RATE}; the C9 lesson). NEVER raise the PROD rate.")
    parser.add_argument("--deezer-concurrency", dest="deezer_concurrency", type=int,
                        default=DEFAULT_DEEZER_CONCURRENCY,
                        help=f"DEEZER_CONCURRENCY for the container (default {DEFAULT_DEEZER_CONCURRENCY})")
    parser.add_argument("--cohort-sizes", dest="cohort_sizes", default="500,1000,3000",
                        help="comma cohort sizes for the per-tier projection table (default 500,1000,3000)")
    parser.add_argument("--cohort", default="",
                        help="exact per-tier cohort for a TOTAL projection, e.g. "
                        "'a_lib=580,b_sets12m=971' (once you've decided the cut)")
    parser.add_argument("--reuse", action="store_true",
                        help="skip pull+fetch, re-report the cached index + discography.ndjson")
    parser.add_argument("--reuse-index", dest="reuse_index", action="store_true",
                        help="reuse a cached catalog_index.csv (skip only the big index pull)")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR,
                        help="working dir for CSVs + NDJSON + report (default: <package>/data)")
    main(parser.parse_args())
