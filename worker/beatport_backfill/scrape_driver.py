"""L1a — Beatport scrape pass. Runs INSIDE the Docker container (the PROD server image).

Reads a candidates CSV (columns ``id,title,isrc,flat_artist,m2m_artists``) and, for
each row, runs the REAL server search+match — ``workers.enrichment._search_beatport_async``
— which embeds the X3 validation (ISRC-first, remix-aware title + folded-artist gate,
release fallback). It emits ONE NDJSON line per row on the L1b import contract:

    {"catalog_id": <id>, "status": "found",     "bp_track": <normalised dict>}
    {"catalog_id": <id>, "status": "not_found", "bp_track": null}

The scraper NEVER writes to the DB — the WRITE is done on the VPS by the OPS script
``server/api/scripts/import_beatport_matches.py`` (invoked by the host orchestrator
at the end of the pipeline), which reuses ``beatport.enrich.enrich_from_beatport``
verbatim. Zero vendoring of the matchers here: this driver runs the same code the
hourly VPS drain runs (``enrich_beatport_batch`` -> ``_search_beatport_async``),
only from the residential IP.

OUTAGE ≠ ATTEMPT (E1 invariant): the reused server fn ``_search_beatport_async``
raises ``BeatportHTTPError`` on ANY non-200, so we reclassify by status:

  * 404 → NOT FOUND (a marked attempt). The Beatport ``release`` fallback probes
    ``/release/{slug}/{id}`` for a title, and a 404 there just means that title
    isn't in Beatport's electronic-music catalogue — a genuine "no match", not an
    outage. We emit a ``not_found`` line (which the import marks searched, correct
    E1 behaviour) so the row doesn't stay fresh and re-404 forever.
  * 403 / 429 / 5xx (and any network error / other exception) → OUTAGE: emit
    NOTHING for that row — the line is simply absent from the NDJSON, so the row
    stays fresh (``beatport_searched_at`` untouched) and is re-tried on a later run.

Only a clean ``found`` / ``not_found`` outcome is written; outages are logged/skipped.

CONCURRENCY: rows are scraped CONCURRENTLY, bounded by ``BEATPORT_CONCURRENCY``
(env, default 6) through an ``asyncio.Semaphore`` + one ``asyncio.gather`` over all
rows. The old sequential driver was latency-bound (~0.6 s/req -> ~1.6 rps) and never
saturated the allowed rate; parallelising the TITLES lets the run finally hit the
rate ceiling (~4x throughput). The TOTAL request rate stays capped by the rate
limiter (``BEATPORT_RATE`` token bucket + its OWN ``BEATPORT_CONCURRENCY`` semaphore,
which MUST match this one — the host orchestrator posts both env vars), so this
driver only parallelises titles; the limiter caps requests. NDJSON line order is
irrelevant (the import reads by ``catalog_id``); each line is a single sync
``write``+``flush`` with no ``await`` between, so the event loop can never interleave
two lines, and counter increments are likewise ``await``-free -> atomic.

403 GUARD (supervised run): now a TOTAL 403 budget, not a consecutive count —
"consecutive" is meaningless when N requests are in flight at once. A shared counter
tallies every 403; once it reaches ``BEATPORT_MAX_CONSECUTIVE_403`` (env, default 5 —
the name is kept for continuity) a shared ``aborted`` flag is set, and every
coroutine that acquires the semaphore afterwards returns immediately, leaving its row
fresh and un-emitted. A simple net abort is enough for a supervised run; no elaborate
multi-tier back-off.

Throughput is governed by the L1b rate knob ``BEATPORT_RATE`` (+ ``BEATPORT_CONCURRENCY``)
read by ``workers.rate_limiter.RateLimiter``: the host orchestrator passes both into
the container via ``docker run -e``. With no Redis reachable in the local container,
the shared Redis window fails open and only the local token bucket governs — so the
residential IP is throttled independently of the VPS's own 0.66 rps window.

Usage (container, via backfill_beatport.py or by hand):
    python /work/scrape_driver.py --csv /work/to_analyze.csv --out /work/matches.ndjson
"""

import argparse
import asyncio
import csv
import functools
import json
import os
import sys
import time

# The prod server image lays the code out under /app (see server/Dockerfile);
# make ``beatport`` / ``workers`` importable exactly as the drain does.
sys.path.insert(0, "/app")

# progress must stay ordered even when the container stdout is piped
print = functools.partial(print, flush=True)  # noqa: A001

# TOTAL 403 budget that trips a clean run abort (Cloudflare blocking the IP). The
# old sequential driver counted CONSECUTIVE 403s, but "consecutive" is meaningless
# once several requests are in flight at once, so this is now a budget over the whole
# run. The env var keeps its historical name for continuity.
MAX_403_BUDGET = int(os.environ.get("BEATPORT_MAX_CONSECUTIVE_403", "5"))


def classify_beatport_error(status_code):
    """Map a ``BeatportHTTPError`` status to a driver outcome.

    A 404 is a genuine "no match" (the release fallback probed a title Beatport's
    electronic catalogue doesn't carry), so it counts as a completed attempt and is
    emitted as ``not_found``. Everything else (403 / 429 / 5xx) is a transient
    outage that must leave the row fresh for a later re-scan.
    """
    return "not_found" if status_code == 404 else "outage"


def _match_artist(row):
    """The artist string to match against — mirror the drain's X4 rule.

    ``m2m_names.get(id) or entry.artist``: prefer the M2M names shown in the UI
    (``catalog_artists``), else the flat ``catalog.artist`` column (correct for
    inline-crawled rows whose M2M is still empty). Empty -> None.
    """
    m2m = (row.get("m2m_artists") or "").strip()
    flat = (row.get("flat_artist") or "").strip()
    return m2m or flat or None


async def _scrape(csv_path, out_path):
    """Scrape every candidate row CONCURRENTLY and stream NDJSON to ``out_path``.

    Returns a counters dict. Rows are fanned out over an ``asyncio.gather`` bounded
    by an ``asyncio.Semaphore(BEATPORT_CONCURRENCY)`` (default 6) — the rate limiter
    caps the actual request rate. Streams (flush per line) so a mid-run 403 abort or
    a container kill still leaves a valid partial NDJSON the host can import; line
    order is irrelevant (the import reads by ``catalog_id``).
    """
    from workers.async_http import BeatportHTTPError, HttpPool
    from workers.enrichment import _search_beatport_async
    from workers.rate_limiter import RateLimiter

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    counts = {"found": 0, "not_found": 0, "outage": 0, "error": 0, "aborted": False}
    # Title-level concurrency: MUST match the rate limiter's beatport semaphore
    # (both read BEATPORT_CONCURRENCY) so neither silently binds the other.
    concurrency = int(os.environ.get("BEATPORT_CONCURRENCY", "6"))
    sem = asyncio.Semaphore(concurrency)
    # Shared, mutable guard state. total_403 = the run-wide 403 budget; done = the
    # completion counter for progress. Both are only ever read/written between
    # ``await`` points -> atomic in the single-threaded event loop.
    guard = {"total_403": 0, "done": 0}
    t0 = time.monotonic()

    limiter = RateLimiter()
    with open(out_path, "w", encoding="utf-8") as out_f:
        async with HttpPool(limiter) as pool:

            async def process(row):
                async with sem:
                    # Budget already spent by a sibling: skip, leave the row fresh.
                    if counts["aborted"]:
                        return
                    cid = int(str(row["id"]).strip())
                    title = (row.get("title") or "").strip()
                    isrc = (row.get("isrc") or "").strip() or None

                    rec = None
                    try:
                        bp_track = await _search_beatport_async(
                            pool, title, _match_artist(row), isrc, rcache=None
                        )
                    except BeatportHTTPError as e:
                        if classify_beatport_error(e.status_code) == "not_found":
                            # A 404 is the release fallback saying "not on Beatport"
                            # (not in its electronic catalogue), NOT a panne: emit a
                            # not_found line so the import marks it searched (E1) and
                            # it won't stay fresh and re-404 on every run.
                            rec = {"catalog_id": cid, "status": "not_found", "bp_track": None}
                            counts["not_found"] += 1
                        else:
                            # Outage (403 / 429 / 5xx), NOT an attempt: emit nothing,
                            # leave the row fresh for a later re-scan.
                            counts["outage"] += 1
                            if e.status_code == 403:
                                guard["total_403"] += 1
                                if (
                                    guard["total_403"] >= MAX_403_BUDGET
                                    and not counts["aborted"]
                                ):
                                    counts["aborted"] = True
                                    print(
                                        f"  ABORT: {guard['total_403']} total 403(s) "
                                        "(Cloudflare blocking the IP); remaining rows "
                                        "left un-scraped and fresh."
                                    )
                    except Exception as e:  # noqa: BLE001 — one dead row must not abort
                        counts["error"] += 1
                        print(f"  catalog {cid}: {type(e).__name__}: {e}")
                    else:
                        if bp_track:
                            rec = {"catalog_id": cid, "status": "found", "bp_track": bp_track}
                            counts["found"] += 1
                        else:
                            rec = {"catalog_id": cid, "status": "not_found", "bp_track": None}
                            counts["not_found"] += 1

                    # One sync write+flush, no await between -> lines never interleave.
                    if rec is not None:
                        out_f.write(json.dumps(rec) + "\n")
                        out_f.flush()

                    guard["done"] += 1
                    done = guard["done"]
                    if done % 50 == 0 or done == total:
                        print(
                            f"[beatport-scrape] {done}/{total} "
                            f"found={counts['found']} not_found={counts['not_found']} "
                            f"outage={counts['outage']} error={counts['error']} "
                            f"elapsed={time.monotonic() - t0:.0f}s"
                        )

            await asyncio.gather(*(process(row) for row in rows))

    return counts


def main():
    ap = argparse.ArgumentParser(
        description="Scrape Beatport for catalog candidates and emit NDJSON matches "
        "(L1a container pass — runs the REAL server matchers, writes nothing to the DB)"
    )
    ap.add_argument("--csv", default="/work/to_analyze.csv")
    ap.add_argument("--out", default="/work/matches.ndjson")
    args = ap.parse_args()

    counts = asyncio.run(_scrape(args.csv, args.out))
    print(
        f"[beatport-scrape] done: found={counts['found']} "
        f"not_found={counts['not_found']} outage={counts['outage']} "
        f"error={counts['error']} aborted={counts['aborted']}"
    )


if __name__ == "__main__":
    main()
