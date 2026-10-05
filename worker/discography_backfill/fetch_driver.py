"""C14.a Phase 2 (benchmark) — discography fetch pass. Runs INSIDE the Docker container (prod server image).

READ-ONLY. This driver dumps an artist's Deezer discography and computes, for each
track, the SAME ``normalized_key`` the ingestion computes — so the host can classify
every track as already-in-base vs NET-NEW exactly as production would on insert. It
writes NOTHING to any DB and creates NOTHING; its only output is an NDJSON of
per-artist track keys + a request count. This is the GATE material for C14.a Phase 2
(decide the backfill cohort where net-new stays digestible + project the Beatport
inflow), not the backfill itself.

For each sampled artist (``artist_id,deezer_id,tier,name`` from the worklist CSV) it
walks, reusing the prod primitives VERBATIM (byte-identical to the nightly
``_check_releases`` crawl, only the horizon gate + the DB writes stripped):

  * ``GET /artist/{deezer_id}/albums`` — PAGINATED (follows ``index``/``next``; the
    prod ``_fetch_artist_releases`` only takes one page, so we add the loop);
  * ``GET /album/{album_id}`` — the tracklist embedded under ``tracks.data`` (track
    SUMMARIES: id/title/artist — NO isrc), following ``tracks.next`` for a long comp;
  * ``workers`` HTTP stack: ``HttpPool.deezer_get`` + ``RateLimiter`` (the shared
    Redis window + local token bucket), paced further by the residential ``DEEZER_RATE``
    floor (the C9 lesson) — REUSED, not re-implemented;
  * ``utils.make_normalized_key(title, artist)`` — the EXACT ingestion identity
    (``normalize(title) + " - " + normalize(artist)``), so a track is "in base" iff its
    key (or, with ``--with-isrc``, its isrc) matches a catalog row.

The key inputs mirror ingestion EXACTLY: ``title`` = the track's ``title``, ``artist``
= the track's top-level ``artist.name`` (the single lead artist, NOT a contributor
join — that is what ``source_clients.fetch_deezer_tracks`` feeds
``make_normalized_key``), falling back to the album artist then the sampled artist.

``--with-isrc`` (opt-in, EXPENSIVE): additionally ``GET /track/{id}`` per track to
attach its isrc, so the host can measure how many "net-new-by-key" tracks isrc would
actually catch (= the duplication the cheap key-only path would create). This adds one
request PER TRACK — run it on a REDUCED sample (``--limit`` a handful of artists), it
is a calibration sub-run, never the full ~40.

It emits ONE NDJSON record per PROCESSED artist:

    {"artist_id": <int>, "deezer_id": <str>, "tier": <str>, "name": <str>,
     "n_requests": <int>, "n_albums": <int>,
     "n_tracks_raw": <int>, "n_tracks_distinct": <int>,
     "error": <str|null>,
     "tracks": [{"key": <str>, "isrc": <str|null>, "title": <str>}]}

``tracks`` is DEDUPED within the artist by ``key`` (Deezer lists the same recording on
a single AND its album — we count the artist's distinct catalog contribution once).
Records are streamed (flush per line) so a container kill leaves a valid partial NDJSON.

OUTAGE ≠ EMPTY (invariant #4-ish for a benchmark): a ``DeezerHTTPError`` on the album
list aborts only THAT artist (``error`` set, ``tracks: []``, so the host counts it as a
failed sample, not an artist with zero discography); an error on a single album/track
skips that album/track and the walk continues.

CONCURRENCY: artists are fetched CONCURRENTLY, bounded by ``DEEZER_CONCURRENCY`` (env,
default 5 = the ``deezer`` source's semaphore). The reused ``RateLimiter`` + the
``DEEZER_RATE`` residential floor cap the request rate globally. With no Redis in the
container the shared window fails open, so only the local bucket + this floor govern.

Usage (container, via benchmark_discography.py or by hand):
    python /work/fetch_driver.py --worklist /work/sample.csv --out /work/discography.ndjson
    python /work/fetch_driver.py --worklist /work/sample.csv --out /work/discography.ndjson --with-isrc
"""

import argparse
import asyncio
import csv
import functools
import json
import os
import sys
import time

# The prod server image lays the code out under /app (see server/Dockerfile): api/ at
# /app (so ``utils`` is importable) and workers/ at /app/workers. Make both resolve
# exactly as the nightly task does. Harmless on the host (the path just doesn't exist)
# — every server import is lazy (inside the functions), so this module imports cleanly
# for the host-only unit tests too.
sys.path.insert(0, "/app")

# progress must stay ordered even when the container stdout is piped
print = functools.partial(print, flush=True)  # noqa: A001

# Row-level concurrency for the gather. Default 5 = the ``deezer`` source's concurrency
# in workers.rate_limiter; the token bucket + the residential floor still cap the rate.
DEEZER_CONCURRENCY = int(os.environ.get("DEEZER_CONCURRENCY", "5"))

# Optional residential-IP inter-request floor in req/s (0/unset = no extra throttle),
# converted to a minimum interval between Deezer requests (C9 lesson).
DEEZER_RATE = float(os.environ.get("DEEZER_RATE", "0") or "0")
MIN_INTERVAL = (1.0 / DEEZER_RATE) if DEEZER_RATE > 0 else 0.0

# Deezer paginates /artist/{id}/albums and /album/{id}/tracks in pages of 100. A hard
# safety cap on albums/tracks per artist stops a pathological discography (a "Various
# Artists" style id, thousands of comps) from stalling the whole benchmark; logged when
# hit so the operator knows a number is a floor, not the truth.
PAGE = 100
MAX_ALBUMS_PER_ARTIST = int(os.environ.get("BENCH_MAX_ALBUMS", "600"))
MAX_TRACKS_PER_ARTIST = int(os.environ.get("BENCH_MAX_TRACKS", "4000"))


class _AsyncFloor:
    """A global inter-request floor (seconds) shared across the gather.

    Serialises the START of Deezer requests to at most one per ``min_interval``. A
    no-op when ``min_interval <= 0``. (Twin of the set_artist_backfill driver's floor.)
    """

    def __init__(self, min_interval):
        self._min = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        if self._min <= 0:
            return
        async with self._lock:
            wait = self._min - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class _FlooredPool:
    """Thin wrapper exposing ``deezer_get`` through an ``_AsyncFloor``.

    Every Deezer request in the walk goes through ``pool.deezer_get``, so routing it
    here applies the residential floor uniformly. Zero overhead when the floor is off.
    """

    def __init__(self, pool, floor):
        self._pool = pool
        self._floor = floor

    async def deezer_get(self, path, params=None):
        await self._floor.wait()
        return await self._pool.deezer_get(path, params=params)


def _track_key(key_fn, track, album_artist, fallback_artist):
    """The ingestion identity for a Deezer album-track summary.

    Mirrors ``source_clients.fetch_deezer_tracks`` EXACTLY: the key artist is the
    track's own top-level ``artist.name`` (the single lead artist), NOT a contributor
    join and NOT the album artist — falling back to the album artist, then the sampled
    artist name, only when the track carries none. ``key_fn`` is injected
    (``utils.make_normalized_key`` in prod, a fake in tests) so this stays pure.
    """
    title = (track.get("title") or "").strip()
    tartist = track.get("artist")
    artist_name = (tartist or {}).get("name") if isinstance(tartist, dict) else None
    artist_name = (artist_name or album_artist or fallback_artist or "").strip()
    return key_fn(title, artist_name), title


async def _fetch_artist_albums(pool, deezer_id):
    """Every album for an artist, following pagination. Returns ``(albums, n_requests)``.

    ``_fetch_artist_releases`` (prod) takes a single page (limit 100); a full
    discography needs the loop — advance ``index`` while a full page comes back and a
    ``next`` link is present, bounded by ``MAX_ALBUMS_PER_ARTIST``.
    """
    albums = []
    n_req = 0
    index = 0
    while True:
        data = await pool.deezer_get(
            f"/artist/{deezer_id}/albums", params={"limit": PAGE, "index": index}
        )
        n_req += 1
        batch = data.get("data") or []
        albums.extend(batch)
        if (
            len(batch) < PAGE
            or not data.get("next")
            or len(albums) >= MAX_ALBUMS_PER_ARTIST
        ):
            break
        index += PAGE
    return albums[:MAX_ALBUMS_PER_ARTIST], n_req


async def _fetch_album_tracks(pool, album_id):
    """Tracklist embedded in ``/album/{id}`` under ``tracks.data``. Returns ``(tracks, album_artist, n_requests)``.

    Follows ``tracks.next`` (rare — a comp longer than one embedded page). Track dicts
    are SUMMARIES: id/title/artist, NO isrc (that needs ``/track/{id}``).
    """
    data = await pool.deezer_get(f"/album/{album_id}")
    n_req = 1
    tracks_obj = data.get("tracks") or {}
    tracks = list(tracks_obj.get("data") or [])
    album_artist = (data.get("artist") or {}).get("name")
    index = len(tracks)
    while tracks_obj.get("next") and len(tracks) < MAX_TRACKS_PER_ARTIST:
        page = await pool.deezer_get(
            f"/album/{album_id}/tracks", params={"limit": PAGE, "index": index}
        )
        n_req += 1
        batch = page.get("data") or []
        tracks.extend(batch)
        tracks_obj = page
        if len(batch) < PAGE:
            break
        index += PAGE
    return tracks, album_artist, n_req


async def _fetch_track_isrc(pool, track_id):
    """``/track/{id}`` -> isrc (or None). One request. Only used under ``--with-isrc``."""
    data = await pool.deezer_get(f"/track/{track_id}")
    return (data.get("isrc") or None), 1


async def walk_discography(pool, deezer_id, key_fn, fallback_artist, with_isrc, http_error):
    """Walk one artist's full discography into deduped track keys + a request count.

    Pure except for ``pool`` (injectable fake in tests) and ``key_fn``
    (``make_normalized_key``). Returns a dict with ``n_requests / n_albums /
    n_tracks_raw / n_tracks_distinct / tracks / error``. ``http_error`` is the
    ``DeezerHTTPError`` class (injected to keep the module host-importable). An error on
    the album LIST aborts the artist (``error`` set); an error on a single album/track
    skips it and the walk continues (recall cost, never a false in-base/net-new).
    """
    try:
        albums, n_req = await _fetch_artist_albums(pool, deezer_id)
    except http_error as e:
        return {
            "n_requests": 1,
            "n_albums": 0,
            "n_tracks_raw": 0,
            "n_tracks_distinct": 0,
            "tracks": [],
            "error": f"albums: {type(e).__name__}: {e}",
        }

    if len(albums) >= MAX_ALBUMS_PER_ARTIST:
        print(f"[cap] artist {deezer_id}: album list capped at {MAX_ALBUMS_PER_ARTIST}")

    seen_keys = set()
    tracks_out = []
    n_tracks_raw = 0
    error = None

    for album in albums:
        if len(tracks_out) >= MAX_TRACKS_PER_ARTIST:
            print(
                f"[cap] artist {deezer_id}: track cap {MAX_TRACKS_PER_ARTIST} hit "
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
            if len(tracks_out) >= MAX_TRACKS_PER_ARTIST:
                break
            n_tracks_raw += 1
            key, title = _track_key(key_fn, t, album_artist, fallback_artist)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            rec = {"key": key, "isrc": None, "title": title}
            if with_isrc and t.get("id") is not None:
                try:
                    isrc, ir = await _fetch_track_isrc(pool, t["id"])
                    n_req += ir
                    rec["isrc"] = isrc
                except http_error as e:
                    n_req += 1
                    error = error or f"track {t.get('id')}: {type(e).__name__}: {e}"
            tracks_out.append(rec)

    return {
        "n_requests": n_req,
        "n_albums": len(albums),
        "n_tracks_raw": n_tracks_raw,
        "n_tracks_distinct": len(tracks_out),
        "tracks": tracks_out,
        "error": error,
    }


async def _run(worklist_path, out_path, with_isrc):
    """Fetch every worklist artist CONCURRENTLY and stream NDJSON to ``out_path``.

    Returns a counters dict. Artists are fanned out over one ``asyncio.gather`` bounded
    by an ``asyncio.Semaphore(DEEZER_CONCURRENCY)``; the reused ``RateLimiter`` + the
    residential floor cap the Deezer request rate. Streams (flush per line) so a
    container kill still leaves a valid partial NDJSON.
    """
    from utils import make_normalized_key
    from workers.async_http import DeezerHTTPError, HttpPool
    from workers.rate_limiter import RateLimiter

    with open(worklist_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    counts = {
        "artists": 0,
        "errors": 0,
        "requests": 0,
        "tracks_distinct": 0,
    }
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
                    tier = (row.get("tier") or "").strip()
                    name = (row.get("name") or "").strip()
                    if not deezer_id or deezer_id == "NOT_FOUND":
                        counts["errors"] += 1
                        print(f"  artist {artist_id}: no usable deezer_id, skipped")
                        return

                    try:
                        res = await walk_discography(
                            pool, deezer_id, make_normalized_key, name,
                            with_isrc, DeezerHTTPError,
                        )
                    except Exception as e:  # noqa: BLE001 — one dead artist must not abort
                        counts["errors"] += 1
                        print(f"  artist {artist_id}: {type(e).__name__}: {e}")
                        return

                    counts["artists"] += 1
                    counts["requests"] += res["n_requests"]
                    counts["tracks_distinct"] += res["n_tracks_distinct"]
                    if res["error"]:
                        counts["errors"] += 1

                    rec = {
                        "artist_id": artist_id,
                        "deezer_id": deezer_id,
                        "tier": tier,
                        "name": name,
                        **res,
                    }
                    out_f.write(json.dumps(rec) + "\n")
                    out_f.flush()

                    guard["done"] += 1
                    done = guard["done"]
                    if done % 5 == 0 or done == total:
                        print(
                            f"[discography-fetch] {done}/{total} "
                            f"artists_ok={counts['artists']} errors={counts['errors']} "
                            f"requests={counts['requests']} "
                            f"tracks={counts['tracks_distinct']} "
                            f"elapsed={time.monotonic() - t0:.0f}s"
                        )

            await asyncio.gather(*(process(row) for row in rows))

    return counts


def main():
    ap = argparse.ArgumentParser(
        description="Dump each sampled artist's Deezer discography and compute the "
        "ingestion normalized_key per track (C14.a Phase 2 benchmark — READ-ONLY, "
        "writes nothing to any DB)."
    )
    ap.add_argument("--worklist", default="/work/sample.csv")
    ap.add_argument("--out", default="/work/discography.ndjson")
    ap.add_argument(
        "--with-isrc",
        action="store_true",
        help="also GET /track/{id} per track for its isrc (EXPENSIVE, +1 req/track) — "
        "run on a REDUCED sample to calibrate the isrc effect on net-new",
    )
    args = ap.parse_args()

    counts = asyncio.run(_run(args.worklist, args.out, args.with_isrc))
    print(
        f"[discography-fetch] done: artists={counts['artists']} "
        f"errors={counts['errors']} requests={counts['requests']} "
        f"tracks_distinct={counts['tracks_distinct']}"
    )


if __name__ == "__main__":
    main()
