#!/usr/bin/env python
"""L2 — TrackID clean-hydration host orchestrator. Runs on the HOST (Windows PC),
stdlib only.

Hydrates a batch of scored TrackID sets "cleanly" from the operator's RESIDENTIAL
IP, in parallel with the VPS's nightly ``backfill_trackid_sets`` drain, feeding the
enrichment through the same reused server code (L1a/L1b container driver) and writing
it back on the VPS through the OPS script that REPLAYS the import funnel verbatim.
Twin of ``worker/beatport_backfill/backfill_beatport.py`` (pull → container → apply-
via-ssh): same SSH/psql channel, same dry-run/apply + checkpoint + salvo-relaunchable
shape, same container-driven compute.

The pipeline, per batch of N sets:

  1. WORKLIST — stream the not-hydrated, SCORED sets (``trackid_id, slug, score``)
     from prod, read-only, via the documented SSH/psql channel fed a ``COPY (...)
     TO STDOUT`` — ``hydration_state='not_hydrated' AND score IS NOT NULL ORDER BY
     score DESC, trackid_id DESC``. ``--limit`` / ``--after-score`` window a salvo
     (a coarse score bound, mirroring backfill's coarse ``--after-id``; the checkpoint
     + the L3 ``hydration_state`` flip are the real cross-run guards). Rows already in
     the local checkpoint are filtered out.
  2. DETAIL — for each set, fetch ``GET .../audiostreams/{slug}`` with the ADAPTIVE
     rate ladder (6→3→2→1) + cooldown recopied faithfully from the shadow tool
     (``scripts/local/trackid_spider/shadow.py``). Keeps the FULL ``detail`` payload
     (consumed by ``import_audiostream(prefetched_detail=)`` on the VPS) and builds the
     merged tracklist with the prod-faithful ``merge_tracklist``/``is_id_track`` (also
     recopied from shadow). Downloads the TrackID set cover bytes → ``set_artwork_b64``.
     A set whose detail fetch fails (outage / exhausted throttle) is DROPPED — not
     hydrated, not checkpointed — so a later run retries it.
  3. DRIVER — build the container-driver CSV (``set_trackid_id,position,title,artist,
     is_id``) for ALL tracks of the batch, build the prod server image + the local
     image (``worker/trackid_hydrate/Dockerfile``), then ``docker run`` the L1a/L1b
     driver (``enrich_driver.py``): Deezer search/match + cover bytes + preview→BPM/
     EffNet + Beatport, emitted as per-track NDJSON. The residential-IP knobs
     (``DEEZER_RATE``/``DEEZER_CONCURRENCY``/``BEATPORT_RATE``/``BEATPORT_CONCURRENCY``/
     ``HYDRATE_EXECUTOR_WORKERS``) are passed by ``-e`` + ``REDIS_URL`` pointed at a
     closed port so the shared rate-limit window fails open to the local bucket.
  4. BUNDLE — join the driver NDJSON onto the fetched tracklist by
     ``(set_trackid_id, position)`` → one bundle per set on the contract of
     ``server/api/scripts/import_trackid_clean.py`` (its docstring is the authority).
     The driver's ``deezer`` block is trimmed to ``track`` + ``cover_catalog_b64`` +
     ``cover_album_b64`` (preview/cover URLs are dropped — the L3 write doesn't use
     them). A track with no ``found`` driver line (Deezer outage or ``not_found``, or
     an ``id`` track) → ``deezer: null`` + every enrichment null.
  5. PUSH — DEFAULT (no flag): the bundle NDJSON is written to the workdir only — a
     purely LOCAL dry-run, no prod write, no ssh. ``--dry-run-push`` pipes the bundle
     to the OPS script WITHOUT ``--apply`` (the OPS script runs the funnel, prints its
     counters and rolls back). ``--apply`` pipes it WITH ``--apply`` and, on success,
     checkpoints the pushed set ids. ``--reuse-bundle`` re-pushes an existing
     ``bundle.ndjson`` without re-fetching or re-running the container.

>>> ``--apply`` MUTATES rows on prod (through the reused import/enrichment funnel).
    DUMP PROD FIRST (docs/restore.md). <<< This tool never writes to the DB; the OPS
    script does, and it is idempotent, but a bad dump is not recoverable.

Usage (from the repo root, or anywhere):
    python worker/trackid_hydrate/hydrate.py --limit 20                 # local dry-run sample
    python worker/trackid_hydrate/hydrate.py --limit 20 --dry-run-push  # + OPS dry-run on the VPS
    python worker/trackid_hydrate/hydrate.py --apply                    # hydrate + write
    python worker/trackid_hydrate/hydrate.py --reuse-bundle --apply     # write a prior bundle
"""

import argparse
import base64
import csv
import functools
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# the fetch/scrape steps interleave container output with ours — keep progress
# ordered even when stdout is piped (block-buffered)
print = functools.partial(print, flush=True)  # noqa: A001

SSH_HOST = "diggy-vps"
# Read path (WORKLIST): -q keeps the COPY stream clean (CSV only on stdout).
REMOTE_PSQL_PULL = (
    "cd /root/diggy && docker compose exec -T postgres "
    "sh -c 'psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -q -f -'"
)

# Prod server image (context ./server via server/Dockerfile) carries workers/ +
# beatport/ + curl_cffi + essentia at /app; the package image (worker/trackid_hydrate/
# Dockerfile) is a thin FROM of it that adds the EffNet graph. The driver
# (enrich_driver.py) is bind-mounted at /work at run time, never baked in.
SERVER_IMAGE = "diggy-trackid-hydrate-server"
IMAGE = "diggy-trackid-hydrate"

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
SERVER_DOCKERFILE = os.path.join(SERVER_DIR, "Dockerfile")
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")
CHECKPOINT_FILE = "processed_ids.txt"
DRIVER_SCRIPT = "enrich_driver.py"
DRIVER_CSV = "to_hydrate.csv"
DRIVER_OUT = "driver.ndjson"
BUNDLE_FILE = "bundle.ndjson"

# Columns of the worklist COPY (parsed into candidate dicts).
WORKLIST_FIELDS = ["trackid_id", "slug", "score"]

# The container-driver CSV column contract (enrich_driver.py DictReader).
DRIVER_CSV_FIELDS = ["set_trackid_id", "position", "title", "artist", "is_id"]

# ── TrackID detail fetch — recopied faithfully from the shadow tool ──────────────
# BASE_URL / HEADERS / TIMEOUT / RATE_LIMIT / _rate_ladder / _parse_retry_after /
# merge_tracklist / is_id_track are byte-faithful replicas of
#   scripts/local/trackid_spider/shadow.py
# (which itself replicates server/api/trackid/{client,parsing}.py). Kept as a copy —
# NOT an import — so this host tool stays stdlib-only (shadow.py pulls httpx) and its
# unit tests need no network/deps. Keep them in sync if shadow/prod change.
BASE_URL = "https://trackid.net/api/public"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://trackid.net",
    "Referer": "https://trackid.net/",
}
TIMEOUT = 15.0
MAX_THROTTLE_RETRY = 6

_ID_MARKERS = {"id", "id - id", "?", "??", "unknown", ""}

# Residential-IP defaults. TrackID detail (host-side): the spider proved 1 req/s
# polite; the ladder backs off further on a throttle. Deezer (container): the C9
# lesson — a sustained residential Deezer pace gets rate-limited, so 1 rps + the
# driver's cooldown clears it. Beatport (container): the probe proved 6 rps with
# 0×403, kept at a prudent 4 (mirror backfill_beatport). Executor width caps the
# residential CPU pic (Essentia is CPU-bound).
DEFAULT_DETAIL_RATE = 1.0
DEFAULT_DEEZER_RATE = 1.0
DEFAULT_DEEZER_CONCURRENCY = 5
DEFAULT_BEATPORT_RATE = 4.0
DEFAULT_BEATPORT_CONCURRENCY = 6
DEFAULT_EXECUTOR_WORKERS = 2


def is_id_track(title, artist):
    """True when a track is an "ID - ID" unknown (skip it). Replica of shadow.py."""
    t = (title or "").strip().lower()
    a = (artist or "").strip().lower()
    if t in _ID_MARKERS and a in _ID_MARKERS:
        return True
    if t in _ID_MARKERS and not a:
        return True
    if not t:
        return True
    return False


def merge_tracklist(detail):
    """Merge all detectionProcesses, dedup on musicTrackId (keep first seen).

    Replica of shadow.py's ``merge_tracklist``. The ordering is irrelevant here: the
    VPS re-merges the SAME ``detail`` through prod ``client.merge_tracklist`` at import
    time, and the bundle enrichment is joined to catalog entries by ``musicTrackId``
    (fallback normalized_key) — never by our position.
    """
    seen = {}
    for process in detail.get("detectionProcesses") or []:
        for track in process.get("detectionProcessMusicTracks") or []:
            mtid = track.get("musicTrackId")
            if mtid is None:
                continue
            seen.setdefault(mtid, track)
    return list(seen.values())


def _rate_ladder(start_rate):
    """Descending req/s steps from start down to 1/s — the throttle backoff path.

    Replica of shadow.py's ``_rate_ladder``.
    """
    levels = sorted({float(start_rate), 3.0, 2.0, 1.0}, reverse=True)
    return [r for r in levels if r <= float(start_rate)] or [1.0]


def _parse_retry_after(value):
    """Retry-After seconds form only; an HTTP-date form -> None. Replica of shadow."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def _urllib_get(url):
    """GET ``url`` with the TrackID headers -> ``(status, body_bytes, headers_dict)``.

    A 4xx/5xx returns its status (HTTPError is caught), so the caller can honour the
    throttle ladder; a network/timeout error propagates for the caller to treat as an
    outage. Stdlib-only (urllib) so the host tool needs no extra dependency.
    """
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.getcode(), resp.read(), dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:  # noqa: BLE001 — best-effort body read for a rejected request
            body = b""
        return e.code, body, dict((e.headers or {}).items())


def _header(headers, name):
    """Case-insensitive header lookup over the dict returned by the getter."""
    lname = name.lower()
    for k, v in headers.items():
        if k.lower() == lname:
            return v
    return None


class DetailFetcher:
    """Fetch TrackID set detail payloads with the shadow tool's adaptive ladder.

    The rate only ever ratchets DOWN (a 429/403 steps the ladder one level and cools
    off, retrying the SAME slug up to ``MAX_THROTTLE_RETRY``). ``getter`` and ``sleep``
    are injectable so the loop is unit-testable without network. ``fetch`` returns the
    ``result`` detail dict, or None on an outage / exhausted throttle / bad payload.
    """

    def __init__(self, start_rate, *, getter=_urllib_get, sleep=time.sleep):
        self._ladder = _rate_ladder(start_rate)
        self._lvl = 0
        self._interval = 1.0 / self._ladder[0]
        self._last = 0.0
        self._getter = getter
        self._sleep = sleep
        self.throttled = 0

    def _respect_interval(self):
        elapsed = time.monotonic() - self._last
        if elapsed < self._interval:
            self._sleep(self._interval - elapsed)
        self._last = time.monotonic()

    def fetch(self, slug):
        retries = 0
        while True:
            self._respect_interval()
            try:
                status, body, headers = self._getter(f"{BASE_URL}/audiostreams/{slug}")
            except Exception as e:  # noqa: BLE001 — a network error = outage, skip set
                print(f"  [detail] {slug}: {type(e).__name__}: {e}")
                return None
            if status in (429, 403):
                self.throttled += 1
                if self._lvl < len(self._ladder) - 1:
                    self._lvl += 1
                    self._interval = 1.0 / self._ladder[self._lvl]
                cooldown = min(
                    300, _parse_retry_after(_header(headers, "Retry-After")) or 45
                )
                print(
                    f"  [throttle] {status} on {slug} -> rate {self._ladder[self._lvl]}"
                    f"/s, cooldown {cooldown}s (total throttled={self.throttled})"
                )
                self._sleep(cooldown)
                retries += 1
                if retries <= MAX_THROTTLE_RETRY:
                    continue
                print(f"  [detail] {slug}: throttle-exhausted, skipping")
                return None
            if status != 200:
                print(f"  [detail] {slug}: HTTP {status}, skipping")
                return None
            try:
                return json.loads(body).get("result", {}) or {}
            except (ValueError, AttributeError) as e:
                print(f"  [detail] {slug}: bad JSON ({e}), skipping")
                return None


def download_artwork(url, getter=_urllib_get):
    """Download an artwork URL -> base64 string, or None (absent/failed/non-200)."""
    if not url:
        return None
    try:
        status, body, _ = getter(url)
    except Exception as e:  # noqa: BLE001 — a bad cover never aborts the set
        print(f"  [artwork] {url}: {type(e).__name__}: {e}")
        return None
    if status != 200 or not body:
        return None
    return base64.b64encode(body).decode("ascii")


# ── worklist / checkpoint (pure host logic) ──────────────────────────────────────


def build_worklist_query(limit=0, after_score=None):
    """COPY query for the not-hydrated SCORED sets, highest score first.

    ``hydration_state='not_hydrated' AND score IS NOT NULL`` (unscored "reste" sets are
    NEVER hydrated) ordered ``score DESC, trackid_id DESC`` — the same order the nightly
    C12 drain consumes. ``after_score`` is a COARSE salvo bound (``score < :after_score``,
    mirroring backfill_beatport's coarse ``after_id``, not a strict keyset — score is a
    non-unique float); the checkpoint and the L3 ``hydration_state`` flip are the real
    cross-run guards. ``limit`` caps the pull.
    """
    clauses = ""
    if after_score is not None:
        clauses += f"    AND score < {float(after_score)}\n"
    limit_clause = f"  LIMIT {int(limit)}\n" if limit else ""
    return (
        "COPY (\n"
        "  SELECT trackid_id,\n"
        "         slug,\n"
        "         score\n"
        "  FROM trackid_index\n"
        "  WHERE hydration_state = 'not_hydrated'\n"
        "    AND score IS NOT NULL\n"
        f"{clauses}"
        "  ORDER BY score DESC, trackid_id DESC\n"
        f"{limit_clause}"
        ") TO STDOUT WITH (FORMAT csv, HEADER true);\n"
    )


def parse_worklist(csv_text):
    """Rows (dicts on WORKLIST_FIELDS) from the COPY CSV output."""
    return list(csv.DictReader(io.StringIO(csv_text)))


def load_checkpoint(path):
    """Set of already-processed trackid_ids (as strings); missing file = empty set."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_checkpoint(path, ids):
    if not ids:
        return
    with open(path, "a", encoding="utf-8") as f:
        for tid in ids:
            f.write(f"{tid}\n")


def filter_new(rows, done):
    """Worklist rows whose trackid_id is not yet in the checkpoint set."""
    return [r for r in rows if str(r["trackid_id"]).strip() not in done]


# ── tracklist / driver CSV / driver output (pure host logic) ─────────────────────


def build_tracklist(detail):
    """Merged, positioned tracklist rows for one set from its detail payload.

    Each row carries the fields the bundle contract keeps
    (``position/raw_title/raw_artist/is_id/musicTrackId/startTime/endTime/label``);
    ``position`` is a 1-based index over the (prod-faithful) merge — used only to join
    the driver output back on (the VPS re-derives set_tracks from ``detail``).
    """
    out = []
    for pos, tr in enumerate(merge_tracklist(detail), 1):
        title = tr.get("title")
        artist = tr.get("artist")
        out.append(
            {
                "position": pos,
                "raw_title": title,
                "raw_artist": artist,
                "is_id": is_id_track(title, artist),
                "musicTrackId": tr.get("musicTrackId"),
                "startTime": tr.get("startTime"),
                "endTime": tr.get("endTime"),
                "label": tr.get("label"),
            }
        )
    return out


def build_driver_rows(trackid_id, tracklist):
    """CSV rows (on DRIVER_CSV_FIELDS) for the container driver, for ONE set.

    ALL tracks are emitted (the driver skips ``is_id`` rows itself, emitting an ``id``
    line). ``is_id`` is serialised "1"/"0" — the driver reads "1" as truthy and "0" as
    falsey (its ``_TRUE_STRINGS`` gate).
    """
    return [
        {
            "set_trackid_id": trackid_id,
            "position": t["position"],
            "title": t["raw_title"] or "",
            "artist": t["raw_artist"] or "",
            "is_id": "1" if t["is_id"] else "0",
        }
        for t in tracklist
    ]


def parse_driver_output(ndjson_text):
    """Index the driver NDJSON by ``(set_trackid_id, position)`` -> record dict.

    Malformed lines (bad JSON, non-dict, unparsable key) are skipped. Both key parts
    are coerced to int so they join the (int, int) keys built in ``assemble_bundle``.
    """
    index = {}
    for line in ndjson_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        try:
            key = (int(rec.get("set_trackid_id")), int(rec.get("position")))
        except (TypeError, ValueError):
            continue
        index[key] = rec
    return index


def _trim_deezer(dz):
    """Keep only the fields L3 consumes from the driver's ``deezer`` block.

    ``track`` (the full /track dict) + the two cover byte fields; the preview/cover
    URLs are dropped (unused by the clean-import). None when the block is absent/blank.
    """
    if not isinstance(dz, dict):
        return None
    return {
        "track": dz.get("track"),
        "cover_catalog_b64": dz.get("cover_catalog_b64"),
        "cover_album_b64": dz.get("cover_album_b64"),
    }


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_float(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def assemble_bundle(set_row, detail, tracklist, driver_index, set_artwork_b64):
    """Join the driver output onto the tracklist -> one bundle on the L3 contract.

    A track is enriched ONLY from a ``found`` driver line joined by ``(trackid_id,
    position)`` (its ``deezer`` trimmed); a ``not_found``/``id`` line, a Deezer outage
    (no line at all) or a driver ``error`` all leave the track fully null. The set cover
    rides as the top-level ``set_artwork_b64``.
    """
    trackid_id = _to_int(set_row.get("trackid_id"))
    tracks = []
    for t in tracklist:
        rec = driver_index.get((trackid_id, t["position"]))
        deezer = beatport = bpm = key = embedding = None
        if isinstance(rec, dict) and rec.get("status") == "found":
            deezer = _trim_deezer(rec.get("deezer"))
            beatport = rec.get("beatport")
            bpm = rec.get("bpm")
            key = rec.get("key")
            embedding = rec.get("embedding")
        tracks.append(
            {
                "position": t["position"],
                "raw_title": t["raw_title"],
                "raw_artist": t["raw_artist"],
                "is_id": t["is_id"],
                "musicTrackId": t["musicTrackId"],
                "startTime": t["startTime"],
                "endTime": t["endTime"],
                "label": t["label"],
                "deezer": deezer,
                "beatport": beatport,
                "bpm": bpm,
                "key": key,
                "embedding": embedding,
            }
        )
    return {
        "trackid_id": trackid_id,
        "slug": set_row.get("slug"),
        "score": _to_float(set_row.get("score")),
        "detail": detail,
        "set_artwork_b64": set_artwork_b64,
        "tracks": tracks,
    }


# ── ssh / docker plumbing (mirrors backfill_beatport) ────────────────────────────


def run_remote_sql(remote_cmd, sql):
    """Feed ``sql`` to psql on the VPS via ssh stdin; return psql's stdout."""
    proc = subprocess.run(
        ["ssh", SSH_HOST, remote_cmd],
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote psql failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def build_import_command(apply):
    """Remote command piping the bundle NDJSON into the OPS clean-import script.

    Dry-run-push invokes it WITHOUT ``--apply`` (the OPS script runs the funnel, prints
    its counters and rolls back); ``--apply`` propagates the flag so it commits.
    """
    flag = " --apply" if apply else ""
    return (
        "cd /root/diggy && docker compose exec -T api "
        f"python scripts/import_trackid_clean.py{flag}"
    )


def run_remote_import(bundle_text, apply):
    """Pipe the bundle NDJSON to the OPS clean-import over ssh; return its stdout."""
    cmd = build_import_command(apply)
    proc = subprocess.run(
        ["ssh", SSH_HOST, cmd],
        input=bundle_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"remote import failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def _docker_build():
    """Build the prod server image, then the thin package image FROM it."""
    print(f"[driver] docker build -t {SERVER_IMAGE} (server/Dockerfile) ...")
    subprocess.run(
        ["docker", "build", "-t", SERVER_IMAGE, "-f", SERVER_DOCKERFILE, SERVER_DIR],
        check=True,
    )
    print(f"[driver] docker build -t {IMAGE} (FROM {SERVER_IMAGE}) ...")
    subprocess.run(
        [
            "docker", "build",
            "-t", IMAGE,
            "--build-arg", f"SERVER_IMAGE={SERVER_IMAGE}",
            PKG_DIR,
        ],
        check=True,
    )


def _docker_run(workdir, *, deezer_rate, deezer_concurrency, beatport_rate,
                beatport_concurrency, executor_workers):
    """Run enrich_driver.py in the container over <workdir>/to_hydrate.csv.

    REDIS_URL points at a closed port so the shared rate-limit window fails open fast
    to the local bucket (the backfill_beatport trick — a refused connection is ~0.04s
    vs ~1.3s waiting on redis:6379). The residential-IP knobs are posted via ``-e``.
    """
    shutil.copy2(
        os.path.join(PKG_DIR, DRIVER_SCRIPT),
        os.path.join(workdir, DRIVER_SCRIPT),
    )
    env_flags = [
        "-e", "REDIS_URL=redis://127.0.0.1:1/0",
        "-e", f"DEEZER_RATE={deezer_rate}",
        "-e", f"DEEZER_CONCURRENCY={deezer_concurrency}",
        "-e", f"BEATPORT_RATE={beatport_rate}",
        "-e", f"BEATPORT_CONCURRENCY={beatport_concurrency}",
        "-e", f"HYDRATE_EXECUTOR_WORKERS={executor_workers}",
    ]
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/work",
            *env_flags,
            IMAGE,
            "python", f"/work/{DRIVER_SCRIPT}",
            "--csv", f"/work/{DRIVER_CSV}",
            "--out", f"/work/{DRIVER_OUT}",
        ],
        check=True,
    )


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ── push gating (mirror of backfill_beatport.apply_or_plan) ──────────────────────


def push_bundle(
    bundle_text,
    pushed_ids,
    *,
    apply,
    dry_run_push,
    checkpoint_path,
    runner=run_remote_import,
):
    """Push the assembled bundle (or not), honouring the three modes.

      * default (no flag): NOTHING is pushed — the bundle is already on disk (a local
        dry-run). No ssh, no checkpoint.
      * ``--dry-run-push``: pipe to the OPS script WITHOUT ``--apply`` (it runs the
        funnel, prints its counters and rolls back). No checkpoint.
      * ``--apply``: pipe WITH ``--apply``, then checkpoint every pushed set id.

    An empty bundle short-circuits without touching the OPS script.
    """
    if not bundle_text.strip():
        print("Empty bundle — nothing to push.")
        return

    if not apply and not dry_run_push:
        print(
            "\n=== LOCAL DRY-RUN — bundle written to the workdir, NOT pushed. "
            "Use --dry-run-push to run the OPS import (rolled back) or --apply to "
            "write (DUMP PROD FIRST, docs/restore.md). ==="
        )
        return

    if dry_run_push:
        print("\n=== DRY-RUN-PUSH — invoking the OPS clean-import WITHOUT --apply ===")
        print(runner(bundle_text, False))
        print(
            "=== DRY-RUN-PUSH — nothing written (the OPS script ran the funnel, "
            "printed its counters and rolled back). No id checkpointed. Re-run with "
            "--apply to write, or --reuse-bundle --apply. DUMP PROD first. ==="
        )
        return

    print("\n=== APPLY — piping the bundle to the OPS clean-import (--apply) ===")
    print(runner(bundle_text, True))
    append_checkpoint(checkpoint_path, pushed_ids)
    print(
        f"\nCheckpointed {len(pushed_ids)} hydrated set id(s). Idempotent: the OPS "
        "import counts already-linked rows as already_* and the next worklist drops "
        "hydrated sets via hydration_state='not_hydrated'."
    )


# ── orchestration ────────────────────────────────────────────────────────────────


def main(args):
    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    checkpoint_path = os.path.join(workdir, CHECKPOINT_FILE)
    bundle_path = os.path.join(workdir, BUNDLE_FILE)

    if args.reuse_bundle:
        if not os.path.exists(bundle_path):
            sys.exit(f"--reuse-bundle: no {bundle_path} from a previous run")
        print(f"[reuse] pushing previous {bundle_path} (no worklist, no fetch, no driver)")
        with open(bundle_path, encoding="utf-8") as f:
            bundle_text = f.read()
        pushed_ids = _bundle_ids(bundle_text)
        push_bundle(
            bundle_text,
            pushed_ids,
            apply=args.apply,
            dry_run_push=args.dry_run_push,
            checkpoint_path=checkpoint_path,
        )
        return

    # 1. WORKLIST — read-only COPY from prod through the documented SSH channel
    print(
        f"[worklist] fetching not-hydrated scored sets "
        f"(limit={args.limit or 'none'}, after_score={args.after_score or 'none'})..."
    )
    csv_text = run_remote_sql(
        REMOTE_PSQL_PULL, build_worklist_query(args.limit, args.after_score)
    )
    rows = parse_worklist(csv_text)
    done = load_checkpoint(checkpoint_path)
    fresh = filter_new(rows, done)
    print(
        f"[worklist] {len(rows)} set(s), {len(rows) - len(fresh)} already processed "
        f"(checkpoint), {len(fresh)} to hydrate"
    )
    if not fresh:
        print("Nothing new to hydrate — done.")
        return

    # 2. DETAIL — adaptive-rate TrackID fetch + tracklist + set cover, per set
    fetcher = DetailFetcher(args.detail_rate)
    fetched = []          # (row, detail, tracklist, set_artwork_b64)
    driver_rows = []
    for i, row in enumerate(fresh, 1):
        slug = row.get("slug")
        detail = fetcher.fetch(slug)
        if not detail:
            continue      # outage / exhausted throttle → drop (not checkpointed)
        tracklist = build_tracklist(detail)
        artwork_b64 = download_artwork(detail.get("artworkUrl"))
        fetched.append((row, detail, tracklist, artwork_b64))
        driver_rows.extend(build_driver_rows(_to_int(row.get("trackid_id")), tracklist))
        if i % 50 == 0 or i == len(fresh):
            print(
                f"  [detail] {i}/{len(fresh)} fetched={len(fetched)} "
                f"tracks={len(driver_rows)} throttled={fetcher.throttled}"
            )
    if not fetched:
        print("No set detail fetched (all outages) — nothing to hydrate.")
        return
    print(
        f"[detail] {len(fetched)} set(s) fetched, {len(driver_rows)} track(s) to drive"
    )
    _write_csv(os.path.join(workdir, DRIVER_CSV), driver_rows, DRIVER_CSV_FIELDS)

    # 3. DRIVER — enrich every track in the prod server image (real matchers + EffNet)
    _docker_build()
    _docker_run(
        workdir,
        deezer_rate=args.rate,
        deezer_concurrency=args.concurrency,
        beatport_rate=args.beatport_rate,
        beatport_concurrency=args.beatport_concurrency,
        executor_workers=args.executor_workers,
    )
    driver_out_path = os.path.join(workdir, DRIVER_OUT)
    if not os.path.exists(driver_out_path):
        sys.exit(f"[driver] the container produced no {driver_out_path}")
    with open(driver_out_path, encoding="utf-8") as f:
        driver_index = parse_driver_output(f.read())

    # 4. BUNDLE — join driver output onto tracklists, one NDJSON line per set
    pushed_ids = []
    with open(bundle_path, "w", encoding="utf-8") as out_f:
        for row, detail, tracklist, artwork_b64 in fetched:
            bundle = assemble_bundle(row, detail, tracklist, driver_index, artwork_b64)
            out_f.write(json.dumps(bundle) + "\n")
            pushed_ids.append(str(bundle["trackid_id"]))
    print(f"[bundle] wrote {len(pushed_ids)} set bundle(s) to {bundle_path}")

    # 5. PUSH (local dry-run / dry-run-push / apply)
    with open(bundle_path, encoding="utf-8") as f:
        bundle_text = f.read()
    push_bundle(
        bundle_text,
        pushed_ids,
        apply=args.apply,
        dry_run_push=args.dry_run_push,
        checkpoint_path=checkpoint_path,
    )


def _bundle_ids(bundle_text):
    """Trackid_ids of every well-formed bundle line (for --reuse-bundle checkpointing)."""
    ids = []
    for line in bundle_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = obj.get("trackid_id") if isinstance(obj, dict) else None
        if tid is not None:
            ids.append(str(tid))
    return ids


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Clean-hydrate scored TrackID sets from a residential IP: pull the "
        "worklist from prod, fetch each set's detail, enrich every track in the prod "
        "server image (Deezer/Beatport/BPM/EffNet), assemble a per-set bundle and "
        "(optionally) push it to the VPS clean-import (L2 host orchestrator). Local "
        "dry-run by default; --dry-run-push runs the OPS import rolled back; --apply "
        "writes (DUMP PROD FIRST)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="pipe the bundle to the OPS clean-import WITH --apply and checkpoint the "
        "pushed set ids (default: local dry-run, bundle only written to the workdir)",
    )
    parser.add_argument(
        "--dry-run-push",
        dest="dry_run_push",
        action="store_true",
        help="pipe the bundle to the OPS clean-import WITHOUT --apply (it runs the "
        "funnel, prints its counters and rolls back — no write, no checkpoint)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="LIMIT on the worklist pull (0 = full not-hydrated scored backlog)",
    )
    parser.add_argument(
        "--after-score",
        dest="after_score",
        type=float,
        default=None,
        help="only pull sets with score < this value (coarse salvo bound; the "
        "checkpoint + the hydration_state flip are the real cross-run guards)",
    )
    parser.add_argument(
        "--detail-rate",
        dest="detail_rate",
        type=float,
        default=DEFAULT_DETAIL_RATE,
        help=f"starting req/s for the TrackID detail fetch (default "
        f"{DEFAULT_DETAIL_RATE}; adaptive backoff 3->2->1 on 429/403)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_DEEZER_RATE,
        help=f"Deezer residential floor in req/s, passed to the container as DEEZER_RATE "
        f"(default {DEFAULT_DEEZER_RATE}; the C9 lesson — a sustained residential Deezer "
        "pace gets rate-limited, 1 rps + cooldown clears it). NEVER raise the PROD rate.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_DEEZER_CONCURRENCY,
        help=f"DEEZER_CONCURRENCY for the container row-level gather (default "
        f"{DEFAULT_DEEZER_CONCURRENCY}; the token bucket / --rate still caps the rate)",
    )
    parser.add_argument(
        "--beatport-rate",
        dest="beatport_rate",
        type=float,
        default=DEFAULT_BEATPORT_RATE,
        help=f"BEATPORT_RATE for the container (default {DEFAULT_BEATPORT_RATE}; the "
        "probe proved 6 rps with 0x403, keep a margin). NEVER raise the PROD rate.",
    )
    parser.add_argument(
        "--beatport-concurrency",
        dest="beatport_concurrency",
        type=int,
        default=DEFAULT_BEATPORT_CONCURRENCY,
        help=f"BEATPORT_CONCURRENCY for the container (default "
        f"{DEFAULT_BEATPORT_CONCURRENCY}; the driver's beatport semaphore and the rate "
        "limiter's beatport semaphore both read it, so they must agree)",
    )
    parser.add_argument(
        "--executor-workers",
        dest="executor_workers",
        type=int,
        default=DEFAULT_EXECUTOR_WORKERS,
        help=f"HYDRATE_EXECUTOR_WORKERS for the container Essentia/EffNet pool "
        f"(default {DEFAULT_EXECUTOR_WORKERS}; caps the residential CPU pic)",
    )
    parser.add_argument(
        "--workdir",
        default=DEFAULT_WORKDIR,
        help="working directory for CSVs + NDJSON + checkpoint (default: <package>/data)",
    )
    parser.add_argument(
        "--reuse-bundle",
        dest="reuse_bundle",
        action="store_true",
        help="skip worklist+fetch+driver and push the existing <workdir>/bundle.ndjson "
        "(e.g. local dry-run first, inspect, then --reuse-bundle --apply)",
    )
    return parser


if __name__ == "__main__":
    main(_build_parser().parse_args())
