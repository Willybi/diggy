"""L1a/L1b — TrackID hydration driver. Runs INSIDE the Docker container (the PROD
server image + EffNet).

L1a is the DEEZER pass; L1b (this extension) completes each ``found`` record with the
rest of the per-track enrichment, SHARING a single preview download between BPM and
EffNet.

Reads a candidates CSV of tracklist rows (columns ``set_trackid_id,position,title,
artist,is_id``) — one row per TrackID set-track — and, for each NON-``id`` row, runs
the REAL server search+match ``workers.enrichment._search_deezer_async`` (which embeds
the X3/X4 validation: ISRC-or-remix-aware title + folded-artist gate) followed by ONE
``/track/{deezer_id}`` fetch through ``HttpPool.deezer_get`` to pull the full track
dict (isrc, duration, preview, album, contributors). For a ``found`` row it then adds,
best-effort (a failure of any leaves its field null WITHOUT dropping the record):

  * ``deezer.cover_catalog_b64`` / ``deezer.cover_album_b64`` — the cover image(s)
    downloaded and base64-encoded (both URLs resolve identically today, so the image
    is downloaded ONCE and reused; both keys are kept for the later contract);
  * ``bpm`` / ``embedding`` — from a SINGLE download of ``deezer.preview_url``: the
    30s MP3 is fetched once, then Essentia ``RhythmExtractor2013(multifeature)`` (BPM,
    conf-gated ≥2.0) and ``TensorflowPredictEffnetDiscogs`` (1280-d, mean+L2) run OFF
    the event loop via ``loop.run_in_executor`` (Essentia is CPU-blocking; the EffNet
    graph is loaded once per thread, thread-local, like embed.py);
  * ``beatport`` / ``key`` — the REAL server ``workers.enrichment._search_beatport_async``
    (independent of Deezer, its OWN rate limiter), with the Camelot ``key`` hoisted
    from the matched track for the contract (the Beatport BPM stays inside ``bp_track``).

It emits ONE NDJSON line per row:

    {"set_trackid_id": <id>, "position": <n>, "status": "found",
     "deezer": {"track": <full /track/{id} dict>, "preview_url": <str|null>,
                "cover_catalog_url": <str|null>, "cover_album_url": <str|null>,
                "cover_catalog_b64": <str|null>, "cover_album_b64": <str|null>},
     "beatport": {"bp_track": <dict>} | null,
     "bpm": {"value": <float>, "conf": <float>} | null,
     "key": <str|null>,
     "embedding": [<1280 float>] | null}
    {"set_trackid_id": <id>, "position": <n>, "status": "not_found", "deezer": null}
    {"set_trackid_id": <id>, "position": <n>, "status": "id",        "deezer": null}

``not_found`` / ``id`` rows carry NO enrichment keys (nothing to enrich). ``id`` rows
(an "ID - ID" unknown track, ``is_id`` truthy) are emitted verbatim without any Deezer
call — nothing to resolve. The driver NEVER writes to the DB; the WRITE is a later lot
(L3) done on the VPS by an OPS script that reuses the enrichment code verbatim. Zero
vendoring of the matchers here — this driver runs the same code the nightly Deezer/
Beatport drains run, only from the residential IP.

BEATPORT OUTAGE ≠ DROP (unlike a Deezer outage): the Deezer hit anchors the record's
identity, so a Deezer outage drops the whole line; Beatport is a SECONDARY enrichment,
so a Beatport 403/429/5xx (or 404 "no match") only leaves ``beatport``/``key`` null —
the rest of the record (deezer, cover, bpm, embedding) is emitted regardless. The L3
write decides E1 ``beatport_searched_at`` marking.

OUTAGE ≠ ATTEMPT (E1 invariant): the reused server fn raises ``DeezerHTTPError`` on any
non-200, so we reclassify by status (mirror of scrape_driver.py):

  * 404 → NOT FOUND (a completed attempt): a genuine "absent from Deezer". Emit a
    ``not_found`` line so the row is a resolved outcome.
  * 429 / 5xx (and any network error / other exception) → OUTAGE: emit NOTHING for
    that row — its line is simply absent from the NDJSON, so a later lot re-tries it.

Only a clean ``found`` / ``not_found`` / ``id`` outcome is written; outages are
skipped. NDJSON line order is irrelevant (later lots read by ``set_trackid_id``); each
line is a single sync ``write``+``flush`` with no ``await`` between, so the event loop
can never interleave two lines, and counter increments are likewise ``await``-free.

CONCURRENCY: rows are hydrated CONCURRENTLY, bounded by ``DEEZER_CONCURRENCY`` (env,
default 5 = the ``deezer`` source's concurrency in workers.rate_limiter) through an
``asyncio.Semaphore`` + one ``asyncio.gather`` over all rows. The TOTAL request rate is
governed by the reused ``RateLimiter`` (``deezer`` config, 10 rps local bucket). With no
Redis reachable in the local container the shared window fails open, so only that local
bucket governs — the residential IP is throttled independently of the VPS.

DEEZER_RATE (env, rps): an OPTIONAL residential-IP inter-request floor layered ON TOP
of the RateLimiter (the C9 lesson: Deezer rate-limits a sustained residential pace).
Unlike ``BEATPORT_RATE`` — which the server rate_limiter reads directly for its beatport
bucket — the server's ``deezer`` source config is FIXED (5 concurrent, 10 rps) and reads
no env, so we cannot reconfigure it without editing server/. This driver-level floor
(default 0 = no extra throttle, PROD-equivalent ceiling) gives a later host orchestrator
a real knob to pace the residential IP gentler than 10 rps.

HORS PÉRIMÈTRE (later lots): no per-set artwork bytes (``set_artwork_b64`` derives from
the TrackID detail ``artworkUrl``, which only the L2 orchestrator holds); no host
orchestrator / TrackID detail fetch / per-set bundle assembly (L2); no VPS write (L3).

Usage (container):
    python /work/enrich_driver.py --csv /work/to_hydrate.csv --out /work/deezer.ndjson
"""

import argparse
import asyncio
import base64
import csv
import functools
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# The prod server image lays the code out under /app (see server/Dockerfile);
# make ``workers`` importable exactly as the drain does. Harmless on the host (the
# path just doesn't exist) — the server imports are lazy, inside ``_hydrate``, so the
# module imports cleanly for host-only unit tests.
sys.path.insert(0, "/app")

# progress must stay ordered even when the container stdout is piped
print = functools.partial(print, flush=True)  # noqa: A001

# Row-level concurrency for the gather. Default 5 = the ``deezer`` source's concurrency
# in workers.rate_limiter (the rate limiter's own deezer semaphore); the token bucket
# still caps the total request rate.
DEEZER_CONCURRENCY = int(os.environ.get("DEEZER_CONCURRENCY", "5"))

# Optional residential-IP inter-request floor in req/s (0/unset = no extra throttle).
# Converted to a minimum interval between Deezer requests; see the module docstring.
DEEZER_RATE = float(os.environ.get("DEEZER_RATE", "0") or "0")
MIN_INTERVAL = (1.0 / DEEZER_RATE) if DEEZER_RATE > 0 else 0.0

# Truthy spellings of the CSV ``is_id`` column (CSV values are strings).
_TRUE_STRINGS = {"1", "true", "yes", "t", "y"}

# ── L1b: preview → BPM + EffNet, cover bytes, Beatport ──

# E2.a benchmark gate: keep a BPM only when RhythmExtractor2013 confidence clears this
# threshold (~84% precision over ~82% of tracks). Same env as server bpm_analysis.py.
BPM_MIN_CONF = float(os.environ.get("ANALYSIS_BPM_MIN_CONF", "2.0"))

# Frozen C9 v1 EffNet model — baked into the L1a image at /models (see the Dockerfile).
EFFNET_GRAPH = "/models/discogs-effnet-bs64-1.pb"
EMBEDDING_DIM = 1280
EMB_DECIMALS = 6

# Width of the ThreadPoolExecutor running the CPU-blocking Essentia work OFF the event
# loop. Kept small (Essentia is CPU-bound); env-tunable to cap the residential CPU pic.
HYDRATE_EXECUTOR_WORKERS = int(os.environ.get("HYDRATE_EXECUTOR_WORKERS", "2"))

# Each executor thread loads the (heavy) EffNet TF graph ONCE via thread-local storage —
# the ThreadPoolExecutor provides the parallelism. Mirrors embed.py.
_local = threading.local()


def classify_deezer_error(status_code):
    """Map a ``DeezerHTTPError`` status to a driver outcome.

    A 404 is a genuine "absent from Deezer" (a completed attempt) → ``not_found``.
    Everything else (429 / 5xx) is a transient outage that must leave the row absent
    from the NDJSON so a later lot re-tries it.
    """
    return "not_found" if status_code == 404 else "outage"


def _is_id_track(row):
    """True when the row is an "ID - ID" unknown track (``is_id`` truthy) — skip it."""
    return (row.get("is_id") or "").strip().lower() in _TRUE_STRINGS


def _match_artist(row):
    """The artist string to search Deezer with, or None when blank.

    TrackID tracklist rows carry the artist directly (one flat field); the reused
    ``_search_deezer_async`` folds/validates it against the hit. Empty → None so the
    cascade falls back to title-only search.
    """
    return (row.get("artist") or "").strip() or None


def extract_deezer(track):
    """Build the ``deezer`` object of a ``found`` NDJSON line from a full /track dict.

    ``track`` = the complete ``/track/{id}`` response (kept verbatim under ``track`` so
    a later lot has isrc / duration / album / contributors in hand). The cover URLs and
    preview URL are hoisted alongside for convenience. Both cover URLs derive from the
    SAME ``album.cover_medium or album.cover_big`` convention the server uses for the
    catalog cover (``enrich_entry``) AND the album cover (``link_catalog_album_from_hit``)
    — kept as two keys for the later contract even though they resolve identically today.
    """
    album = track.get("album") or {}
    cover = album.get("cover_medium") or album.get("cover_big")
    preview = (track.get("preview") or "").strip() or None
    return {
        "track": track,
        "preview_url": preview,
        "cover_catalog_url": cover,
        "cover_album_url": cover,
    }


def build_record(set_trackid_id, position, status, deezer):
    """Assemble a bare (``not_found`` / ``id``) NDJSON record — no enrichment keys."""
    return {
        "set_trackid_id": set_trackid_id,
        "position": position,
        "status": status,
        "deezer": deezer,
    }


def build_found_record(set_trackid_id, position, deezer, beatport, bpm, key, embedding):
    """Assemble one ``found`` NDJSON record on the full L1b contract.

    ``beatport`` is the normalised bp_track dict or None → wrapped as
    ``{"bp_track": …}`` / null. ``bpm`` is the gated ``{"value", "conf"}`` dict or None;
    ``embedding`` the 1280-float list or None; ``key`` the Camelot string or None.
    """
    return {
        "set_trackid_id": set_trackid_id,
        "position": position,
        "status": "found",
        "deezer": deezer,
        "beatport": {"bp_track": beatport} if beatport else None,
        "bpm": bpm,
        "key": key,
        "embedding": embedding,
    }


def new_counts():
    """Fresh counters dict (single source of truth for the keys)."""
    return {
        "found": 0,
        "not_found": 0,
        "id": 0,
        "outage": 0,
        "error": 0,
        "bp_found": 0,
        "bp_outage": 0,
        "bpm_ok": 0,
        "embed_ok": 0,
    }


def gate_bpm(bpm, conf, min_conf=BPM_MIN_CONF):
    """The gated BPM object, or None when confidence is below ``min_conf``.

    Mirrors ``worker/bpm_backfill/analyze_bpm.py`` — keep a BPM only when the
    RhythmExtractor2013 confidence clears the E2.a gate (better no BPM than a wrong
    one). ``value`` rounded to 1 decimal, ``conf`` to 2.
    """
    if conf < min_conf:
        return None
    return {"value": round(float(bpm), 1), "conf": round(float(conf), 2)}


def extract_key(bp_track):
    """The top-level Camelot ``key`` for the contract, hoisted from the bp_track.

    The Beatport BPM stays inside ``bp_track`` (``bp_track['bpm']``); only the Camelot
    ``key`` is lifted out. None when there is no matched Beatport track.
    """
    return bp_track.get("key") if bp_track else None


def _bpm_blocking(path):
    """``(bpm, conf)`` via Essentia ``RhythmExtractor2013(multifeature)`` at 44.1 kHz.

    CPU-blocking → ALWAYS called through ``loop.run_in_executor``. Essentia is imported
    HERE (lazily) so importing this module never needs essentia (host unit tests). A
    FRESH loader + extractor per call — Essentia instances are not thread-safe to share.
    Verbatim of ``worker/bpm_backfill/analyze_bpm.py::analyze_file``.
    """
    import essentia.standard as es

    audio = es.MonoLoader(filename=path, sampleRate=44100)()
    bpm, _beats, conf, _estimates, _intervals = es.RhythmExtractor2013(
        method="multifeature"
    )(audio)
    return float(bpm), float(conf)


def _embed_blocking(path):
    """1280-d L2-normalised EffNet embedding (mean over patches) as a list of floats.

    CPU-blocking → ALWAYS called through ``loop.run_in_executor``. The frozen C9 v1
    logic from ``worker/embedding_backfill/embed.py::effnet_embed`` (``PartitionedCall:1``,
    16 kHz). The heavy TF graph is loaded ONCE per executor thread (thread-local);
    essentia/numpy are imported HERE (lazily) so the module import stays dependency-free.
    """
    import numpy as np

    m = getattr(_local, "effnet", None)
    if m is None:
        import essentia.standard as es

        _local.es = es
        # embeddings node = PartitionedCall:1 (1280-d penultimate); :0 = genre logits
        _local.effnet = es.TensorflowPredictEffnetDiscogs(
            graphFilename=EFFNET_GRAPH, output="PartitionedCall:1"
        )
        m = _local.effnet
    es = _local.es
    audio = es.MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)()
    patches = m(audio)  # (n_patches, 1280)
    v = np.asarray(patches, dtype=np.float32).mean(axis=0)
    n = float(np.linalg.norm(v))
    if n > 0:
        v = v / n
    return [round(float(x), EMB_DECIMALS) for x in v.tolist()]


class _AsyncFloor:
    """A global inter-request floor (seconds) shared across the gather.

    Serialises the START of Deezer requests to at most one per ``min_interval`` — the
    async twin of embed.py's ``throttle()``. A no-op when ``min_interval <= 0``.
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

    ``_search_deezer_async`` only calls ``pool.deezer_get`` (its whole cascade), and the
    track fetch uses the same method, so routing every Deezer request through this
    wrapper applies the residential-IP floor uniformly. Zero overhead when the floor is
    disabled.
    """

    def __init__(self, pool, floor):
        self._pool = pool
        self._floor = floor

    async def deezer_get(self, path, params=None):
        await self._floor.wait()
        return await self._pool.deezer_get(path, params=params)


async def process_row(
    row,
    search_fn,
    fetch_fn,
    counts,
    *,
    beatport_fn=None,
    analyze_fn=None,
    cover_fn=None,
):
    """Hydrate ONE candidate row → an NDJSON record dict, or None to emit nothing.

    Pure of any server import: every heavy call is an injected async callable (the real
    ones close over the pooled clients + executor; tests pass mocks). Mutates ``counts``
    in place. Deezer semantics (identity anchor):

      * ``is_id`` truthy            → ``id`` line, no Deezer call.
      * search returns a hit + /track fetch ok → ``found`` line (then L1b enrichment).
      * search returns None (or /track resolves to a Deezer error dict) → ``not_found``.
      * ``DeezerHTTPError`` (duck-typed via ``.status_code``): 404 → ``not_found`` line;
        429 / 5xx → OUTAGE → return None (no line, row re-tried later).
      * any other exception → OUTAGE + ``error`` count → return None.

    L1b enrichment (``found`` rows only, all best-effort — a failure leaves its field
    null WITHOUT dropping the record):

      * ``cover_fn(cat_url, alb_url)`` → ``(cat_b64, alb_b64)`` added to ``deezer``.
      * ``analyze_fn(preview_url)`` → ``(bpm_obj, embedding)`` from ONE preview download.
        Skipped (both null) when there is no preview.
      * ``beatport_fn(title, artist, isrc)`` → the normalised bp_track (or None). A
        ``BeatportHTTPError`` / any error → null beatport (record still emitted, E1
        outage-tolerant); 404 is a "no match", anything else counts an outage.

    Any of the three injected callables may be None (tests exercising the Deezer paths),
    in which case that enrichment is skipped.
    """
    try:
        sid = int(str(row["set_trackid_id"]).strip())
        pos = int(str(row["position"]).strip())
    except (KeyError, ValueError, TypeError) as e:
        counts["error"] += 1
        print(f"  malformed row: {type(e).__name__}: {e}")
        return None

    if _is_id_track(row):
        counts["id"] += 1
        return build_record(sid, pos, "id", None)

    title = (row.get("title") or "").strip()
    artist = _match_artist(row)

    try:
        hit = await search_fn(artist, title)
        track = await fetch_fn(hit["id"]) if hit else None
    except Exception as e:  # noqa: BLE001 — one dead row must not abort the gather
        status_code = getattr(e, "status_code", None)
        if status_code is not None:
            if classify_deezer_error(status_code) == "not_found":
                counts["not_found"] += 1
                return build_record(sid, pos, "not_found", None)
            # Outage (429 / 5xx): emit nothing, leave the row for a later re-scan.
            counts["outage"] += 1
            return None
        # Network / unexpected error: also emit nothing (row stays un-hydrated).
        counts["error"] += 1
        print(f"  set_track {sid}: {type(e).__name__}: {e}")
        return None

    # A Deezer /track error dict ({"error": ...}) means the id resolved to nothing.
    if track and not (isinstance(track, dict) and track.get("error")):
        counts["found"] += 1
        deezer = extract_deezer(track)

        # Cover bytes (best-effort): both URLs identical today → downloaded once by the
        # real cover_fn; both keys kept for the contract.
        cat_b64 = alb_b64 = None
        if cover_fn is not None:
            try:
                cat_b64, alb_b64 = await cover_fn(
                    deezer["cover_catalog_url"], deezer["cover_album_url"]
                )
            except Exception as e:  # noqa: BLE001 — a bad cover never drops the record
                print(f"  set_track {sid}: cover download failed: {type(e).__name__}: {e}")
        deezer["cover_catalog_b64"] = cat_b64
        deezer["cover_album_b64"] = alb_b64

        # Preview → BPM + embedding (SINGLE download inside analyze_fn, best-effort).
        bpm_obj = embedding = None
        preview_url = deezer.get("preview_url")
        if preview_url and analyze_fn is not None:
            try:
                bpm_obj, embedding = await analyze_fn(preview_url)
            except Exception as e:  # noqa: BLE001 — analysis failure ≠ record failure
                print(f"  set_track {sid}: analysis failed: {type(e).__name__}: {e}")
        if bpm_obj:
            counts["bpm_ok"] += 1
        if embedding:
            counts["embed_ok"] += 1

        # Beatport (independent of Deezer; E1 outage-tolerant — record emitted regardless).
        bp_track = None
        if beatport_fn is not None:
            isrc = (track.get("isrc") or "").strip() or None
            try:
                bp_track = await beatport_fn(title, artist, isrc)
                if bp_track:
                    counts["bp_found"] += 1
            except Exception as e:  # noqa: BLE001 — beatport is secondary enrichment
                if getattr(e, "status_code", None) != 404:
                    counts["bp_outage"] += 1
                print(f"  set_track {sid}: beatport {type(e).__name__}: {e}")

        return build_found_record(
            sid, pos, deezer, bp_track, bpm_obj, extract_key(bp_track), embedding
        )
    counts["not_found"] += 1
    return build_record(sid, pos, "not_found", None)


async def _hydrate(csv_path, out_path):
    """Hydrate every candidate row CONCURRENTLY and stream NDJSON to ``out_path``.

    Returns a counters dict. Rows are fanned out over one ``asyncio.gather`` bounded by
    an ``asyncio.Semaphore(DEEZER_CONCURRENCY)``; the reused ``RateLimiter`` caps the
    request rate. The CPU-blocking Essentia work (BPM + EffNet) runs OFF the event loop
    on a bounded ``ThreadPoolExecutor``. Streams (flush per line) so a container kill
    still leaves a valid partial NDJSON.

    Deezer search/track go through the FLOORED pool (residential-IP pace); Beatport, the
    preview download and the cover downloads use the RAW pool (Beatport has its own rate
    limiter; the CDN downloads are unlimited — the ``_FlooredPool`` wrapper only exposes
    ``deezer_get``).
    """
    from workers.async_http import (  # noqa: F401 (import gate)
        BeatportHTTPError,
        DeezerHTTPError,
        HttpPool,
    )
    from workers.enrichment import _search_beatport_async, _search_deezer_async
    from workers.rate_limiter import RateLimiter

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    counts = new_counts()
    sem = asyncio.Semaphore(DEEZER_CONCURRENCY)
    guard = {"done": 0}
    t0 = time.monotonic()

    limiter = RateLimiter()
    floor = _AsyncFloor(MIN_INTERVAL)
    with (
        open(out_path, "w", encoding="utf-8") as out_f,
        ThreadPoolExecutor(max_workers=HYDRATE_EXECUTOR_WORKERS) as executor,
    ):
        async with HttpPool(limiter) as raw_pool:
            pool = _FlooredPool(raw_pool, floor)

            async def search_fn(artist, title):
                return await _search_deezer_async(pool, artist, title, None)

            async def fetch_fn(deezer_id):
                return await pool.deezer_get(f"/track/{deezer_id}")

            async def beatport_fn(title, artist, isrc):
                # RAW pool: Beatport has its OWN rate limiter (beatport bucket); the
                # Deezer floor must not throttle it.
                return await _search_beatport_async(
                    raw_pool, title, artist, isrc, rcache=None
                )

            async def cover_fn(cat_url, alb_url):
                # Download each distinct URL once, base64-encode. The two cover URLs
                # resolve identically today → a single download reused for both keys.
                cache = {}

                async def dl(url):
                    if not url:
                        return None
                    if url not in cache:
                        raw = await raw_pool.download_image(url)
                        cache[url] = (
                            base64.b64encode(raw).decode("ascii") if raw else None
                        )
                    return cache[url]

                return (await dl(cat_url), await dl(alb_url))

            async def analyze_fn(preview_url):
                # SINGLE preview download shared by BPM + EffNet; Essentia runs OFF the
                # event loop; the temp MP3 is always deleted. Each analysis is guarded
                # independently so one failing leaves the other intact.
                audio = await raw_pool.download_audio(preview_url)
                if not audio:
                    return (None, None)
                loop = asyncio.get_event_loop()
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                bpm_obj = embedding = None
                try:
                    tmp.write(audio)
                    tmp.close()
                    try:
                        bpm, conf = await loop.run_in_executor(
                            executor, _bpm_blocking, tmp.name
                        )
                        bpm_obj = gate_bpm(bpm, conf)
                    except Exception as e:  # noqa: BLE001
                        print(f"  bpm analysis error: {type(e).__name__}: {e}")
                    try:
                        embedding = await loop.run_in_executor(
                            executor, _embed_blocking, tmp.name
                        )
                    except Exception as e:  # noqa: BLE001
                        print(f"  embed error: {type(e).__name__}: {e}")
                finally:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                return (bpm_obj, embedding)

            async def process(row):
                async with sem:
                    rec = await process_row(
                        row,
                        search_fn,
                        fetch_fn,
                        counts,
                        beatport_fn=beatport_fn,
                        analyze_fn=analyze_fn,
                        cover_fn=cover_fn,
                    )
                    # One sync write+flush, no await between → lines never interleave.
                    if rec is not None:
                        out_f.write(json.dumps(rec) + "\n")
                        out_f.flush()
                    guard["done"] += 1
                    done = guard["done"]
                    if done % 50 == 0 or done == total:
                        print(
                            f"[hydrate] {done}/{total} "
                            f"found={counts['found']} not_found={counts['not_found']} "
                            f"id={counts['id']} outage={counts['outage']} "
                            f"error={counts['error']} bp_found={counts['bp_found']} "
                            f"bpm={counts['bpm_ok']} emb={counts['embed_ok']} "
                            f"elapsed={time.monotonic() - t0:.0f}s"
                        )

            await asyncio.gather(*(process(row) for row in rows))

    return counts


def main():
    ap = argparse.ArgumentParser(
        description="Hydrate TrackID set-track candidates: Deezer search/match + cover "
        "bytes + preview→BPM/EffNet + Beatport, emitted as NDJSON (L1a/L1b container "
        "pass — runs the REAL server matchers, writes nothing to the DB)"
    )
    ap.add_argument("--csv", default="/work/to_hydrate.csv")
    ap.add_argument("--out", default="/work/deezer.ndjson")
    args = ap.parse_args()

    counts = asyncio.run(_hydrate(args.csv, args.out))
    print(
        f"[hydrate] done: found={counts['found']} "
        f"not_found={counts['not_found']} id={counts['id']} "
        f"outage={counts['outage']} error={counts['error']} "
        f"bp_found={counts['bp_found']} bp_outage={counts['bp_outage']} "
        f"bpm={counts['bpm_ok']} emb={counts['embed_ok']}"
    )


if __name__ == "__main__":
    main()
