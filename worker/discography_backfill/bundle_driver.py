"""C14.a Phase 2 (backfill) — discography BUNDLE driver. Runs INSIDE the Docker container (prod server image).

The WRITE-path twin of ``fetch_driver.py`` (the read-only benchmark). For each cohort
artist it walks the full Deezer discography, classifies each track NET-NEW vs our
catalog using the SAME identity the ingestion uses (``make_normalized_key`` — reused
VERBATIM through ``fetch_driver._track_key``), and for the net-new ones fetches the full
``/track/{id}`` hit, emitting a per-artist BUNDLE the OPS script
``server/api/scripts/import_discography.py`` replays through the enrichment funnel.

Why per-track fetch only for net-new: the album tracklist summaries (``/album/{id}``)
carry no ISRC and no ``contributors`` (feat. artists) — the OPS funnel needs the full
hit to link the M2M artists + album + ISRC. Fetching ``/track/{id}`` ONLY for the
tracks that are net-new BY TITLE (classified against the mounted catalog index) bounds
that cost to the tracks we will actually insert; the ISRC on the fetched hit then lets
the OPS dedup fold a cosmetic title variant into an existing row (so a net-new-by-title
that is already-in-base-by-ISRC creates no duplicate).

It emits ONE NDJSON record per PROCESSED artist:

    {"artist_id": <int>, "deezer_id": <str>, "name": <str>, "tier": <str>,
     "n_requests": <int>, "n_albums": <int>, "n_net_new": <int>, "error": <str|null>,
     "tracks": [ <full Deezer /track hit>, ... ]}

``tracks`` are DEDUPED within the artist by key (Deezer lists the same recording on a
single AND its album). Records are streamed (flush per line) so a container kill leaves a
valid partial NDJSON. Reuses ``fetch_driver`` (bind-mounted alongside at /work): the walk
helpers, the residential floor, the concurrency shape — identical to the benchmark, so
the classification is byte-identical to the numbers the gate was decided on.

OUTAGE ≠ EMPTY (invariant #4-ish): a ``DeezerHTTPError`` on the album list aborts only
THAT artist (``error`` set, ``tracks: []`` → the OPS counts it as no-new, not zero
discography); an error on a single album / a single ``/track`` fetch skips it and the
walk continues.

CONCURRENCY / PACING: artists fanned out over one ``asyncio.gather`` bounded by
``DEEZER_CONCURRENCY``; the reused ``RateLimiter`` + the ``DEEZER_RATE`` residential
floor cap the request rate globally (C9 lesson). No Redis in the container → the shared
window fails open, only the local bucket + the floor govern.

Usage (container, via backfill_discography.py or by hand):
    python /work/bundle_driver.py --worklist /work/sample.csv --index /work/catalog_index.csv \
        --out /work/bundle.ndjson
"""

import argparse
import asyncio
import csv
import functools
import json
import os
import sys
import time

# Prod server image lays code at /app (api/ → utils, workers/). fetch_driver is
# bind-mounted next to this file at /work, importable as a sibling module.
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_driver  # noqa: E402  (sibling module at /work)
from fetch_driver import (  # noqa: E402
    _AsyncFloor,
    _fetch_album_tracks,
    _fetch_artist_albums,
    _FlooredPool,
    _track_key,
)

print = functools.partial(print, flush=True)  # noqa: A001

DEEZER_CONCURRENCY = int(os.environ.get("DEEZER_CONCURRENCY", "5"))
DEEZER_RATE = float(os.environ.get("DEEZER_RATE", "0") or "0")
MIN_INTERVAL = (1.0 / DEEZER_RATE) if DEEZER_RATE > 0 else 0.0


def load_keyset(index_path):
    """The set of catalog ``normalized_key`` values from the mounted index CSV.

    Only the key column is needed here: the walk classifies net-new BY TITLE (album
    summaries carry no ISRC), and the ISRC dedup happens OPS-side on the fetched hit.
    """
    keys = set()
    if not index_path or not os.path.exists(index_path):
        return keys
    with open(index_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = row.get("normalized_key")
            if k:
                keys.add(k)
    return keys


async def walk_and_bundle(pool, deezer_id, key_fn, keyset, fallback_artist, http_error):
    """Walk one artist's discography → the full hits of its NET-NEW tracks + a req count.

    Pure except for ``pool`` (injectable fake in tests) and ``key_fn``
    (``make_normalized_key``). Classifies each album-summary track by key: in ``keyset``
    → in base (skip); else net-new → fetch ``/track/{id}`` for the full hit. Deduped
    within the artist by key. Returns ``{n_requests, n_albums, n_net_new, tracks, error}``.
    ``http_error`` (``DeezerHTTPError``) is injected to keep the module host-importable.
    """
    try:
        albums, n_req = await _fetch_artist_albums(pool, deezer_id)
    except http_error as e:
        return {"n_requests": 1, "n_albums": 0, "n_net_new": 0, "tracks": [],
                "error": f"albums: {type(e).__name__}: {e}"}

    if len(albums) >= fetch_driver.MAX_ALBUMS_PER_ARTIST:
        print(f"[cap] artist {deezer_id}: album list capped at {fetch_driver.MAX_ALBUMS_PER_ARTIST}")

    seen_keys = set()
    net_new_ids = []
    error = None

    for album in albums:
        if len(net_new_ids) >= fetch_driver.MAX_TRACKS_PER_ARTIST:
            print(
                f"[cap] artist {deezer_id}: net-new cap {fetch_driver.MAX_TRACKS_PER_ARTIST} hit "
                "— remaining albums skipped"
            )
            break
        album_id = album.get("id")
        if album_id is None:
            continue
        try:
            raw_tracks, album_artist, ar = await _fetch_album_tracks(pool, album_id)
        except http_error as e:
            n_req += 1
            error = error or f"album {album_id}: {type(e).__name__}: {e}"
            continue
        n_req += ar
        for t in raw_tracks:
            if len(net_new_ids) >= fetch_driver.MAX_TRACKS_PER_ARTIST:
                break
            key, _title = _track_key(key_fn, t, album_artist, fallback_artist)
            tid = t.get("id")
            if not key or key in seen_keys or tid is None:
                continue
            seen_keys.add(key)
            if key in keyset:
                continue  # already in base (by title) — not net-new
            net_new_ids.append(tid)

    tracks = []
    for tid in net_new_ids:
        try:
            hit = await pool.deezer_get(f"/track/{tid}")
        except http_error as e:
            n_req += 1
            error = error or f"track {tid}: {type(e).__name__}: {e}"
            continue
        n_req += 1
        if isinstance(hit, dict) and hit.get("id") is not None and hit.get("title"):
            tracks.append(hit)

    return {"n_requests": n_req, "n_albums": len(albums), "n_net_new": len(tracks),
            "tracks": tracks, "error": error}


async def _run(worklist_path, index_path, out_path):
    """Bundle every worklist artist CONCURRENTLY and stream NDJSON to ``out_path``."""
    from utils import make_normalized_key
    from workers.async_http import DeezerHTTPError, HttpPool
    from workers.rate_limiter import RateLimiter

    keyset = load_keyset(index_path)
    print(f"[discography-bundle] catalog index: {len(keyset)} keys")

    with open(worklist_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    counts = {"artists": 0, "errors": 0, "requests": 0, "net_new": 0}
    sem = asyncio.Semaphore(DEEZER_CONCURRENCY)
    guard = {"done": 0}
    t0 = time.monotonic()

    limiter = RateLimiter()
    floor = _AsyncFloor(MIN_INTERVAL)
    with open(out_path, "w", encoding="utf-8") as out_f:
        async with HttpPool(limiter) as raw_pool:
            pool = _FlooredPool(raw_pool, floor)

            async def process(row):
                async with sem:
                    try:
                        artist_id = int(str(row["artist_id"]).strip())
                        deezer_id = (row.get("deezer_id") or "").strip()
                    except (KeyError, ValueError, TypeError) as e:
                        counts["errors"] += 1
                        print(f"  malformed worklist row: {type(e).__name__}: {e}")
                        return
                    name = (row.get("name") or "").strip()
                    tier = (row.get("tier") or "").strip()
                    if not deezer_id or deezer_id == "NOT_FOUND":
                        counts["errors"] += 1
                        print(f"  artist {artist_id}: no usable deezer_id, skipped")
                        return

                    try:
                        res = await walk_and_bundle(
                            pool, deezer_id, make_normalized_key, keyset, name,
                            DeezerHTTPError,
                        )
                    except Exception as e:  # noqa: BLE001 — one dead artist must not abort
                        counts["errors"] += 1
                        print(f"  artist {artist_id}: {type(e).__name__}: {e}")
                        return

                    counts["artists"] += 1
                    counts["requests"] += res["n_requests"]
                    counts["net_new"] += res["n_net_new"]
                    if res["error"]:
                        counts["errors"] += 1

                    rec = {"artist_id": artist_id, "deezer_id": deezer_id,
                           "name": name, "tier": tier, **res}
                    out_f.write(json.dumps(rec) + "\n")
                    out_f.flush()

                    guard["done"] += 1
                    done = guard["done"]
                    if done % 5 == 0 or done == total:
                        print(
                            f"[discography-bundle] {done}/{total} "
                            f"artists_ok={counts['artists']} errors={counts['errors']} "
                            f"requests={counts['requests']} net_new={counts['net_new']} "
                            f"elapsed={time.monotonic() - t0:.0f}s"
                        )

            await asyncio.gather(*(process(row) for row in rows))

    return counts


def main():
    ap = argparse.ArgumentParser(
        description="Walk each cohort artist's Deezer discography, classify net-new vs "
        "the catalog, and emit the full /track hits of the net-new ones as a per-artist "
        "bundle (C14.a Phase 2 write path — the OPS import replays the funnel)."
    )
    ap.add_argument("--worklist", default="/work/sample.csv")
    ap.add_argument("--index", default="/work/catalog_index.csv")
    ap.add_argument("--out", default="/work/bundle.ndjson")
    args = ap.parse_args()

    counts = asyncio.run(_run(args.worklist, args.index, args.out))
    print(
        f"[discography-bundle] done: artists={counts['artists']} "
        f"errors={counts['errors']} requests={counts['requests']} "
        f"net_new={counts['net_new']}"
    )


if __name__ == "__main__":
    main()
