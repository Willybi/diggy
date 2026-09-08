"""C13 C3 — set-artist resolve pass. Runs INSIDE the Docker container (prod server image).

Reads the worklist CSV (``id,title,channel``) + the artist-base CSVs
(``name,artist_id`` for the main names and, separately, the aliases) and, for each
set, derives the artists to link by REUSING the fil-de-l'eau chain VERBATIM:

  * ``workers.set_artist_extract.extract_artist_candidates(title, channel)`` — the
    subtractive extractor;
  * ``workers.set_artist_link.resolve_name_to_id`` / ``scan_known_artists`` — resolve
    a candidate name against our own base (fold keys) + recover a KNOWN multi-token
    artist buried in the title;
  * on a base MISS: a Deezer ``/search/artist`` gated by
    ``workers.tasks.artists._matching_deezer_hits`` (the X4 matcher) + the optional
    ``_link_set_artist_fan_floor`` — BOTH reused verbatim.

It emits ONE NDJSON record per PROCESSED set on the C3 import contract:

    {"set_id": <id>, "title": <str>, "channel": <str|null>, "links": [
       {"source": "base",   "name": <str>, "artist_id": <int>},
       {"source": "deezer", "name": <str>, "deezer_id": <str>}
    ]}

``source`` is the IDENTITY LANE: ``"base"`` carries a VALID PROD ``artist_id`` (the
base was pulled from prod), ``"deezer"`` carries a confirmed ``deezer_id`` and the
name — the artist is get-or-created LIVE at push by the OPS script (invariant #4:
this tool NEVER creates an artist and NEVER writes to the DB). A set with no
resolvable artist emits ``"links": []`` (a completed attempt, so the host can
checkpoint it and not re-resolve it forever). Records are streamed (flush per line)
so a container kill leaves a valid partial NDJSON.

WHY NOT reuse ``set_artist_resolve.resolve_link_artist_ids`` verbatim: that core is
the RIGHT shape but returns prod ``artist_id`` ints only (its ``deezer_verify`` does
the get-or-create and yields an id). Here a base-miss has NO prod id yet — only a
``deezer_id`` resolved live at push — so this driver reproduces its SMALL ordered/
deduped orchestration while emitting the heterogeneous base/deezer links, and reuses
every PURE building block underneath verbatim.

OUTAGE ≠ LINK (invariant #4): a ``DeezerHTTPError`` on a candidate's search yields
NO link for that candidate (logged, not raised) — it costs recall, never precision,
exactly like the fil-de-l'eau task.

CONCURRENCY: sets are resolved CONCURRENTLY, bounded by ``DEEZER_CONCURRENCY`` (env,
default 5 = the ``deezer`` source's semaphore) through an ``asyncio.Semaphore`` + one
``asyncio.gather``. The Deezer requests are additionally paced by ``DEEZER_RATE``
(env, req/s; 0 = no extra floor) layered on top of the reused ``RateLimiter`` — the
C9 residential-IP lesson (the server ``deezer`` config is fixed at 10 rps and reads
no env, so the floor is the only knob). With no Redis in the container the shared
window fails open, so only the local bucket + this floor govern.

Usage (container, via backfill_set_artists.py or by hand):
    python /work/resolve_driver.py --worklist /work/worklist.csv \
        --artists /work/artists.csv --aliases /work/aliases.csv --out /work/links.ndjson
"""

import argparse
import asyncio
import csv
import functools
import json
import os
import sys
import time

# The prod server image lays the code out under /app (see server/Dockerfile); make
# ``workers`` importable exactly as the fil-de-l'eau task does. Harmless on the host
# (the path just doesn't exist) — every server import is lazy (inside the functions),
# so this module imports cleanly for the host-only unit tests too.
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


class _AsyncFloor:
    """A global inter-request floor (seconds) shared across the gather.

    Serialises the START of Deezer requests to at most one per ``min_interval``.
    A no-op when ``min_interval <= 0``. (Twin of the trackid_hydrate driver's floor.)
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

    Both the reused Deezer name-search cascade and any direct call go through
    ``pool.deezer_get``, so routing them here applies the residential floor uniformly.
    Zero overhead when the floor is disabled.
    """

    def __init__(self, pool, floor):
        self._pool = pool
        self._floor = floor

    async def deezer_get(self, path, params=None):
        await self._floor.wait()
        return await self._pool.deezer_get(path, params=params)


def _load_pairs(artists_path, aliases_path):
    """``(name, artist_id)`` pairs from the two base CSVs — main names FIRST.

    Order matters: ``build_artist_lookup`` keeps the FIRST spelling on a fold-key
    collision, so a main name wins over an alias (parity with the task's
    ``_load_artist_lookup``). ``artist_id`` is cast to int (CSV values are strings);
    a row with a non-int id is skipped.
    """
    pairs = []
    for path in (artists_path, aliases_path):
        if not path or not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("name") or "").strip()
                raw_id = (row.get("artist_id") or "").strip()
                if not name or not raw_id:
                    continue
                try:
                    pairs.append((name, int(raw_id)))
                except ValueError:
                    continue
    return pairs


def _fan_floor():
    """Reuse the task's optional fan floor VERBATIM (reads LINK_SET_ARTIST_FAN_FLOOR)."""
    from workers.tasks.artists import _link_set_artist_fan_floor

    return _link_set_artist_fan_floor()


def _make_deezer_search(pool, fan_floor):
    """Build the ``deezer_search(name) -> deezer_id | None`` callable (prod matcher).

    Mirrors :func:`workers.tasks.artists._verify_set_artist_via_deezer` steps 1-3
    EXACTLY (search ``/search/artist`` → gate through ``_matching_deezer_hits`` →
    apply the optional fan floor on the best hit) but STOPS before step 4
    (``_resolve_or_create_artist``): the artist is get-or-created LIVE at push, so
    here we return the raw ``deezer_id`` string. A ``DeezerHTTPError`` (outage) → None
    (no link; not raised — an outage must never burn precision, invariant #4).
    """
    from workers.async_http import DeezerHTTPError
    from workers.tasks.artists import _matching_deezer_hits

    async def deezer_search(name):
        try:
            data = await pool.deezer_get(
                "/search/artist", params={"q": name, "limit": 10}
            )
        except DeezerHTTPError as e:
            print(f"  deezer search failed for {name!r}: {e}")
            return None
        matches = _matching_deezer_hits(data.get("data", []), name)
        if not matches:
            return None
        best = matches[0]
        if fan_floor and (best.get("nb_fan", 0) or 0) < fan_floor:
            return None
        return str(best["id"])

    return deezer_search


async def resolve_set_links(title, channel, lookup, deezer_search):
    """Resolve one set ``(title, channel)`` into an ordered, deduped list of links.

    Reproduces the ordered/deduped orchestration of
    :func:`workers.set_artist_resolve.resolve_link_artist_ids` (extractor candidates
    in order, base-first with a Deezer fallback on a base miss, then the buried KNOWN
    artists appended) while emitting HETEROGENEOUS links:

      * base hit  → ``{"source": "base", "name", "artist_id"}`` (a valid prod id);
      * base miss → ``deezer_search(name)`` → ``{"source": "deezer", "name",
        "deezer_id"}`` when confirmed, else NO link.

    De-dup is per identity space: base by ``artist_id``, deezer by ``deezer_id`` —
    first occurrence wins, order preserved (so a set never links the same artist
    twice). ``deezer_search`` is injected (a fake in tests) so this function is pure
    and deterministic except for that callable.
    """
    from workers.set_artist_extract import extract_artist_candidates
    from workers.set_artist_link import resolve_name_to_id, scan_known_artists

    out = []
    seen_artist_ids = set()
    seen_deezer_ids = set()

    def _add_base(artist_id, name):
        if artist_id is None or artist_id in seen_artist_ids:
            return
        seen_artist_ids.add(artist_id)
        out.append({"source": "base", "name": name, "artist_id": artist_id})

    def _add_deezer(deezer_id, name):
        if not deezer_id or deezer_id in seen_deezer_ids:
            return
        seen_deezer_ids.add(deezer_id)
        out.append({"source": "deezer", "name": name, "deezer_id": deezer_id})

    # ── extractor candidates: base first, Deezer only on a base miss ──
    for cand in extract_artist_candidates(title, channel):
        artist_id = resolve_name_to_id(cand.name, lookup)
        if artist_id is not None:
            _add_base(artist_id, cand.name)
        else:
            _add_deezer(await deezer_search(cand.name), cand.name)

    # ── buried KNOWN artists (already resolved in the base) ──
    for name, artist_id in scan_known_artists(title, lookup):
        _add_base(artist_id, name)

    return out


async def _resolve(worklist_path, artists_path, aliases_path, out_path):
    """Resolve every worklist set CONCURRENTLY and stream NDJSON to ``out_path``.

    Returns a counters dict. Sets are fanned out over one ``asyncio.gather`` bounded
    by an ``asyncio.Semaphore(DEEZER_CONCURRENCY)``; the reused ``RateLimiter`` + the
    residential floor cap the Deezer request rate. Streams (flush per line) so a
    container kill still leaves a valid partial NDJSON; line order is irrelevant (the
    import reads by ``set_id``).
    """
    from workers.async_http import HttpPool
    from workers.rate_limiter import RateLimiter
    from workers.set_artist_link import build_artist_lookup

    lookup = build_artist_lookup(_load_pairs(artists_path, aliases_path))

    with open(worklist_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    counts = {"sets": 0, "with_links": 0, "no_links": 0, "base": 0, "deezer": 0, "error": 0}
    sem = asyncio.Semaphore(DEEZER_CONCURRENCY)
    guard = {"done": 0}
    t0 = time.monotonic()
    fan_floor = _fan_floor()

    limiter = RateLimiter()
    floor = _AsyncFloor(MIN_INTERVAL)
    with open(out_path, "w", encoding="utf-8") as out_f:
        async with HttpPool(limiter) as raw_pool:
            pool = _FlooredPool(raw_pool, floor)
            deezer_search = _make_deezer_search(pool, fan_floor)

            async def process(row):
                async with sem:
                    try:
                        sid = int(str(row["id"]).strip())
                    except (KeyError, ValueError, TypeError) as e:
                        counts["error"] += 1
                        print(f"  malformed worklist row: {type(e).__name__}: {e}")
                        return
                    title = (row.get("title") or "").strip()
                    channel = (row.get("channel") or "").strip() or None

                    try:
                        links = await resolve_set_links(
                            title, channel, lookup, deezer_search
                        )
                    except Exception as e:  # noqa: BLE001 — one dead set must not abort
                        counts["error"] += 1
                        print(f"  set {sid}: {type(e).__name__}: {e}")
                        return

                    counts["sets"] += 1
                    if links:
                        counts["with_links"] += 1
                    else:
                        counts["no_links"] += 1
                    for link in links:
                        counts["deezer" if link["source"] == "deezer" else "base"] += 1

                    rec = {
                        "set_id": sid,
                        "title": title,
                        "channel": channel,
                        "links": links,
                    }
                    # One sync write+flush, no await between -> lines never interleave.
                    out_f.write(json.dumps(rec) + "\n")
                    out_f.flush()

                    guard["done"] += 1
                    done = guard["done"]
                    if done % 50 == 0 or done == total:
                        print(
                            f"[set-artist-resolve] {done}/{total} "
                            f"with_links={counts['with_links']} "
                            f"no_links={counts['no_links']} "
                            f"base={counts['base']} deezer={counts['deezer']} "
                            f"elapsed={time.monotonic() - t0:.0f}s"
                        )

            await asyncio.gather(*(process(row) for row in rows))

    return counts


def main():
    ap = argparse.ArgumentParser(
        description="Resolve artist links for TrackID sets and emit NDJSON (C3 "
        "container pass — runs the REAL extractor + matchers, writes nothing to the DB)"
    )
    ap.add_argument("--worklist", default="/work/worklist.csv")
    ap.add_argument("--artists", default="/work/artists.csv")
    ap.add_argument("--aliases", default="/work/aliases.csv")
    ap.add_argument("--out", default="/work/links.ndjson")
    args = ap.parse_args()

    counts = asyncio.run(
        _resolve(args.worklist, args.artists, args.aliases, args.out)
    )
    print(
        f"[set-artist-resolve] done: sets={counts['sets']} "
        f"with_links={counts['with_links']} no_links={counts['no_links']} "
        f"base={counts['base']} deezer={counts['deezer']} error={counts['error']}"
    )


if __name__ == "__main__":
    main()
